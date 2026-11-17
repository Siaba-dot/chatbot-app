"""Reels studija: paruošia jau sumontuotą vertikalų (9:16) video Instagram Reels / TikTok / Shorts.

Ant video_editor.auto_edit rezultato uždedama:
- kabliukas (hook) – didelis pavadinimas pirmas kelias sekundes,
- kvietimas veikti (CTA) paskutinėmis sekundėmis ir paskyros vardas (@vardas),
- foninė muzika, kuri automatiškai patylėja, kai kalbama (ducking),
- spalvų filtras, greitis, trukmės riba ir progreso juostelė.
Taip pat: viršelis (JPG) ir aprašymas su grotažymėmis (OpenAI, jei yra raktas).

Komandinė eilutė:
  python3 reels_studio.py IN.mp4 OUT.mp4 --hook "3 klaidos, kurias daro visi" --music daina.mp3
"""
import json
import os
import re
import subprocess
import tempfile

import video_editor
from video_editor import FONT_DIR, FONT_NAME, TRAINING_FONT, _ass_escape, _ass_time, _filter_path

# Akcento spalvos: pavadinimas -> (RGB hex, teksto spalva ant jos)
ACCENTS = {
    "Auksas": ("E3C16F", "0B0B0C"),
    "Šampanas": ("F1E3C6", "0B0B0C"),
    "Balta": ("FFFFFF", "000000"),
    "Geltona": ("FFD60A", "000000"),
    "Raudona": ("FF3B30", "FFFFFF"),
    "Mėlyna": ("0A84FF", "FFFFFF"),
    "Rožinė": ("FF2D92", "FFFFFF"),
}

SERIF = "Playfair Display"

# Teksto šablonai. elegant – serifinis šriftas be dėžutės su plona linija, box – ryški dėžutė.
TEMPLATES = {
    "Prabangus auksas": {"kind": "elegant", "accent": "Auksas", "color": "Auksinė valanda"},
    "Elegantiškas minimalizmas": {"kind": "elegant", "accent": "Šampanas", "color": "Kino"},
    "Ryškus (TikTok stilius)": {"kind": "box", "accent": "Geltona", "color": "Ryškios"},
}

COLOR_FILTERS = {
    "Natūralios": [],
    "Auksinė valanda": ["colorbalance=rs=0.05:gs=0.01:bs=-0.06:rh=0.06:bh=-0.05",
                        "eq=contrast=1.08:saturation=1.08:gamma=0.98", "vignette=PI/6"],
    "Kino": ["eq=contrast=1.12:saturation=0.85:gamma=0.97", "vignette=PI/5"],
    "Ryškios": ["eq=saturation=1.3:contrast=1.06"],
    "Šaltos": ["colorbalance=rs=-0.06:bs=0.08", "eq=saturation=1.05"],
    "Nespalvotos": ["hue=s=0", "eq=contrast=1.1"],
}

LENGTHS = {"Be ribos": None, "15 s": 15, "30 s": 30, "60 s": 60, "90 s": 90}


def _ass_color(rgb, alpha="00"):
    """RGB hex (FFD60A) -> ASS spalva (&HAABBGGRR)."""
    return f"&H{alpha}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}".upper()


def _ass_header(width, height, styles):
    return [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]


def _rule(cx, y, length, thick, color, start_ms=0):
    """Plona dekoratyvinė linija, kuri „išsitiesia“ iš centro."""
    return (f"{{\\an5\\pos({cx},{y})\\bord0\\shad0\\1c{color}\\fscx0"
            f"\\t({start_ms},{start_ms + 700},0.5,\\fscx100)\\p1}}"
            f"m 0 0 l {length} 0 l {length} {thick} l 0 {thick}{{\\p0}}")


