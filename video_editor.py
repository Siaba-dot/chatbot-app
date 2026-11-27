"""Automatinis video montažas: iškerpa tylą/pauzes, pašalina foninį triukšmą, sutvarko formatą, garsą
ir (pasirinktinai) uždeda modernius animuotus titrus.
Montažas daromas vietoje su ffmpeg; balso atpažinimui titrams naudojamas OpenAI Whisper.

Naudojama iš Streamlit puslapio (pages/1_Video_montazas.py), bet galima
paleisti ir iš komandinės eilutės:

  python3 video_editor.py IN.mp4 OUT.mp4 --format 9:16 --subtitles [--text tekstas.txt]
"""
import json
import math
import os
import re
import subprocess
import threading
import tempfile

import numpy as np

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_NAME = "Montserrat Black"
TRAINING_FONT = "Montserrat SemiBold"
SUBTITLE_STYLES = ("modern", "training")

# Streamlit Cloud turi ~1 GB atminties, o ffmpeg mato visus serverio procesorius ir paleidžia dešimtis gijų
# (kiekviena – su savo kadrų buferiais). Ribojam gijas, kad programa nenulūžtų dėl atminties.
FFMPEG_THREADS = os.environ.get("REELS_FFMPEG_THREADS", "2")


_ACTIVE = threading.local()  # šios gijos paleisti ffmpeg procesai – kad sustabdžius darbą juos būtų galima nutraukti


def popen(cmd, **kw):
    """subprocess.Popen, įsimenant procesą (žr. kill_active)."""
    proc = subprocess.Popen(cmd, **kw)
    procs = getattr(_ACTIVE, "procs", None)
    if procs is None:
        procs = _ACTIVE.procs = []
    procs[:] = [p for p in procs if p.poll() is None] + [proc]
    return proc


def kill_active():
    """Nutraukia visus šios gijos dar veikiančius ffmpeg procesus (naudotojas sustabdė darbą)."""
    for p in getattr(_ACTIVE, "procs", None) or []:
        if p.poll() is None:
            try:
                p.kill()
                p.wait(timeout=5)
            except Exception:
                pass
    _ACTIVE.procs = []


def limit_threads(cmd, threads=None):
    """Prideda gijų ribas ffmpeg komandai: filtrams, kiekvieno įėjimo dekoderiui ir koduotojui."""
    t = threads or FFMPEG_THREADS
    out = [cmd[0], "-filter_threads", t, "-filter_complex_threads", t]
    for i, x in enumerate(cmd[1:-1], 1):
        if x == "-i":
            out += ["-threads", t]
        out.append(x)
        if x == "libx264":  # trumpesnė „žiūra į priekį“ – ~15 % mažiau atminties, kokybė beveik ta pati
            out += ["-x264-params", "rc-lookahead=5:sync-lookahead=0", "-bf", "1"]
    return out + ["-threads", t, cmd[-1]]


STANDARD_SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
FORMATS = {"original": None, "9:16": 9 / 16, "1:1": 1.0, "16:9": 16 / 9, "4:5": 4 / 5}


# ---------- Analizė ----------

def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,avg_frame_rate:stream_side_data=rotation:format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    w, h = v["width"], v["height"]
    rot = next((abs(int(d.get("rotation", 0))) for d in v.get("side_data_list", []) if "rotation" in d), 0)
    if rot in (90, 270):
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    fps = int(num) / int(den) if int(den) else 30
    fps = min(60, max(15, round(fps))) if fps else 30
    dur = j["format"].get("duration")
    if dur in (None, "N/A"):  # pvz. naršyklės WebM įrašai – trukmę sužinom perskaitę failą
        err = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        t = re.findall(r"time=(\d+):(\d+):([\d.]+)", err)
        dur = int(t[-1][0]) * 3600 + int(t[-1][1]) * 60 + float(t[-1][2]) if t else 0
    return {"width": w, "height": h, "fps": fps,
            "duration": float(dur),
            "has_audio": any(s["codec_type"] == "audio" for s in j["streams"])}


FRAME = 0.03  # s – garso analizės langas


