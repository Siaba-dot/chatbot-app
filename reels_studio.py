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
    "Aukso gradientas": ("D9B24C", "0B0B0C"),
    "Sidabro gradientas": ("C9CBD1", "0B0B0C"),
    "Auksas": ("E3C16F", "0B0B0C"),
    "Šampanas": ("F1E3C6", "0B0B0C"),
    "Balta": ("FFFFFF", "000000"),
    "Geltona": ("FFD60A", "000000"),
    "Raudona": ("FF3B30", "FFFFFF"),
    "Mėlyna": ("0A84FF", "FFFFFF"),
    "Rožinė": ("FF2D92", "FFFFFF"),
}

SERIF = "Playfair Display"
SCRIPT = "Great Vibes"

# Metaliniai gradientai (spalvų taškai nuo raidės viršaus iki apačios): akcento pavadinimas -> [(vieta, RGB)]
GRADIENTS = {
    "Aukso gradientas": [(0.0, "FFF4C8"), (0.28, "F3D67E"), (0.48, "C99A30"), (0.56, "B07F1C"),
                         (0.68, "E9C964"), (0.86, "FBE7A2"), (1.0, "A47A1E")],
    "Sidabro gradientas": [(0.0, "FFFFFF"), (0.28, "E2E4E9"), (0.48, "9A9DA5"), (0.56, "80838C"),
                           (0.68, "CDD0D6"), (0.86, "F5F6F8"), (1.0, "6F727A")],
}

# Teksto šablonai. elegant – serifinis šriftas be dėžutės su plona linija, box – ryški dėžutė.
TEMPLATES = {
    "Prabangus auksas": {"kind": "elegant", "accent": "Aukso gradientas", "color": "Auksinė valanda"},
    "Ranka rašytas": {"kind": "script", "accent": "Aukso gradientas", "color": "Auksinė valanda"},
    "Elegantiškas minimalizmas": {"kind": "elegant", "accent": "Sidabro gradientas", "color": "Kino"},
    "Ryškus (TikTok stilius)": {"kind": "box", "accent": "Geltona", "color": "Ryškios"},
}

COLOR_FILTERS = {
    "Natūralios": [],
    # Firminiai studijos filtrai
    "Paryžiaus rytas": ["curves=r='0/0.10 0.5/0.58 1/1':g='0/0.07 0.5/0.52 1/0.96':b='0/0.11 0.5/0.52 1/0.95'",
                        "eq=saturation=0.8:contrast=0.92:brightness=0.02",
                        "colorbalance=rh=0.07:gh=0.0:bh=0.05:rm=0.03:bm=0.02"],
    "Milano naktis": ["curves=all='0/0 0.25/0.17 0.75/0.83 1/1'",
                      "colorbalance=rs=-0.07:bs=0.08:rh=0.08:gh=0.02:bh=-0.06", "eq=saturation=0.88:gamma=0.95",
                      "vignette=PI/4.5"],
    "Baltijos auksas": ["colorbalance=rs=0.09:gs=0.04:bs=-0.12:rm=0.10:gm=0.04:bm=-0.12:rh=0.07:gh=0.02:bh=-0.10",
                        "curves=all='0/0.03 0.5/0.55 1/0.98'", "eq=saturation=1.18:contrast=1.06",
                        "vignette=PI/6"],
    "Auksinė valanda": ["colorbalance=rs=0.05:gs=0.01:bs=-0.06:rh=0.06:bh=-0.05",
                        "eq=contrast=1.08:saturation=1.08:gamma=0.98", "vignette=PI/6"],
    "Kino": ["eq=contrast=1.12:saturation=0.85:gamma=0.97", "vignette=PI/5"],
    "Teal & Orange": ["colorbalance=rs=-0.08:bs=0.10:rh=0.10:gh=0.03:bh=-0.08",
                      "eq=saturation=1.15:contrast=1.08"],
    "Noir auksas": ["hue=s=0", "eq=contrast=1.2:gamma=0.95", "colorbalance=rm=0.16:gm=0.08:bm=-0.10:rh=0.10:bh=-0.06"],
    "Ryškios": ["eq=saturation=1.3:contrast=1.06"],
    "Vintažas": ["curves=preset=vintage", "eq=saturation=0.9"],
    "Pastelinės": ["eq=saturation=0.72:brightness=0.04:contrast=0.9", "colorbalance=rh=0.03:bh=0.04"],
    "Sepija": ["colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131", "eq=contrast=1.05"],
    "Šaltos": ["colorbalance=rs=-0.06:bs=0.08", "eq=saturation=1.05"],
    "Nespalvotos": ["hue=s=0", "eq=contrast=1.1"],
}

# Efektai (galima derinti kelis). Taikomi po spalvų filtro, prieš tekstus.
EFFECTS = {
    "Lėtas priartėjimas": "Vaizdas per visą video lėtai artėja – gyvumas net statiškam kadrui.",
    "Švytėjimas": "Švelnus šviesų švytėjimas – svajinga, prabangi nuotaika.",
    "Kino juostos": "Juodos juostos viršuje ir apačioje – kino vaizdas.",
    "Kino grūdeliai": "Lengvas juostos grūdėtumas – analoginis jausmas.",
    "Vinjetė": "Patamsinti kraštai – akys krypsta į centrą.",
    "Ryškumas": "Aiškesnės detalės ir faktūros.",
    "Šviesos blyksnis": "Video prasideda baltu blyksniu.",
    "Aukso blizgesys": "Firminis: per auksinį ar sidabrinį tekstą periodiškai perbėga šviesos blyksnis.",
    "Auksinės dulkės": "Firminis: vaizde švelniai plaukioja ir mirga auksinės kibirkštėlės.",
    "Auksinis rėmelis": "Firminis: plona dviguba metalinė linija aplink kadrą su deimantėliais (aukso ar sidabro).",
}
TEXT_EFFECTS = ("Aukso blizgesys",)  # matosi tik ant teksto – peržiūra rodoma su pavyzdiniu tekstu