def build_overlay_ass(width, height, duration, hook="", hook_duration=3.0, cta="", cta_duration=2.5,
                      handle="", accent="Auksas", hook_ypos=0.2, template="Prabangus auksas"):
    """Kabliukas pradžioje, kvietimas veikti (CTA) pabaigoje ir @vardas viršuje.
    Šablonas „elegant“ – serifinis šriftas su plona auksine linija ir švelniu ryškėjimu,
    „box“ – didelės raidės spalvotoje dėžutėje, kuri „iššoka“."""
    kind = TEMPLATES.get(template, TEMPLATES["Prabangus auksas"])["kind"]
    bg, fg = ACCENTS.get(accent, ACCENTS["Auksas"])
    acc = _ass_color(bg)
    margin = round(width * 0.09)
    nsize = round(width * 0.03)
    cx = width // 2
    hook, cta = hook.strip(), cta.strip()
    handle = handle.strip()
    if handle and not handle.startswith("@"):
        handle = "@" + handle

    if kind == "box":
        hsize, csize = round(width * 0.074), round(width * 0.07)
        box = max(6, round(hsize * 0.28))
        styles = [
            # BorderStyle 3 – nepermatoma dėžutė už teksto (Outline – dėžutės paraštė)
            f"Style: Hook,{FONT_NAME},{hsize},{_ass_color(fg)},{_ass_color(fg)},{acc},&H64000000,"
            f"0,0,0,0,100,100,0,0,3,{box},0,5,{margin},{margin},0,1",
            f"Style: Cta,{FONT_NAME},{csize},{acc},{acc},&H00000000,&H78000000,"
            f"0,0,0,0,100,100,0,0,1,{max(3, csize // 12)},{max(2, csize // 24)},5,{margin},{margin},0,1",
        ]
    else:
        hsize, csize = round(width * 0.088), round(width * 0.075)
        styles = [
            f"Style: Hook,{SERIF},{hsize},{acc},{acc},&H50000000,&H96000000,"
            f"-1,0,0,0,100,100,1,0,1,{max(1, hsize // 40)},{max(2, hsize // 22)},2,{margin},{margin},0,1",
            f"Style: Cta,{SERIF},{csize},{acc},{acc},&H50000000,&H96000000,"
            f"0,-1,0,0,100,100,1,0,1,{max(1, csize // 40)},{max(2, csize // 22)},2,{margin},{margin},0,1",
        ]
    styles.append(f"Style: Handle,{TRAINING_FONT},{nsize},&H20FFFFFF,&H20FFFFFF,&H78000000,&H00000000,"
                  f"0,0,0,0,100,100,{round(nsize * 0.25)},0,1,{max(1, nsize // 16)},0,5,"
                  f"{margin},{margin},0,1")
    lines = _ass_header(width, height, styles)

    def text(t, upper):
        return _ass_escape(t.upper() if upper else t).replace("\n", "\\N")

    if hook:
        end = min(duration, hook_duration)
        y = round(height * hook_ypos)
        if kind == "box":
            lines.append(
                f"Dialogue: 2,{_ass_time(0)},{_ass_time(end)},Hook,,0,0,0,,"
                f"{{\\an5\\pos({cx},{y})\\fad(80,200)\\fscx70\\fscy70"
                f"\\t(0,220,\\fscx106\\fscy106)\\t(220,320,\\fscx100\\fscy100)}}" + text(hook, True))
        else:
            # Tekstas „išryškėja“ iš sulieto ir lėtai priartėja; po juo išsitiesia plona linija.
            y += round(hsize * 0.9)
            lines.append(
                f"Dialogue: 2,{_ass_time(0)},{_ass_time(end)},Hook,,0,0,0,,"
                f"{{\\an2\\pos({cx},{y})\\fad(450,350)\\blur8\\fscx108\\fscy108"
                f"\\t(0,700,\\blur0)\\t(0,{round(end * 1000)},\\fscx100\\fscy100)}}" + text(hook, False))
            lines.append(f"Dialogue: 1,{_ass_time(0.2)},{_ass_time(end)},Hook,,0,0,0,,{{\\fad(0,350)}}"
                         + _rule(cx, y + round(hsize * 0.45), round(width * 0.22), max(2, width // 400),
                                 acc, 200))
    if cta and duration > cta_duration + 1:
        a = duration - cta_duration
        y = round(height * 0.44)
        if kind == "box":
            lines.append(
                f"Dialogue: 2,{_ass_time(a)},{_ass_time(duration + 1)},Cta,,0,0,0,,"
                f"{{\\an5\\pos({cx},{y})\\fad(150,0)\\fscx80\\fscy80\\t(0,200,\\fscx100\\fscy100)}}"
                + text(cta, True))
        else:
            lines.append(
                f"Dialogue: 2,{_ass_time(a)},{_ass_time(duration + 1)},Cta,,0,0,0,,"
                f"{{\\an2\\pos({cx},{y})\\fad(500,0)\\blur6\\t(0,600,\\blur0)}}" + text(cta, False))
            lines.append(f"Dialogue: 1,{_ass_time(a + 0.2)},{_ass_time(duration + 1)},Cta,,0,0,0,,"
                         + _rule(cx, y + round(csize * 0.45), round(width * 0.16), max(2, width // 400),
                                 acc, 0))
    if handle:
        label = handle.upper() if kind == "elegant" else handle
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration + 1)},Handle,,0,0,0,,"
                     f"{{\\an5\\pos({cx},{round(height * 0.085)})\\fad(600,0)}}" + _ass_escape(label))
    return "\n".join(lines) + "\n"


