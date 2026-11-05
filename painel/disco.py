"""Uso do disco local (SSD do Guts) e tamanho real da pasta de cache.

O tamanho real da pasta é caro de medir (percorre todos os arquivos),
então uma thread mede a cada CACHE_REAL_INTERVALO segundos e guarda o
resultado em memória. A rota só lê o último valor.
"""
import os
import shutil
import subprocess
import threading
import time

import config

_ultimo = {"bytes": None, "medido_em": None, "erro": None}
_trava = threading.Lock()


# No container existe /usr/local/bin/du-cache (ver Dockerfile), que consegue
# ler as pastas 0700 que o rclone cria. No PC usamos Python puro.
DU_CACHE = shutil.which("du-cache")


def _tamanho_com_du(caminho):
    """Tamanho em bytes via `du-cache -s -B1` (conta blocos alocados)."""
    proc = subprocess.run([DU_CACHE, "-s", "-B1", caminho],
                          capture_output=True, text=True, timeout=120)
    if "Permission denied" in proc.stderr or not proc.stdout:
        raise PermissionError(proc.stderr.strip().splitlines()[-1] if proc.stderr else "du falhou")
    # Saída: "123456\t/cache". Código 1 com arquivo sumindo no meio é normal.
    return int(proc.stdout.split()[0])


def _tamanho_com_python(caminho):
    """Soma o espaço ocupado de verdade (blocos alocados) pelos arquivos.

    Usamos st_blocks em vez de st_size porque o cache do rclone guarda
    arquivos esparsos: um vídeo de 2 GB lido só pela metade ocupa 1 GB.
    """
    erros = []
    total = 0
    for raiz, _pastas, arquivos in os.walk(caminho, onerror=erros.append):
        for nome in arquivos:
            try:
                total += os.lstat(os.path.join(raiz, nome)).st_blocks * 512
            except OSError:
                pass  # arquivo apagado no meio da contagem: normal
    # Se alguma pasta não pôde ser lida, o total estaria errado (para menos).
    if any(isinstance(e, PermissionError) for e in erros):
        raise PermissionError("sem permissão para ler todas as pastas do cache")
    return total


def _medir_para_sempre():
    """Loop da thread de fundo."""
    while True:
        try:
            if DU_CACHE:
                tamanho = _tamanho_com_du(config.CACHE_DIR)
            else:
                tamanho = _tamanho_com_python(config.CACHE_DIR)
            novo = {"bytes": tamanho, "medido_em": time.time(), "erro": None}
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            novo = {"bytes": None, "medido_em": time.time(), "erro": str(e)}
        with _trava:
            _ultimo.update(novo)
        time.sleep(config.INTERVALO_CACHE_REAL)


def iniciar_medicao():
    """Liga a thread de medição (chamar uma vez, na subida do app)."""
    threading.Thread(target=_medir_para_sempre, name="cache-real", daemon=True).start()


def info_ssd():
    """Uso do sistema de arquivos onde está a pasta de cache (o SSD)."""
    try:
        uso = shutil.disk_usage(config.CACHE_DIR)
    except OSError as e:
        return {"erro": f"não consegui ler o disco: {e}"}

    with _trava:
        medido = dict(_ultimo)

    return {
        "total": uso.total,
        "usado": uso.used,
        "livre": uso.free,
        "pct": round(uso.used * 100 / uso.total, 1) if uso.total else None,
        "cache_real": medido["bytes"],
        "cache_real_medido_em": medido["medido_em"],
        "cache_real_erro": medido["erro"],
        "cache_limite": config.CACHE_LIMITE,
    }
