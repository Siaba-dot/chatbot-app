"""Automatinis video montažas: iškerpa tylą/pauzes, pašalina foninį triukšmą, sutvarko formatą, garsą
ir (pasirinktinai) uždeda modernius animuotus titrus.
Montažas daromas vietoje su ffmpeg; balso atpažinimui titrams naudojamas OpenAI Whisper.

Naudojama iš Streamlit puslapio (pages/1_Video_montazas.py), bet galima
paleisti ir iš komandinės eilutės:

  python3 video_editor.py IN.mp4 OUT.mp4 --format 9:16 --subtitles [--text tekstas.txt]
"""
import json
import os
import re
import subprocess
import tempfile

import numpy as np

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_NAME = "Montserrat Black"
TRAINING_FONT = "Montserrat SemiBold"
SUBTITLE_STYLES = ("modern", "training")

FORMATS = {"original": None, "9:16": 9 / 16, "1:1": 1.0, "16:9": 16 / 9}


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
    noise, loud = float(np.percentile(lv, 10)), float(np.percentile(lv, 95))
    contrast = loud - noise
    # Riba tarp triukšmo ir kalbos; kai skirtumas mažas – arti triukšmo lygio.
    threshold = noise + (contrast * 0.35 if contrast >= 10 else 3)
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


def group_phrases(words, max_words=4, max_gap=0.6):
    phrases, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w[1] - cur[-1][2] > max_gap):
            phrases.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", w[0]):
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


