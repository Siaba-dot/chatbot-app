# Chatbot + automatinis video montažas

Paleidimas: `streamlit run main.py` – atsidaro video montažo programa. Pokalbių robotas – šoniniame meniu (**Chatbot**, jam reikia `OPENAI_API_KEY`).

## 🎬 Video montažas
Įkeliate video, programa pati:
- iškerpa tylą ir pauzes (jump-cut),
- apkarpo į pasirinktą formatą (9:16, 1:1, 16:9 arba originalus),
- suvienodina garsumą, prideda švelnią pradžią/pabaigą,
- uždeda animuotus titrus (Montserrat Black, sakomas žodis geltonas):
  - jei įraše yra **balsas** – kalba atpažįstama automatiškai (OpenAI Whisper, reikia `OPENAI_API_KEY`);
    jei kalbama kita kalba nei pasirinkta titrams (pvz. angliškai), titrai išverčiami (pvz. į lietuvių),
  - jei **balso nėra** – įklijuojate tekstą, ir jis tolygiai išdėliojamas per video.

Pats montažas (kirpimas, formatas, garsas) veikia be jokių API – su ffmpeg.

Reikalinga `ffmpeg` (Streamlit Cloud ją įdiegia iš `packages.txt`).
Galima naudoti ir be naršyklės: `python3 video_editor.py IN.mp4 OUT.mp4 --format 9:16 --subtitles [--text tekstas.txt]`.

## 📱 Ranka išlenda iš nuotraukos (pop-out)
Puslapis **Pop out video**: įkeliate nuotrauką, kurioje žmogus laiko telefoną su **žaliu ekranu**.
Programa įdeda jūsų ekraną (sukurtą pagal tekstą arba įkeltą paveikslėlį), iškerpa ranką su telefonu
(plaštaką, dilbį ir rankovę – be kūno po ranka) ir sudeda įrašo vaizdą 4:5: viršuje nuotrauka, apačioje
komentarai su laikais, o ranka išlenda per nuotraukos kraštą ir uždengia komentarus.

Video:
- **AI video pagal užklausą** – nuotrauka paverčiama video su natūraliu rankos judesiu (fal.ai, Kling modelis),
  efektas uždedamas kiekvienam kadrui. Reikia `FAL_KEY` (Streamlit → Secrets).
- **Be AI** – nuotrauka animuojama (ranka „išstumia“ telefoną į priekį).
- **Savo video** – efektas uždedamas jau turimam video su žaliu telefono ekranu.

Be naršyklės: `python3 popout.py NUOTRAUKA.png OUT.png [--video OUT.mp4]`.
