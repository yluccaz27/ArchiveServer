"""Configuração do painel, lida das variáveis de ambiente.

Tudo que muda entre o PC (desenvolvimento) e o Guts (produção) fica aqui,
para o resto do código não precisar mexer em os.environ.
"""
import os


def _ler_segredo(nome):
    """Lê um segredo de NOME_FILE (arquivo, ex.: Docker secret) ou de NOME.

    No compose usamos arquivos em /run/secrets, porque variáveis definidas
    no compose aparecem no `docker inspect`. No PC dá para usar a variável
    direto, que é mais prático.
    """
    caminho = os.environ.get(f"{nome}_FILE")
    if caminho:
        try:
            with open(caminho, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""
    return os.environ.get(nome, "")


def tamanho_em_bytes(texto):
    """Converte '40G', '512M', '1T' (unidades do rclone, base 1024) em bytes."""
    texto = (texto or "").strip().upper().removesuffix("B")
    if not texto:
        return 0
    unidades = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
    if texto[-1] in unidades:
        return int(float(texto[:-1]) * unidades[texto[-1]])
    return int(float(texto))


# Modo mock: dados falsos, para desenvolver sem o rclone rodando.
MOCK = os.environ.get("RCLONE_MOCK", "0") == "1"

# Endereço da API rc. No compose é o nome do serviço na rede interna.
RC_URL = os.environ.get("RCLONE_RC_URL", "http://rclone:5572").rstrip("/")
RC_USER = _ler_segredo("RCLONE_RC_USER")
RC_PASS = _ler_segredo("RCLONE_RC_PASS")
RC_TIMEOUT = float(os.environ.get("RCLONE_RC_TIMEOUT", "3"))

# Nome do remote configurado no rclone.conf (sem os dois pontos).
REMOTE = os.environ.get("RCLONE_REMOTE", "gdrive").rstrip(":")

# Ponto de montagem (o mesmo caminho dentro do container e no host).
MOUNT_POINT = os.environ.get("MOUNT_POINT", "/mnt/cloud")

# Pasta do cache VFS, montada no painel somente para leitura.
CACHE_DIR = os.environ.get("CACHE_DIR", "/cache")
CACHE_LIMITE = tamanho_em_bytes(os.environ.get("VFS_CACHE_MAX_SIZE", "40G"))

# De quanto em quanto tempo medir o tamanho real da pasta de cache.
INTERVALO_CACHE_REAL = int(os.environ.get("CACHE_REAL_INTERVALO", "60"))

# Por quanto tempo reaproveitar a resposta do /api/status.
STATUS_TTL = float(os.environ.get("STATUS_CACHE_SEGUNDOS", "2.5"))
