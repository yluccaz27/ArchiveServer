"""Painel do Guts: rotas Flask.

O navegador só fala com este app. Este app é o único que fala com o rclone.
Versão 1 é somente leitura: nenhuma rota apaga, move ou altera arquivos.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template

import config
import disco
import mock
import rclone_client as rc

app = Flask(__name__)

# As 5 consultas ao rclone rodam em paralelo: se ele estiver travado, a rota
# espera ~3s (um timeout) em vez de 3s x 5.
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="rc")

# Cache curto do /api/status: várias abas abertas não multiplicam as
# chamadas ao rclone.
_cache_status = {"dados": None, "quando": 0.0}
_trava_status = threading.Lock()

if not config.MOCK:
    disco.iniciar_medicao()


def montar_status():
    """Junta todos os blocos num único dicionário."""
    if config.MOCK:
        dados = mock.status()
    else:
        tarefas = {
            "mount": _pool.submit(rc.info_mount),
            "nuvem": _pool.submit(rc.info_nuvem),
            "transferencias": _pool.submit(rc.info_transferencias),
            "cache": _pool.submit(rc.info_cache),
            "fila": _pool.submit(rc.info_fila),
        }
        dados = {nome: futuro.result() for nome, futuro in tarefas.items()}
        dados["ssd"] = disco.info_ssd()

        # Se nem o core/version respondeu, o mount também não está ok.
        if "erro" in dados["mount"]:
            dados["mount"] = {"online": False, "montado": False,
                              "ponto": config.MOUNT_POINT, **dados["mount"]}

    dados["gerado_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dados["mock"] = config.MOCK
    return dados


@app.get("/")
def index():
    return render_template("index.html", remote=config.REMOTE, mock=config.MOCK)


@app.get("/api/status")
def status():
    with _trava_status:
        agora = time.monotonic()
        if _cache_status["dados"] is None or agora - _cache_status["quando"] > config.STATUS_TTL:
            _cache_status["dados"] = montar_status()
            _cache_status["quando"] = agora
        dados = _cache_status["dados"]
    resp = jsonify(dados)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/health")
def health():
    # Só diz se o painel está de pé. Não depende do rclone: se ele cair,
    # o painel continua no ar justamente para mostrar o erro.
    return jsonify({"ok": True})


if __name__ == "__main__":
    # Só para desenvolvimento. Em produção quem serve é o gunicorn.
    app.run(host="0.0.0.0", port=8080, debug=True)
