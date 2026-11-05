"""Dados falsos (mas com cara de reais) para o modo RCLONE_MOCK=1.

Os valores mudam um pouco a cada chamada, para dar para ver o polling
funcionando no navegador sem ter o rclone rodando.
"""
import math
import random
import time

GB = 1024**3
MB = 1024**2

_inicio = time.time()

_ARQUIVOS = [
    "ACDB/renders/cena_04_final.mp4",
    "ACDB/texturas/parede_tijolo_8k.png",
    "ACDB/referencias/storyboard_v3.psd",
    "Projetos/tcc/gravacao_banca.mkv",
    "Fotos/2026-10/IMG_20261028_183211.jpg",
    "Fotos/2026-10/IMG_20261028_183240.jpg",
]


def status():
    """Mesmo formato do /api/status real."""
    t = time.time() - _inicio
    # Velocidade "respira" entre ~1 e ~9 MB/s, com ruído.
    velocidade = int((5 + 4 * math.sin(t / 20)) * MB + random.randint(-300, 300) * 1024)
    bytes_total = int(t * 4.5 * MB) + 37 * GB

    em_envio = _ARQUIVOS[int(t / 15) % len(_ARQUIVOS)]
    pct_envio = int((t % 15) / 15 * 100)

    cache_usado = int(14.2 * GB + (t % 600) * 2 * MB)
    cache_limite = 40 * GB

    na_fila = [
        {"nome": nome, "tamanho": [210, 48, 1300, 3, 95, 4][_ARQUIVOS.index(nome)] * MB,
         "enviando": False, "tentativas": 0, "espera": 5 + i * 3}
        for i, nome in enumerate(_ARQUIVOS[:3])
        if nome != em_envio
    ]
    fila = [{"nome": em_envio, "tamanho": 820 * MB, "enviando": True,
             "tentativas": 0, "espera": 0}] + na_fila

    ssd_total = 117 * GB
    ssd_usado = int(51 * GB + cache_usado - 14 * GB)

    return {
        "mount": {"online": True, "versao": "v1.75.2", "so": "linux/amd64",
                  "montado": True, "ponto": "/mnt/cloud", "vfs": ["gdrive:"]},
        "nuvem": {"remote": "gdrive:", "suportado": True,
                  "total": 2048 * GB, "usado": 743 * GB + int(t * MB),
                  "livre": 1305 * GB - int(t * MB), "lixeira": 2 * GB,
                  "objetos": None, "pct": round((743 * GB + t * MB) * 100 / (2048 * GB), 1)},
        "transferencias": {
            "velocidade": velocidade, "bytes": bytes_total, "transferidos": 214 + int(t / 15),
            "erros": 0, "ultimo_erro": None, "tempo": t,
            "ativas": [{"nome": em_envio, "tamanho": 820 * MB, "pct": pct_envio,
                        "velocidade": velocidade, "eta": int((100 - pct_envio) * 0.8)}],
        },
        "cache": {"usado": cache_usado, "limite": cache_limite,
                  "pct": round(cache_usado * 100 / cache_limite, 1),
                  "arquivos": 318 + int(t / 30), "com_erro": 0, "sem_espaco": False,
                  "enviando": 1, "na_fila": len(na_fila)},
        "fila": {"aguardando": len(na_fila), "enviando": 1,
                 "bytes": sum(i["tamanho"] for i in fila), "itens": fila},
        "ssd": {"total": ssd_total, "usado": ssd_usado, "livre": ssd_total - ssd_usado,
                "pct": round(ssd_usado * 100 / ssd_total, 1),
                "cache_real": int(cache_usado * 0.97), "cache_real_medido_em": time.time() - (t % 60),
                "cache_real_erro": None, "cache_limite": cache_limite},
    }
