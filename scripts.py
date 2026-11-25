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
    ],
    "uzkulisiai": [
        ["Norite pamatyti, kaip viskas atrodo iš vidaus?", "{Kur} vyksta daugiau, nei matote.",
         "Šiandien rodome: {t}.", "Kiekviena smulkmena turi reikšmę.", "Štai kodėl rezultatas džiugina.",
         "Sekite mus – parodysime dar daugiau!"],
        ["Viena diena su mūsų komanda.", "Rytas prasideda nuo pasiruošimo.", "Tada – {t}.",
         "Dirbame su meile ir dėmesiu detalėms.", "Ar norėtumėte užsukti? Parašykite!"],
        ["Ko dažniausiai nepamatote?", "Užkulisiai: {t}.", "Daug darbo lieka už kadro.",
         "Bet būtent jis lemia kokybę.", "Pamėgkite, jei norite daugiau tokių video!"],
    ],
    "istorija": [
        ["Pas mus atėjo klientė su vienu klausimu.", "Jai rūpėjo: {t}.", "Kartu radome geriausią sprendimą.",
         "Rezultatas pranoko lūkesčius.", "Ačiū už pasitikėjimą!", "Norite tokio paties rezultato? Rašykite!"],
        ["Prieš ir po – skirtumas akivaizdus.", "Kliento noras buvo aiškus: {t}.",
         "{Kur} viską atlikome kruopščiai ir laiku.", "Džiaugiamės kiekvienu laimingu klientu.",
         "Jūsų istorija gali būti kita – susisiekite!"],
        ["Ką sako mūsų klientai?", "„Pagaliau radau tuos, kuriais galiu pasitikėti.“", "Tema buvo {t}.",
         "Tokie žodžiai motyvuoja dirbti dar geriau.", "Išbandykite ir jūs!"],
    ],
    "klausimas": [
        ["Dažniausiai mūsų klausiate apie tai.", "Klausimas: {t}?", "Trumpas atsakymas – taip, tai įmanoma.",
         "Svarbiausia – tinkamai pasiruošti ir pasirinkti specialistą.", "Turite kitą klausimą? Rašykite komentare!"],
        ["Atsakome į jūsų klausimą!", "{T} – kiek tai trunka ir kainuoja?",
         "Viskas priklauso nuo jūsų poreikių, bet pradėti galima jau šiandien.",
         "Pirmoji konsultacija padės viską aiškiai suplanuoti.", "Parašykite mums – atsakysime greitai!"],
        ["Mitas ar tiesa?", "Sakoma, kad {t} – sudėtinga.", "Iš tikrųjų viskas paprasčiau, nei atrodo.",
         "Su patyrusiu specialistu – greita ir be streso.", "Sekite mus ir sužinokite daugiau!"],
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


def template_variants(sector, goal, topic, seconds=30, n=3, offset=0):
    sec = SECTORS.get(sector, SECTORS["kita"])
    topic = topic.strip() or sec[2]
    tpls = TEMPLATES.get(goal, TEMPLATES["pristatymas"])
    out = []
    rnd = random.Random(f"{sector}|{goal}|{topic}|{offset}")
    pool = sec[3][:]
    for k in range(min(n, len(tpls))):
        lines = _fill(tpls[(offset + k) % len(tpls)], topic, sec[1])
        extra = EXTRA.get(goal, [])[:]
        rnd.shuffle(extra)
        while extra and sum(len(x.split()) for x in lines) < seconds * 2.3 * 0.8:
            lines.insert(len(lines) - 1, extra.pop())
        lines = _fit(lines, seconds)
        text = " ".join(lines)
        rnd.shuffle(pool)
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
        {"topic": topic or sec[2], "avoid_these_hooks": list(avoid)[:9]})
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
