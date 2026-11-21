#!/usr/bin/env bash
# Reels studijos įdiegimas naujame Ubuntu 24.04 serveryje (paleisti kaip root):
#   curl -fsSL https://raw.githubusercontent.com/Siaba-dot/chatbot-app/main/deploy/install.sh | bash
# Kartojant – atnaujina studiją (nustatymai ir duomenys išlieka).
set -euo pipefail
DIR=/opt/reels-studija
echo "==> Ruošiu serverį…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl openssl >/dev/null
if ! command -v docker >/dev/null; then
  echo "==> Diegiu Docker…"
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
if ! swapon --show | grep -q .; then  # atsarginė atmintis – kad video kūrimas neperpildytų RAM
  echo "==> Kuriu 2 GB swap…"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi
if [ -d "$DIR/.git" ]; then
  echo "==> Atnaujinu studiją…"
  git -C "$DIR" pull -q --ff-only
else
  echo "==> Atsisiunčiu studiją…"
  git clone -q https://github.com/Siaba-dot/chatbot-app.git "$DIR"
fi
cd "$DIR/deploy"
if [ ! -f .env ]; then
  IP=$(hostname -I | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | grep -vE '^(10|127|172|192\.168)\.' | head -1)
  echo "DOMAIN=studija.${IP//./-}.sslip.io" > .env
fi
NEW_PW=""
if [ ! -f secrets.toml ]; then
  NEW_PW=$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 12)
  sed "s/PAKEISKITE/$NEW_PW/" secrets.example.toml > secrets.toml
  chmod 600 secrets.toml
fi
echo "==> Paleidžiu studiją (pirmą kartą – kelios minutės)…"
docker compose up -d --build
docker image prune -f >/dev/null
. ./.env
echo
echo "✅ Studija veikia: https://$DOMAIN"
echo "   Naujos programos API: https://$DOMAIN/api/docs"
if [ -n "$NEW_PW" ]; then
  echo "   Prisijungimas: admin / $NEW_PW   (išsisaugokite – daugiau nerodomas)"
fi
echo "   OpenAI raktą įklijuokite studijoje: 👑 Administravimas → OpenAI raktas
   Kiti nustatymai (klientai): nano $DIR/deploy/secrets.toml"
echo "   Pakeitus nustatymus: cd $DIR/deploy && docker compose restart studija"
