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
**Dizainas – „Baltijos gintaras“:** gilus Baltijos nakties mėlynas fonas, šiltas gintaro auksas, logotipas – natūralus
Baltijos gintaro gabalėlis su subtiliu baltišku saulės ženklu viduje (`assets/gintaras.svg`), lietuviškas rombų
ornamentas. Šablonas „Baltijos gintaras“ ir akcentas „Gintaro gradientas“ – numatytieji.

**Išdėstymas:** viršuje – peržiūra ir mygtukai (👁 Viršelis · ▶ Peržiūra · ✨ Kurti) bei rezultatas; žemiau – medžiaga ir
titrų taisymas; visi nustatymai (formatas, stilius, tekstai, garsas, tempas) – šoniniame skydelyje.

**Formatai:** 9:16 (Reels, TikTok, Shorts – 1080×1920), 16:9 (YouTube – 1920×1080), 1:1 ir 4:5 (Instagram įrašai).
Kitokios orientacijos vaizdas dedamas per vidurį su sulietu fonu; teksto dydžiai pritaikomi kadrui.
**Titrų ir kabliuko dydis** reguliuojamas slankikliais (60–150 %).

Prabangi (tamsi su auksu) studija Instagram Reels / TikTok / Shorts vaizdo įrašams – šoniniame meniu **Reels studija**.
Viskas, ką daro automatinis montažas (pauzių kirpimas, triukšmo valymas, titrai), plius:
- **šablonai** (langeliai su peržiūra ant jūsų kadro): „Prabangus auksas“, „Ranka rašytas“ (Great Vibes kaligrafija),
  „Elegantiškas minimalizmas“ (Playfair Display, plona linija, švelnus ryškėjimas), „Ryškus (TikTok stilius)“;
- **titrų stiliai** (langeliai su pavyzdžiu): Modernūs, Elegantiški, Dėžutėje, Ranka rašyti (Dancing Script), Rašomi ranka,
  Minimalūs;
- **aukso ir sidabro gradientas** – metalinis blizgesys „įliejamas“ į kabliuką, kvietimą ir paryškintą titrų žodį;
- **firminiai filtrai** (✦): „Paryžiaus rytas“ (švelnus rožinis pastelinis), „Milano naktis“ (tamsi kino nuotaika),
  „Baltijos auksas“ (šiltas gintarinis) ir efektas **„Auksinis rėmelis“** (dviguba metalinė linija su deimantėliais);
- **🎁 Grafikos efektai** (pasirenkami šoninėje juostoje, viename video studija parenka tinkamiausius 3–4):
  🎞️ kino juosta, 🃏 kortelių vėduoklė, 📸 polaroidų lietus, 🖼️ galerijos tinklelis (visi – su jūsų video kadrais),
  🔲 kadras kadre (video telefone / monitoriuje), 💬 žinutės telefone (klausimas ir atsakymas), ⭐ atsiliepimo kortelė,
  📈 augantis grafikas (+50 %), 🔔 telefono pranešimas, 🔢 skaitiklis (0 → 500 klientų); vietas ir tekstus parenka AI
  arba taisyklės (skaičius – skaitiklis, % – grafikas, klausimas – žinutės…);
- **📱 Nuotraukos skrenda į telefoną** – apačioje išnyra du telefonai, iš vieno išskrenda kortelės su jūsų video
  kadrais, pasisklaido ir sukrenta į kitą (galerija prisipildo); **🎆 Efektų mozaika** – viename video vis kitas efektas
  ties naujais sakiniais: byrančios kaladėlės, glitch, blyksnis, šviesos nutekėjimas, nespalvota akimirka;
  titrų stilius **Kino** (siauras Anton šriftas, svarbiausias žodis didesnis ir metalinis);
- **🎬 Animacijos** (skiltis šoninėje juostoje): **animuoti lipdukai** (kylančios širdelės, žvaigždučių sprogimas,
  konfeti, liepsnelės), **ranka piešti žymėjimai** (apskritimas, rodyklė, pabraukimas „nusipiešia“ ties svarbiausiais
  žodžiais), **iššokančios kortelės** („1. …, 2. …“ kai vardijama), **įžanga** (logotipas ir paskyra įskrenda) ir
  **pabaiga** („AČIŪ!“, logotipas, paskyra). Vietas parenka AI pagal kalbą arba taisyklės pagal žodžius;
  viskas piešiama vektoriškai (libass) – veikia ir Streamlit Cloud; Autopilotas jas įjungia;
- **✨ Autopilotas** – vienas mygtukas „padaryk viską už mane“: atpažįsta kalbą, parenka stilių, titrus, kabliuką,
  efektus, debesėlius ir muziką (su AI raktu – AI pagal turinį, be jo – patikrintas studijos derinys), sukuria
  3 formatus su viršeliais ir aprašymu; parodo, ką parinko, viską galima atšaukti;