def build_ass(words, width, height, ypos=0.67):
    """Modernūs titrai: Montserrat Black, DIDŽIOSIOS, balta su juodu kontūru,
    sakomas žodis geltonas, frazė 'iššoka' ir išnyksta."""
    fsize = round(width * 0.085)
    outline = max(3, round(fsize / 12))
    margin = round(width * 0.065)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{FONT_NAME},{fsize},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,"
        f"0,0,0,0,100,100,0,0,1,{outline},{max(2, outline // 2)},5,{margin},{margin},0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    pos = f"\\an5\\pos({width // 2},{round(height * ypos)})"
    phrases = group_phrases(words)
    for pi, ph in enumerate(phrases):
        end = ph[-1][2] + 0.35
        if pi + 1 < len(phrases):
            end = min(end, phrases[pi + 1][0][1])
        texts = [_ass_escape(w[0].upper()) for w in ph]
        for i, (_, s, _) in enumerate(ph):
            a = ph[0][1] if i == 0 else s
            b = ph[i + 1][1] if i + 1 < len(ph) else end
            if b <= a:
                continue
            parts = []
            for j, t in enumerate(texts):
                if j < i:
                    parts.append("{\\1c&HFFFFFF&\\1a&H00&}" + t)
                elif j == i:
                    parts.append("{\\1c&H0AD6FF&\\1a&H00&}" + t)
                else:
                    parts.append("{\\1c&HFFFFFF&\\1a&H70&}" + t)
            fx = pos
            if i == 0:
                fx += "\\fad(100,0)\\fscx82\\fscy82\\t(0,180,\\fscx100\\fscy100)"
            if i == len(ph) - 1:
                fx += "\\fad(0,120)" if i else ""
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
        text = _ass_escape(" ".join(w[0] for w in g))
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


def frame_size(w, h, fmt="original", band=False):
    """Galutinis kadro dydis ir mokymų titrų juostos aukštis: (plotis, aukštis, juosta).
    Fiksuotame formate juosta įsiterpia į kadrą (vaizdas sumažinamas), originaliame – pridedama apačioje."""
    ow, oh = _out_size(w, h, FORMATS.get(fmt))
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
           ass_file=None, progress=None, denoise=False, analysis=None, band=False):
    w, h = info["width"], info["height"]
    ratio = FORMATS.get(fmt)
    ow, oh, bh = frame_size(w, h, fmt, band)
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
        a = denoise_filter(analysis and analysis["noise"], analysis and analysis["loud"]) if denoise else []
        if cut:
            a += [f"aselect='{sel}'", "asetpts=N/SR/TB"]
        if loudnorm:
            a.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        a.append("aresample=48000")
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
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-t", f"{total:.3f}", out_path]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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


def concat_clips(paths, out_path, fmt="original", progress=None):
    """Sujungia kelis video į vieną (nurodyta tvarka). Visi įrašai suvienodinami: kadro dydis
    pagal pirmą įrašą (arba pasirinktą formatą), kadrų dažnis, garsas 48 kHz stereo.
    Įrašai be garso gauna tylą, kad garsas ir vaizdas nepasislinktų."""
    infos = [probe(p) for p in paths]
    ratio = FORMATS.get(fmt)
    sizes = [_out_size(i["width"], i["height"], ratio) for i in infos]
    W, H = max(sizes, key=lambda wh: wh[0] * wh[1]) if ratio else sizes[0]
    fps = infos[0]["fps"]
    parts, total = [], 0.0
    for i, (p, inf) in enumerate(zip(paths, infos)):
        d = inf["duration"]
        total += d
        if ratio:  # fiksuotas formatas – užpildom kadrą (kraštai apkarpomi)
            fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        else:  # originalus – kitokios orientacijos įrašai įtalpinami su juodais kraštais
            fit = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
        parts.append(f"[{i}:v]{fit},setsar=1,fps={fps},format=yuv420p,trim=duration={d:.3f},"
                     f"setpts=PTS-STARTPTS[v{i}]")
        if inf["has_audio"] and len(_frame_levels(p)):
            parts.append(f"[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo,apad,"
                         f"atrim=duration={d:.3f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.3f}[a{i}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{i}][a{i}]" for i in range(len(paths))) + \
        f"concat=n={len(paths)}:v=1:a=1[v][a]"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(graph)
        script = f.name
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    for p in paths:
        cmd += ["-i", p]
    cmd += ["-filter_complex_script", script, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
            "-preset", "ultrafast", "-crf", "17", "-c:a", "aac", "-b:a", "192k", out_path]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in proc.stdout:
            m = re.match(r"out_time_us=(\d+)", line)
            if m and progress and total > 0:
                progress(min(1.0, int(m.group(1)) / 1e6 / total))
        err = proc.stderr.read()
        if proc.wait() != 0:
            raise RuntimeError(f"Nepavyko sujungti įrašų:\n{err[-2000:]}")
    finally:
        os.unlink(script)
    return out_path


def auto_edit(path, out_path, fmt="original", remove_silence=True, noise_db=None, min_silence=0.5,
              padding=0.15, loudnorm=True, fades=True, denoise=True, subtitles=False, client=None,
              language=None, subtitle_language="lt", subtitle_text="", subtitle_style="modern",
              ypos=0.67, translate_model=None, status=None, progress=None):
    """Visas automatinis montažas vienu kvietimu. Grąžina santrauką (dict).

    Titrai: jei įraše yra balsas – atpažįstami automatiškai (reikia OpenAI kliento);
    language – kalbama kalba (None = nustatyti automatiškai), subtitle_language – titrų
    kalba (None = kaip kalbama; kitaip išverčiama). Jei balso nėra – naudojamas
    subtitle_text, tolygiai išdėliotas per visą video. subtitle_style: "modern" – animuoti
    titrai vaizdo viduryje, "training" – mokymų titrai juodoje juostoje po vaizdu.
    """
    say = status or (lambda msg: None)
    say("Analizuoju video…")
    info = probe(path)
    status_, an = audio_status(path, info)
    keep = [(0.0, info["duration"])]
    if remove_silence and an is not None:
        say("Ieškau tylos ir pauzių…")
        keep = keep_segments(info["duration"], detect_silences(path, noise_db, min_silence, an), padding)

    ass_file, n_words, sub_mode = None, 0, None
    if subtitles:
        words = []
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
        n_words = len(words)
        if words:
            training = subtitle_style == "training"
            w, h, bh = frame_size(info["width"], info["height"], fmt, training)
            with tempfile.NamedTemporaryFile("w", suffix=".ass", delete=False, encoding="utf-8") as f:
                f.write(build_ass_training(words, w, h, bh) if training else build_ass(words, w, h, ypos))
                ass_file = f.name

    say("Montuoju video…")
    try:
        res = render(path, out_path, keep, info, fmt, loudnorm, fades, ass_file, progress,
                     denoise=denoise and an is not None, analysis=an,
                     band=bool(ass_file) and subtitle_style == "training")
    finally:
        if ass_file:
            os.unlink(ass_file)
    res.update(original_duration=info["duration"], cuts=len(keep) - 1, words=n_words,
               subtitle_mode=sub_mode, segments=keep)
    return res


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
