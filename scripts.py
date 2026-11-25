"""✨ Scenarijai pagal verslo sritį: tekstas sufleriui / įgarsinimui ir vaizdų planas (scenos su paieškos žodžiais).

AI (Premium) parašo kelis skirtingus variantus; be AI – variantai sudaromi iš šablonų (veikia visiems).
"""
import random
import re

# raktas: (pavadinimas, kur – vietininkas, numatyta tema, anglų k. vaizdų paieškos žodžiai, muzika)
SECTORS = {
    "grozis": ("💇 Grožis, kirpykla, manikiūras", "mūsų salone", "nauja šukuosena",
               ["hair salon", "hairdresser cutting hair", "makeup artist", "manicure", "woman mirror", "beauty salon"],
               "✨ Prabangus pianinas"),
    "kavine": ("☕ Kavinė, restoranas", "mūsų kavinėje", "naujas sezoninis meniu",
               ["barista coffee", "restaurant food", "chef cooking", "dessert", "cafe interior", "friends eating"],
               "🍸 Lounge"),
    "kepykla": ("🥐 Kepykla, maisto gamyba", "mūsų kepykloje", "šviežiai iškepti pyragai",
                ["bakery bread", "baking dough", "cake decorating", "pastry", "fresh croissant", "oven"],
                "🎸 Akustinė"),
    "nt": ("🏠 Nekilnojamasis turtas", "su mumis", "naujas butas pardavimui",
           ["modern apartment", "house exterior", "living room", "keys door", "kitchen interior", "city aerial"],
           "🎬 Kinematografiška"),
    "sportas": ("💪 Sportas, treneris", "mūsų sporto klube", "efektyvi treniruotė",
                ["gym workout", "running", "fitness training", "stretching", "weights", "sport shoes"],
                "⚡ Energinga"),
    "sveikata": ("🧘 Sveikata, SPA, masažas", "mūsų SPA", "atpalaiduojantis masažas",
                 ["spa massage", "relaxation", "spa candles", "wellness", "meditation", "healthy food"],
                 "🧘 SPA ir ramybė"),
    "rankudarbai": ("🧶 Rankų darbas, e. parduotuvė", "mūsų parduotuvėje", "nauja rankų darbo kolekcija",
                    ["handmade craft", "crafting hands", "packaging box", "online shopping", "gift wrapping",
                     "small business"], "🎸 Akustinė"),
    "renginiai": ("🎉 Renginiai, fotografija", "su mumis", "nepamirštama šventė",
                  ["party celebration", "wedding", "photographer camera", "confetti", "event lights", "dancing"],
                  "🕺 Funk ir disco"),
    "auto": ("🚗 Automobiliai, servisas", "mūsų servise", "automobilio paruošimas žiemai",
             ["car repair", "mechanic", "car wash", "tires", "driving car", "car interior"], "🏎 Phonk"),
    "statyba": ("🔨 Statyba, remontas", "su mūsų komanda", "buto remontas",
                ["construction", "renovation", "painting wall", "tools", "carpenter", "new home interior"],
                "🚀 Motyvuojanti"),
    "mokymai": ("🎓 Mokymai, konsultacijos", "mūsų mokymuose", "nauji mokymai",
                ["laptop work", "office meeting", "teacher", "notebook writing", "online course", "team"],
                "☕ Lo-fi"),
    "turizmas": ("✈ Turizmas, apgyvendinimas", "pas mus", "savaitgalio poilsis",
                 ["travel", "hotel room", "beach", "mountains", "suitcase", "lake nature"], "🌴 Tropical house"),
    "gyvunai": ("🐾 Gyvūnų priežiūra", "mūsų salone", "augintinio kirpimas",
                ["dog grooming", "cute dog", "cat", "pet care", "dog walking", "veterinarian"], "🎸 Akustinė"),
    "kita": ("💼 Kita paslauga", "pas mus", "mūsų paslauga",
             ["small business", "happy customer", "team work", "handshake", "shop", "city"], "🚀 Motyvuojanti"),
}