def _run(cmd, total, progress, what):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and progress and total > 0:
            progress(min(1.0, int(m.group(1)) / 1e6 / total))
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError(f"{what}:\n{err[-2000:]}")


def finish(path, out_path, hook="", hook_duration=3.0, cta="", cta_duration=2.5, handle="",
           accent="Auksas", template="Prabangus auksas", music=None, music_volume=0.25, ducking=True, max_length=None, speed=1.0,
           color="Auksinė valanda", progress_bar="Viršuje", progress=None):
    """Reels apdaila ant sumontuoto video. Grąžina {"duration", "width", "height"}."""
    info = video_editor.probe(path)
    W, H, fps = info["width"], info["height"], info["fps"]
    speed = max(0.5, min(2.0, float(speed or 1.0)))
    duration = info["duration"] / speed
    trimmed = bool(max_length) and duration > max_length + 0.05
    if trimmed:
        duration = float(max_length)

    tmp = tempfile.mkdtemp()
    try:
        ass = os.path.join(tmp, "reels.ass")
        with open(ass, "w", encoding="utf-8") as f:
            f.write(build_overlay_ass(W, H, duration, hook, hook_duration, cta, cta_duration, handle, accent,
                                      template=template))

        v = []
        if abs(speed - 1) > 0.001:
            v.append(f"setpts=PTS/{speed:.4f}")
        v += COLOR_FILTERS.get(color, [])
        v.append(f"ass=filename='{_filter_path(ass)}':fontsdir='{_filter_path(FONT_DIR)}'")
        if trimmed:
            v.append(f"fade=t=out:st={duration - 0.5:.3f}:d=0.5")
        graph = ["[0:v]" + ",".join(v) + "[base]"]
        vout = "[base]"
        if progress_bar in ("Viršuje", "Apačioje"):
            bh = max(6, round(H * 0.006)) // 2 * 2
            y = 0 if progress_bar == "Viršuje" else H - bh
            bg = ACCENTS.get(accent, ACCENTS["Auksas"])[0]
            graph.append(f"color=c=0x{bg}:s={W}x{bh}:r={fps}[bar]")
            graph.append(f"[base][bar]overlay=x='-w+w*t/{duration:.3f}':y={y}:shortest=1[vout]")
            vout = "[vout]"

        inputs = ["-i", path]
        voice = None
        if info["has_audio"]:
            a = ["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
            if abs(speed - 1) > 0.001:
                a.append(f"atempo={speed:.4f}")
            graph.append("[0:a:0]" + ",".join(a) + "[voice]")
            voice = "[voice]"
        aout = voice
        if music:
            inputs = ["-i", path, "-stream_loop", "-1", "-i", music]
            graph.append(f"[1:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                         f"volume={music_volume:.3f},afade=t=in:st=0:d=0.8[music]")
            if voice and ducking:
                graph.append("[voice]asplit=2[v1][v2]")
                graph.append("[music][v2]sidechaincompress=threshold=0.015:ratio=8:attack=30:release=500[duck]")
                graph.append("[v1][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]")
                aout = "[mix]"
            elif voice:
                graph.append("[voice][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]")
                aout = "[mix]"
            else:
                aout = "[music]"
        if aout and (music or trimmed) and duration > 2:
            graph.append(f"{aout}afade=t=out:st={duration - 0.8:.3f}:d=0.8[aend]")
            aout = "[aend]"

        script = os.path.join(tmp, "graph.txt")
        with open(script, "w") as f:
            f.write(";".join(graph))
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
               *inputs, "-filter_complex_script", script, "-map", vout]
        if aout:
            cmd += ["-map", aout, "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
                "-r", str(fps), "-movflags", "+faststart", "-t", f"{duration:.3f}", out_path]
        _run(cmd, duration, progress, "Nepavyko paruošti Reels")
    finally:
        for name in os.listdir(tmp):
            os.unlink(os.path.join(tmp, name))
        os.rmdir(tmp)
    return {"duration": duration, "width": W, "height": H, "trimmed": trimmed}


def make_cover(path, out_path, at=0.5, hook="", accent="Auksas", template="Prabangus auksas",
               handle="", width=1080, height=1920):
    """Viršelis (JPG 1080×1920): kadras iš video (arba nuotrauka) su kabliuko tekstu per vidurį."""
    tmp = tempfile.mkdtemp()
    try:
        vf = [f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}",
              "setsar=1"]
        if hook.strip() or handle.strip():
            ass = os.path.join(tmp, "cover.ass")
            with open(ass, "w", encoding="utf-8") as f:
                f.write(build_overlay_ass(width, height, 10, hook, 10, handle=handle, accent=accent,
                                          hook_ypos=0.42, template=template))
            vf.insert(2, ",".join(COLOR_FILTERS.get(TEMPLATES.get(template, {}).get("color"), []) or ["null"]))
            vf.append(f"ass=filename='{_filter_path(ass)}':fontsdir='{_filter_path(FONT_DIR)}'")
        # Kabliukas „iššoka“ per pirmas 0.3 s – kadras imamas jau po animacijos.
        seek = [] if video_editor.is_image(path) else ["-ss", f"{max(0.0, at):.3f}"]
        vf.insert(0, "setpts=PTS-STARTPTS+5/TB")  # po visų animacijų
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *seek, "-i", path, "-vf", ",".join(vf),
               "-frames:v", "1", "-q:v", "2", out_path]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Nepavyko sukurti viršelio:\n{r.stderr[-1500:]}")
    finally:
        for name in os.listdir(tmp):
            os.unlink(os.path.join(tmp, name))
        os.rmdir(tmp)
    return out_path


