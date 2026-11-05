// Painel do Guts: busca /api/status a cada 5s e preenche a página.
// Sem bibliotecas: só fetch e DOM. Nomes de arquivo entram via textContent,
// nunca innerHTML, para não abrir brecha de injeção de HTML.

const INTERVALO_MS = 5000;

// Faixas de cor das barras (em %). Acima de "atencao" fica amarelo,
// acima de "critico" fica vermelho.
const FAIXAS = {
  padrao: { atencao: 70, critico: 85 },
  cache:  { atencao: 80, critico: 95 }, // cache cheio é normal: o rclone limpa sozinho
};

let ultimoSucesso = null; // Date do último /api/status que deu certo
let falhou = false;

// ---------- Formatação ----------

const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

function formatarBytes(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  const unidades = ["B", "KB", "MB", "GB", "TB", "PB"];
  let valor = bytes;
  let i = 0;
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024;
    i++;
  }
  // Valores pequenos ganham uma casa decimal: 4,2 GB; grandes não: 743 GB.
  const casas = valor < 100 && i > 0 ? 1 : 0;
  return `${valor.toFixed(casas).replace(".", ",")} ${unidades[i]}`;
}

function formatarVelocidade(bps) {
  return bps ? `${formatarBytes(bps)}/s` : "parado";
}