# Kai tema neįrašyta – kiekvienam variantui parenkama vis kita sričiai būdinga tema (su jai tinkamais vaizdais)
TOPICS = {
    "grozis": [("plaukų kirpimas ir šukuosenos", ["hairdresser cutting hair", "hair salon", "hair styling"]),
               ("plaukų dažymas", ["hair coloring", "hair dye salon", "blonde hair"]),
               ("manikiūras ir nagų dizainas", ["manicure", "nail polish", "nail art"]),
               ("pedikiūras", ["pedicure", "spa feet", "nail salon"]),
               ("makiažas šventei", ["makeup artist", "makeup brush", "woman makeup"]),
               ("antakių ir blakstienų priežiūra", ["eyelash extension", "eyebrows", "beauty face"]),
               ("veido procedūros", ["facial treatment", "skin care", "face mask spa"])],
    "kavine": [("sezoninis meniu", ["restaurant food", "chef cooking", "plating food"]),
               ("aromatinga kava", ["barista coffee", "latte art", "coffee beans"]),
               ("pusryčiai", ["breakfast", "pancakes", "brunch"]),
               ("desertai", ["dessert", "cake slice", "chocolate cake"]),
               ("pietūs darbo dienomis", ["lunch plate", "soup", "salad bowl"]),
               ("jauki vieta susitikimams", ["cafe interior", "friends cafe", "cozy cafe"])],
    "kepykla": [("šviežia duona", ["bakery bread", "bread oven", "sourdough"]),
                ("tortai užsakymui", ["cake decorating", "birthday cake", "wedding cake"]),
                ("croissant'ai ir bandelės", ["croissant", "pastry", "cinnamon roll"]),
                ("sausainiai", ["cookies", "baking cookies", "gingerbread"])],
    "nt": [("butas pardavimui", ["modern apartment", "living room", "apartment interior"]),
           ("namas su sklypu", ["house exterior", "garden house", "family house"]),
           ("nuoma", ["keys door", "apartment keys", "moving boxes"]),
           ("būsto vertinimas", ["real estate agent", "city aerial", "handshake"])],
    "sportas": [("treniruotės pradedantiesiems", ["gym workout", "fitness beginner", "personal trainer"]),
                ("bėgimas", ["running", "jogging park", "running shoes"]),
                ("jėgos treniruotės", ["weights", "dumbbells", "strength training"]),
                ("tempimo pratimai", ["stretching", "yoga", "flexibility"]),
                ("grupinės treniruotės", ["group fitness", "fitness class", "aerobics"])],
    "sveikata": [("masažas", ["spa massage", "back massage", "massage oil"]),
                 ("SPA ritualai", ["spa candles", "spa towels", "relaxation"]),
                 ("kineziterapija", ["physiotherapy", "rehabilitation", "stretching therapy"]),
                 ("joga ir meditacija", ["yoga", "meditation", "calm nature"])],
    "rankudarbai": [("nauja kolekcija", ["handmade craft", "crafting hands", "artisan workshop"]),
                    ("dovanos šventėms", ["gift wrapping", "gift box", "christmas gift"]),
                    ("užsakymų pakavimas", ["packaging box", "online shopping", "parcel"]),
                    ("individualūs užsakymai", ["artisan", "sewing", "pottery"])],
    "renginiai": [("vestuvės", ["wedding", "wedding couple", "wedding rings"]),
                  ("gimtadieniai", ["birthday party", "balloons", "birthday cake candles"]),
                  ("įmonių vakarėliai", ["corporate event", "party celebration", "event lights"]),
                  ("fotosesija", ["photographer camera", "photo shoot", "portrait photography"])],
    "auto": [("padangų keitimas", ["tires", "tire change", "car wheel"]),
             ("techninė apžiūra ir remontas", ["car repair", "mechanic", "car engine"]),
             ("automobilio plovimas", ["car wash", "car cleaning", "car detailing"]),
             ("kondicionieriaus pildymas", ["car air conditioning", "car interior", "mechanic tools"])],
    "statyba": [("buto remontas", ["renovation", "painting wall", "new home interior"]),
                ("vonios kambario įrengimas", ["bathroom renovation", "tiles", "modern bathroom"]),
                ("stogo darbai", ["roof construction", "roofer", "house roof"]),
                ("baldai pagal užsakymą", ["carpenter", "woodworking", "kitchen furniture"])],
    "mokymai": [("nauji kursai", ["online course", "laptop work", "notebook writing"]),
                ("individualios konsultacijos", ["office meeting", "consultation", "coach"]),
                ("komandos mokymai", ["team", "workshop", "presentation"]),
                ("kalbų pamokos", ["teacher", "learning", "students"])],
    "turizmas": [("savaitgalio poilsis", ["lake nature", "cabin", "weekend getaway"]),
                 ("kelionės į šiltus kraštus", ["beach", "tropical", "airplane"]),
                 ("kalnų žygiai", ["mountains", "hiking", "mountain view"]),
                 ("jaukūs kambariai", ["hotel room", "bedroom", "hotel"])],
    "gyvunai": [("šunų kirpimas", ["dog grooming", "dog bath", "cute dog"]),
                ("kačių priežiūra", ["cat", "cat grooming", "kitten"]),
                ("augintinių maistas", ["pet food", "dog eating", "pet store"]),
                ("šunų dresūra", ["dog training", "dog walking", "puppy"])],
    "kita": [("mūsų paslaugos", ["small business", "happy customer", "team work"]),
             ("kokybė ir patikimumas", ["handshake", "quality", "professional"]),
             ("klientų aptarnavimas", ["customer service", "shop", "smiling staff"])],
}