def write_caption(client, text="", hook="", topic="", language="lt", model=None):
    """Instagram aprašymas, grotažymės ir kabliukų idėjos per OpenAI.
    Grąžina {"caption": str, "hashtags": [str], "hooks": [str]}."""
    lang = video_editor.LANGUAGES.get(language, language)
    prompt = (f"You are a social media copywriter. Write in {lang} with correct diacritics. "
              "Based on the Reel's spoken text, hook and topic, write: an engaging Instagram Reels "
              "caption (2-4 short lines, 1-3 fitting emojis, ends with a question or call to action); "
              "8-12 relevant hashtags (mix of popular and niche, in the caption language and English); "
              "3 alternative short hooks (max 8 words) for the first seconds of the video. "
              'Reply only with JSON: {"caption": "...", "hashtags": ["#..."], "hooks": ["..."]}')
    user = json.dumps({"spoken_text": text[:4000], "hook": hook, "topic": topic}, ensure_ascii=False)
    models = ([model] if model else []) + [m for m in video_editor.TRANSLATE_MODELS if m != model]
    last = None
    for m in models:
        try:
            r = client.chat.completions.create(
                model=m, temperature=0.7, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user}])
            j = json.loads(r.choices[0].message.content)
            tags = [t if t.startswith("#") else "#" + t
                    for t in (str(x).strip().replace(" ", "") for x in j.get("hashtags", [])) if t]
            return {"caption": str(j.get("caption", "")).strip(), "hashtags": tags,
                    "hooks": [str(h).strip() for h in j.get("hooks", []) if str(h).strip()]}
        except Exception as e:  # modelis nepasiekiamas – bandom kitą
            last = e
    raise RuntimeError(f"Nepavyko sugeneruoti aprašymo: {last}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Reels apdaila sumontuotam 9:16 video")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--hook", default="")
    ap.add_argument("--hook-duration", type=float, default=3.0)
    ap.add_argument("--cta", default="")
    ap.add_argument("--handle", default="")
    ap.add_argument("--accent", default="Auksas", choices=list(ACCENTS))
    ap.add_argument("--template", default="Prabangus auksas", choices=list(TEMPLATES))
    ap.add_argument("--music")
    ap.add_argument("--music-volume", type=float, default=0.25)
    ap.add_argument("--no-ducking", action="store_true")
    ap.add_argument("--max-length", type=float)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--color", default="Auksinė valanda", choices=list(COLOR_FILTERS))
    ap.add_argument("--progress-bar", default="Viršuje", choices=["Viršuje", "Apačioje", "Nėra"])
    ap.add_argument("--cover", metavar="JPG", help="Papildomai sukurti viršelį")
    a = ap.parse_args()
    r = finish(a.input, a.output, a.hook, a.hook_duration, a.cta, 2.5, a.handle, a.accent, a.template, a.music,
               a.music_volume, not a.no_ducking, a.max_length, a.speed, a.color, a.progress_bar)
    if a.cover:
        make_cover(a.input, a.cover, 0.5, a.hook, a.accent, a.template, a.handle)
    print(f"Gatava: {r['duration']:.1f} s, {r['width']}x{r['height']}")
