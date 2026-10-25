# Chatbot + automatinis video montažas

Paleidimas: `streamlit run main.py` (šoniniame meniu – puslapis **Video montazas**).

## 🎬 Video montažas
Įkeliate video, programa pati:
- iškerpa tylą ir pauzes (jump-cut),
- apkarpo į pasirinktą formatą (9:16, 1:1, 16:9 arba originalus),
- suvienodina garsumą, prideda švelnią pradžią/pabaigą,
- (pasirinktinai) atpažįsta kalbą per OpenAI Whisper ir uždeda animuotus titrus
  (Montserrat Black, sakomas žodis geltonas). Reikia `OPENAI_API_KEY` Streamlit secrets.

Reikalinga `ffmpeg` (Streamlit Cloud ją įdiegia iš `packages.txt`).
Galima naudoti ir be naršyklės: `python3 video_editor.py IN.mp4 OUT.mp4 --format 9:16 --subtitles`.
