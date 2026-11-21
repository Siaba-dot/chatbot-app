# Reels montavimo studija – serveriui (Hetzner ir pan.).
# Ubuntu 24.04: ffmpeg 6.1 su libass – ta pati versija, su kuria studija išbandyta.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg ca-certificates fontconfig \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /venv && /venv/bin/pip install -r requirements.txt
COPY . .
# REELS_DATA_DIR – nuolatiniai duomenys (prekės ženklai, minutės); TMPDIR – laikini video failai tame pačiame diske
ENV PATH=/venv/bin:$PATH REELS_DATA_DIR=/data TMPDIR=/data/tmp REELS_FFMPEG_THREADS=2 REELS_MAX_RENDERS=1
EXPOSE 8501
# Laikini failai, senesni nei 6 val., valomi kas valandą (diskas neprisipildo)
CMD ["sh", "-c", "mkdir -p /data/tmp && (while true; do find /data/tmp -mindepth 1 -mmin +360 -delete 2>/dev/null; sleep 3600; done) & exec streamlit run pages/1_Reels_studija.py --server.port 8501 --server.address 0.0.0.0 --server.headless true --server.fileWatcherType none"]