GOALS = {
    "pristatymas": "Pristatymas – kas mes",
    "akcija": "Akcija / pasiūlymas",
    "patarimas": "Naudingas patarimas",
    "uzkulisiai": "Užkulisiai",
    "istorija": "Kliento istorija",
    "klausimas": "Atsakymas į klausimą",
}

LENGTHS = (15, 30, 60)

# Šablonai be AI: {t} – tema, {kur} – „mūsų salone“. Sakiniai paprasti, kad tiktų bet kuriai temai.
TEMPLATES = {
    "pristatymas": [
        ["Ieškote, kas tikrai išmano savo darbą?", "Tema šiandien: {t}.", "{Kur} kiekvienam skiriame laiko ir dėmesio.",
         "Dirbame kruopščiai, su kokybiškomis priemonėmis.", "Rezultatas, kuriuo norisi pasidalinti.",
         "Užsukite – mielai jus pakalbinsime!"],
        ["Leiskite prisistatyti!", "{Kur} viskas prasideda nuo jūsų poreikių.", "Mūsų stiprybė – {t}.",
         "Mus renkasi tie, kurie vertina kokybę ir šiltą bendravimą.", "Rašykite žinutę ir susitarkime!"],
        ["Trys priežastys, kodėl verta rinktis mus.", "Pirma – {t}.", "Antra – patyrusi ir draugiška komanda.",
         "Trečia – sąžiningos kainos be staigmenų.", "Išbandykite patys – registruokitės jau šiandien!"],
        ["Kas mes tokie?", "Esame komanda, kuri myli savo darbą.", "{Kur} rasite: {t}.",
         "Kiekvieną dieną stengiamės, kad išeitumėte su šypsena.", "Sekite mus ir sužinokite daugiau!"],
        ["Sveiki! Malonu susipažinti.", "{Kur} rasite tai, ko ieškote: {t}.", "Mums svarbu ne tik rezultatas, bet ir jūsų savijauta.", "Kiekvieną kartą stengiamės nustebinti.", "Ateikite susipažinti – kava mūsų!"],
        ["Ką daryti, jei norite geriausio?", "Rinktis tuos, kurie išmano savo darbą.", "Mūsų specializacija – {t}.", "Turime patirties ir daugybę laimingų klientų.", "Užsiregistruokite ir įsitikinkite patys!"],
        ["Šis video – tiems, kurie dar mūsų nepažįsta.", "Esame vietinis verslas, kuriam rūpi kiekvienas klientas.", "Didžiuojamės tuo, ką darome: {t}.", "Kokybė, patikimumas ir šypsena – mūsų pažadas.", "Sekite mus ir būkime pažįstami!"],
        ["Kodėl klientai grįžta pas mus?", "Nes čia jaučiasi laukiami.", "Nes {t} – mūsų kasdienybė.", "Ir nes rezultatas visada atitinka lūkesčius.", "Laukiame ir jūsų!"],
    ],
    "akcija": [
        ["Dėmesio – ypatingas pasiūlymas!", "Tik dabar: {t}.", "Pasiūlymas galioja ribotą laiką.",
         "Nepraleiskite progos sutaupyti.", "Rašykite žinutę ir užsisakykite jau šiandien!"],
        ["Ar žinojote, kad šią savaitę galite gauti daugiau?", "{Kur} dabar: {t}.",
         "Tai puiki proga išbandyti tai, ką seniai planavote.", "Vietų skaičius ribotas.",
         "Spauskite nuorodą ir registruokitės!"],
        ["Turime gerą žinią!", "{T} – dabar dar patraukliau.", "Pakvieskite draugą ir džiaukitės kartu.",
         "Pasiūlymas baigsis greičiau, nei manote.", "Susisiekite su mumis jau dabar!"],
        ["Laukėte progos? Ji atėjo.", "Specialus pasiūlymas: {t}.", "Daugiau naudos už tą pačią kainą.",
         "Galioja tik iki mėnesio pabaigos.", "Užsisakykite žinute arba telefonu!"],
        ["Stop! Šito nepraleiskite.", "{T} – su specialia nuolaida.", "Puiki proga išbandyti mus pirmą kartą.", "Arba grįžti, jei jau esate mūsų klientas.", "Rezervuokite laiką dar šiandien!"],
        ["Savaitės pasiūlymas!", "{Kur} ruošiame staigmeną: {t}.", "Kiekis ribotas, todėl skubėkite.", "Daugiau informacijos – žinute.", "Iki greito pasimatymo!"],
        ["Ieškote dovanos?", "Turime idėją: {t}.", "Tokia dovana tikrai nudžiugins.", "O dabar – ir patrauklesne kaina.", "Užsisakykite, kol galioja pasiūlymas!"],
        ["Paskutinė galimybė!", "Pasiūlymas „{t}“ baigiasi jau greitai.", "Daugelis jau spėjo pasinaudoti.", "Nelikite be jo ir jūs.", "Rašykite mums dabar!"],
    ],
    "patarimas": [
        ["Vienas patarimas, kuris jums sutaupys laiko.", "Tema: {t}.",
         "Dažniausia klaida – atidėlioti ir tikėtis, kad viskas išsispręs savaime.",
         "Geriau pasitarti su specialistu iš anksto.", "Taip išvengsite papildomų išlaidų.",
         "Išsaugokite šį video, kad nepamirštumėte!"],
        ["Ar darote šią klaidą?", "Kalbame apie tai: {t}.", "Daugelis pamiršta paprastą dalyką – reguliarumą.",
         "Mažas žingsnis kiekvieną savaitę duoda didelį rezultatą.", "Parašykite komentare, jei buvo naudinga!"],
        ["Trys greiti patarimai.", "Pirmas – pradėkite nuo paprasčiausio žingsnio.",
         "Antras – rinkitės kokybę, ne pigiausią variantą.", "Trečias – klauskite specialisto, jei abejojate.",
         "Daugiau patarimų apie tai, kas yra {t} – mūsų paskyroje!"],
        ["Specialisto patarimas per 30 sekundžių.", "{T} – nuo ko pradėti?",
         "Pirmiausia įvertinkite, ko iš tiesų reikia.", "Tada pasirinkite patikimą sprendimą.",
         "O jei reikia pagalbos – mes šalia. Sekite mus!"],
        ["Šito jums niekas nepasakys.", "Kalbame apie tai: {t}.", "Pirmas žingsnis – paprastas, bet daugelis jį praleidžia.", "Skirkite tam vos penkias minutes per dieną.", "Rezultatas jus nustebins. Išsaugokite!"],
        ["Mažas triukas, didelis skirtumas.", "{T} – štai ką verta žinoti.", "Nepirkite to, ko nereikia.", "Geriau investuokite į kokybę vieną kartą.", "Daugiau patarimų – sekite mus!"],
        ["Klientai dažnai klausia, kaip pasiekti geresnį rezultatą.", "Atsakymas susijęs su tuo: {t}.", "Svarbu ne kiekis, o reguliarumas.", "Ir, žinoma, tinkamos priemonės.", "Parašykite, jei turite klausimų!"],
        ["Prieš pradėdami, pagalvokite apie tai.", "Tema: {t}.", "Dažnai skubame ir padarome klaidų.", "Geriau viską gerai suplanuoti iš anksto.", "Išsaugokite šį video ateičiai!"],
    ],
    "uzkulisiai": [
        ["Norite pamatyti, kaip viskas atrodo iš vidaus?", "{Kur} vyksta daugiau, nei matote.",
         "Šiandien rodome: {t}.", "Kiekviena smulkmena turi reikšmę.", "Štai kodėl rezultatas džiugina.",
         "Sekite mus – parodysime dar daugiau!"],
        ["Viena diena su mūsų komanda.", "Rytas prasideda nuo pasiruošimo.", "Tada – {t}.",
         "Dirbame su meile ir dėmesiu detalėms.", "Ar norėtumėte užsukti? Parašykite!"],
        ["Ko dažniausiai nepamatote?", "Užkulisiai: {t}.", "Daug darbo lieka už kadro.",
         "Bet būtent jis lemia kokybę.", "Pamėgkite, jei norite daugiau tokių video!"],
        ["Taip atrodo mūsų darbas iš arti.", "Šiandien: {t}.", "Daug kruopštumo ir dar daugiau kantrybės.", "Bet galutinis rezultatas to vertas.", "Patiko? Paspauskite širdelę!"],
        ["Ar žinojote, kiek darbo slypi už vieno rezultato?", "{T} – nuo pradžios iki pabaigos.", "Kiekvienas žingsnis svarbus.", "Ir kiekvienas daromas su meile.", "Sekite – rodysime daugiau!"],
        ["Pakviečiame jus į užkulisius.", "{Kur} kiekviena diena kitokia.", "Šiandien dirbame su tuo: {t}.", "Mėgstame savo darbą ir tai norime parodyti.", "Ką parodyti kitą kartą? Rašykite!"],
    ],
    "istorija": [
        ["Pas mus atėjo klientė su vienu klausimu.", "Jai rūpėjo: {t}.", "Kartu radome geriausią sprendimą.",
         "Rezultatas pranoko lūkesčius.", "Ačiū už pasitikėjimą!", "Norite tokio paties rezultato? Rašykite!"],
        ["Prieš ir po – skirtumas akivaizdus.", "Kliento noras buvo aiškus: {t}.",
         "{Kur} viską atlikome kruopščiai ir laiku.", "Džiaugiamės kiekvienu laimingu klientu.",
         "Jūsų istorija gali būti kita – susisiekite!"],
        ["Ką sako mūsų klientai?", "„Pagaliau radau tuos, kuriais galiu pasitikėti.“", "Tema buvo {t}.",
         "Tokie žodžiai motyvuoja dirbti dar geriau.", "Išbandykite ir jūs!"],
        ["Šią istoriją norisi papasakoti.", "Klientas atėjo su vienu tikslu: {t}.", "Iš pradžių atrodė sudėtinga.", "Bet kartu viską įveikėme.", "Toks rezultatas mus įkvepia. O kokia jūsų istorija?"],
        ["Kai klientas grįžta su šypsena, žinome, kad pavyko.", "Šį kartą tema buvo {t}.", "Viskas atlikta taip, kaip sutarėme.", "Ačiū už gražius žodžius!", "Laukiame ir jūsų!"],
        ["Prieš kelias savaites mums parašė klientė.", "Ji norėjo pokyčių: {t}.", "Pasiūlėme sprendimą, kuris tiko būtent jai.", "Šiandien ji – nuolatinė mūsų klientė.", "Norite ir jūs pokyčių? Rašykite!"],
    ],
    "klausimas": [
        ["Dažniausiai mūsų klausiate apie tai.", "Klausimas: {t}?", "Trumpas atsakymas – taip, tai įmanoma.",
         "Svarbiausia – tinkamai pasiruošti ir pasirinkti specialistą.", "Turite kitą klausimą? Rašykite komentare!"],
        ["Atsakome į jūsų klausimą!", "{T} – kiek tai trunka ir kainuoja?",
         "Viskas priklauso nuo jūsų poreikių, bet pradėti galima jau šiandien.",
         "Pirmoji konsultacija padės viską aiškiai suplanuoti.", "Parašykite mums – atsakysime greitai!"],
        ["Mitas ar tiesa?", "Sakoma, kad {t} – sudėtinga.", "Iš tikrųjų viskas paprasčiau, nei atrodo.",
         "Su patyrusiu specialistu – greita ir be streso.", "Sekite mus ir sužinokite daugiau!"],
        ["Jūs klausiate – mes atsakome.", "{T}: nuo ko pradėti?", "Pirmiausia – pasitarkite su specialistu.", "Tada kartu sudarysime planą.", "Klausimų turite? Rašykite komentaruose!"],
        ["Ar tikrai reikia to bijoti?", "Daugelis abejoja dėl to: {t}.", "Iš tikrųjų viskas paprasčiau.", "Svarbiausia – rinktis patikimus žmones.", "Sekite mus – atsakysime ir į kitus klausimus!"],
        ["Klausimas, kurį girdime kasdien.", "Kiek kainuoja {t}?", "Kaina priklauso nuo jūsų poreikių.", "Bet visada pasiūlome kelis variantus.", "Parašykite – pasakysime tiksliai!"],
    ],
}


