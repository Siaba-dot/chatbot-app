"""Automatinis video montažas: iškerpa tylą/pauzes, sutvarko formatą, garsą
ir (pasirinktinai) uždeda modernius animuotus titrus.
Viskas veikia vietoje su ffmpeg – be API ir be interneto.

Naudojama iš Streamlit puslapio (pages/1_Video_montazas.py), bet galima
paleisti ir iš komandinės eilutės:

  python3 video_editor.py IN.mp4 OUT.mp4 --format 9:16 --subtitles tekstas.txt
"""
import json
import os
import re
import subprocess
import tempfile

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_NAME = "Montserrat Black"

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
    return {"width": w, "height": h, "fps": fps,
            "duration": float(j["format"]["duration"]),
            "has_audio": any(s["codec_type"] == "audio" for s in j["streams"])}


def detect_silences(path, noise_db=-35, min_silence=0.5):
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", path, "-map", "0:a:0",
         "-af", f"silencedetect=n={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return [(max(0.0, s), ends[i] if i < len(ends) else None) for i, s in enumerate(starts)]


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


# ---------- Titrai ----------

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
    """Išdėlioja įvesto teksto žodžius per kalbos intervalus pagal skiemenų skaičių.

    Veikia be jokio kalbos atpažinimo modelio ar interneto: laikai apytiksliai,
    bet pauzės tarp sakinių sutampa su tikromis kalbos pauzėmis.
    """
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


# ---------- Montažas ----------

def _out_size(w, h, ratio, max_side=1920):
    if ratio:
        if w / h > ratio:
            w = h * ratio
        else:
            h = w / ratio
    k = min(1.0, max_side / max(w, h))
    return int(w * k) // 2 * 2, int(h * k) // 2 * 2


def _filter_path(p):
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render(path, out_path, keep, info, fmt="original", loudnorm=True, fades=True,
           ass_file=None, progress=None):
    w, h = info["width"], info["height"]
    ratio = FORMATS.get(fmt)
    ow, oh = _out_size(w, h, ratio)
    total = sum(b - a for a, b in keep)
    cut = not (len(keep) == 1 and keep[0][0] <= 0.01 and keep[0][1] >= info["duration"] - 0.01)
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep)

    v = [f"fps={info['fps']}"]
    if cut:
        v += [f"select='{sel}'", "setpts=N/FRAME_RATE/TB"]
    if ratio:
        v.append(f"crop='min(iw,ih*{ratio:.6f})':'min(ih,iw/{ratio:.6f})'")
    v += [f"scale={ow}:{oh}", "setsar=1"]
    if fades and total > 2:
        v += ["fade=t=in:st=0:d=0.4", f"fade=t=out:st={total - 0.5:.3f}:d=0.5"]
    if ass_file:
        v.append(f"ass=filename='{_filter_path(ass_file)}':fontsdir='{_filter_path(FONT_DIR)}'")
    graph = "[0:v]" + ",".join(v) + "[v]"

    if info["has_audio"]:
        a = []
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


def auto_edit(path, out_path, fmt="original", remove_silence=True, noise_db=-35, min_silence=0.5,
              padding=0.15, loudnorm=True, fades=True, subtitle_text="", ypos=0.67,
              status=None, progress=None):
    """Visas automatinis montažas vienu kvietimu. Grąžina santrauką (dict)."""
    say = status or (lambda msg: None)
    say("Analizuoju video…")
    info = probe(path)
    keep = [(0.0, info["duration"])]
    if remove_silence and info["has_audio"]:
        say("Ieškau tylos ir pauzių…")
        keep = keep_segments(info["duration"], detect_silences(path, noise_db, min_silence), padding)

    ass_file, n_words = None, 0
    if subtitle_text.strip():
        say("Sulyginu titrus su kalba…")
        if info["has_audio"]:
            speech = keep_segments(info["duration"], detect_silences(path, noise_db, 0.25), 0.0, 0.05)
        else:
            speech = [(0.0, info["duration"])]
        words = align_text(subtitle_text, remap_segments(speech, keep))
        n_words = len(words)
        if words:
            w, h = _out_size(info["width"], info["height"], FORMATS.get(fmt))
            with tempfile.NamedTemporaryFile("w", suffix=".ass", delete=False, encoding="utf-8") as f:
                f.write(build_ass(words, w, h, ypos))
                ass_file = f.name

    say("Montuoju video…")
    try:
        res = render(path, out_path, keep, info, fmt, loudnorm, fades, ass_file, progress)
    finally:
        if ass_file:
            os.unlink(ass_file)
    res.update(original_duration=info["duration"], cuts=len(keep) - 1, words=n_words,
               segments=keep)
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Automatinis video montažas")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--format", default="original", choices=list(FORMATS))
    ap.add_argument("--keep-silence", action="store_true", help="Neiškirpti tylos")
    ap.add_argument("--noise-db", type=float, default=-35)
    ap.add_argument("--min-silence", type=float, default=0.5)
    ap.add_argument("--padding", type=float, default=0.15)
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--no-fades", action="store_true")
    ap.add_argument("--subtitles", metavar="TEXT_FILE", help="Tekstas titrams (ką sakoma video)")
    a = ap.parse_args()
    text = open(a.subtitles, encoding="utf-8").read() if a.subtitles else ""
    r = auto_edit(a.input, a.output, a.format, not a.keep_silence, a.noise_db, a.min_silence,
                  a.padding, not a.no_loudnorm, not a.no_fades, text, status=print)
    print(f"Gatava: {r['original_duration']:.1f}s -> {r['duration']:.1f}s, kirpimų: {r['cuts']}")
