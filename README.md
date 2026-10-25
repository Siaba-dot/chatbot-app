# Chatbot + automatinis video montažas

Paleidimas: `streamlit run main.py` – atsidaro video montažo programa. Pokalbių robotas – šoniniame meniu (**Chatbot**, jam reikia `OPENAI_API_KEY`).

## 🎬 Video montažas
Įkeliate video, programa pati:
- iškerpa tylą ir pauzes (jump-cut),
- apkarpo į pasirinktą formatą (9:16, 1:1, 16:9 arba originalus),
- suvienodina garsumą, prideda švelnią pradžią/pabaigą,
- (pasirinktinai) uždeda animuotus titrus (Montserrat Black, sakomas žodis geltonas):
  įklijuojate tekstą, ką sakote, o programa pati sulygina žodžius su kalba.

Montažui nereikia jokių API raktų, paskyrų ar interneto ryšio – viskas daroma su ffmpeg.

Reikalinga `ffmpeg` (Streamlit Cloud ją įdiegia iš `packages.txt`).
Galima naudoti ir be naršyklės: `python3 video_editor.py IN.mp4 OUT.mp4 --format 9:16 --subtitles tekstas.txt`.