def zoom_filters(W, H, duration):
    """Lėtas priartėjimas per visą video (10 %)."""
    d = max(1.0, duration)
    return [f"scale=w='trunc({W}*(1+0.10*t/{d:.3f})/2)*2':h='trunc({H}*(1+0.10*t/{d:.3f})/2)*2':eval=frame",
            f"crop={W}:{H}"]


def look_graph(inp, out, color="Natūralios", effects=(), W=1080, H=1920, duration=10.0, still=False,
               pre=(), post=()):
    """Filtrų grandinė nuo `inp` iki `out` etikečių: spalvų filtras + efektai.
    still=True – vienam kadrui (miniatiūroms ir viršeliui): judesio efektai parodomi statiškai."""
    effects = set(effects or ())
    a = list(pre) + list(COLOR_FILTERS.get(color, []))
    if "Lėtas priartėjimas" in effects:
        a += ["crop=iw*0.88:ih*0.88", f"scale={W}:{H}"] if still else zoom_filters(W, H, duration)
    b = []
    if "Ryškumas" in effects:
        b.append("unsharp=5:5:0.8:5:5:0")
    if "Vinjetė" in effects:
        b.append("vignette=PI/4.2")
    if "Kino grūdeliai" in effects:
        b.append("noise=alls=11:allf=u" if still else "noise=alls=11:allf=t+u")
    if "Kino juostos" in effects:
        b += ["drawbox=x=0:y=0:w=iw:h=ih*0.085:color=black:t=fill",
              "drawbox=x=0:y=ih*0.915:w=iw:h=ih*0.085:color=black:t=fill"]
    if "Šviesos blyksnis" in effects:
        b.append("lutrgb=r='val+(255-val)*0.55':g='val+(255-val)*0.55':b='val+(255-val)*0.55'" if still
                 else "fade=t=in:st=0:d=0.7:color=white")
    b += list(post)
    if "Švytėjimas" in effects:
        sigma = max(4, round(W / 45))
        tail = ("," + ",".join(b)) if b else ""
        return (f"{inp}{','.join(a + ['format=gbrp', 'split'])}[gA][gB];"
                f"[gB]gblur=sigma={sigma},curves=all='0/0 0.5/0.35 1/1'[gC];"
                f"[gA][gC]blend=all_mode=screen:all_opacity=0.45,format=yuv420p{tail}{out}")
    return f"{inp}{','.join(a + b) or 'null'}{out}"


def still_extras(inp, out, width, height, effects, tmp, accent="Aukso gradientas", fps=25):
    """Dulkės ir rėmelis vienam kadrui (miniatiūroms, viršeliui, peržiūroms)."""
    chains, cur = [], inp
    if "Auksinės dulkės" in (effects or ()):
        chains += dust_chains(cur, "[sx1]", width, height, fps, tmp, still=True)
        cur = "[sx1]"
    if "Auksinis rėmelis" in (effects or ()):
        chains += frame_chains(cur, "[sx2]", width, height, fps, tmp, accent)
        cur = "[sx2]"
    chains.append(f"{cur}null{out}")
    return chains


def thumbnail(frame, out_path, color="Natūralios", effects=(), width=180, height=320, accent="Aukso gradientas"):
    """Mažas peržiūros paveikslėlis filtrų / efektų langeliui."""
    pre = [f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}", "setsar=1"]
    tmp = tempfile.mkdtemp()
    try:
        g = ";".join([look_graph("[0:v]", "[lk]", color, effects, width, height, still=True, pre=pre)]
                     + still_extras("[lk]", "[out]", width, height, effects, tmp, accent))
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", frame, "-filter_complex", g, "-map",
                            "[out]", "-frames:v", "1", "-q:v", "4", out_path], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-800:])
    finally:
        for name in os.listdir(tmp):
            os.unlink(os.path.join(tmp, name))
        os.rmdir(tmp)
    return out_path


SUBTITLE_POSITIONS = {"Viduryje": 0.62, "Žemiau": 0.72, "Apačioje": 0.78}
HOOK_POSITIONS = {"Viršuje": 0.12, "Aukščiau": 0.2, "Žemiau": 0.3}

SAMPLE_WORDS = [("Taip", 0.2, 0.6), ("atrodo", 0.6, 1.5), ("titrai", 1.5, 2.2)]


