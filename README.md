# Chatbot + automatinis video montažas

Paleidimas: `streamlit run main.py` – atsidaro video montažo programa. Pokalbių robotas – šoniniame meniu (**Chatbot**, jam reikia `OPENAI_API_KEY`).

## 🎬 Video montažas
Įkeliate vieną ar kelis video arba nufilmuojate juos tiesiai programoje („🎥 Filmuoti dabar“ – programa paprašo leidimo
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