# Papildomi sakiniai ilgesniems video (30–60 s) – įterpiami prieš kvietimą veikti
EXTRA = {
    "pristatymas": ["Kiekvienas klientas mums ypatingas.", "Klausome, patariame ir pasiūlome tai, kas jums tinka.",
                    "Naudojame tik patikrintas priemones ir medžiagas.", "Mūsų klientai grįžta ir rekomenduoja mus draugams.",
                    "Laiką galite užsirezervuoti greitai ir patogiai.", "Dirbame ir savaitgaliais."],
    "akcija": ["Tai puiki proga pradžiuginti save ar artimą žmogų.", "Pasiūlymą galite padovanoti ir draugui.",
               "Daugiau informacijos rasite mūsų paskyroje.", "Registruotis galite žinute ar telefonu.",
               "Kokybė lieka tokia pati – tik kaina malonesnė.", "Skubėkite – laisvų laikų lieka vis mažiau."],
    "patarimas": ["Tai užtrunka vos kelias minutes.", "Rezultatą pajusite jau po kelių savaičių.",
                  "Svarbiausia – nuoseklumas.", "Jei abejojate, visada galite pasitarti su mumis.",
                  "Pasidalinkite šiuo patarimu su draugu, kuriam jo reikia.", "Kitame video – dar vienas naudingas patarimas."],
    "uzkulisiai": ["Mūsų komanda kiekvieną dieną mokosi ir tobulėja.", "Mėgstame tai, ką darome, ir tai matosi.",
                   "Kiekvienas darbas – su meile ir kruopštumu.", "Ačiū, kad esate kartu su mumis.",
                   "Parašykite, ką dar norėtumėte pamatyti."],
    "istorija": ["Mums svarbiausia – kad klientas jaustųsi išgirstas.", "Kiekvienas atvejis yra skirtingas.",
                 "Todėl sprendimą visada pritaikome individualiai.", "Tokios akimirkos primena, kodėl mylime savo darbą.",
                 "Ačiū visiems, kurie mumis pasitiki."],
    "klausimas": ["Šį klausimą girdime labai dažnai.", "Atsakymas paprastesnis, nei gali pasirodyti.",
                  "Svarbiausia – nebijoti paklausti.", "Kiekvienam pritaikome geriausią sprendimą.",
                  "Klausimus galite rašyti ir žinute."],
}


