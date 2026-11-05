# Painel do Guts

Servidor de arquivos do homelab **Guts**. A nuvem é o armazenamento principal e o SSD local serve só de cache.

```
PC (Windows) --Samba--> Guts --> container rclone (mount FUSE) --> Drive / OneDrive / B2
                              \-> cache local no SSD (limitado)

Navegador --fetch--> painel Flask (/api/...) --HTTP--> rclone rc (rede interna)
```
``` IMportante: 
- **rclone**: monta o remote em `/mnt/cloud` no host, com cache VFS em `./cache`. O servidor rc roda no mesmo processo do mount. Se ele cair, o Docker reinicia o container e o mount volta sozinho.
- **painel**: Flask + gunicorn, com HTML/CSS/JS puro. É somente leitura: não apaga nem move nada.

## Estrutura

```
docker-compose.yml     os dois serviços
.env.example           configuração (sem segredos)
secrets/               rc_user e rc_pass (NÃO versionar)
rclone/                rclone.conf (NÃO versionar)
cache/                 cache VFS (NÃO versionar)
scripts/validar-rc.sh  confere se a versão do rclone tem os comandos usados
painel/                app Flask, mock, front-end
```

## Subindo no Guts

### 1. Pré-requisitos (uma vez)

```bash
sudo usermod -aG docker $USER
```

Saia e entre de novo na sessão para o grupo `docker` valer.

> O container recebe a pasta `/mnt` inteira, e não só a `/mnt/cloud` (o motivo está em *Coisas que descobri testando*). Não guarde outras coisas em `/mnt`. Se `/mnt` já tiver outro uso no seu sistema, troque `MOUNT_PAI` no `.env` por uma pasta dedicada (exemplo: `/srv/arquivos`), e o Samba aponta para `/srv/arquivos/cloud`.

Descomente `user_allow_other` no `/etc/fuse.conf`:

```bash
sudo sed -i 's/^#user_allow_other/user_allow_other/' /etc/fuse.conf
```

> O rclone roda como root dentro do container, então o `--allow-other` funciona mesmo sem isso. Mesmo assim, deixe ligado: se um dia o mount for feito por um usuário comum, ele passa a ser obrigatório.

### 2. Configuração

```bash
cp .env.example .env
```

Edite o `.env`. Os valores do `.env.example` são só exemplos, troque pelos seus. Os campos principais são `RCLONE_REMOTE`, `MOUNT_PAI`/`MOUNT_PASTA` (juntos formam `/mnt/cloud`), `PAINEL_BIND_IP` (o IP do Guts na LAN, exemplo: `192.168.1.10`) e `PUID`/`PGID` (veja com `id`).

Crie usuário e senha do rc. Eles vão para arquivos, e não para o `.env`, para não aparecerem no `docker inspect`. Troque `SEU_USUARIO_RC` pelo nome que quiser (é só um exemplo):

```bash
printf 'SEU_USUARIO_RC' > secrets/rc_user
```

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(24),end='')" > secrets/rc_pass && chmod 600 secrets/*
```

### 3. Autenticar o remote (uma vez)

```bash
docker compose run --rm --entrypoint rclone rclone config
```
### Limitar o servidor a uma pasta do Drive

Para o servidor enxergar só uma pasta (e não o Drive inteiro), abra o `rclone/rclone.conf`
e adicione, embaixo de `[gdrive]`:

```
root_folder_id = ID_DA_PASTA_AQUI
```

O ID é o trecho final da URL da pasta no navegador (`.../folders/ID_DA_PASTA_AQUI`).
Não publique o seu ID nem o `rclone.conf`.
- Crie o remote com o **mesmo nome** do `RCLONE_REMOTE` (ex.: `gdrive`).
- Google Drive e OneDrive pedem login pelo navegador. Como o Guts não tem um, responda **`n`** em *"Use web browser to automatically authenticate?"*. Depois rode `rclone authorize "drive"` (ou `"onedrive"`) no PC Windows, faça login e cole o token que aparecer de volta no Guts.
- O arquivo é salvo em `./rclone/rclone.conf`.

### 4. Subir

```bash
docker compose up -d --build
```

Abra `http://IP-DO-GUTS:8080`.

### 5. Conferir

A propagação do mount precisa ser `shared`. Sem isso o host vê `/mnt/cloud` vazio:

```bash
findmnt -o TARGET,PROPAGATION /mnt/cloud
```

O esperado é `shared` na coluna PROPAGATION. Se aparecer `private`, rode `sudo mount --make-rshared /` e suba o compose de novo.

Confira se a versão do rclone tem todos os comandos rc que o painel usa:

```bash
sh scripts/validar-rc.sh
```

```bash
docker compose ps
```

Os dois serviços devem aparecer como `healthy`.

### 6. Samba (no host)

Adicione ao `/etc/samba/smb.conf`. É um exemplo: troque `SEU_USUARIO` pelo usuário Linux dono dos arquivos (o mesmo do `PUID`):