def style_preview(frame, out_path, template="Prabangus auksas", accent="Auksas", color="Natūralios", effects=(),
                  hook="", look=None, width=270, height=480, subs_ypos=0.72, hook_ypos=0.2):
    """Šablono / titrų stiliaus peržiūra ant kadro: kabliukas (jei hook) ir titrų pavyzdys (jei look)
    taip, kaip atrodys video ~1 s (animacijos jau pasibaigusios, paryškintas antras žodis)."""
    tmp = tempfile.mkdtemp()
    try:
        post = []
        if hook.strip():
            a = os.path.join(tmp, "hook.ass")
            with open(a, "w", encoding="utf-8") as f:
                f.write(build_overlay_ass(width, height, 10, hook, 10, accent=accent, template=template,
                                          hook_ypos=hook_ypos))
            post.append(f"ass=filename='{_filter_path(a)}':fontsdir='{_filter_path(FONT_DIR)}'")
        if look:
            hl = _ass_color(ACCENTS.get(accent, ACCENTS["Auksas"])[0])[4:]
            a = os.path.join(tmp, "subs.ass")
            with open(a, "w", encoding="utf-8") as f:
                f.write(video_editor.build_ass(SAMPLE_WORDS, width, height, ypos=subs_ypos, highlight=hl,
                                               look=look))
            post.append(f"ass=filename='{_filter_path(a)}':fontsdir='{_filter_path(FONT_DIR)}'")
        pre = [f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}", "setsar=1"]
        shine = "Aukso blizgesys" in (effects or ())
        if (accent in GRADIENTS or shine) and post:
            masks = []
            if look:
                a = os.path.join(tmp, "subs_mask.ass")
                with open(a, "w", encoding="utf-8") as f:
                    f.write(video_editor.build_ass(SAMPLE_WORDS, width, height, ypos=subs_ypos, look=look,
                                                   mask=True))
                masks.append(f"ass=filename='{_filter_path(a)}':fontsdir='{_filter_path(FONT_DIR)}'")
            if hook.strip():
                masks.append(_cover_mask(tmp, width, height, hook, accent, template, hook_ypos))
            g = ";".join([look_graph("[0:v]", "[base]", color, effects, width, height, still=True, pre=pre,
                                     post=post)]
                         + gradient_chains("[base]", "[gl]", width, height, 10, 1.3, accent, masks, tmp, template,
                                           hook_ypos,
                                           shine=shine, still=True)
                         + ["[gl]select='gte(t,1.0)'[sel]"])
        else:
            g = look_graph("[0:v]", "[sel]", color, effects, width, height, still=True, pre=pre,
                           post=post + ["select='gte(t,1.0)'"])
        g += ";" + ";".join(still_extras("[sel]", "[out]", width, height, effects, tmp, accent, 10))
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "10", "-t", "1.3",
                            "-i", frame, "-filter_complex", g, "-map", "[out]", "-frames:v", "1", "-q:v", "4",
                            out_path], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-800:])
    finally:
        for name in os.listdir(tmp):
            os.unlink(os.path.join(tmp, name))
        os.rmdir(tmp)
    return out_path


SIGNATURE_TRANSITIONS = ("Lapo vertimas", "Kvadratėliai")


def transition_preview(frame_a, frame_b, out_path, transition, width=180, height=320, at=0.45):
    """Perėjimo vidurys tarp dviejų kadrų (langeliui)."""
    fit = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=20,format=gbrp"
    if not video_editor.TRANSITIONS.get(transition):
        g = f"[1:v]{fit},format=yuv420p[out]"
    else:
        g = (f"[0:v]{fit}[a];[1:v]{fit}[b];[a][b]{video_editor.xfade_filter(transition, 1.0, 0.0)},"
             f"select='gte(t,{at})',format=yuv420p[out]")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", "1.2", "-i", frame_a, "-loop", "1",
                        "-t", "1.2", "-i", frame_b, "-filter_complex", g, "-map", "[out]", "-frames:v", "1",
                        "-q:v", "4", out_path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    return out_path


def grab_frame(path, out_path, at=1.0, width=360, height=640):
    """Vienas kadras (9:16) – pagrindas miniatiūroms."""
    seek = [] if video_editor.is_image(path) else ["-ss", f"{max(0.0, at):.3f}"]
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *seek, "-i", path, "-vf",
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                        "-frames:v", "1", "-q:v", "3", out_path], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(r.stderr[-800:] or "Kadro paimti nepavyko")
    return out_path


MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
# Studijos muzikos biblioteka (sukurta tools/make_music.py – be autorių teisių apribojimų)
MUSIC = {
    "prabangus_pianinas": ("✨ Prabangus pianinas", "Lėti pianino akordai, daug erdvės – mada, interjeras, grožis."),
    "lounge": ("🍸 Lounge", "Šiltas elektrinis pianinas ir minkštas ritmas – kavinės, viešbučiai, stilius."),
    "kinematografiska": ("🎬 Kinematografiška", "Platūs pasažai ir lėtas pulsas – kelionės, prieš/po, istorijos."),
    "energinga": ("⚡ Energinga", "118 BPM, gyvas ritmas – sportas, renginiai, greiti patarimai."),
    "lofi": ("☕ Lo-fi", "Ramus siūbuojantis ritmas – kasdienybė, darbas, mokymai."),
    "romantiska": ("🌸 Romantiška", "Švelnūs varpeliai – vestuvės, dovanos, gėlės."),
}


def music_library():
    """{rodomas pavadinimas: {"path", "desc"}} – tik esantys failai."""
    out = {}
    for key, (title, desc) in MUSIC.items():
        path = os.path.join(MUSIC_DIR, key + ".mp3")
        if os.path.exists(path):
            out[title] = {"path": path, "desc": desc}
    return out


SIGNATURE_FILTERS = ("Paryžiaus rytas", "Milano naktis", "Baltijos auksas")
SIGNATURE_EFFECTS = ("Aukso blizgesys", "Auksinės dulkės", "Auksinis rėmelis")

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


