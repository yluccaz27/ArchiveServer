FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# du-cache: uma cópia do `du` com permissão só de LEITURA em qualquer pasta
# (cap_dac_read_search). O rclone roda como root e cria as pastas do cache
# com modo 0700; sem isso o painel (não-root) não conseguiria medir o tamanho.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libcap2-bin \
 && cp /usr/bin/du /usr/local/bin/du-cache \
 && setcap cap_dac_read_search+ep /usr/local/bin/du-cache \
 && apt-get purge -y libcap2-bin && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

USER 1000:1000
EXPOSE 8080

# 1 worker de propósito: o cache do /api/status e a medição da pasta de
# cache ficam em memória, e com vários workers cada um teria a sua cópia.
# As threads dão conta de várias abas abertas ao mesmo tempo.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", \
     "--worker-tmp-dir", "/tmp", "--access-logfile", "-", "app:app"]
