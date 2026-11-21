# Reels studijos API (1 etapas)

Naujos naršyklės programos pagrindas: tas pats video variklis (`engine.py` → `video_editor`, `reels_studio`,
`animations`, `fxpack`), tik be Streamlit. Serveryje veikia šalia studijos: `https://DOMAIN/api/docs`.

| Veiksmas | Kelias |
|---|---|
| Prisijungti (tie patys klientai kaip studijoje) | `POST /api/login` → `token` |
| Kas aš, planas, likusios minutės | `GET /api/me` |
| Visi pasirinkimai (šablonai, filtrai, efektai, titrai, muzika…) | `GET /api/options` |
| Mano projektai | `GET /api/projects`, `POST /api/projects` |
| Įkelti video / nuotrauką / įrašą | `POST /api/projects/{id}/clips` (multipart `file`, `recorded`) |
| Nustatymai | `PUT /api/projects/{id}/settings` |
| Paruošti titrus (atpažinti kalbą) | `POST /api/projects/{id}/prepare` |
| Kurti video (greita peržiūra arba galutinis) | `POST /api/projects/{id}/render` `{quick, words, settings}` |
| Darbo eiga | `GET /api/jobs/{job}` → `progress`, `message`, `result` |
| Atsisiųsti | `GET /api/projects/{id}/files/reels.mp4?token=…&download=1` (`preview.mp4`, `cover.jpg`) |

Žetonas – `Authorization: Bearer …` arba `?token=…` (video žymei). Projektai saugomi
`REELS_DATA_DIR/projects/<naudotojas>/<projektas>/` ir išlieka perkrovus serverį.

Paleisti vietoje: `uvicorn api.server:app --port 8000` (iš repozitorijos šaknies).
