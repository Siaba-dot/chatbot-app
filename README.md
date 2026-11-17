# Chatbot + automatinis video montažas

Paleidimas: `streamlit run main.py` – atsidaro video montažo programa. Šoniniame meniu – **Reels studija** ir pokalbių robotas (**Chatbot**, jam reikia `OPENAI_API_KEY`).

## 🎬 Video montažas
Įkeliate vieną ar kelis video ar nuotraukas (nuotraukos rodomos po kelias sekundes) arba nufilmuojate juos tiesiai programoje („🎥 Filmuoti dabar“ – programa paprašo leidimo
naudoti kamerą ir mikrofoną, rodo garso lygio juostelę), o programa pati:
- sujungia kelis video į vieną (tvarką galima keisti, skirtingo dydžio / orientacijos įrašai suvienodinami),
- iškerpa tylą ir pauzes (jump-cut),
- apkarpo į pasirinktą formatą (9:16, 1:1, 16:9 arba originalus),
- pašalina foninį triukšmą (ūžesį, šnypštimą, vėją), suvienodina garsumą, prideda švelnią pradžią/pabaigą,
- uždeda titrus – **modernius** (animuoti, Montserrat Black, sakomas žodis geltonas) arba
  **mokymų** (ramūs, juodoje juostoje po vaizdu, vaizdo neuždengia):
  - jei įraše yra **balsas** – kalba atpažįstama automatiškai (OpenAI Whisper, reikia `OPENAI_API_KEY`);
    jei kalbama kita kalba nei pasirinkta titrams (pvz. angliškai), titrai išverčiami (pvz. į lietuvių),
  - jei **balso nėra** – įklijuojate tekstą, ir jis tolygiai išdėliojamas per video.

Pats montažas (kirpimas, formatas, garsas) veikia be jokių API – su ffmpeg.

Reikalinga `ffmpeg` (Streamlit Cloud ją įdiegia iš `packages.txt`).
Galima naudoti ir be naršyklės: `python3 video_editor.py IN.mp4 OUT.mp4 --format 9:16 --subtitles [--text tekstas.txt]`.

## ✨ Reels studija
Prabangi (tamsi su auksu) studija Instagram Reels / TikTok / Shorts vaizdo įrašams – šoniniame meniu **Reels studija**.
Viskas, ką daro automatinis montažas (pauzių kirpimas, triukšmo valymas, titrai), plius:
- **šablonai**: „Prabangus auksas“ ir „Elegantiškas minimalizmas“ (Playfair Display šriftas, plona auksinė linija,
  švelnus ryškėjimas), „Ryškus (TikTok stilius)“ (didelės raidės spalvotoje dėžutėje);
- **kabliukas** – antraštė pirmoms sekundėms, **kvietimas veikti** pabaigoje, **@paskyra** viršuje;
- **foninės muzikos biblioteka** (6 kūriniai be autorių teisių apribojimų: Prabangus pianinas, Lounge, Kinematografiška,
  Energinga, Lo-fi, Romantiška – `music/`, sukurta `tools/make_music.py`) arba sava muzika; ji automatiškai patyli, kai kalbama;
- **filtrai langeliuose** – kiekvienas parodomas ant jūsų video kadro (Auksinė valanda, Kino, Teal & Orange, Noir auksas,
  Ryškios, Vintažas, Pastelinės, Sepija, Šaltos, Nespalvotos); akcento spalva (ir titrų paryškinimui);
- **efektai langeliuose** (galima derinti): Lėtas priartėjimas, Švytėjimas, Kino juostos, Kino grūdeliai, Vinjetė,
  Ryškumas, Šviesos blyksnis;
- **trukmės riba** (15 / 30 / 60 / 90 s), **greitis**, **progreso juostelė**;
- **viršelis** (JPG 1080×1920) su peržiūra prieš kuriant;
- **balso atpažinimas titrams** ir **aprašymas, grotažymės, kabliukų idėjos** – reikia OpenAI rakto: `OPENAI_API_KEY`
  Streamlit Secrets arba įvedamas pačioje studijoje (laikomas tik naršyklės sesijoje).

Be naršyklės: `python3 reels_studio.py SUMONTUOTA.mp4 REELS.mp4 --hook "..." --cta "..." --music daina.mp3 --cover virselis.jpg`.

## 🔐 Klientai ir planai (svetainei)
Kai Streamlit Secrets (⋮ → Settings → Secrets) aprašomi klientai, studija atsidaro tik prisijungus:

```toml
OPENAI_API_KEY = "sk-..."      # jūsų raktas – naudojamas tik Premium klientams
contact = "info@jusu.lt"       # rodoma Pagrindinio plano klientams

[users.admin]
password = "labai-slaptas"
plan = "admin"                 # mato visų klientų naudojimą

[users.salonas]
password = "slaptazodis1"
plan = "premium"               # + automatiniai titrai iš kalbos, vertimas, aprašymai
minutes = 60                   # balso atpažinimo minučių per mėnesį
name = "Grožio salonas"

[users.kirpykla]
password = "slaptazodis2"
plan = "basic"                 # viskas, išskyrus balso atpažinimą ir aprašymus
name = "Kirpykla"
```

- **Pagrindinis** – montažas, garsas, šablonai, filtrai, efektai, muzika, viršelis, titrai iš įvesto teksto.
- **Premium** – plius automatiniai titrai iš kalbos, vertimas, aprašymas su grotažymėmis (iki `minutes` per mėnesį).
- Klientą išjungti: ištrinkite jo bloką arba įrašykite `active = false`.
- Minučių apskaita laikoma serveryje (`.data/usage.json`) ir išsivalo, kai programa perkraunama – OpenAI
  svetainėje papildomai nustatykite išlaidų ribą.
- Be `[users]` programa atvira visiems, kaip anksčiau.
