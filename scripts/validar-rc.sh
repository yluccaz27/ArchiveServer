#!/bin/sh
# Confere se o rclone do container tem os comandos rc que o painel usa.
# Não depende do número da versão: pergunta ao próprio rclone (rc/list).
#
# Obs.: `rclone rc --list` não existe na v1.75.2 (dá "unknown flag").
# O jeito que funciona é o comando rc "rc/list".
#
# Uso (na pasta do projeto, com o compose no ar):  sh scripts/validar-rc.sh

set -eu

NECESSARIOS="core/version core/stats mount/listmounts vfs/list operations/about vfs/stats vfs/queue"

# Roda dentro do container, lendo usuário/senha dos secrets.
LISTA=$(docker compose exec -T rclone sh -c '
  rclone rc --url http://127.0.0.1:5572 \
    --user "$(cat /run/secrets/rc_user)" --pass "$(cat /run/secrets/rc_pass)" rc/list
' | grep -o '"Path": *"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')

FALTANDO=0
for cmd in $NECESSARIOS; do
  if printf '%s\n' "$LISTA" | grep -qx "$cmd"; then
    echo "ok      $cmd"
  else
    echo "FALTA   $cmd"
    FALTANDO=1
  fi
done

[ "$FALTANDO" -eq 0 ] && echo "Tudo certo: a versão da imagem tem todos os comandos." || {
  echo "Algum comando não existe nesta versão. Troque RCLONE_VERSAO no .env."
  exit 1
}