```ini
[nuvem]
   path = /mnt/cloud
   valid users = SEU_USUARIO
   read only = no
   # o rclone já guarda tudo como PUID:PGID (umask 002)
   force user = SEU_USUARIO
```

```bash
sudo systemctl restart smbd
```

No Windows, abra `\\IP-DO-GUTS\nuvem`.

> Suba o compose **antes** do Samba usar a pasta. Se o Samba abrir `/mnt/cloud` antes do mount, ele vê a pasta vazia do SSD, e o que for gravado ali fica no SSD em vez de ir para a nuvem.

## Desenvolvendo no PC (modo mock)

Com `RCLONE_MOCK=1` o painel gera dados falsos e não precisa do rclone.

Sem Docker:

```bash
cd painel && pip install -r requirements.txt && RCLONE_MOCK=1 python app.py
```

Com Docker, só o painel (ponha `RCLONE_MOCK=1` no `.env`):

```bash
docker compose up --build --no-deps painel
```

Abra `http://localhost:8080`.

## Como o painel funciona

| Rota | O que faz |
|---|---|
| `GET /` | página |
| `GET /api/status` | JSON único com todos os blocos (cache de 2,5s no Flask) |
| `GET /api/health` | `{"ok": true}` para o healthcheck |

Comandos rc usados (todos de leitura): `core/version`, `mount/listmounts`, `vfs/list`, `operations/about`, `core/stats`, `vfs/stats`, `vfs/queue`.

Se um bloco falhar (rclone fora do ar, timeout de 3s, senha errada), só ele vira `{"erro": "..."}`. O resto continua aparecendo. As chamadas rodam em paralelo, então com o rclone travado a página responde em ~3s.

### Coisas que descobri testando na v1.75.2

- **`rclone rc --list` não existe** (dá "unknown flag"). O script usa o comando rc `rc/list`.
- **`mount/listmounts` vem vazio** para um mount feito com `rclone mount` na linha de comando. Ele só lista mounts criados pelo rc (`mount/mount`). Por isso o painel também usa o `vfs/list`: se o rc responde e existe um VFS ativo, o mount está ativo.
- **Provedor sem cota** (ex.: alguns S3) não devolve campos vazios: o `operations/about` dá erro *"doesn't support about"*. O painel mostra "sem cota" em vez de erro.
- **`diskCache.bytesUsed`** só é recalculado a cada `--vfs-cache-poll-interval` (1 min). Logo depois de copiar um arquivo, ele ainda mostra o valor antigo. O "Pasta de cache" do card SSD é medido direto no disco a cada 60s.
- **`core/stats.speed`** guarda a última média mesmo sem nada transferindo. O painel mostra "parado" quando não há transferência ativa.
- **Fazer o bind direto de `/mnt/cloud` não funciona.** O ponto de bind já conta como "montado", e o rclone se recusa a montar ali (`directory already mounted`). Pior: se o rclone morrer, o mount FUSE fica preso no host e o Docker não consegue nem abrir a pasta. Aí o container não sobe mais sem um `fusermount` como root. Por isso o compose faz o bind da pasta-pai (`/mnt:/mnt:shared`), e o entrypoint desmonta sozinho um mount preso antes de montar de novo. Testado com `SIGKILL` no rclone: o Docker reiniciou e o mount voltou sem intervenção.
- **As pastas do cache são criadas como `root` com modo 0700.** Por isso existe o `du-cache` (ver *Segurança*).

## Segurança

- O rc **não** é publicado no host. Ele só existe na rede interna do compose (`http://rclone:5572`).
- Só a porta do painel é publicada, e só no `PAINEL_BIND_IP`.
- Os segredos ficam em `./secrets` (Docker secrets). `.env`, `secrets/`, `rclone/` e `cache/` estão no `.gitignore`.
- O painel roda como usuário não-root, com sistema de arquivos somente leitura e `cap_drop: ALL`. A única capability devolvida é a `DAC_READ_SEARCH`, usada só pelo binário `du-cache` para medir as pastas do cache que o rclone cria como root.

## Problemas comuns

**`/mnt/cloud` dá "Transport endpoint is not connected"**: o rclone caiu. Num crash, o Docker reinicia o container em segundos e o mount volta sozinho. Se ele não voltar (por exemplo depois de um `docker kill` ou `docker stop`, que o Docker trata como parada manual), suba de novo e o entrypoint limpa o mount preso:

```bash
docker compose up -d
```

Só se o compose estiver desligado de vez e você quiser liberar a pasta:

```bash
sudo fusermount -uz /mnt/cloud
```

**"usuário/senha do rc inválidos" no painel**: os dois serviços leem os mesmos arquivos em `secrets/`. Se você trocou a senha, reinicie os dois com `docker compose up -d --force-recreate`.

**"Pasta de cache: não foi possível medir"**: confira se `PUID` é o dono de `./secrets` e se o compose tem o `cap_add: DAC_READ_SEARCH` do painel.