function formatarSegundos(s) {
  if (s === null || s === undefined) return "";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${numero.format(s / 3600)} h`;
}

function faixaDe(pct, limites = FAIXAS.padrao) {
  if (pct === null || pct === undefined) return "";
  if (pct >= limites.critico) return "critico";
  if (pct >= limites.atencao) return "atencao";
  return "ok";
}

// ---------- Ajudantes de DOM ----------

function campo(card, nome) {
  return card.querySelector(`[data-campo="${nome}"]`);
}

function escrever(card, nome, texto) {
  const el = campo(card, nome);
  if (el) el.textContent = texto;
}

function pintarBarra(barra, pct, faixa) {
  if (!barra) return;
  const valor = Math.max(0, Math.min(100, pct ?? 0));
  barra.firstElementChild.style.width = `${valor}%`;
  barra.setAttribute("aria-valuenow", String(Math.round(valor)));
  barra.dataset.faixa = faixa;
}

// Mostra o erro de um bloco sem apagar o resto da página.
function mostrarErro(card, mensagem) {
  card.dataset.faixa = "critico";
  let caixa = card.querySelector(".erro-card");
  if (!caixa) {
    caixa = document.createElement("p");
    caixa.className = "erro-card";
    card.querySelector(".conteudo").before(caixa);
  }
  caixa.textContent = mensagem;
  card.querySelector(".conteudo").hidden = true;
}

function limparErro(card) {
  card.querySelector(".erro-card")?.remove();
  card.querySelector(".conteudo").hidden = false;
}

// Separa "ACDB/renders/cena.mp4" em pasta + nome, para a lista ficar legível.
function itemDeArquivo(caminho, meta) {
  const li = document.createElement("li");
  const nome = document.createElement("span");
  nome.className = "nome";
  nome.title = caminho;
  const corte = caminho.lastIndexOf("/");
  if (corte >= 0) {
    const pasta = document.createElement("span");
    pasta.className = "pasta";
    pasta.textContent = caminho.slice(0, corte + 1);
    nome.append(pasta);
  }
  nome.append(caminho.slice(corte + 1));
  const lado = document.createElement("span");
  lado.className = "meta";
  lado.textContent = meta;
  li.append(nome, lado);
  return li;
}

function listaVazia(ul, texto) {
  const li = document.createElement("li");
  li.className = "vazio";
  li.textContent = texto;
  ul.replaceChildren(li);
}

// ---------- Um renderizador por bloco ----------

function renderCache(dados) {
  const card = document.getElementById("cache");
  if (dados.erro) return mostrarErro(card, dados.erro);
  limparErro(card);

  const faixa = dados.sem_espaco ? "critico" : faixaDe(dados.pct, FAIXAS.cache);
  card.dataset.faixa = faixa;
  escrever(card, "usado", formatarBytes(dados.usado));
  escrever(card, "limite", `de ${formatarBytes(dados.limite)}`);
  pintarBarra(card.querySelector(".barra"), dados.pct, faixa);

  let nota = `${dados.arquivos} arquivos no cache`;
  if (dados.sem_espaco) nota = "Sem espaço no SSD: o rclone parou de gravar no cache.";
  else if (dados.com_erro) nota += `, ${dados.com_erro} com erro`;
  escrever(card, "nota", nota);
}

function renderFila(dados) {
  const card = document.getElementById("fila");
  const lista = campo(document.getElementById("fila-itens"), "itens");
  if (dados.erro) {
    mostrarErro(card, dados.erro);
    listaVazia(lista, "Fila indisponível.");
    return;
  }
  limparErro(card);

  card.dataset.faixa = dados.aguardando > 50 ? "atencao" : "ok";
  escrever(card, "aguardando", String(dados.aguardando));
  escrever(card, "sufixo", dados.aguardando === 1 ? "arquivo aguardando" : "arquivos aguardando");
  escrever(card, "nota", dados.enviando
    ? `${dados.enviando} subindo agora, ${formatarBytes(dados.bytes)} no total`
    : dados.aguardando ? `${formatarBytes(dados.bytes)} para subir` : "Tudo já está na nuvem.");

  if (!dados.itens.length) return listaVazia(lista, "Nenhum arquivo esperando upload.");
  lista.replaceChildren(...dados.itens.map((item) => {
    const meta = item.enviando
      ? "subindo"
      : `${formatarBytes(item.tamanho)}${item.espera ? `, em ${formatarSegundos(item.espera)}` : ""}`;
    const li = itemDeArquivo(item.nome, meta);
    if (item.enviando) li.querySelector(".meta").classList.add("marca-envio");
    if (item.tentativas > 0) li.querySelector(".meta").textContent += `, tentativa ${item.tentativas + 1}`;
    return li;
  }));
}

function renderNuvem(dados) {
  const card = document.getElementById("nuvem");
  if (dados.erro) return mostrarErro(card, dados.erro);
  limparErro(card);

  if (!dados.suportado) {
    // Provedor não informa cota (alguns S3/B2, por exemplo): não é erro.
    card.dataset.faixa = "";
    escrever(card, "usado", "sem cota");
    escrever(card, "total", "");
    pintarBarra(card.querySelector(".barra"), 0, "");
    escrever(card, "nota", `${dados.remote} não informa espaço usado ou total.`);
    return;
  }

  const faixa = faixaDe(dados.pct);
  card.dataset.faixa = faixa;
  escrever(card, "usado", formatarBytes(dados.usado));
  escrever(card, "total", dados.total ? `de ${formatarBytes(dados.total)}` : "usados");
  pintarBarra(card.querySelector(".barra"), dados.pct, faixa);

  const partes = [];
  if (dados.livre !== null) partes.push(`${formatarBytes(dados.livre)} livres`);
  if (dados.lixeira) partes.push(`${formatarBytes(dados.lixeira)} na lixeira`);
  escrever(card, "nota", partes.join(", ") || dados.remote);
}

function renderMount(dados) {
  const card = document.getElementById("mount");
  limparErro(card);
  const estado = campo(card, "estado");
  if (!dados.online) {
    estado.textContent = "rclone não responde";
    estado.className = "estado-ruim";
    escrever(card, "ponto", dados.ponto);
    escrever(card, "versao", dados.erro || "—");
    return;
  }
  estado.textContent = dados.montado ? "Montado" : "Não montado";
  estado.className = dados.montado ? "estado-ok" : "estado-ruim";
  escrever(card, "ponto", dados.ponto);
  escrever(card, "versao", `${dados.versao} (${dados.so})`);
}

function renderSsd(dados) {
  const card = document.getElementById("ssd");
  if (dados.erro) return mostrarErro(card, dados.erro);
  limparErro(card);

  const faixa = faixaDe(dados.pct);
  escrever(card, "pct", `${numero.format(dados.pct)}%`);
  pintarBarra(card.querySelector(".barra"), dados.pct, faixa);
  escrever(card, "livre", `${formatarBytes(dados.livre)} de ${formatarBytes(dados.total)}`);

  let cache;
  if (dados.cache_real_erro) cache = `não foi possível medir (${dados.cache_real_erro})`;
  else if (dados.cache_real === null) cache = "medindo…";
  else cache = `${formatarBytes(dados.cache_real)} de ${formatarBytes(dados.cache_limite)} (limite)`;
  escrever(card, "cache_real", cache);
}

function renderTransferencias(dados) {
  const card = document.getElementById("transferencias");
  const canoNuvem = document.getElementById("cano-nuvem");
  const canoFila = document.getElementById("cano-fila");
  if (dados.erro) {
    canoNuvem.classList.remove("ativo");
    canoFila.classList.remove("ativo");
    document.getElementById("cano-vel").textContent = "—";
    return mostrarErro(card, dados.erro);
  }
  limparErro(card);

  const subindo = dados.ativas.length > 0;
  canoNuvem.classList.toggle("ativo", subindo);
  canoFila.classList.toggle("ativo", subindo);
  document.getElementById("cano-vel").textContent = formatarVelocidade(dados.velocidade);

  escrever(card, "velocidade", formatarVelocidade(dados.velocidade));
  escrever(card, "bytes", formatarBytes(dados.bytes));
  const erros = campo(card, "erros");
  erros.textContent = String(dados.erros);
  erros.className = dados.erros ? "estado-ruim" : "";

  const ultimo = campo(card, "ultimo_erro");
  ultimo.hidden = !dados.ultimo_erro;
  ultimo.textContent = dados.ultimo_erro ? `Último erro: ${dados.ultimo_erro}` : "";

  const lista = campo(card, "ativas");
  if (!subindo) return listaVazia(lista, "Nenhuma transferência agora.");
  lista.replaceChildren(...dados.ativas.map((t) => {
    const eta = t.eta ? `, faltam ${formatarSegundos(t.eta)}` : "";
    const li = itemDeArquivo(t.nome, `${t.pct ?? 0}% de ${formatarBytes(t.tamanho)}${eta}`);
    const barra = document.createElement("div");
    barra.className = "barra fina";
    barra.setAttribute("role", "progressbar");
    barra.setAttribute("aria-label", `Progresso de ${t.nome}`);
    barra.append(document.createElement("span"));
    li.append(barra);
    pintarBarra(barra, t.pct, "ok");
    barra.dataset.faixa = "";
    barra.firstElementChild.style.background = "var(--fluxo)";
    return li;
  }));
}

// ---------- Estado geral (LED + "última atualização") ----------

function estadoGeral(s) {
  if (!s.mount.online || !s.mount.montado) return "critico";
  const blocos = [s.nuvem, s.cache, s.fila, s.transferencias, s.ssd];
  if (blocos.some((b) => b.erro) || s.cache.sem_espaco) return "critico";
  if (s.ssd.pct >= FAIXAS.padrao.critico) return "critico";
  if (s.transferencias.erros || s.ssd.pct >= FAIXAS.padrao.atencao) return "atencao";
  return "ok";
}

const TEXTO_ESTADO = {
  ok: "tudo certo",
  atencao: "requer atenção",
  critico: "com problema",
};

let estadoAtual = "";

function atualizarRotulo() {
  const el = document.getElementById("atualizado");
  if (!ultimoSucesso) return;
  const seg = Math.round((Date.now() - ultimoSucesso) / 1000);
  const quando = seg < 2 ? "agora" : `há ${formatarSegundos(seg)}`;
  el.textContent = falhou
    ? `Sem resposta do painel. Último dado ${quando}.`
    : `Guts ${TEXTO_ESTADO[estadoAtual] || ""}, atualizado ${quando}`;
}

// ---------- Ciclo principal ----------

async function atualizar() {
  const alerta = document.getElementById("alerta");
  try {
    const resp = await fetch("/api/status", { cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (!resp.ok) throw new Error(`o servidor respondeu ${resp.status}`);
    const s = await resp.json();

    renderMount(s.mount);
    renderNuvem(s.nuvem);
    renderCache(s.cache);
    renderFila(s.fila);
    renderTransferencias(s.transferencias);
    renderSsd(s.ssd);

    estadoAtual = estadoGeral(s);
    document.getElementById("led").dataset.estado = estadoAtual;
    ultimoSucesso = Date.now();
    falhou = false;
    alerta.hidden = true;
    document.body.classList.remove("desconectado");
  } catch (e) {
    falhou = true;
    document.getElementById("led").dataset.estado = "critico";
    document.body.classList.add("desconectado");
    alerta.hidden = false;
    // fetch dá TypeError quando não há conexão; o timeout vira TimeoutError.
    const motivo = e.name === "TypeError" ? "sem conexão com o Guts"
      : e.name === "TimeoutError" ? "demorou mais de 8s" : e.message;
    alerta.textContent = `O painel não respondeu (${motivo}). Os números abaixo podem estar desatualizados; tentando de novo a cada ${INTERVALO_MS / 1000}s.`;
    if (!ultimoSucesso) document.getElementById("atualizado").textContent = "Sem resposta do painel.";
  }
  atualizarRotulo();
}

atualizar();
setInterval(atualizar, INTERVALO_MS);
setInterval(atualizarRotulo, 1000);