- **💡 Ką filmuoti?** – įrašote savo sritį, gaunate 5 Reels idėjas su kabliuku, paruoštu tekstu, kvietimu ir
  patarimu, ką rodyti (su AI raktu – AI, be jo – studijos šablonai); „🎬 Filmuoti su šiuo tekstu“ įrašo kabliuką ir
  kvietimą, atidaro filmavimą su **sufleriu** – tekstas slenka ant kameros vaizdo (🐢/🐇 greitis, A−/A+ dydis);
  be AI rakto tas pats tekstas tampa titrais;
- **Žingsnių juosta** viršuje: ① Medžiaga → ② Stilius → ③ Peržiūra → ④ Kurti, dabartinis žingsnis paryškintas, ir
  „🎁 Pabaigoje gausite“: 3 video formatai, viršelis, paruoštas aprašymas su grotažymėmis, viskas viename ZIP;
- **„Kurti“ iš karto sukuria 3 formatus** (Reels/TikTok 9:16, YouTube 16:9, Instagram 4:5; galima išjungti
  šoninėje juostoje); **aprašymas su grotažymėmis – visada** (su AI raktu rašo AI, be jo – paprastas iš kabliuko,
  temos, kalbos ir kategorijos grotažymių);
- **Šablonai pagal kategorijas** – 15 šablonų skirtukuose **Verslas · Grožis · Maistas · Kelionės · Šventės**
  (pvz. „Verslo galia“, „Grožio salonas“, „Gardžiai!“, „Nuotykis“, „Vakarėlis“), naujas stambių raidžių stilius;
- **13 titrų stilių**, tarp jų nauji: **Iššokantys** (vienas didelis žodis vienu metu), **Mišrūs** (svarbiausi
  žodžiai dideli, jungiamieji maži, dalis – ranka ir kreivai), **Karaoke**, **Neoniniai**, **Šokinėjantys**,
  **Žymeklis** (žodis spalvotame fone), **Rašomoji mašinėlė**;
- **✦ Debesėliai** – komiksų debesėliai „?“, „!“, „WOW!“, „Hmm…“, „IDĖJA!“, „TOP!“, širdelė iššoka tinkamose
  vietose: Premium – vietas parenka AI pagal kalbą, be jo – pagal ? ir ! tekste;
- **✨ AI režisierius** (Premium) – po peržiūros langu parašote savais žodžiais, pvz. „padaryk prabangiau ir
  energingiau, iki 30 s, sustabdyk ties žodžiu paslaptis“: dirbtinis intelektas pakeičia šabloną, filtrą, efektus,
  titrų stilių, kabliuką, kvietimą, muziką, tempą ir trukmę, parodo, ką pakeitė, ir iškart sukuria peržiūrą;
  greiti mygtukai „Prabangiau“, „Energingiau“, „Ramiau“, „Akimirka svarbiausioje vietoje“; viską galima atšaukti;
- **✨ AI kabliukai** – pagal tai, ką sakote video, pasiūlo 5 kabliukus, įrašomus vienu paspaudimu;
- **✨ AI svarbiausi žodžiai** (Premium) – paryškinamus žodžius parenka dirbtinis intelektas (be rakto – taisyklė);
- **✦ Pabaigos kortelė** – video pabaigoje gintarinė kortelė (3,5 s): kvietimas veikti, nuoroda, **QR kodas** ir paskyra;
  **YouTube pabaigos ekranas** (16:9) – 10 s kortelė su auksinėmis vietomis, ant kurių YouTube Studio uždedami
  paspaudžiami elementai „Video“ ir „Prenumeruoti“. Prie rezultato – nuoroda kopijavimui, ji pridedama ir prie AI
  aprašymo, bei instrukcija, kaip padaryti nuorodą paspaudžiamą kiekvienoje platformoje;
- **💎 Prekės ženklo rinkinys** – logotipas ant kiekvieno video ir viršelio (vieta, dydis, matomumas), sava prekės
  ženklo spalva kaip akcentas ir mygtukas „Išsaugoti mano prekės ženklą“: šablonas, akcentas, filtras, paskyra,
  kvietimas ir logotipas kitą kartą prisijungus nustatomi automatiškai (saugoma `.data/brand/`; Streamlit Cloud
  atnaujinus programą gali tekti išsaugoti iš naujo);
- **📐 Visi formatai vienu paspaudimu** – sukūrus Reels, tas pats montažas, titrai, muzika ir efektai vienu mygtuku
  perkuriami 16:9 (YouTube), 1:1 ir 4:5 formatais (kalbos atpažinimas nekartojamas); visi video su viršeliais – viename ZIP;