def _frame_levels(path):
    """Garsumas (dB) kas FRAME sekundžių. Tuščias masyvas, jei garso nėra arba jo nepavyko perskaityti."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    n = int(16000 * FRAME)
    if len(x) < n:
        return np.array([])
    x = x[:len(x) // n * n].reshape(-1, n)
    return 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-6)


def analyze_audio(path):
    """Išmatuoja foninio triukšmo ir kalbos lygį. Grąžina dict arba None, jei garso nėra."""
    lv = _frame_levels(path)
    if not len(lv):
        return None
    # Skaitmeninės tylos (lygiai nulis) vietos neatspindi fono – jų nevertinam, kitaip fono ūžesys
    # atrodytų kaip kalba.
    real = lv[lv > -100]
    if len(real) < max(3, 0.05 * len(lv)):
        return {"levels": lv, "noise": -120.0, "loud": -120.0, "threshold": -100.0, "speech": False}
    noise, loud = float(np.percentile(real, 10)), float(np.percentile(real, 95))
    zeros = 1 - len(real) / len(lv)
    if loud - noise < 10 and zeros >= 0.05 and loud > -50:
        # Girdimas garsas su visiškos tylos pauzėmis (pvz. nutildytos vietos) – pauzės yra tos tylos vietos.
        noise = -120.0
    contrast = loud - noise
    # Riba tarp triukšmo ir kalbos; kai skirtumas mažas – arti triukšmo lygio.
    threshold = (noise + contrast * 0.35 if contrast >= 10 else noise + 3) if noise > -120 else -100.0
    voiced = float((lv > threshold).sum() * FRAME)
    return {"levels": lv, "noise": noise, "loud": loud, "threshold": threshold,
            "speech": contrast >= 10 and loud > -65 and voiced >= 0.5}


def detect_silences(path, noise_db=None, min_silence=0.5, analysis=None):
    """Tylos intervalai [(pradžia, pabaiga)]. noise_db=None – riba parenkama pagal įrašą."""
    an = analysis or analyze_audio(path)
    if an is None:
        return []
    quiet = an["levels"] <= (an["threshold"] if noise_db is None else noise_db)
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * FRAME >= min_silence:
                out.append((start * FRAME, i * FRAME))
            start = None
    return out


def keep_segments(duration, silences, padding=0.15, min_keep=0.2):
    """Paverčia tylos intervalus į paliekamus intervalus (su nedideliu 'oru' aplink kalbą)."""
    keep, t = [], 0.0
    for s, e in silences:
        e = duration if e is None else e
        if s > t:
            keep.append((t, s))
        t = max(t, e)
    if t < duration:
        keep.append((t, duration))
    padded = [(max(0.0, a - padding), min(duration, b + padding)) for a, b in keep]
    merged = []
    for a, b in padded:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return [(a, b) for a, b in merged if b - a >= min_keep] or [(0.0, duration)]


def audio_status(path, info=None, analysis=None):
    """'none' – nėra garso, 'silent' – garsas yra, bet balso neaptikta, 'speech' – yra balsas.
    Grąžina (būsena, analizė)."""
    info = info or probe(path)
    an = analysis or (analyze_audio(path) if info["has_audio"] else None)
    if an is None:
        return "none", None
    return ("speech" if an["speech"] else "silent"), an


def has_speech(path, info=None):
    return audio_status(path, info)[0] == "speech"


# ---------- Titrai ----------

LANGUAGES = {"lt": "Lithuanian", "en": "English", "ru": "Russian", "pl": "Polish",
             "de": "German", "lv": "Latvian", "uk": "Ukrainian", "fr": "French", "es": "Spanish"}
TRANSLATE_MODELS = ("gpt-4.1-mini", "gpt-4o-mini")


def transcribe(path, client, language=None):
    """Atpažįsta kalbą per OpenAI Whisper (kalba nustatoma automatiškai, jei nenurodyta).

    Grąžina (žodžiai [(žodis, pradžia, pabaiga)], sakiniai [(tekstas, pradžia, pabaiga)],
    atpažinta kalba – pvz. "english").
    """
    with tempfile.TemporaryDirectory() as tmp:
        audio = os.path.join(tmp, "audio.mp3")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vn", "-ac", "1",
                        "-ar", "16000", "-b:a", "48k", audio], check=True)
        kw = {"language": language} if language else {}
        with open(audio, "rb") as f:
            res = client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="verbose_json",
                timestamp_granularities=["word", "segment"], **kw)
    words = [(w.word.strip(), float(w.start), float(w.end)) for w in (res.words or []) if w.word.strip()]
    segments = [(sg.text.strip(), float(sg.start), float(sg.end))
                for sg in (res.segments or []) if sg.text.strip()]
    return words, segments, (getattr(res, "language", "") or "").lower()


def same_language(code, detected):
    detected = (detected or "").lower()
    return detected in (code, LANGUAGES.get(code, "").lower())


def translate_lines(client, lines, target, model=None):
    """Išverčia titrų eilutes į kalbą `target` (kodas, pvz. "lt"), išlaikant eilučių skaičių."""
    lang = LANGUAGES.get(target, target)
    prompt = (f"Translate these video subtitle lines into {lang}. Use natural, grammatically correct "
              f"{lang} with correct diacritics, short enough for subtitles. Use the surrounding lines "
              "as context, but keep exactly one translated line per input line, in the same order. "
              'Reply only with JSON: {"translations": ["...", ...]}')
    models = ([model] if model else []) + [m for m in TRANSLATE_MODELS if m != model]
    out = []
    for i in range(0, len(lines), 40):
        batch = lines[i:i + 40]
        last_err = None
        for m in models:
            try:
                r = client.chat.completions.create(
                    model=m, temperature=0.2, response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": prompt},
                              {"role": "user", "content": json.dumps(batch, ensure_ascii=False)}])
                tr = json.loads(r.choices[0].message.content).get("translations", [])
                break
            except Exception as e:  # modelis nepasiekiamas – bandom kitą
                last_err = e
        else:
            raise RuntimeError(f"Nepavyko išversti titrų: {last_err}")
        if len(tr) != len(batch):  # retas atvejis – verčiam po vieną eilutę
            tr = [translate_lines(client, [line], target, m)[0] for line in batch] if len(batch) > 1 \
                else [" ".join(map(str, tr))]
        out += [str(t) for t in tr]
    return out


def translated_words(segments, translations, words):
    """Išdėlioja išverstus sakinius per tą laiką, kai originale buvo kalbama."""
    out = []
    for (_, a, b), text in zip(segments, translations):
        inside = [w for w in words if a <= (w[1] + w[2]) / 2 <= b]
        if inside:
            a, b = inside[0][1], inside[-1][2]
        out += align_text(text, [(a, max(b, a + 0.3))])
    return out


def remap_words(words, keep):
    """Perkelia žodžių laikus į sumontuoto video laiko ašį; iškirptose vietose esantys žodžiai išmetami."""
    out, offsets, acc = [], [], 0.0
    for a, b in keep:
        offsets.append(acc)
        acc += b - a
    for w, s, e in words:
        mid = (s + e) / 2
        for (a, b), off in zip(keep, offsets):
            if a <= mid <= b:
                out.append((w, off + max(s, a) - a, off + min(e, b) - a))
                break
    return out


def _syllables(word):
    return max(1, len(re.findall(r"[aeiouyąęėįųū]+", word.lower())))


def remap_segments(segs, keep):
    """Perkelia intervalus į sumontuoto video laiko ašį (iškirptos dalys išmetamos)."""
    out, off = [], 0.0
    for a, b in keep:
        for s, e in segs:
            s, e = max(s, a), min(e, b)
            if e - s > 0.05:
                out.append((off + s - a, off + e - a))
        off += b - a
    return out


def align_text(text, speech):
    """Išdėlioja įvesto teksto žodžius per nurodytus intervalus pagal skiemenų skaičių
    (naudojama, kai įraše nėra balso – tada intervalas yra visas video)."""
    words = text.split()
    if not words or not speech:
        return []
    weights = [_syllables(w) + (1.5 if re.search(r"[.!?…,;:]$", w) else 0) for w in words]
    total_speech = sum(e - s for s, e in speech)
    scale = total_speech / sum(weights)

    def at(x):
        for s, e in speech:
            if x <= e - s:
                return s + x
            x -= e - s
        return speech[-1][1]

    out, acc = [], 0.0
    for w, k in zip(words, weights):
        a = at(acc)
        acc += k * scale
        b = at(acc - 1e-6)
        if b < a:  # žodis peršoko į kitą kalbos intervalą
            b = a + _syllables(w) * scale
        out.append((w, a, b))
    return out


KEY_MARK = "*"
# Dažni lietuviški (ir angliški) žodžiai, kurie niekada nebūna „svarbiausi“
_COMMON = set("""ir bet kad kai kaip kur kas jei nes tai tas ta tie tos šis ši šie šios čia ten dar jau
labai tik net gal yra buvo bus būti esu esi esame galima reikia savo mano tavo jūsų mūsų jo jos jų man tau
mums jums jie jos mes jūs aš tu su be per prie nuo iki apie dėl po už ant į iš pas tarp prieš ar arba nei
taip ne nė va štai kiek koks kokia toks tokia viską viskas kažkas niekas kiekvienas visi visos the and for
you that this with are was have just""".split())


def is_key(word):
    """Ar žodis pažymėtas kaip svarbiausias (*žodis*)."""
    return len(word) > 2 and word.startswith(KEY_MARK) and KEY_MARK in word[1:]


def plain(word):
    """Žodis be paryškinimo žymių."""
    return word.replace(KEY_MARK, "")


def plain_text(words):
    return " ".join(plain(w[0]) for w in words)


def mark_key_words(words, every=2.4):
    """Automatiškai pažymi svarbiausius žodžius (*žodis*): skaičius, šauktinius ir ilgus prasminius žodžius –
    daugiausiai po vieną frazėje ir ne dažniau kaip kas `every` s. Jei naudotojas pats pažymėjo
    bent vieną žodį – paliekama jo valia."""
    if any(is_key(w[0]) for w in words):
        return list(words)
    out, last = list(words), -1e9
    pos = 0
    for ph in group_phrases(words):
        best, score = None, 0
        for k, (w, a, b) in enumerate(ph):
            core = re.sub(r"[^\w%€$]", "", w, flags=re.UNICODE)
            if not core or core.lower() in _COMMON:
                continue
            sc = len(core) + (12 if re.search(r"\d", core) else 0) + (3 if w.endswith("!") else 0) \
                + (2 if core.isupper() and len(core) > 1 else 0)
            if sc > score:
                best, score = k, sc
        if best is not None and score >= 7 and ph[best][1] - last >= every:
            w, a, b = ph[best]
            m = re.match(r"^(\W*)(.*?)(\W*)$", w, flags=re.UNICODE)  # skyrybos ženklai lieka už žymių
            out[pos + best] = (f"{m.group(1)}{KEY_MARK}{m.group(2)}{KEY_MARK}{m.group(3)}", a, b)
            last = a
        pos += len(ph)
    return out


def group_phrases(words, max_words=4, max_gap=0.6):
    phrases, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w[1] - cur[-1][2] > max_gap):
            phrases.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?…]\**$", w[0]):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    return phrases


def _ass_time(t):
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_escape(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


# Animuotų titrų išvaizdos (look). Spalvos – ASS BGR be &H.
SUBTITLE_LOOKS = {
    "modern": {"title": "Modernūs", "font": FONT_NAME, "bold": 0, "size": 0.085, "upper": True, "base": "FFFFFF",
               "box": False, "outline": 1 / 12, "shadow": 0.5, "dim": "70", "pop": True, "ypos": None},
    "elegant": {"title": "Elegantiški", "font": "Playfair Display", "bold": -1, "size": 0.078, "upper": False,
                "base": "DFEEF4", "box": False, "outline": 1 / 20, "shadow": 1.2, "dim": "60", "pop": False,
                "ypos": None},
    "box": {"title": "Dėžutėje", "font": FONT_NAME, "bold": 0, "size": 0.068, "upper": True, "base": "FFFFFF",
            "box": True, "outline": 0.28, "shadow": 0, "dim": "50", "pop": True, "ypos": None},
    "script": {"title": "Ranka rašyti", "font": "Dancing Script", "bold": -1, "size": 0.082, "upper": False,
               "base": "FFFFFF", "box": False, "outline": 1 / 18, "shadow": 0.8, "dim": "50", "pop": False,
               "ypos": None},
    "write": {"title": "Rašomi ranka", "font": "Dancing Script", "bold": -1, "size": 0.082, "upper": False,
              "base": "FFFFFF", "box": False, "outline": 1 / 18, "shadow": 0.8, "dim": "00", "pop": False,
              "ypos": None, "write": True},
    "minimal": {"title": "Minimalūs", "font": "Montserrat SemiBold", "bold": 0, "size": 0.056, "upper": False,
                "base": "FFFFFF", "box": False, "outline": 1 / 16, "shadow": 0.4, "dim": "38", "pop": False,
                "ypos": 0.74},
    "cinema": {"title": "Kino", "font": "Anton", "bold": 0, "size": 0.098, "upper": True, "base": "EDEDED",
               "box": False, "outline": 1 / 28, "shadow": 1.6, "dim": "00", "pop": True, "ypos": None},
    # --- dinamiški stiliai (savas išdėstymas: žodžiai matuojami ir dedami po vieną) ---
    "popout": {"title": "Iššokantys", "font": FONT_NAME, "bold": 0, "size": 0.12, "upper": True, "base": "FFFFFF",
               "box": False, "outline": 1 / 10, "shadow": 0.6, "dim": "00", "pop": True, "ypos": None,
               "mode": "popout"},
    "mixed": {"title": "Mišrūs", "font": FONT_NAME, "bold": 0, "size": 0.078, "upper": True, "base": "FFFFFF",
              "box": False, "outline": 1 / 12, "shadow": 0.6, "dim": "00", "pop": True, "ypos": None,
              "mode": "mixed"},
    "trailer": {"title": "Kino anonsas", "font": FONT_NAME, "bold": 0, "size": 0.074, "upper": False,
                "base": "FFFFFF", "box": False, "outline": 1 / 14, "shadow": 0.7, "dim": "00", "pop": False,
                "ypos": None, "mode": "trailer"},
    "oneword": {"title": "Po vieną žodį", "font": "Anton", "bold": 0, "size": 0.15, "upper": True, "base": "FFFFFF",
                "box": False, "outline": 1 / 16, "shadow": 0.9, "dim": "00", "pop": False, "ypos": None,
                "mode": "oneword"},
    "wave": {"title": "Banguojantys", "font": "Anton", "bold": 0, "size": 0.092, "upper": True, "base": "F2F2F2",
             "box": False, "outline": 1 / 22, "shadow": 1.4, "dim": "00", "pop": False, "ypos": None, "mode": "wave"},
    "karaoke": {"title": "Karaoke", "font": FONT_NAME, "bold": 0, "size": 0.075, "upper": True, "base": "FFFFFF",
                "box": False, "outline": 1 / 12, "shadow": 0.5, "dim": "00", "pop": True, "ypos": None,
                "mode": "karaoke"},
    "neon": {"title": "Neoniniai", "font": "Montserrat SemiBold", "bold": 0, "size": 0.075, "upper": False,
             "base": "FFFFFF", "box": False, "outline": 1 / 9, "shadow": 0, "dim": "50", "pop": False,
             "ypos": None, "glow": True},
    "bounce": {"title": "Šokinėjantys", "font": FONT_NAME, "bold": 0, "size": 0.08, "upper": True,
               "base": "FFFFFF", "box": False, "outline": 1 / 12, "shadow": 0.5, "dim": "40", "pop": True,
               "ypos": None, "mode": "bounce"},
    "marker": {"title": "Žymeklis", "font": FONT_NAME, "bold": 0, "size": 0.078, "upper": True, "base": "FFFFFF",
               "box": False, "outline": 1 / 14, "shadow": 0.4, "dim": "00", "pop": True, "ypos": None,
               "mode": "marker"},
    "typewriter": {"title": "Rašomoji mašinėlė", "font": "Montserrat SemiBold", "bold": 0, "size": 0.066,
                   "upper": False, "base": "FFFFFF", "box": False, "outline": 1 / 12, "shadow": 0.6, "dim": "00",
                   "pop": False, "ypos": None, "mode": "typewriter"},
}

# Šriftų failai – žodžių pločiui matuoti (savas išdėstymas)
FONT_FILES = {"Montserrat Black": "Montserrat_900Black.ttf", "Montserrat SemiBold": "Montserrat_600SemiBold.ttf",
              "Dancing Script": "DancingScript_700Bold.ttf", "Playfair Display": "PlayfairDisplay_700Bold.ttf",
              "Playfair Display Italic": "PlayfairDisplay_400Regular_Italic.ttf",
              "Great Vibes": "GreatVibes_400Regular.ttf", "Anton": "Anton_400Regular.ttf"}
# libass ir PIL šrifto dydį supranta skirtingai – pataisos išmatuotos pagal tikrą libass atvaizdą
FONT_WIDTH_FIX = {"Montserrat Black": 0.774, "Montserrat SemiBold": 0.763, "Dancing Script": 0.89,
                  "Playfair Display": 0.93, "Playfair Display Italic": 0.955, "Great Vibes": 0.79,
                  "Anton": 0.873}
_FONT_CACHE = {}


def text_width(font, size, text):
    """Teksto plotis px (libass dydžio vienetais: dydis = šrifto aukštis ascender+descender)."""
    key = (font, round(size))
    if key not in _FONT_CACHE:
        from PIL import ImageFont
        path = os.path.join(FONT_DIR, FONT_FILES.get(font, FONT_FILES["Montserrat Black"]))
        ref = ImageFont.truetype(path, 200)
        a, d = ref.getmetrics()
        _FONT_CACHE[key] = ImageFont.truetype(path, max(4, round(size * 200 / (a + d))))
    return _FONT_CACHE[key].getlength(text) * FONT_WIDTH_FIX.get(font, 0.8)


def _layout(items, width, height, ypos, max_w):
    """Išdėsto žodžius eilutėmis (centruota). items: [{"text", "font", "size"}].
    Grąžina [(x_centras, y_apačia)] kiekvienam žodžiui."""
    rows, cur, cur_w = [], [], 0.0
    for i, it in enumerate(items):
        w = text_width(it["font"], it["size"], it["text"])
        sp = max(text_width(it["font"], it["size"], " ") * 1.6, it["size"] * 0.22)
        it["w"] = w
        if cur and cur_w + sp + w > max_w:
            rows.append(cur)
            cur, cur_w = [], 0.0
        if cur:
            cur_w += sp
        it["x0"] = cur_w
        cur.append(i)
        cur_w += w
    if cur:
        rows.append(cur)
    heights = [max(items[i]["size"] for i in r) * 0.98 for r in rows]
    total = sum(heights)
    y = height * ypos - total / 2
    pos = [None] * len(items)
    for r, h in zip(rows, heights):
        y += h
        last = items[r[-1]]
        row_w = last["x0"] + last["w"]
        left = width / 2 - row_w / 2
        for i in r:
            pos[i] = (round(left + items[i]["x0"] + items[i]["w"] / 2), round(y))
    return pos


def _light(bgr):
    """Ar spalva šviesi (ASS BBGGRR)."""
    b, g, r = (int(bgr[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b > 150


def _mixed_role(w, k, pi):
    """Mišrių titrų žodžio vaidmuo: big (svarbiausias), script (ranka, kreivai), small (jungiamasis), normal."""
    core = re.sub(r"[^\w]", "", plain(w), flags=re.UNICODE)
    if is_key(w):
        return "big"
    if not core or core.lower() in _COMMON or len(core) <= 3:
        return "small"
    return "normal"


def _dynamic_events(L, phrases, width, height, ypos, fsize, outline, shadow, base, highlight, mask):
    """Dinamiški titrų stiliai (iššokantys, mišrūs, karaoke, šokinėjantys, žymeklis, rašomoji mašinėlė)."""
    mode, out = L["mode"], []
    font = L["font"]
    up = (lambda t: t.upper()) if L["upper"] else (lambda t: t)
    max_w = width * 0.84
    ol = 0 if mask else outline
    sh = 0 if mask else max(1, shadow)
    hl = "FFFFFF" if mask else highlight

    def ev(a, b, tags, text, layer=0):
        if b > a + 0.01:
            out.append(f"Dialogue: {layer},{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,{{{tags}}}" + text)

    for pi, ph in enumerate(phrases):
        start = ph[0][1]
        end = ph[-1][2] + 0.35
        if pi + 1 < len(phrases):
            end = min(end, phrases[pi + 1][0][1])
        if end <= start:
            continue
        if mode == "popout":  # vienas didelis žodis vienu metu: įšoka, truputį pasvyra
            for i, (w, a, b) in enumerate(ph):
                b2 = ph[i + 1][1] if i + 1 < len(ph) else end
                key = is_key(w)
                if mask and not key:
                    continue
                col = hl if key else base
                rot = (-3, 2, -2, 3)[(pi + i) % 4]
                size = round(fsize * (1.18 if key else 1.0))
                tags = (f"\\an5\\pos({width // 2},{round(height * ypos)})\\fs{size}\\1c&H{col}&\\bord{ol}"
                        f"\\shad{sh}\\frz{rot}\\fscx45\\fscy45\\t(0,90,\\fscx114\\fscy114)"
                        f"\\t(90,170,\\fscx100\\fscy100)")
                ev(a if i else start, b2, tags, _ass_escape(up(plain(w))))
            continue
        if mode == "oneword":  # po vieną žodį: balta, siaura, didelė; įsiveržia su judesio suliejimu (glitch)
            if mask:
                continue
            for i, (w, a, b) in enumerate(ph):
                b2 = ph[i + 1][1] if i + 1 < len(ph) else end
                jitter = (-14, 10, -8, 12)[(pi + i) % 4]
                word = up(plain(w))
                k = min(1.0, max_w / max(1.0, text_width(font, fsize, word)))  # ilgas žodis – mažinamas, kad tilptų
                f_ = lambda x: round(x * k)  # noqa: E731
                tags = (f"\\an5\\pos({width // 2 + jitter},{round(height * ypos)})\\1c&H{base}&\\bord{ol}\\shad{sh}"
                        f"\\blur9\\fscx{f_(150)}\\fscy{f_(92)}\\alpha&H70&"
                        f"\\t(0,70,\\blur3\\fscx{f_(108)}\\fscy{f_(100)}\\alpha&H10&)"
                        f"\\t(70,130,\\blur0\\fscx{f_(100)}\\fscy{f_(100)}\\alpha&H00&)")
                ev(a if i else start, max(b2, a + 0.14), tags, _ass_escape(word))
            continue
        if mode == "karaoke":  # žodžiai užsipildo akcento spalva, kai ištariami
            parts, t = [], start
            for i, (w, a, b) in enumerate(ph):
                gap = max(0, round((a - t) * 100))
                dur = max(1, round(((ph[i + 1][1] if i + 1 < len(ph) else b) - a) * 100))
                parts.append((f"{{\\k{gap}}}" if gap else "") + f"{{\\kf{dur}}}" + _ass_escape(up(plain(w))))
                t = a + dur / 100
            ev(start, end, f"\\an5\\pos({width // 2},{round(height * ypos)})\\fad(80,100)", " ".join(parts))
            continue
        if mode == "typewriter":  # raidės atsiranda po vieną, lyg spausdinamos
            parts = []
            for i, (w, a, b) in enumerate(ph):
                txt = plain(w)
                span = max(0.08, min(b - a, 0.45))
                for c_i, ch in enumerate(txt):
                    t0 = round((a - start + span * c_i / max(1, len(txt))) * 1000)
                    parts.append(f"{{\\alpha&HFF&\\t({t0},{t0 + 1},\\alpha&H00&)}}" + _ass_escape(ch))
                if i + 1 < len(ph):
                    parts.append(" ")
            if mask:
                continue
            ev(start, end, f"\\an5\\pos({width // 2},{round(height * ypos)})\\fad(0,120)", "".join(parts))
            continue
        # --- išdėstomi žodžiai (mišrūs, šokinėjantys, žymeklis) ---
        items = []
        for i, (w, a, b) in enumerate(ph):
            role = _mixed_role(w, i, pi) if mode == "mixed" else "normal"
            if mode == "trailer":  # pirma frazės pusė – balta stora, antra – pasvirusi serifinė akcento spalva
                role = "normal" if i < (len(ph) + 1) // 2 else "serif"
            if mode == "wave":  # svarbiausias žodis – didesnis
                role = "big" if is_key(w) else "normal"
            if mode == "mixed" and role == "normal" and len(ph) > 1 and (pi + i) % 3 == 1:
                role = "script"  # dalis žodžių – ranka, kreivai
            spec = {"big": (FONT_NAME, 1.55, True), "normal": (FONT_NAME, 1.0, True),
                    "small": ("Playfair Display Italic", 0.78, False), "script": ("Dancing Script", 1.35, False)}
            if mode == "trailer":
                spec = {"normal": (FONT_NAME, 1.0, False), "serif": ("Playfair Display Italic", 1.18, False)}
            if mode == "wave":
                spec = {"normal": ("Anton", 1.0, True), "big": ("Anton", 1.32, True)}
            f, k, upper = spec[role] if mode in ("mixed", "trailer", "wave") else (font, 1.0, L["upper"])
            txt = plain(w).upper() if upper else plain(w)
            items.append({"text": txt, "font": f, "size": fsize * k, "role": role, "a": a, "b": b})
        pos = _layout(items, width, height, ypos, max_w)
        for i, (it, (x, y)) in enumerate(zip(items, pos)):
            a = it["a"] if i else start
            b_spoken = items[i + 1]["a"] if i + 1 < len(items) else end
            fnt = "Playfair Display" if it["font"] == "Playfair Display Italic" else it["font"]
            ital = "\\i1" if it["font"] == "Playfair Display Italic" else ""
            base_tags = (f"\\an2\\pos({x},{y})\\fn{fnt}{ital}\\fs{round(it['size'])}\\bord{ol}\\shad{sh}")
            txt = _ass_escape(it["text"])
            if mode == "wave":  # žodžiai atsiranda po vieną (iš suliejimo) ir visą frazę švelniai banguoja
                if mask and it["role"] != "big":
                    continue
                col = hl if (it["role"] == "big" and L.get("key_color")) else base
                amp = max(3, round(it["size"] * 0.07))
                period, steps = 1.1, 4
                seg = period / steps
                t0, k_ = a, 0
                first = True
                while t0 < end - 0.02:
                    t1 = min(end, t0 + seg)
                    ph0 = 2 * math.pi * ((t0 - start) / period) + i * 0.9
                    ph1 = 2 * math.pi * ((t1 - start) / period) + i * 0.9
                    y0, y1 = round(y + amp * math.sin(ph0)), round(y + amp * math.sin(ph1))
                    if first:  # įsiveržimas: iš apačios, suliejęs ir permatomas
                        y0 = y0 + round(it["size"] * 0.25)
                    tags = (f"\\an2\\move({x},{y0},{x},{y1})\\fn{fnt}\\fs{round(it['size'])}\\bord{ol}\\shad{sh}"
                            f"\\1c&H{col}&\\4a&H60&")
                    if first:
                        tags += "\\blur7\\alpha&H90&\\t(0,140,\\blur0\\alpha&H00&)"
                    ev(t0, t1, tags, txt)
                    first, t0, k_ = False, t1, k_ + 1
                continue
            if mode == "trailer":  # žodis švelniai išryškėja, kai ištariamas, ir lieka iki frazės pabaigos
                serif = it["role"] == "serif"
                if mask and not serif:
                    continue
                col = hl if serif else base
                ev(a, end, base_tags + f"\\1c&H{col}&\\fad(140,0)", txt)
                continue
            if mode == "mixed":  # žodis įšoka, kai ištariamas, ir lieka iki frazės pabaigos
                accent_word = it["role"] in ("big", "script")
                if mask and not accent_word:
                    continue
                col = hl if accent_word else base
                rot = {"script": -7 if (pi + i) % 2 else 6, "big": -2}.get(it["role"], 0)
                tags = (base_tags + f"\\1c&H{col}&\\org({x},{y - round(it['size'] / 2)})\\frz{rot}"
                        "\\fscx40\\fscy40\\t(0,110,\\fscx112\\fscy112)\\t(110,190,\\fscx100\\fscy100)")
                ev(a, end, tags, txt)
            elif mode == "bounce":  # ištariamas žodis pašoka aukštyn ir nusidažo
                jump = round(it["size"] * 0.22)
                if not mask:
                    ev(start, a, base_tags + f"\\1c&H{base}&\\alpha&H{L['dim']}&", txt)
                    ev(b_spoken, end, base_tags + f"\\1c&H{base}&", txt)
                ev(a, b_spoken, (f"\\an2\\move({x},{y},{x},{y - jump},0,90)\\fn{fnt}\\fs{round(it['size'])}"
                                 f"\\bord{ol}\\shad{sh}\\1c&H{hl}&\\fscx100\\fscy100"
                                 "\\t(0,90,\\fscx116\\fscy116)\\t(90,200,\\fscx106\\fscy106)"), txt, 1)
            elif mode == "marker":  # ištariamas žodis – spalvotame žymeklio fone
                if mask:
                    continue
                ev(start, a, base_tags + f"\\1c&H{base}&", txt, 2)
                ev(b_spoken, end, base_tags + f"\\1c&H{base}&", txt, 2)
                pad, h = round(it["size"] * 0.16), round(it["size"] * 0.96)
                bw = round(it["w"] + 2 * pad)
                r = round(h * 0.22)
                box = (f"m {r} 0 l {bw - r} 0 b {bw} 0 {bw} 0 {bw} {r} l {bw} {h - r} b {bw} {h} {bw} {h} {bw - r} {h} "
                       f"l {r} {h} b 0 {h} 0 {h} 0 {h - r} l 0 {r} b 0 0 0 0 {r} 0")
                txt_col = "1A1A1A" if _light(highlight) else base
                ev(a, b_spoken, (f"\\an7\\pos({x - bw // 2},{y - h})\\bord0\\shad0\\1c&H{highlight}&"
                                 f"\\org({x},{y - h // 2})\\frz-2\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)\\p1"),
                   box, 1)
                ev(a, b_spoken, base_tags + f"\\1c&H{txt_col}&\\bord0\\shad0", txt, 3)
    return out


KEY_SCALE = 128  # svarbiausio žodžio dydis, %


def build_ass(words, width, height, ypos=0.67, highlight="0AD6FF", look="modern", mask=False, size=1.0):
    """Animuoti titrai. look: "modern" – Montserrat Black, DIDŽIOSIOS, balta su juodu kontūru, frazė „iššoka“;
    "elegant" – Playfair Display, šampano spalva, švelniai išryškėja; "box" – didelės raidės permatomoje juodoje
    dėžutėje; "script" – ranka rašytas šriftas; "minimal" – ramus, mažesnis šriftas žemiau. Sakomas žodis
    paryškinamas highlight spalva (ASS BGR). mask=True – kaukė gradientui: baltas tik sakomas žodis, be kontūrų."""
    L = SUBTITLE_LOOKS.get(look, SUBTITLE_LOOKS["modern"])
    if L["ypos"] and ypos == 0.67:
        ypos = L["ypos"]
    # Dydis – nuo trumpesnės kraštinės (horizontaliame video tekstas nebūna milžiniškas); size – naudotojo mastelis.
    ref = min(width, height * 0.75)
    fsize = max(12, round(ref * L["size"] * size))
    outline = max(1 if not L["box"] else 4, round(fsize * L["outline"]))
    shadow = round(outline * L["shadow"]) if not L["box"] else 0
    margin = round(width * 0.065)
    base = L["base"]
    if mask:  # tik užpildas – kontūrai, šešėliai ir dėžutė lieka iš įprastų titrų
        base, highlight = "FFFFFF", "FFFFFF"
        style = (f"Style: Default,{L['font']},{fsize},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
                 f"{L['bold']},0,0,0,100,100,0,0,1,0,0,5,{margin},{margin},0,1")
    elif L["box"]:  # BorderStyle 3: OutlineColour – dėžutės spalva
        style = (f"Style: Default,{L['font']},{fsize},&H00{base},&H00{base},&H55000000,&H00000000,"
                 f"{L['bold']},0,0,0,100,100,0,0,3,{outline},0,5,{margin},{margin},0,1")
    elif L.get("glow"):  # neonas: baltas tekstas, švytintis akcento spalvos kontūras
        style = (f"Style: Default,{L['font']},{fsize},&H00{base},&H00{base},&H00{highlight},&H00000000,"
                 f"{L['bold']},0,0,0,100,100,0,0,1,{outline},0,5,{margin},{margin},0,1")
    elif L.get("mode") == "karaoke":  # Primary – jau ištarta (akcentas), Secondary – dar ne (balta)
        style = (f"Style: Default,{L['font']},{fsize},&H00{highlight},&H00{base},&H00000000,&H78000000,"
                 f"{L['bold']},0,0,0,100,100,0,0,1,{outline},{max(1, shadow)},5,{margin},{margin},0,1")
    else:
        oc = "&H00000000" if look != "elegant" else "&H20100A08"
        style = (f"Style: Default,{L['font']},{fsize},&H00{base},&H00{base},{oc},&H78000000,"
                 f"{L['bold']},0,0,0,100,100,0,0,1,{outline},{max(1, shadow)},5,{margin},{margin},0,1")
    if mask and L.get("mode") == "karaoke":
        style = (f"Style: Default,{L['font']},{fsize},&H00FFFFFF,&HFFFFFFFF,&H00000000,&H00000000,"
                 f"{L['bold']},0,0,0,100,100,0,0,1,0,0,5,{margin},{margin},0,1")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style,
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    pos = f"\\an5\\pos({width // 2},{round(height * ypos)})"
    phrases = group_phrases(words, max_words=6) if L.get("mode") == "trailer" else group_phrases(words)
    if L.get("mode") == "trailer":  # vienas žodis eilutėje atrodo prastai – prijungiam prie ankstesnės frazės
        merged = []
        for ph in phrases:
            if merged and len(ph) == 1 and len(merged[-1]) < 7 and not re.search(r"[.!?…]$", merged[-1][-1][0]):
                merged[-1] = merged[-1] + ph
            else:
                merged.append(ph)
        phrases = merged
    if L.get("mode"):
        lines += _dynamic_events(L, phrases, width, height, ypos, fsize, outline, shadow, base, highlight, mask)
        return "\n".join(lines) + "\n"
    if L.get("write"):  # frazė „rašoma“ rašikliu iš kairės į dešinę, kol ji ištariama
        color = "FFFFFF" if mask else highlight
        for pi, ph in enumerate(phrases):
            a, spoken = ph[0][1], ph[-1][2]
            end = spoken + 0.6
            if pi + 1 < len(phrases):
                end = min(end, phrases[pi + 1][0][1])
            if end <= a:
                continue
            text = " ".join(_ass_escape(plain(w[0])) for w in ph)
            # tikras teksto plotis (šriftas pasviręs – su atsarga); netelpantis tekstas laužomas į 2 eilutes
            est = min(width - 2 * margin, text_width(L["font"], fsize, text) * 1.08 + fsize * 0.3)
            x0, x1 = round(width / 2 - est / 2 - fsize * 0.3), round(width / 2 + est / 2 + fsize * 0.4)
            dur = max(0.25, min(spoken, end) - a)
            fx = (f"{pos}\\1c&H{color}&\\clip({x0},0,{x0},{height})"
                  f"\\t(0,{round(dur * 1000)},\\clip({x0},0,{x1},{height}))\\fad(0,150)")
            lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(end)},Default,,0,0,0,,{{{fx}}}" + text)
        return "\n".join(lines) + "\n"
    for pi, ph in enumerate(phrases):
        end = ph[-1][2] + 0.35
        if pi + 1 < len(phrases):
            end = min(end, phrases[pi + 1][0][1])
        texts = [_ass_escape(plain(w[0]).upper() if L["upper"] else plain(w[0])) for w in ph]
        keys = [is_key(w[0]) for w in ph]
        if L.get("glow") and not mask:  # neonas: ištartas žodis ne nusidažo, o užsidega (baltas, ryškus)
            keys = [False] * len(ph)
        for i, (_, s, _) in enumerate(ph):
            a = ph[0][1] if i == 0 else s
            b = ph[i + 1][1] if i + 1 < len(ph) else end
            if b <= a:
                continue
            parts = []
            dur_ms = max(1, round((b - a) * 1000))
            for j, t in enumerate(texts):
                if keys[j]:  # svarbiausias žodis – visada akcento spalva, didesnis; ištariant „iššoka“
                    big = f"\\fscx{KEY_SCALE}\\fscy{KEY_SCALE}"
                    pop = (f"\\fscx{KEY_SCALE + 22}\\fscy{KEY_SCALE + 22}\\t(0,{min(220, dur_ms)},{big})"
                           if j == i else big)
                    col = "\\1a&H00&" if mask else f"\\1c&H{highlight}&\\1a&H00&"
                    parts.append(f"{{{col}{pop}}}" + t + "{\\fscx100\\fscy100}")
                elif mask and j != i:
                    parts.append("{\\1a&HFF&}" + t)
                elif j < i:
                    parts.append(f"{{\\1c&H{base}&\\1a&H00&}}" + t)
                elif j == i:
                    parts.append(f"{{\\1c&H{base if L.get('glow') else highlight}&\\1a&H00&}}" + t)
                else:
                    parts.append(f"{{\\1c&H{base}&\\1a&H{L['dim']}&}}" + t)
            fx = pos + ("\\blur4" if L.get("glow") and not mask else "")
            if i == 0:
                fx += ("\\fad(100,0)\\fscx82\\fscy82\\t(0,180,\\fscx100\\fscy100)" if L["pop"]
                       else "\\fad(160,0)\\blur3\\t(0,220,\\blur0)")
            if i == len(ph) - 1:
                fx += "\\fad(0,120)" if i else ""
            if L.get("glow") and not mask:  # neonas: apačioje sulietas švytėjimas, viršuje – ryškus tekstas
                lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,"
                             f"{{{fx}\\bord{outline * 2}\\blur{max(4, outline * 2)}}}" + " ".join(parts))
                lines.append(f"Dialogue: 1,{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,"
                             f"{{{fx.replace(chr(92) + 'blur4', '')}\\bord{max(1, outline // 3)}}}" + " ".join(parts))
                continue
            lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,{{{fx}}}" + " ".join(parts))
    return "\n".join(lines) + "\n"


def training_band(width, height):
    """Mokymų titrų juostos po vaizdu dydis: (šrifto dydis, juostos aukštis) px."""
    fsize = max(20, round(min(width, height) * 0.06))
    return fsize, int(fsize * 3.6) // 2 * 2  # 2 eilutės + paraštės


def group_lines(words, max_chars=80, max_dur=6.0, max_gap=0.8):
    """Mokymų titrams: ilgesnės frazės (iki 2 eilučių). Eilutė visada baigiasi sakinio pabaigoje,
    ilgi sakiniai skaidomi ties kableliu, o jei jo nėra – ties ilgio riba."""
    out, cur = [], []
    for w in words:
        length = len(" ".join(x[0] for x in cur + [w]))
        if cur and (length > max_chars or w[2] - cur[0][1] > max_dur or w[1] - cur[-1][2] > max_gap):
            out.append(cur)
            cur = []
        cur.append(w)
        text = " ".join(x[0] for x in cur)
        if re.search(r"[.!?…]$", w[0]) or (re.search(r"[,;:–]$", w[0]) and len(text) >= 40):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def build_ass_training(words, width, height, band):
    """Mokymų titrai: įprastas šriftas, be animacijos, juodoje juostoje po vaizdu (vaizdo neuždengia)."""
    fsize, _ = training_band(width, height - band)
    margin = round(width * 0.04)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{TRAINING_FONT},{fsize},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        f"0,0,0,0,100,100,0,0,1,0,0,5,{margin},{margin},0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    pos = f"{{\\an5\\pos({width // 2},{height - band // 2})}}"
    groups = group_lines(words)
    for gi, g in enumerate(groups):
        a = g[0][1]
        b = max(g[-1][2] + 0.5, a + 1.0)
        if gi + 1 < len(groups):
            b = min(b, groups[gi + 1][0][1])
        text = _ass_escape(plain_text(g))
        lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,{pos}{text}")
    return "\n".join(lines) + "\n"


# ---------- Montažas ----------

def _out_size(w, h, ratio, max_side=1920):
    if ratio:
        if w / h > ratio:
            w = h * ratio
        else:
            h = w / ratio
    k = min(1.0, max_side / max(w, h))
    return int(w * k) // 2 * 2, int(h * k) // 2 * 2


def frame_size(w, h, fmt="original", band=False, max_side=1920):
    """Galutinis kadro dydis ir mokymų titrų juostos aukštis: (plotis, aukštis, juosta).
    Fiksuotame formate juosta įsiterpia į kadrą (vaizdas sumažinamas), originaliame – pridedama apačioje."""
    ow, oh = _out_size(w, h, FORMATS.get(fmt), max_side)
    if not band:
        return ow, oh, 0
    b = training_band(ow, oh)[1]
    return (ow, oh, b) if FORMATS.get(fmt) else (ow, oh + b, b)


def _filter_path(p):
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def denoise_filter(noise=None, loud=None):
    """Foninio triukšmo šalinimas pagal išmatuotą fono lygį: nukerpa žemą ūžesį (vėjas, eismas),
    FFT slopinimu sumažina pastovų foną (šnypštimas, ventiliacija), o tarpuose tarp žodžių
    švelniai prislopina likutį (vartai)."""
    noise = -50 if noise is None else noise
    nf = int(max(-80, min(-20, round(noise + 15))))
    f = ["highpass=f=80", f"afftdn=nr=25:nf={nf}:tn=1"]
    if loud is not None and loud - noise >= 10:  # vartai – tik kai kalba aiškiai garsesnė už foną
        thr = max(0.001, min(0.5, 10 ** ((noise + min(8, (loud - noise) * 0.3)) / 20)))
        f.append(f"agate=threshold={thr:.5f}:ratio=2:range=0.25:attack=10:release=250")
    return f


def render(path, out_path, keep, info, fmt="original", loudnorm=True, fades=True,
           ass_file=None, progress=None, denoise=False, analysis=None, band=False, max_side=1920,
           preset="veryfast", crf=20):
    w, h = info["width"], info["height"]
    ratio = FORMATS.get(fmt)
    ow, oh, bh = frame_size(w, h, fmt, band, max_side)
    total = sum(b - a for a, b in keep)
    cut = not (len(keep) == 1 and keep[0][0] <= 0.01 and keep[0][1] >= info["duration"] - 0.01)
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep)

    v = [f"fps={info['fps']}"]
    if cut:
        v += [f"select='{sel}'", "setpts=N/FRAME_RATE/TB"]
    if ratio:
        v.append(f"crop='min(iw,ih*{ratio:.6f})':'min(ih,iw/{ratio:.6f})'")
    if bh and ratio:  # vaizdas sumažinamas, kad po juo tilptų titrų juosta
        v += [f"scale={ow}:{oh - bh}:force_original_aspect_ratio=decrease:force_divisible_by=2",
              f"pad={ow}:{oh}:(ow-iw)/2:({oh - bh}-ih)/2:black"]
    elif bh:  # originalus formatas – juosta pridedama apačioje
        v += [f"scale={ow}:{oh - bh}", f"pad={ow}:{oh}:0:0:black"]
    else:
        v.append(f"scale={ow}:{oh}")
    v.append("setsar=1")
    if fades and total > 2:
        v += ["fade=t=in:st=0:d=0.4", f"fade=t=out:st={total - 0.5:.3f}:d=0.5"]
    if ass_file:
        v.append(f"ass=filename='{_filter_path(ass_file)}':fontsdir='{_filter_path(FONT_DIR)}'")
    graph = "[0:v]" + ",".join(v) + "[v]"

    if info["has_audio"]:
        # Pirmiausia aiškus formatas (48 kHz, stereo) – senesnės ffmpeg versijos kitaip nesusitaria dėl
        # kanalų išdėstymo. Tada negirdimas (~-120 dB) fonas: senesnėse versijose (pvz. 5.1 Streamlit
        # Cloud) afftdn / loudnorm visiškos tylos (lygiai nulio) vietose grąžina NaN, ir AAC nutraukia darbą.
        a = ["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo",
             "aeval=val(ch)+0.000002*(random(0)-0.5):c=stereo"]
        if denoise:
            a += denoise_filter(analysis and analysis["noise"], analysis and analysis["loud"])
        if cut:
            a += [f"aselect='{sel}'", "asetpts=N/SR/TB"]
        if loudnorm:
            a.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        a += ["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
        if fades and total > 2:
            a += ["afade=t=in:st=0:d=0.3", f"afade=t=out:st={total - 0.5:.3f}:d=0.5"]
        graph += ";[0:a:0]" + ",".join(a) + "[a]"

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(graph)
        script = f.name
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
           "-i", path, "-filter_complex_script", script, "-map", "[v]"]
    if info["has_audio"]:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-t", f"{total:.3f}", out_path]
    try:
        proc = popen(limit_threads(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in proc.stdout:
            m = re.match(r"out_time_us=(\d+)", line)
            if m and progress and total > 0:
                progress(min(1.0, int(m.group(1)) / 1e6 / total))
        err = proc.stderr.read()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg klaida:\n{err[-2000:]}")
    finally:
        os.unlink(script)
    return {"duration": total, "width": ow, "height": oh}


IMAGE_DURATION = 3.0  # s – kiek rodoma viena nuotrauka


def is_image(path):
    """Ar failas yra nuotrauka (ne video)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=format_name", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return out == "image2" or out.endswith("_pipe")


