"""Funções que conversam com a API rc do rclone.

Referência dos comandos: https://rclone.org/rc/
Toda chamada é um POST com corpo JSON para http://rclone:5572/<comando>.

Regra de ouro deste módulo: nenhuma função lança exceção para quem chama.
Se algo der errado, o bloco correspondente vira {"erro": "..."} e o resto
do painel continua funcionando.
"""
import functools

import requests

import config


class ErroRc(Exception):
    """Falha ao falar com o rclone, já com mensagem amigável."""


def chamar_rc(comando, params=None):
    """Executa um comando rc e devolve o JSON da resposta."""
    url = f"{config.RC_URL}/{comando}"
    auth = (config.RC_USER, config.RC_PASS) if config.RC_USER else None
    try:
        resp = requests.post(url, json=params or {}, auth=auth, timeout=config.RC_TIMEOUT)
    except requests.Timeout:
        raise ErroRc(f"rclone não respondeu em {config.RC_TIMEOUT:g}s")
    except requests.ConnectionError:
        raise ErroRc("rclone fora do ar (sem conexão com o rc)")

    if resp.status_code == 401:
        raise ErroRc("usuário/senha do rc inválidos")
    if resp.status_code == 404:
        raise ErroRc(f"comando '{comando}' não existe nesta versão do rclone")
    if resp.status_code != 200:
        # Em caso de erro o rclone devolve {"error": "...", "status": 500, ...}
        try:
            detalhe = resp.json().get("error", resp.text)
        except ValueError:
            detalhe = resp.text
        raise ErroRc(f"{comando}: {detalhe}".strip()[:200])

    try:
        return resp.json()
    except ValueError:
        raise ErroRc(f"{comando}: resposta inválida (não é JSON)")


def protegido(funcao):
    """Decorator: transforma qualquer falha em {"erro": "..."}."""

    @functools.wraps(funcao)
    def envolvida(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except ErroRc as e:
            return {"erro": str(e)}
        except Exception as e:  # dado inesperado: não derruba a rota
            return {"erro": f"erro inesperado: {e.__class__.__name__}: {e}"}

    return envolvida


def _pct(parte, total):
    """Porcentagem com 1 casa, ou None se não der para calcular."""
    if parte is None or not total:
        return None
    return round(parte * 100 / total, 1)


@protegido
def info_mount():
    """Versão do rclone (core/version) e se o mount está ativo.

    Atenção (testado na v1.75.2): mount/listmounts só lista mounts criados
    pelo próprio rc (mount/mount). O mount feito com `rclone mount` na linha
    de comando NÃO aparece lá, a lista vem vazia. Por isso também olhamos o
    vfs/list: o mount registra um VFS, e se o FUSE for desmontado o processo
    `rclone mount` termina (e o rc junto). Então: rc respondendo + VFS ativo
    = mount ativo.
    """
    versao = chamar_rc("core/version")
    montagens = chamar_rc("mount/listmounts").get("mountPoints") or []
    vfses = chamar_rc("vfs/list").get("vfses") or []

    # Cada item tem {"Fs", "MountPoint", "MountedOn"}. Aceitamos string também,
    # por garantia, caso alguma versão devolva só o caminho.
    pontos = [m.get("MountPoint") if isinstance(m, dict) else m for m in montagens]
    return {
        "online": True,
        "versao": versao.get("version"),
        "so": f"{versao.get('os', '?')}/{versao.get('arch', '?')}",
        "montado": config.MOUNT_POINT in pontos or len(vfses) > 0,
        "ponto": config.MOUNT_POINT,
        "vfs": vfses,
    }


@protegido
def info_nuvem():
    """Cota do remote (operations/about).

    Alguns provedores não informam tudo: o rclone simplesmente omite os
    campos. Por isso usamos .get() e marcamos "suportado": False quando
    não há nada para mostrar.
    """
    try:
        about = chamar_rc("operations/about", {"fs": f"{config.REMOTE}:"})
    except ErroRc as e:
        # Backends sem suporte nenhum a "about" respondem com erro 500
        # "... doesn't support about". Isso não é falha: só não há cota.
        if "doesn't support about" not in str(e):
            raise
        about = {}
    total = about.get("total")
    usado = about.get("used")
    livre = about.get("free")

    # Às vezes vem só usado + livre: dá para deduzir o total.
    if total is None and usado is not None and livre is not None:
        total = usado + livre

    return {
        "remote": f"{config.REMOTE}:",
        "suportado": total is not None or usado is not None,
        "total": total,
        "usado": usado,
        "livre": livre,
        "lixeira": about.get("trash"),
        "objetos": about.get("objects"),
        "pct": _pct(usado, total),
    }


@protegido
def info_transferencias():
    """Velocidade, bytes e arquivos em transferência (core/stats)."""
    stats = chamar_rc("core/stats")
    ativas = [
        {
            "nome": t.get("name"),
            "tamanho": t.get("size"),
            "pct": t.get("percentage"),
            "velocidade": t.get("speed"),
            "eta": t.get("eta"),
        }
        for t in stats.get("transferring") or []
    ]
    return {
        # "speed" guarda a última média mesmo depois que tudo terminou;
        # sem transferência ativa, a velocidade real é zero.
        "velocidade": stats.get("speed", 0) if ativas else 0,
        "bytes": stats.get("bytes", 0),
        "transferidos": stats.get("transfers", 0),
        "erros": stats.get("errors", 0),
        "ultimo_erro": stats.get("lastError") or None,
        "tempo": stats.get("elapsedTime"),
        "ativas": ativas,
    }


@protegido
def info_cache():
    """Uso do cache VFS segundo o próprio rclone (vfs/stats -> diskCache).

    Com um único mount ativo não precisamos passar o parâmetro "fs".
    """
    stats = chamar_rc("vfs/stats")
    disco = stats.get("diskCache")
    if disco is None:
        raise ErroRc("cache em disco desligado (--vfs-cache-mode off)")

    # O limite real vem das opções do VFS; se não vier, usamos o do .env.
    limite = (stats.get("opt") or {}).get("CacheMaxSize") or config.CACHE_LIMITE
    if not isinstance(limite, (int, float)) or limite < 0:
        limite = config.CACHE_LIMITE

    usado = disco.get("bytesUsed", 0)
    return {
        "usado": usado,
        "limite": limite,
        "pct": _pct(usado, limite),
        "arquivos": disco.get("files", 0),
        "com_erro": disco.get("erroredFiles", 0),
        "sem_espaco": bool(disco.get("outOfSpace")),
        "enviando": disco.get("uploadsInProgress", 0),
        "na_fila": disco.get("uploadsQueued", 0),
    }


@protegido
def info_fila():
    """Arquivos esperando para subir para a nuvem (vfs/queue)."""
    fila = chamar_rc("vfs/queue").get("queue") or []
    itens = [
        {
            "nome": item.get("name"),
            "tamanho": item.get("size", 0),
            "enviando": bool(item.get("uploading")),
            "tentativas": item.get("tries", 0),
            "espera": item.get("delay"),  # segundos até tentar subir
        }
        for item in fila
    ]
    # Quem está subindo primeiro, depois quem vai subir antes.
    itens.sort(key=lambda i: (not i["enviando"], i["espera"] or 0))
    return {
        "aguardando": sum(1 for i in itens if not i["enviando"]),
        "enviando": sum(1 for i in itens if i["enviando"]),
        "bytes": sum(i["tamanho"] or 0 for i in itens),
        "itens": itens[:20],  # o front não precisa de uma lista gigante
    }