- **✦ Svarbiausi žodžiai** – studija pati parenka svarbiausius žodžius (skaičius, prasminius žodžius) ir titruose juos
  padidina bei nuspalvina akcento (ar metalo gradiento) spalva; titrų taisyme žodį galima pažymėti ir patiems: `*žodis*`.
  **Akcentų priartėjimas** – ties tais žodžiais kadras trumpam „įšoka“ arčiau;
- **✦ „Gintaro akimirka“** – firminis efektas: pasirinktoje vietoje (slankiklis „kurioje sekundėje nušvinta“) kadras
  1,6 s švelniai nušvinta šilta gintaro šviesa su švytėjimu ir truputį priartėja; video ir kalba nesustoja;
- **firminiai efektai**: „Aukso blizgesys“ (per metalinį tekstą kas 2,6 s perbėga šviesos ruožas) ir titrų stilius
  „Rašomi ranka“ (frazė rašoma
  rašikliu iš kairės į dešinę, kol ištariama);
- **kabliukas** – antraštė pirmoms sekundėms, **kvietimas veikti** pabaigoje, **@paskyra** viršuje;
- **foninės muzikos biblioteka** (6 kūriniai be autorių teisių apribojimų: Prabangus pianinas, Lounge, Kinematografiška,
  Energinga, Lo-fi, Romantiška – `music/`, sukurta `tools/make_music.py`) arba sava muzika; ji automatiškai patyli, kai kalbama;
- **filtrai langeliuose** – kiekvienas parodomas ant jūsų video kadro (Auksinė valanda, Kino, Teal & Orange, Noir auksas,
  Ryškios, Vintažas, Pastelinės, Sepija, Šaltos, Nespalvotos); akcento spalva (ir titrų paryškinimui);
- **efektai langeliuose** (galima derinti): Lėtas priartėjimas, Švytėjimas, Kino juostos, Kino grūdeliai, Vinjetė,
  Ryškumas, Šviesos blyksnis;
- **trukmės riba** (15 / 30 / 60 / 90 s), **greitis**, **progreso juostelė**;
- **perėjimai tarp įrašų** (langeliai su peržiūra tarp jūsų kadrų): ✦ Lapo vertimas (kadras persiverčia nuo apatinio
  dešiniojo kampo kaip knygos lapas – su lapo nugarėle ir šešėliu), ✦ Kvadratėliai (kadras keičiasi mažais
  kvadratėliais atsitiktine tvarka), Švelnus išnykimas, Per šviesą, Slinkimas, Atsivėrimas;
- **kabliuko ir titrų vieta** – „Kabliuko vieta“ (Viršuje / Aukščiau / Žemiau) ir „Titrų vieta“ (Viduryje / Žemiau /
  Apačioje), kad tekstas neuždengtų veido;
- **įgarsinimas** – šoniniame skydelyje „Garsas“ → „🎙️ Įgarsinimas“: įkeliate savo balsą (garso ar video failą);
  jis sustiprinamas ir išvalomas, skamba visu garsumu, titrai kuriami iš jo, muzika po juo patyli; video klipų garsą
  galima išjungti / patylinti / palikti; jei balsas ilgesnis – paskutinis kadras prailginamas;
- **muzikos takelis** – „III Muzikos takelis“: pagal paruoštą video (iškirptos pauzės, greitis) – kadrų juosta ir muzikos
  juosta; „+ Pridėti“ deda pasirinktą kūrinį padėties linijos vietoje, blokus galima tempti, keisti jų ilgį kraštais,
  kiekvienam – atskiras garsumas; tarp blokų – tyla, bloko pradžia ir pabaiga švelniai įsilieja / užgęsta;
- **kadrų takelis apkarpymui** – kiekvienam video „✂️ Apkarpyti – kadrų takelis“: juosta su kadrų miniatiūromis,
  tempiamos geltonos rankenėlės (pradžia / pabaiga), padėties linija su kadro peržiūra, „✂ Skelti“ (padalinti toje
  vietoje), „🗑 Ištrinti“ (pažymėtą dalį) ir „↺ Iš naujo“; veikia ir liečiant telefone;
- **titrų taisymas** – „Paruošti titrus ir peržiūrą“ parodo titrus lentelėje, klaidas galima pataisyti prieš kuriant
  (balso atpažinimas vyksta tik kartą – taisymas ir peržiūra nieko nekainuoja);
- **greita peržiūra** – visas Reels mažesne kokybe per kelias sekundes, prieš kuriant galutinį video;
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
- Prisijungimo puslapyje rodoma **planų lentelė** su kainomis ir mygtuku „Susisiekti“ (pagal `contact` – el. paštas,
  telefonas arba nuoroda). Kainos keičiamos Secrets:

```toml
[pricing]
basic = "9 €/mėn."
premium = "19 €/mėn."
premium_minutes = 60
note = "7 dienos nemokamai · mokant už metus – 2 mėnesiai dovanų"
show = true    # false – lentelės nerodyti
```

Šriftai – SIL Open Font License (licencijos `fonts/licenses/`).