# Perėjimai tarp įrašų (ffmpeg xfade). "page" – lapo vertimas (savas perėjimas): įstrižas lenkimas eina nuo
# dešiniojo apatinio kampo į kairę, už jo matosi šviesi lapo nugarėlė, ant kito kadro krenta šešėlis;
# "tiles" – kvadratėliai.
TRANSITIONS = {
    "Be perėjimo": None,
    "Lapo vertimas": "page",
    "Kvadratėliai": "tiles",
    "Švelnus išnykimas": "fade",
    "Per šviesą": "fadewhite",
    "Slinkimas": "smoothleft",
    "Atsivėrimas": "circleopen",
}
TRANSITION_DURATION = 0.8
# Be st()/ld(): xfade skaičiuoja keliomis gijomis, o bendri kintamieji tada „susimaišo“.
PAGE_EXPR = "if(lt((X+0.35*Y),((W*1.13+0.35*H)*P)-(0.13*W)),A,if(lt((X+0.35*Y),((W*1.13+0.35*H)*P)),A*0.2+255*0.8*(0.78+0.22*((X+0.35*Y)-((W*1.13+0.35*H)*P)+(0.13*W))/(0.13*W)),B*(1-0.55*exp(-((X+0.35*Y)-((W*1.13+0.35*H)*P))/(0.05*W)))))"
# Kvadratėliai: kadras keičiasi mažais kvadratėliais atsitiktine tvarka (pseudoatsitiktinis kiekvieno kvadrato laikas).
TILES_EXPR = "if(lt(((sin(floor(X/(W/18))*12.9898+floor(Y/(W/18))*78.233)*43758.5453)-floor((sin(floor(X/(W/18))*12.9898+floor(Y/(W/18))*78.233)*43758.5453))),(1-P)*1.08-0.04),B,A)"


