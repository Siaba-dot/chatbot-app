# Studijos diegimas savo serveryje (Hetzner)

1. Hetzner Console → projektas → **Add Server**: Falkenstein / Nuremberg, **Ubuntu 24.04**, **CX33** (arba CX23).
2. Atidarykite serverį → viršuje dešinėje **„>_“ (Console)** → prisijunkite `root` ir slaptažodžiu iš el. laiško.
3. Įklijuokite ir paspauskite Enter:

   ```
   curl -fsSL https://raw.githubusercontent.com/Siaba-dot/chatbot-app/main/deploy/install.sh | bash
   ```

4. Po kelių minučių pamatysite studijos adresą (`https://studija.<IP>.sslip.io`) ir administratoriaus slaptažodį – išsisaugokite.

## Nustatymai
- OpenAI raktas, kontaktai, klientai: `nano /opt/reels-studija/deploy/secrets.toml`, tada
  `cd /opt/reels-studija/deploy && docker compose restart studija`.
- Studijos atnaujinimas (po naujų pakeitimų GitHub): vėl paleiskite 3 punkto komandą – nustatymai ir duomenys išlieka.
- Savas domenas: DNS įraše nukreipkite domeną į serverio IP, tada `/opt/reels-studija/deploy/.env` įrašykite
  `DOMAIN=studija.jusudomenas.lt` ir `docker compose up -d`.

## Kaip sutvarkyta
- `Dockerfile` – Ubuntu 24.04 su ffmpeg 6.1 (ta pati versija, su kuria studija išbandyta), Python, šriftai.
- `docker-compose.yml` – studija + Caddy (automatinis HTTPS sertifikatas); duomenys – nuolatinėje saugykloje
  (`studija-data`), nedingsta atnaujinant.
- Vienu metu kuriamas vienas video (`REELS_MAX_RENDERS=1`), laikini failai valomi kas valandą, sukuriamas 2 GB swap.