def _fill(lines, topic, kur):
    t = topic.strip().rstrip(".!?") or ""
    out = []
    for ln in lines:
        s = ln.replace("{t}", t).replace("{T}", t[:1].upper() + t[1:]).replace("{kur}", kur)
        s = s.replace("{Kur}", kur[:1].upper() + kur[1:])
        out.append(s)
    return out


def _fit(lines, seconds):
    """Pritaiko ilgį: ~2,3 žodžio per sekundę. Kabliukas ir paskutinis kvietimas lieka visada."""
    budget = seconds * 2.3
    if sum(len(x.split()) for x in lines) <= budget or len(lines) <= 3:
        return lines
    keep = [lines[0]]
    body, cta = lines[1:-1], lines[-1]
    used = len(lines[0].split()) + len(cta.split())
    for ln in body:
        if used + len(ln.split()) > budget and len(keep) >= 2:
            break
        keep.append(ln)
        used += len(ln.split())
    return keep + [cta]


def sentences(text):
    parts = re.split(r"(?<=[.!?…])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def scenes_for(text, sector, queries=None):
    """Tekstas -> scenos (sakinys + vaizdo paieškos žodžiai). Per trumpi sakiniai sujungiami."""
    qs = list(queries or [])
    pool = SECTORS.get(sector, SECTORS["kita"])[3]
    out = []
    for s in sentences(text):
        if out and len(out[-1]["text"].split()) < 5:
            out[-1]["text"] += " " + s
            continue
        out.append({"text": s, "query": ""})
    for i, sc in enumerate(out):
        sc["query"] = (qs[i] if i < len(qs) and qs[i] else pool[i % len(pool)])
    return out


def template_variants(sector, goal, topic, seconds=30, n=3, offset=0, avoid=()):
    """Šablonų variantai: kiekvieną kartą atsitiktinai parenkami, ką tik rodyti (avoid) – praleidžiami."""
    sec = SECTORS.get(sector, SECTORS["kita"])
    own = topic.strip()
    tpls = TEMPLATES.get(goal, TEMPLATES["pristatymas"])
    out = []
    rnd = random.Random()
    avoid = set(avoid or ())
    order = list(range(len(tpls)))
    rnd.shuffle(order)
    fresh = [i for i in order if _fill(tpls[i][:1], own or sec[2], sec[1])[0] not in avoid]
    order = fresh + [i for i in order if i not in fresh]
    themes = TOPICS.get(sector) or [(sec[2], [])]
    themes = rnd.sample(themes, len(themes))
    for j, k in enumerate(order[:n]):
        topic, tq = (own, []) if own else themes[j % len(themes)]
        pool = sec[3][:]
        rnd.shuffle(pool)
        pool = tq + [q for q in pool if q not in tq]
        lines = _fill(tpls[k], topic, sec[1])
        extra = EXTRA.get(goal, [])[:]
        rnd.shuffle(extra)
        while extra and sum(len(x.split()) for x in lines) < seconds * 2.3 * 0.8:
            lines.insert(len(lines) - 1, extra.pop())
        lines = _fit(lines, seconds)
        text = " ".join(lines)
        out.append({"title": lines[0], "text": text, "scenes": scenes_for(text, sector, pool)})
    return out


def ai_variants(client, ai_json, sector, goal, topic, seconds=30, n=3, language="Lithuanian", avoid=()):
    sec = SECTORS.get(sector, SECTORS["kita"])
    words = int(seconds * 2.2)
    j = ai_json(client, (
        f"You write scripts for short vertical business videos (Reels/TikTok) in {language} with perfect grammar and "
        f"diacritics. Business area: {sec[0]}. Goal: {GOALS.get(goal, goal)}. Write {n} clearly DIFFERENT variants "
        f"(different hooks, angles and structure), each about {words} words (~{seconds} s spoken): a strong first-line "
        "hook, short concrete spoken sentences, a short call to action at the end. No emojis, no hashtags. "
        "Also split each variant into scenes (one or two sentences each, 3-8 scenes) and give for each scene an "
        "English stock-video search query of 1-3 concrete visual words that illustrates it. "
        "Reply only JSON: {\"variants\": [{\"title\": \"short hook\", \"text\": \"full script\", "
        "\"scenes\": [{\"text\": \"...\", \"query\": \"...\"}]}]}"),
        {"topic": topic or ("(no topic given – choose a DIFFERENT typical service or product of this business area for "
                            "each variant, e.g. " + ", ".join(t for t, _ in TOPICS.get(sector, [])[:6]) + ")"),
         "avoid_these_hooks": list(avoid)[:9]})
    out = []
    for v in (j.get("variants") or [])[:n]:
        text = str(v.get("text") or " ".join(str(s.get("text", "")) for s in v.get("scenes") or [])).strip()
        if not text:
            continue
        scenes = [{"text": str(s.get("text", "")).strip(), "query": str(s.get("query", "")).strip()[:60]}
                  for s in (v.get("scenes") or []) if str(s.get("text", "")).strip()]
        if not scenes:
            scenes = scenes_for(text, sector)
        for i, s in enumerate(scenes):
            s["query"] = s["query"] or sec[3][i % len(sec[3])]
        out.append({"title": str(v.get("title") or sentences(text)[0])[:120], "text": text, "scenes": scenes})
    return out