def xfade_filter(transition, duration, offset):
    kind = TRANSITIONS.get(transition, transition)
    if kind in ("page", "tiles"):
        expr = PAGE_EXPR if kind == "page" else TILES_EXPR
        return f"xfade=transition=custom:duration={duration:.3f}:offset={offset:.3f}:expr='{expr}'"
    return f"xfade=transition={kind}:duration={duration:.3f}:offset={offset:.3f}"


def _concat_with_transitions(paths, out_path, fmt, progress, image_duration, segments, transition, td, size, fps,
                             fill=False):
    """Perėjimai dviem žingsniais: kiekvienas įrašas pirma paruošiamas atskirai (vienodas dydis, pastovus kadrų
    dažnis), o tada tarp paruoštų failų daromas xfade. Taip xfade gauna įprastus failus su žinomu kadrų dažniu –
    įvairios ffmpeg versijos kitaip negauna pastovaus kadrų dažnio iš sudėtinės filtrų grandinės."""
    W, H = size
    n = len(paths)
    tmp = tempfile.mkdtemp()
    try:
        parts_paths, lens = [], []
        for k, p in enumerate(paths):
            part = os.path.join(tmp, f"part{k}.mkv")
            concat_clips([p], part, fmt, (lambda x, k=k: progress(0.6 * (k + x) / n)) if progress else None,
                         image_duration, [segments[k] if k < len(segments) else None], size=(W, H), rate=fps,
                         fill=fill)
            parts_paths.append(part)
            lens.append(probe(part)["duration"])
        td = max(0.2, min(td, min(lens) / 2.5))
        g = [f"[{k}:v]fps={fps},format=gbrp[gv{k}]" for k in range(n)]
        g += [f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo[ga{k}]" for k in range(n)]
        cur_v, cur_a, t = "[gv0]", "[ga0]", lens[0]
        spans = [(0.0, lens[0])]
        for k in range(1, n):
            off = t - td
            g.append(f"{cur_v}[gv{k}]{xfade_filter(transition, td, off)}[xv{k}]")
            g.append(f"{cur_a}[ga{k}]acrossfade=d={td:.3f}[xa{k}]")
            cur_v, cur_a = f"[xv{k}]", f"[xa{k}]"
            spans.append((off, off + lens[k]))
            t = off + lens[k]
        g.append(f"{cur_v}format=yuv420p[v]")
        g.append(f"{cur_a}anull[a]")
        script = os.path.join(tmp, "graph.txt")
        with open(script, "w") as f:
            f.write(";".join(g))
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
        for part in parts_paths:
            cmd += ["-r", str(fps), "-i", part]
        cmd += ["-filter_complex_script", script, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "17", "-c:a", "aac", "-b:a", "192k", out_path]
        proc = popen(limit_threads(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in proc.stdout:
            m = re.match(r"out_time_us=(\d+)", line)
            if m and progress and t > 0:
                progress(min(1.0, 0.6 + 0.4 * int(m.group(1)) / 1e6 / t))
        err = proc.stderr.read()
        if proc.wait() != 0:
            raise RuntimeError(f"Nepavyko sujungti įrašų:\n{err[-2000:]}")
    finally:
        for name in os.listdir(tmp):
            os.unlink(os.path.join(tmp, name))
        os.rmdir(tmp)
    return out_path, spans


def concat_clips(paths, out_path, fmt="original", progress=None, image_duration=IMAGE_DURATION, segments=None,
                 transition=None, transition_duration=TRANSITION_DURATION, size=None, rate=None, fill=False):
    """Sujungia kelis video į vieną (nurodyta tvarka). Visi įrašai suvienodinami: kadro dydis
    pagal pirmą įrašą (arba pasirinktą formatą), kadrų dažnis, garsas 48 kHz stereo.
    Įrašai be garso gauna tylą, kad garsas ir vaizdas nepasislinktų. Nuotraukos rodomos
    image_duration sekundžių. segments – kiekvienam įrašui paliekamos dalys [(nuo, iki), ...]
    (None – visas įrašas); taip įrašą galima apkarpyti ar iškirpti jo vidurį.
    fill – kitokios orientacijos įrašas užpildo visą kadrą (kraštai apkarpomi) vietoj sulieto fono.
    Grąžina (kelias, [(pradžia, pabaiga)] – kiekvieno įrašo vieta sujungtame video)."""
    infos = [probe(p) for p in paths]
    images = [is_image(p) for p in paths]
    for inf, img in zip(infos, images):
        if img:
            inf.update(duration=float(image_duration), has_audio=False)
    ratio = FORMATS.get(fmt)
    sizes = [_out_size(i["width"], i["height"], ratio) for i in infos]
    if ratio:  # standartinis platformų dydis (pvz. YouTube 1920×1080, Reels 1080×1920)
        W, H = STANDARD_SIZES.get(fmt) or max(sizes, key=lambda wh: wh[0] * wh[1])
    else:  # kadro forma – pagal pirmą įrašą, raiška – pagal didžiausią (iki 1920)
        W, H = sizes[0]
        k = min(1920, max(max(wh) for wh in sizes)) / max(W, H)
        W, H = int(W * k) // 2 * 2, int(H * k) // 2 * 2
    fps = next((i["fps"] for i, img in zip(infos, images) if not img), 30)
    if size:
        W, H = size
    if rate:
        fps = rate
    segments = list(segments or [None] * len(paths))
    if TRANSITIONS.get(transition, transition) and len(paths) > 1:
        return _concat_with_transitions(paths, out_path, fmt, progress, image_duration, segments, transition,
                                        transition_duration, (W, H), fps, fill)
    # Kiekviena paliekama dalis – atskiras įėjimas (tas pats failas su -ss / -t).
    pieces = []  # (įrašo nr., kelias, nuotrauka?, pradžia, trukmė)
    for k, (p, inf, img) in enumerate(zip(paths, infos, images)):
        segs = segments[k] if k < len(segments) else None
        if img or not segs:
            pieces.append((k, p, img, 0.0, inf["duration"]))
        else:
            for a, b in segs:
                a, b = max(0.0, a), min(inf["duration"], b)
                if b - a >= 0.1:
                    pieces.append((k, p, img, a, b - a))
    parts, total, spans = [], 0.0, [None] * len(paths)
    audio_ok = {}
    for i, (k, p, img, start, d) in enumerate(pieces):
        a0 = spans[k][0] if spans[k] else total
        spans[k] = (a0, total + d)
        total += d
        src_ar = infos[k]["width"] / max(1, infos[k]["height"])
        tail = f"setsar=1,fps={fps},format=yuv420p,trim=duration={d:.3f},setpts=PTS-STARTPTS[v{i}]"
        if ratio and not fill and abs(math.log(src_ar / ratio)) > math.log(1.3):
            # Labai kitokia orientacija (pvz. vertikalus video YouTube'ui): vaizdas per vidurį, o fone –
            # tas pats vaizdas, išplėstas ir sulietas (užuot nukirpus galvą ir kojas).
            bw, bh = max(2, W // 8) // 2 * 2, max(2, H // 8) // 2 * 2
            parts += [f"[{i}:v]split[s{i}a][s{i}b]",
                      f"[s{i}a]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},gblur=sigma=4,"
                      f"eq=brightness=-0.06:saturation=1.1,scale={W}:{H}[bg{i}]",
                      f"[s{i}b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg{i}]",
                      f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2,{tail}"]
        else:
            if ratio:  # fiksuotas formatas – užpildom kadrą (kraštai apkarpomi)
                fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
            else:  # originalus – kitokios orientacijos įrašai įtalpinami su juodais kraštais
                fit = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
            parts.append(f"[{i}:v]{fit},{tail}")
        if p not in audio_ok:
            audio_ok[p] = infos[k]["has_audio"] and len(_frame_levels(p)) > 0
        if audio_ok[p]:
            parts.append(f"[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo,apad,"
                         f"atrim=duration={d:.3f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.3f}[a{i}]")
    spans = [sp or (total, total) for sp in spans]
    graph = ";".join(parts) + ";" + "".join(f"[v{i}][a{i}]" for i in range(len(pieces))) + \
        f"concat=n={len(pieces)}:v=1:a=1[v][a]"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(graph)
        script = f.name
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    for k, p, img, start, d in pieces:
        if img:  # nuotrauka kartojama kaip video
            cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{d:.3f}"]
        elif start > 0 or d < infos[k]["duration"] - 0.01:
            cmd += ["-ss", f"{start:.3f}", "-t", f"{d + 0.1:.3f}"]
        cmd += ["-i", p]
    cmd += ["-filter_complex_script", script, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
            "-preset", "ultrafast", "-crf", "17", "-c:a", "aac", "-b:a", "192k", out_path]
    try:
        proc = popen(limit_threads(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in proc.stdout:
            m = re.match(r"out_time_us=(\d+)", line)
            if m and progress and total > 0:
                progress(min(1.0, int(m.group(1)) / 1e6 / total))
        err = proc.stderr.read()
        if proc.wait() != 0:
            raise RuntimeError(f"Nepavyko sujungti įrašų:\n{err[-2000:]}")
    finally:
        os.unlink(script)
    return out_path, spans


def analyze(path, remove_silence=True, noise_db=None, min_silence=0.5, padding=0.15, subtitles=False,
            client=None, language=None, subtitle_language="lt", subtitle_text="", translate_model=None,
            protect=None, status=None):
    """1-as žingsnis: suranda, ką palikti (tylos kirpimas), ir paruošia titrų žodžius
    [(žodis, pradžia, pabaiga)] jau sumontuoto video laiko skalėje. Rezultatą galima
    peržiūrėti / pataisyti ir perduoti render_edit()."""
    say = status or (lambda msg: None)
    say("Analizuoju video…")
    info = probe(path)
    status_, an = audio_status(path, info)
    keep = [(0.0, info["duration"])]
    # Tylą kerpam tik kai yra balsas: video be balso (vaizdo kadrai, b-roll) paliekamas visas.
    if remove_silence and status_ == "speech":
        say("Ieškau tylos ir pauzių…")
        keep = keep_segments(info["duration"], detect_silences(path, noise_db, min_silence, an), padding)
        if protect:  # įrašai be balso sujungtame video – paliekami visi
            merged = []
            for a, b in sorted(keep + [tuple(x) for x in protect]):
                if merged and a <= merged[-1][1] + 0.01:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], b))
                else:
                    merged.append((a, b))
            keep = merged

    words, sub_mode = [], None
    if subtitles:
        speech = status_ == "speech"
        # Jei girdimas garsas yra, bet balso neaptikome ir teksto neįvesta – vis tiek bandom atpažinti
        # (visiškos tylos Whisper'iui nesiunčiam – jis tada „prigalvoja“ teksto).
        audible = an is not None and an["loud"] > -60
        if client is not None and audible and (speech or not subtitle_text.strip()):
            say("Atpažįstu balsą titrams…")
            words, segments, detected = transcribe(path, client, language)
            sub_mode = "voice"
            if subtitle_language and segments and not same_language(subtitle_language, detected):
                say("Verčiu titrus…")
                tr = translate_lines(client, [t for t, _, _ in segments], subtitle_language,
                                     translate_model)
                words = translated_words(segments, tr, words)
                sub_mode = "translated"
            words = remap_words(words, keep)
        elif subtitle_text.strip():
            say("Dėlioju titrus…")
            segs = [(0.0, info["duration"])]
            if speech:  # balsas yra, bet atpažinti negalima – derinam prie kalbos intervalų
                segs = keep_segments(info["duration"], detect_silences(path, noise_db, 0.25, an), 0.0, 0.05)
            words = align_text(subtitle_text, remap_segments(segs, keep))
            sub_mode = "text"
    return {"info": info, "audio": an, "keep": keep, "words": words, "subtitle_mode": sub_mode}


def media_duration(path):
    """Bet kokio garso / video failo trukmė (s)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def analyze_voice(path, subtitles=True, client=None, language=None, subtitle_language="lt", subtitle_text="",
                  translate_model=None, status=None):
    """Įgarsinimo (atskiro balso failo) titrai: žodžiai [(žodis, pradžia, pabaiga)] balso laiko skalėje.
    Balsas atpažįstamas (OpenAI) arba įvestas tekstas išdėliojamas pagal kalbos intervalus."""
    say = status or (lambda msg: None)
    if not subtitles:
        return [], None
    an = analyze_audio(path)
    dur = media_duration(path)
    audible = an is not None and an["loud"] > -60
    if client is not None and audible and not subtitle_text.strip():
        say("Atpažįstu įgarsinimo balsą titrams…")
        words, segments, detected = transcribe(path, client, language)
        mode = "voice"
        if subtitle_language and segments and not same_language(subtitle_language, detected):
            say("Verčiu titrus…")
            tr = translate_lines(client, [t for t, _, _ in segments], subtitle_language, translate_model)
            words = translated_words(segments, tr, words)
            mode = "translated"
        return words, mode
    if subtitle_text.strip():
        say("Dėlioju titrus pagal įgarsinimą…")
        segs = keep_segments(dur, detect_silences(path, None, 0.25, an), 0.0, 0.05) if an else [(0.0, dur)]
        return align_text(subtitle_text, segs or [(0.0, dur)]), "text"
    return [], None


def edit_lines(words):
    """Titrai redagavimui: sakiniai [(pradžia, pabaiga, tekstas)]."""
    return [(g[0][1], g[-1][2], " ".join(w[0] for w in g)) for g in group_lines(words)]


def apply_line_edits(words, lines):
    """Pataisyti sakiniai -> žodžiai. Nepakeistų sakinių žodžių laikai išlieka tikslūs,
    pakeistų – išdėliojami per to sakinio laiką; tuščias sakinys pašalinamas."""
    groups = group_lines(words)
    out = []
    for i, (a, b, text) in enumerate(lines):
        text = (text or "").strip()
        if not text:
            continue
        g = groups[i] if i < len(groups) else None
        if g and " ".join(w[0] for w in g) == text and abs(g[0][1] - a) < 0.01 and abs(g[-1][2] - b) < 0.01:
            out += g
        else:
            out += align_text(text, [(float(a), max(float(b), float(a) + 0.3))])
    return out


def render_edit(path, out_path, analysis, words=None, fmt="original", loudnorm=True, fades=True,
                denoise=True, subtitle_style="modern", ypos=0.67, highlight="0AD6FF", status=None,
                progress=None, max_side=1920, preset="veryfast", crf=20, subtitle_look="modern", subtitle_size=1.0):
    """2-as žingsnis: sumontuoja video pagal analyze() rezultatą su (galbūt pataisytais) titrais.
    max_side / preset / crf – mažesnė raiška ir greitesnis kodavimas greitai peržiūrai."""
    say = status or (lambda msg: None)
    info, an, keep = analysis["info"], analysis["audio"], analysis["keep"]
    words = analysis["words"] if words is None else words
    ass_file = None
    if words:
        training = subtitle_style == "training"
        w, h, bh = frame_size(info["width"], info["height"], fmt, training, max_side)
        with tempfile.NamedTemporaryFile("w", suffix=".ass", delete=False, encoding="utf-8") as f:
            f.write(build_ass_training(words, w, h, bh) if training
                    else build_ass(words, w, h, ypos, highlight, subtitle_look, size=subtitle_size))
            ass_file = f.name

    say("Montuoju video…")
    try:
        band = bool(ass_file) and subtitle_style == "training"
        # Bandymai nuo pilno garso apdorojimo iki paprasčiausio: senesnės ffmpeg versijos kartais
        # garso filtruose grąžina NaN – tada montuojam be jų, kad video vis tiek būtų sukurtas.
        attempts = [(denoise and an is not None and an["loud"] > -60, loudnorm, fades),
                    (False, False, fades), (False, False, False)]
        for n, (dn, ln, fd) in enumerate(attempts):
            try:
                res = render(path, out_path, keep, info, fmt, ln, fd, ass_file, progress,
                             denoise=dn, analysis=an, band=band, max_side=max_side, preset=preset, crf=crf)
                break
            except RuntimeError as e:
                if "NaN" not in str(e) or n == len(attempts) - 1:
                    raise
                say("Garso apdorojimas nepavyko – montuoju paprasčiau…")
    finally:
        if ass_file:
            os.unlink(ass_file)
    res.update(original_duration=info["duration"], cuts=len(keep) - 1, words=len(words),
               subtitle_mode=analysis["subtitle_mode"], segments=keep, text=plain_text(words))
    return res


def auto_edit(path, out_path, fmt="original", remove_silence=True, noise_db=None, min_silence=0.5,
              padding=0.15, loudnorm=True, fades=True, denoise=True, subtitles=False, client=None,
              language=None, subtitle_language="lt", subtitle_text="", subtitle_style="modern",
              ypos=0.67, translate_model=None, protect=None, status=None, progress=None,
              highlight="0AD6FF"):
    """Visas automatinis montažas vienu kvietimu (analyze + render_edit). Grąžina santrauką (dict).

    Titrai: jei įraše yra balsas – atpažįstami automatiškai (reikia OpenAI kliento);
    language – kalbama kalba (None = nustatyti automatiškai), subtitle_language – titrų
    kalba (None = kaip kalbama; kitaip išverčiama). Jei balso nėra – naudojamas
    subtitle_text, tolygiai išdėliotas per visą video. protect – laiko intervalai, kurių tylos
    kirpimas neliečia (pvz. sujungti įrašai be balso). subtitle_style: "modern" – animuoti
    titrai vaizdo viduryje, "training" – mokymų titrai juodoje juostoje po vaizdu.
    """
    a = analyze(path, remove_silence, noise_db, min_silence, padding, subtitles, client, language,
                subtitle_language, subtitle_text, translate_model, protect, status)
    return render_edit(path, out_path, a, None, fmt, loudnorm, fades, denoise, subtitle_style, ypos, highlight,
                       status, progress)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Automatinis video montažas")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--format", default="original", choices=list(FORMATS))
    ap.add_argument("--keep-silence", action="store_true", help="Neiškirpti tylos")
    ap.add_argument("--noise-db", type=float, default=None, help="Tylos riba (numatytai – automatiškai)")
    ap.add_argument("--no-denoise", action="store_true", help="Nešalinti foninio triukšmo")
    ap.add_argument("--min-silence", type=float, default=0.5)
    ap.add_argument("--padding", type=float, default=0.15)
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--no-fades", action="store_true")
    ap.add_argument("--subtitles", action="store_true",
                    help="Titrai: balsas atpažįstamas per OpenAI (reikia OPENAI_API_KEY)")
    ap.add_argument("--text", metavar="FILE", help="Tekstas titrams, jei įraše nėra balso")
    ap.add_argument("--style", default="modern", choices=SUBTITLE_STYLES,
                    help="Titrų stilius: modern – animuoti, training – mokymų (po vaizdu)")
    ap.add_argument("--language", default=None, help="Kalbama kalba (numatytai – automatiškai)")
    ap.add_argument("--subtitle-language", default="lt", help="Titrų kalba ('orig' – kaip kalbama)")
    a = ap.parse_args()
    text = open(a.text, encoding="utf-8").read() if a.text else ""
    cl = None
    if a.subtitles and os.environ.get("OPENAI_API_KEY"):
        import openai
        cl = openai.OpenAI()
    r = auto_edit(a.input, a.output, a.format, not a.keep_silence, a.noise_db, a.min_silence,
                  a.padding, not a.no_loudnorm, not a.no_fades, not a.no_denoise,
                  a.subtitles or bool(text), cl,
                  a.language, None if a.subtitle_language == "orig" else a.subtitle_language,
                  text, a.style, status=print)
    print(f"Gatava: {r['original_duration']:.1f}s -> {r['duration']:.1f}s, kirpimų: {r['cuts']}")