def _overlay_layout(width, height, template, hook_ypos=0.2):
    """Kabliuko ir CTA išdėstymas (bendras tekstui, kaukei ir gradientui)."""
    kind = TEMPLATES.get(template, TEMPLATES["Prabangus auksas"])["kind"]
    if kind == "box":
        hsize, csize = round(width * 0.074), round(width * 0.07)
    elif kind == "script":
        hsize, csize = round(width * 0.15), round(width * 0.12)
    else:
        hsize, csize = round(width * 0.088), round(width * 0.075)
    hook_y = round(height * hook_ypos) + (0 if kind == "box" else round(hsize * 0.9))
    cta_y = round(height * 0.44)
    return kind, hsize, csize, hook_y, cta_y


def build_overlay_ass(width, height, duration, hook="", hook_duration=3.0, cta="", cta_duration=2.5,
                      handle="", accent="Auksas", hook_ypos=0.2, template="Prabangus auksas", mask=False):
    """Kabliukas pradžioje, kvietimas veikti (CTA) pabaigoje ir @vardas viršuje.
    Šablonas „elegant“ – serifinis šriftas su plona linija ir švelniu ryškėjimu, „script“ – ranka rašytas
    kaligrafinis šriftas, „box“ – didelės raidės spalvotoje dėžutėje, kuri „iššoka“.
    mask=True – kaukė gradientui: balta tik ta dalis, kuri turi būti metalinė (be kontūrų ir šešėlių)."""
    kind, hsize, csize, hook_y, cta_y = _overlay_layout(width, height, template, hook_ypos)
    bg, fg = ACCENTS.get(accent, ACCENTS["Auksas"])
    acc = "&H00FFFFFF" if mask else _ass_color(bg)
    margin = round(width * 0.09)
    nsize = round(width * 0.03)
    cx = width // 2
    hook, cta = hook.strip(), cta.strip()
    handle = "" if mask else handle.strip()
    if handle and not handle.startswith("@"):
        handle = "@" + handle

    if kind == "box":
        box = max(6, round(hsize * 0.28))
        text_c = "&H00000000" if mask else _ass_color(fg)
        cta_ol, cta_sh = (0, 0) if mask else (max(3, csize // 12), max(2, csize // 24))
        styles = [
            # BorderStyle 3 – nepermatoma dėžutė už teksto (Outline – dėžutės paraštė)
            f"Style: Hook,{FONT_NAME},{hsize},{text_c},{text_c},{acc},&H64000000,"
            f"0,0,0,0,100,100,0,0,3,{box},0,5,{margin},{margin},0,1",
            f"Style: Cta,{FONT_NAME},{csize},{acc},{acc},&H00000000,&H78000000,"
            f"0,0,0,0,100,100,0,0,1,{cta_ol},{cta_sh},5,{margin},{margin},0,1",
        ]
    else:
        font = SCRIPT if kind == "script" else SERIF
        hb, cb, ci = (0, 0, 0) if kind == "script" else (-1, 0, -1)
        def ol(sz):
            return (0, 0) if mask else (max(1, sz // 40), max(2, sz // 22))
        styles = [
            f"Style: Hook,{font},{hsize},{acc},{acc},&H50000000,&H96000000,"
            f"{hb},0,0,0,100,100,1,0,1,{ol(hsize)[0]},{ol(hsize)[1]},2,{margin},{margin},0,1",
            f"Style: Cta,{font},{csize},{acc},{acc},&H50000000,&H96000000,"
            f"{cb},{ci},0,0,100,100,1,0,1,{ol(csize)[0]},{ol(csize)[1]},2,{margin},{margin},0,1",
        ]
    styles.append(f"Style: Handle,{TRAINING_FONT},{nsize},&H20FFFFFF,&H20FFFFFF,&H78000000,&H00000000,"
                  f"0,0,0,0,100,100,{round(nsize * 0.25)},0,1,{max(1, nsize // 16)},0,5,"
                  f"{margin},{margin},0,1")
    lines = _ass_header(width, height, styles)

    def text(t, upper):
        return _ass_escape(t.upper() if upper else t).replace("\n", "\\N")

    if hook:
        end = min(duration, hook_duration)
        if kind == "box":
            lines.append(
                f"Dialogue: 2,{_ass_time(0)},{_ass_time(end)},Hook,,0,0,0,,"
                f"{{\\an5\\pos({cx},{hook_y})\\fad(80,200)\\fscx70\\fscy70"
                f"\\t(0,220,\\fscx106\\fscy106)\\t(220,320,\\fscx100\\fscy100)}}" + text(hook, True))
        else:
            # Tekstas „išryškėja“ iš sulieto ir lėtai priartėja; po juo išsitiesia plona linija.
            lines.append(
                f"Dialogue: 2,{_ass_time(0)},{_ass_time(end)},Hook,,0,0,0,,"
                f"{{\\an2\\pos({cx},{hook_y})\\fad(450,350)\\blur8\\fscx108\\fscy108"
                f"\\t(0,700,\\blur0)\\t(0,{round(end * 1000)},\\fscx100\\fscy100)}}" + text(hook, False))
            lines.append(f"Dialogue: 1,{_ass_time(0.2)},{_ass_time(end)},Hook,,0,0,0,,{{\\fad(0,350)}}"
                         + _rule(cx, hook_y + round(hsize * (0.3 if kind == "script" else 0.45)),
                                 round(width * 0.22), max(2, width // 400), acc, 200))
    if cta and duration > cta_duration + 1:
        a = duration - cta_duration
        if kind == "box":
            lines.append(
                f"Dialogue: 2,{_ass_time(a)},{_ass_time(duration + 1)},Cta,,0,0,0,,"
                f"{{\\an5\\pos({cx},{cta_y})\\fad(150,0)\\fscx80\\fscy80\\t(0,200,\\fscx100\\fscy100)}}"
                + text(cta, True))
        else:
            lines.append(
                f"Dialogue: 2,{_ass_time(a)},{_ass_time(duration + 1)},Cta,,0,0,0,,"
                f"{{\\an2\\pos({cx},{cta_y})\\fad(500,0)\\blur6\\t(0,600,\\blur0)}}" + text(cta, False))
            lines.append(f"Dialogue: 1,{_ass_time(a + 0.2)},{_ass_time(duration + 1)},Cta,,0,0,0,,"
                         + _rule(cx, cta_y + round(csize * (0.3 if kind == "script" else 0.45)),
                                 round(width * 0.16), max(2, width // 400), acc, 0))
    if handle:
        label = handle.upper() if kind != "box" else handle
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration + 1)},Handle,,0,0,0,,"
                     f"{{\\an5\\pos({cx},{round(height * 0.085)})\\fad(600,0)}}" + _ass_escape(label))
    return "\n".join(lines) + "\n"


# ---------- Metalinis gradientas ----------

def _hex(c):
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


def grad_stops(accent):
    """Gradiento spalvų taškai; vienspalviam akcentui – ta pati spalva (blizgesiui ant paprasto teksto)."""
    if accent in GRADIENTS:
        return GRADIENTS[accent]
    c = ACCENTS.get(accent, ACCENTS["Auksas"])[0]
    return [(0.0, c), (1.0, c)]


def shine_image(path, width, height):
    """Šviesos ruožas (RGBA PNG): švelnus įstrižas blyksnis, kuris perbėga per metalinį tekstą."""
    import numpy as np
    full_w, full_h = width, height
    width, height = max(2, width // 2), max(2, height // 2)  # švelnus – užtenka pusės raiškos
    bw = width * 0.16
    y = np.arange(height, dtype=np.float32)[:, None]
    x = np.arange(width, dtype=np.float32)[None, :]
    d = (x - width / 2 + 0.45 * (y - height / 2)) / bw
    a = np.exp(-d ** 2 * 2.2) * 0.85 + np.exp(-(d * 4) ** 2) * 0.15
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = 255, 252, 236
    rgba[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s",
                    f"{width}x{height}", "-i", "-", "-vf", f"scale={full_w}:{full_h}:flags=bicubic", "-frames:v", "1",
                    path], input=rgba.tobytes(), check=True)
    return path


def dust_media(path, width=360, height=640, fps=30, seconds=4.0, still=False, seed=11):
    """Auksinės dulkės: permatomas, be sandūros kartojamas kibirkštėlių sluoksnis (MOV qtrle) arba vienas kadras (PNG)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    n = 70
    px, py = rng.uniform(0, width, n), rng.uniform(0, height, n)
    rise = rng.choice([1, 1, 2], n) * height  # per ciklą pakyla 1–2 kadro aukščius – ciklas be sandūros
    sway, sph = rng.uniform(4, 18, n), rng.uniform(0, 2 * np.pi, n)
    tw, tph = rng.choice([1, 2, 3], n), rng.uniform(0, 2 * np.pi, n)
    size = rng.uniform(1.2, 3.6, n)
    gold = np.array([[255, 236, 170], [245, 210, 120], [255, 248, 220]])[rng.integers(0, 3, n)]
    r = 18
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    window = np.clip(1 - (xx ** 2 + yy ** 2) / r ** 2, 0, 1) ** 2  # apvalūs, švelnūs kraštai
    frames = 1 if still else int(round(fps * seconds))
    codec = [] if still else ["-c:v", "qtrle"]
    # Kadrai siunčiami ffmpeg po vieną (ne kaupiami atmintyje).
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s",
                             f"{width}x{height}", "-r", str(fps), "-i", "-", *codec, path],
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for f in range(frames):
        ph = 0.37 if still else f / frames
        img = np.zeros((height, width, 4), dtype=np.float32)
        cx = (px + sway * np.sin(2 * np.pi * ph + sph)) % width
        cy = (py - rise * ph) % height
        bright = 0.25 + 0.75 * (0.5 + 0.5 * np.sin(2 * np.pi * tw * ph + tph)) ** 3
        for i in range(n):
            g = np.exp(-(xx ** 2 + yy ** 2) / (2 * size[i] ** 2)) * bright[i]
            g += np.exp(-(xx ** 2 + yy ** 2) / (2 * (size[i] * 2.4) ** 2)) * bright[i] * 0.22  # švytėjimas
            g *= window
            x0, y0 = int(cx[i]) - r, int(cy[i]) - r
            xs, ys = slice(max(0, x0), min(width, x0 + 2 * r + 1)), slice(max(0, y0), min(height, y0 + 2 * r + 1))
            gs = g[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0]
            img[ys, xs, 3] = np.maximum(img[ys, xs, 3], gs)
            img[ys, xs, :3] = np.where(gs[..., None] > 0.02, gold[i], img[ys, xs, :3])
        img[..., 3] = np.clip(img[..., 3], 0, 1) * 255
        proc.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    proc.stdin.close()
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError(f"Nepavyko sukurti auksinių dulkių: {err[-500:]}")
    return path


def frame_image(path, width, height, accent="Aukso gradientas"):
    """Auksinis (ar sidabrinis) rėmelis: dviguba linija suapvalintais kampais ir deimantėliai viršuje bei
    apačioje (RGBA PNG)."""
    import numpy as np
    stops = GRADIENTS.get(accent) or (GRADIENTS["Sidabro gradientas"] if "idabr" in accent
                                      else GRADIENTS["Aukso gradientas"])
    pos = np.array([p for p, _ in stops])
    cols = np.array([_hex(c) for _, c in stops], dtype=float)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    alpha = np.zeros((height, width), dtype=np.float32)

    def rounded(m, r, thick):
        cx, cy = width / 2, height / 2
        hx, hy = width / 2 - m, height / 2 - m
        qx, qy = np.abs(x - cx) - (hx - r), np.abs(y - cy) - (hy - r)
        d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
        return np.clip(thick / 2 + 0.5 - np.abs(d), 0, 1)

    m = width * 0.035
    alpha = np.maximum(alpha, rounded(m, width * 0.03, max(2.0, width * 0.0042)))
    alpha = np.maximum(alpha, rounded(m + width * 0.014, width * 0.02, max(1.0, width * 0.0018)) * 0.9)
    # deimantėliai viršuje ir apačioje (linija aplink juos „pertraukiama“)
    sz = width * 0.016
    for cy in (m, height - m):
        dd = np.abs(x - width / 2) + np.abs(y - cy)
        alpha = np.where(dd < sz * 1.9, 0, alpha)
        alpha = np.maximum(alpha, np.clip(sz - dd + 0.5, 0, 1))
        alpha = np.maximum(alpha, np.clip(1.2 - np.abs(dd - sz * 1.45), 0, 1) * 0.8)
    period = width * 0.6
    d = ((x + 0.6 * y) % period) / period
    t = 1 - np.abs(2 * d - 1)
    del d
    rgba = np.empty((height, width, 4), dtype=np.uint8)
    for c in range(3):
        rgba[..., c] = np.clip(np.interp(t, pos, cols[:, c]), 0, 255)
    rgba[..., 3] = np.clip(alpha * 255, 0, 255)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s",
                    f"{width}x{height}", "-i", "-", "-frames:v", "1", path], input=rgba.tobytes(), check=True)
    return path


def frame_chains(inp, out, width, height, fps, tmp, accent="Aukso gradientas"):
    """Uždeda auksinį rėmelį (inp -> out)."""
    p = frame_image(os.path.join(tmp, "frame.png"), width, height, accent)
    return [f"movie='{_filter_path(p)}',loop=loop=-1:size=1:start=0,format=rgba[frm]",
            f"{inp}[frm]overlay=shortest=1:format=auto{out}"]


def dust_chains(inp, out, width, height, fps, tmp, still=False):
    """Uždeda auksines dulkes ant vaizdo (inp -> out)."""
    p = dust_media(os.path.join(tmp, "dust.png" if still else "dust.mov"), fps=fps, still=still)
    src = f"movie='{_filter_path(p)}'" + ("" if still else ":loop=0,setpts=N/(FRAME_RATE*TB)")
    loop = ",loop=loop=-1:size=1:start=0" if still else ""
    return [f"{src}{loop},scale={width}:{height},format=rgba[dust]",
            f"{inp}[dust]overlay=shortest=1:format=auto{out}"]


def gradient_image(path, width, height, accent, template="Prabangus auksas", hook_ypos=0.2):
    """Gradiento paveikslėlis (PPM). Kabliuko ir CTA srityse – metalinės juostos, sutapdintos su teksto
    eilutėmis (šviesus viršus, tamsesnė vidurio linija, blizgi apačia); likusiame kadre (titrams) – įstrižas
    blizgesys."""
    import numpy as np
    stops = grad_stops(accent)
    pos = np.array([p for p, _ in stops])
    cols = np.array([_hex(c) for _, c in stops], dtype=float)
    kind, hsize, csize, hook_y, cta_y = _overlay_layout(width, height, template, hook_ypos)
    # Piešiama per pusę mažesne raiška (gradientas švelnus) – ffmpeg padidina; taip mažiau atminties.
    full_w, full_h = width, height
    k = 2 if width >= 720 else 1
    width, height = width // k, height // k
    hook_y, cta_y, hsize, csize = hook_y / k, cta_y / k, hsize / k, csize / k
    y = np.arange(height, dtype=np.float32)[:, None]
    x = np.arange(width, dtype=np.float32)[None, :]
    # įstrižas blizgesys (trikampė banga – be ryškių sandūrų)
    period = width * 0.55
    d = ((x + 0.5 * y) % period) / period
    t = (1 - np.abs(2 * d - 1)).astype(np.float32)
    del d
    t = np.broadcast_to(t, (height, width)).copy()
    if kind != "box":  # eilutėmis sutapdintos juostos kabliukui ir CTA
        for yb, size, lo, hi in ((hook_y, hsize, 0, (hook_y + cta_y) // 2),
                                 (cta_y, csize, (hook_y + cta_y) // 2, round(height * 0.55))):
            pitch = size * (1.3 if kind == "script" else 1.18)
            top = yb - pitch * (0.88 if kind == "script" else 0.95)
            rows = slice(max(0, int(lo)), min(height, int(hi)))
            yy = y[rows]
            band = ((yy - top) % pitch) / pitch
            t[rows] = np.broadcast_to(band, (yy.shape[0], width))
    img = np.empty((height, width, 3), dtype=np.uint8)
    for c in range(3):
        img[..., c] = np.clip(np.interp(t, pos, cols[:, c]), 0, 255)
    del t
    small = path + ".small.ppm"
    with open(small, "wb") as f:
        f.write(f"P6 {width} {height} 255\n".encode())
        f.write(img.tobytes())
    del img
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", small, "-vf", f"scale={full_w}:{full_h}:flags=bicubic",
                    "-f", "image2", "-c:v", "ppm", path], check=True)
    os.unlink(small)
    return path


def gradient_chains(base, out, width, height, fps, duration, accent, masks, tmp, template="Prabangus auksas",
                    hook_ypos=0.2, mask_pre=(), name="g", shine=False, still=False):
    """Filtrų grandinės, kurios „įlieja“ gradientą į tekstą: masks – ass filtrai, piešiantys baltą kaukę
    ant juodo fono (mask_pre – filtrai prieš juos, pvz. laiko poslinkis ar priartėjimas).
    shine – „Aukso blizgesys“: per tekstą kas 2,6 s perbėga šviesos ruožas (still – sustabdytas viduryje)."""
    grad = gradient_image(os.path.join(tmp, f"{name}.ppm"), width, height, accent, template, hook_ypos)
    mask_chain = ",".join(list(mask_pre) + list(masks))
    chains = [
        f"color=c=black:s={width}x{height}:r={fps}:d={duration:.3f},format=yuv420p,{mask_chain},format=gbrp[{name}m]",
        f"movie='{_filter_path(grad)}',loop=loop=-1:size=1:start=0,fps={fps},format=gbrp[{name}g0]",
        f"{base}format=gbrp[{name}b]",
    ]
    if shine:
        sh = shine_image(os.path.join(tmp, f"{name}_shine.png"), width, height)
        # Pirmas perbėgimas – kai kabliukas jau ryškus (~1 s), vėliau kas 2,6 s.
        x = "-W*0.08" if still else "if(lt(mod(t+1.6,2.6),1.1),-W+2*W*mod(t+1.6,2.6)/1.1,W)"
        chains += [f"movie='{_filter_path(sh)}',loop=loop=-1:size=1:start=0,fps={fps},format=rgba[{name}s]",
                   f"[{name}g0][{name}s]overlay=x='{x}':y=0:eval=frame:format=gbrp[{name}g]"]
    else:
        chains.append(f"[{name}g0]null[{name}g]")
    chains.append(f"[{name}b][{name}g][{name}m]maskedmerge,format=yuv420p{out}")
    return chains


def _run(cmd, total, progress, what):
    proc = subprocess.Popen(video_editor.limit_threads(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    for line in proc.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and progress and total > 0:
            progress(min(1.0, int(m.group(1)) / 1e6 / total))
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError(f"{what}:\n{err[-2000:]}")


def finish(path, out_path, hook="", hook_duration=3.0, cta="", cta_duration=2.5, handle="",
           accent="Auksas", template="Prabangus auksas", music=None, music_volume=0.25, ducking=True, max_length=None, speed=1.0,
           color="Auksinė valanda", progress_bar="Viršuje", progress=None, effects=(), preview=False,
           subs_words=None, subs_look="modern", subs_ypos=0.72, hook_ypos=0.2):
    """Reels apdaila ant sumontuoto video. Grąžina {"duration", "width", "height"}.
    Gradiento akcentui (GRADIENTS) metalas „įliejamas“ į kabliuką, CTA ir paryškintą titrų žodį
    (subs_words – sumontuoto video titrų žodžiai, subs_look – jų išvaizda)."""
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
                                      hook_ypos=hook_ypos, template=template))

        pre = [f"setpts=PTS/{speed:.4f}"] if abs(speed - 1) > 0.001 else []
        post = [f"ass=filename='{_filter_path(ass)}':fontsdir='{_filter_path(FONT_DIR)}'"]
        graph = [look_graph("[0:v]", "[base]", color, effects, W, H, duration, pre=pre, post=post)]
        vout = "[base]"
        shine = "Aukso blizgesys" in (effects or ())
        if accent in GRADIENTS or shine:
            masks = []
            if subs_words:
                sw = [(w, a0 / speed, b0 / speed) for w, a0, b0 in subs_words]
                sm = os.path.join(tmp, "subs_mask.ass")
                with open(sm, "w", encoding="utf-8") as f:
                    f.write(video_editor.build_ass(sw, W, H, ypos=subs_ypos, look=subs_look, mask=True))
                masks.append(f"ass=filename='{_filter_path(sm)}':fontsdir='{_filter_path(FONT_DIR)}'")
                if "Lėtas priartėjimas" in (effects or ()):  # titrai sumontuoti anksčiau – priartėja kartu su vaizdu
                    masks += zoom_filters(W, H, duration)
            om = os.path.join(tmp, "overlay_mask.ass")
            with open(om, "w", encoding="utf-8") as f:
                f.write(build_overlay_ass(W, H, duration, hook, hook_duration, cta, cta_duration, "", accent,
                                          hook_ypos=hook_ypos, template=template, mask=True))
            masks.append(f"ass=filename='{_filter_path(om)}':fontsdir='{_filter_path(FONT_DIR)}'")
            graph += gradient_chains("[base]", "[gold]", W, H, fps, duration + 1, accent, masks, tmp, template,
                                     hook_ypos=hook_ypos, shine=shine)
            vout = "[gold]"
        if "Auksinės dulkės" in (effects or ()):
            graph += dust_chains(vout, "[dusty]", W, H, fps, tmp)
            vout = "[dusty]"
        if "Auksinis rėmelis" in (effects or ()):
            graph += frame_chains(vout, "[framed]", W, H, fps, tmp, accent)
            vout = "[framed]"
        if trimmed:
            graph.append(f"{vout}fade=t=out:st={duration - 0.5:.3f}:d=0.5[faded]")
            vout = "[faded]"
        if progress_bar in ("Viršuje", "Apačioje"):
            bh = max(6, round(H * 0.006)) // 2 * 2
            y = 0 if progress_bar == "Viršuje" else H - bh
            bg = ACCENTS.get(accent, ACCENTS["Auksas"])[0]
            graph.append(f"color=c=0x{bg}:s={W}x{bh}:r={fps}[bar]")
            graph.append(f"{vout}[bar]overlay=x='-w+w*t/{duration:.3f}':y={y}:shortest=1[vout]")
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
        cmd += ["-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-crf", "28" if preview else "19",
                "-pix_fmt", "yuv420p",
                "-r", str(fps), "-movflags", "+faststart", "-t", f"{duration:.3f}", out_path]
        _run(cmd, duration, progress, "Nepavyko paruošti Reels")
    finally:
        for name in os.listdir(tmp):
            os.unlink(os.path.join(tmp, name))
        os.rmdir(tmp)
    return {"duration": duration, "width": W, "height": H, "trimmed": trimmed}


def _cover_mask(tmp, width, height, hook, accent, template, ypos=0.42):
    p = os.path.join(tmp, "cover_mask.ass")
    with open(p, "w", encoding="utf-8") as f:
        f.write(build_overlay_ass(width, height, 10, hook, 10, accent=accent, hook_ypos=ypos, template=template,
                                  mask=True))
    return f"ass=filename='{_filter_path(p)}':fontsdir='{_filter_path(FONT_DIR)}'"


def make_cover(path, out_path, at=0.5, hook="", accent="Auksas", template="Prabangus auksas",
               handle="", width=1080, height=1920, color=None, effects=()):
    """Viršelis (JPG 1080×1920): kadras iš video (arba nuotrauka) su filtru, efektais ir kabliuku per vidurį."""
    if color is None:
        color = TEMPLATES.get(template, {}).get("color", "Natūralios")
    tmp = tempfile.mkdtemp()
    try:
        # setpts: kadras „po“ teksto animacijų (kabliukas iššoka per pirmas dalis sekundės)
        pre = ["setpts=PTS-STARTPTS+5/TB", f"scale={width}:{height}:force_original_aspect_ratio=increase",
               f"crop={width}:{height}", "setsar=1"]
        post = []
        if hook.strip() or handle.strip():
            ass = os.path.join(tmp, "cover.ass")
            with open(ass, "w", encoding="utf-8") as f:
                f.write(build_overlay_ass(width, height, 10, hook, 10, handle=handle, accent=accent,
                                          hook_ypos=0.42, template=template))
            post.append(f"ass=filename='{_filter_path(ass)}':fontsdir='{_filter_path(FONT_DIR)}'")
        fx = [e for e in effects if e != "Šviesos blyksnis"]
        shine = "Aukso blizgesys" in fx
        if (accent in GRADIENTS or shine) and post and hook.strip():
            g = ";".join([look_graph("[0:v]", "[base]", color, fx, width, height, still=True, pre=pre, post=post)]
                         + gradient_chains("[base]", "[cv]", width, height, 25, 10, accent, [_cover_mask(
                             tmp, width, height, hook, accent, template)], tmp, template, 0.42,
                             mask_pre=["setpts=PTS+5/TB"], shine=shine, still=True))
        else:
            g = look_graph("[0:v]", "[cv]", color, fx, width, height, still=True, pre=pre, post=post)
        g += ";" + ";".join(still_extras("[cv]", "[out]", width, height, fx, tmp, accent))
        seek = [] if video_editor.is_image(path) else ["-ss", f"{max(0.0, at):.3f}"]
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *seek, "-i", path, "-filter_complex", g, "-map", "[out]",
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
    ap.add_argument("--effect", action="append", default=[], choices=list(EFFECTS))
    ap.add_argument("--progress-bar", default="Viršuje", choices=["Viršuje", "Apačioje", "Nėra"])
    ap.add_argument("--cover", metavar="JPG", help="Papildomai sukurti viršelį")
    a = ap.parse_args()
    r = finish(a.input, a.output, a.hook, a.hook_duration, a.cta, 2.5, a.handle, a.accent, a.template, a.music,
               a.music_volume, not a.no_ducking, a.max_length, a.speed, a.color, a.progress_bar,
               effects=a.effect)
    if a.cover:
        make_cover(a.input, a.cover, 0.5, a.hook, a.accent, a.template, a.handle, color=a.color,
                   effects=a.effect)
    print(f"Gatava: {r['duration']:.1f} s, {r['width']}x{r['height']}")
