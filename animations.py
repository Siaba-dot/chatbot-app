"""Animacijos Reels video: animuoti lipdukai, ranka piešti žymėjimai, iššokančios kortelės, įžanga ir pabaiga.

Viskas piešiama ASS vektoriniais piešiniais (libass) – be papildomų programų, todėl veikia ir Streamlit Cloud.
Laikai – galutinio video sekundėmis. Planas: {"stickers": [(t, rūšis)], "marks": [(t, rūšis)],
"cards": [(t, tekstas)]}.
"""
import json
import math
import random
import re

import video_editor
from video_editor import FONT_NAME, _ass_escape, _ass_time

STICKERS = {"hearts": "Širdelės", "stars": "Žvaigždutės", "confetti": "Konfeti", "fire": "Liepsnelės"}
MARKS = {"circle": "Apskritimas", "arrow": "Rodyklė", "underline": "Pabraukimas"}
FX = {"shatter": "Byrančios kaladėlės", "glitch": "Glitch", "flash": "Blyksnis", "leak": "Šviesos nutekėjimas",
      "bw": "Nespalvota akimirka"}
FX_ORDER = ("shatter", "flash", "glitch", "leak", "bw")
SHATTER_LEN, GLITCH_LEN, BW_LEN = 1.4, 0.45, 1.3
INTRO_LEN, OUTRO_LEN = 1.3, 1.8

# ---------- žodžiai, pagal kuriuos parenkama be AI ----------
_STICKER_WORDS = [
    ("hearts", r"^(myli|patink|šird|meil|graž|mieg|ačiū|dėkoj|love)"),
    ("stars", r"^(super|puik|nuostab|geriaus|wow|tobul|fantast|stebuk)"),
    ("confetti", r"^(švent|dovan|sveikin|laimėj|pagaliau|gimtadien|akcij|nuolaid)"),
    ("fire", r"^(karšt|ugn|hit|top|trend|energ)"),
]
_NUMBERS = {"pirm": 1, "antr": 2, "treč": 3, "ketvirt": 4, "penkt": 5}


def _f(v):
    return f"{v:.0f}"


def _c(rgb, alpha="00"):
    """RGB hex -> ASS (&HAABBGGRR&)."""
    return f"&H{alpha}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&".upper()


def _ellipse(cx, cy, rx, ry):
    k = 0.5523
    return (f"m {_f(cx)} {_f(cy - ry)} b {_f(cx + k * rx)} {_f(cy - ry)} {_f(cx + rx)} {_f(cy - k * ry)} "
            f"{_f(cx + rx)} {_f(cy)} b {_f(cx + rx)} {_f(cy + k * ry)} {_f(cx + k * rx)} {_f(cy + ry)} "
            f"{_f(cx)} {_f(cy + ry)} b {_f(cx - k * rx)} {_f(cy + ry)} {_f(cx - rx)} {_f(cy + k * ry)} "
            f"{_f(cx - rx)} {_f(cy)} b {_f(cx - rx)} {_f(cy - k * ry)} {_f(cx - k * rx)} {_f(cy - ry)} "
            f"{_f(cx)} {_f(cy - ry)}")


def _heart(s):
    return (f"m {_f(s / 2)} {_f(s * 0.95)} b {_f(-s * 0.05)} {_f(s * 0.55)} {_f(s * 0.1)} {_f(-s * 0.05)} "
            f"{_f(s / 2)} {_f(s * 0.25)} b {_f(s * 0.9)} {_f(-s * 0.05)} {_f(s * 1.05)} {_f(s * 0.55)} "
            f"{_f(s / 2)} {_f(s * 0.95)}")


def _star(r, points=5, inner=0.45):
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * inner
        a = math.pi * i / points - math.pi / 2
        pts.append((r + math.cos(a) * rr, r + math.sin(a) * rr))
    return "m " + " l ".join(f"{_f(x)} {_f(y)}" for x, y in pts)


def _flame(w, h):
    return (f"m {_f(w / 2)} 0 b {_f(w * 0.75)} {_f(h * 0.3)} {_f(w)} {_f(h * 0.5)} {_f(w)} {_f(h * 0.72)} "
            f"b {_f(w)} {_f(h * 0.92)} {_f(w * 0.75)} {_f(h)} {_f(w / 2)} {_f(h)} "
            f"b {_f(w * 0.25)} {_f(h)} 0 {_f(h * 0.92)} 0 {_f(h * 0.72)} "
            f"b 0 {_f(h * 0.5)} {_f(w * 0.3)} {_f(h * 0.42)} {_f(w * 0.35)} {_f(h * 0.2)} "
            f"b {_f(w * 0.45)} {_f(h * 0.3)} {_f(w * 0.45)} {_f(h * 0.12)} {_f(w / 2)} 0")


def _rrect(w, h, r):
    return (f"m {_f(r)} 0 l {_f(w - r)} 0 b {_f(w)} 0 {_f(w)} 0 {_f(w)} {_f(r)} l {_f(w)} {_f(h - r)} "
            f"b {_f(w)} {_f(h)} {_f(w)} {_f(h)} {_f(w - r)} {_f(h)} l {_f(r)} {_f(h)} b 0 {_f(h)} 0 {_f(h)} 0 "
            f"{_f(h - r)} l 0 {_f(r)} b 0 0 0 0 {_f(r)} 0")


def _ev(lines, layer, a, b, tags, text):
    if b > a + 0.02:
        lines.append(f"Dialogue: {layer},{_ass_time(max(0.0, a))},{_ass_time(b)},A,,0,0,0,,{{{tags}}}{text}")


# ---------- animuoti lipdukai ----------
def _stickers(lines, t, kind, W, H, acc, rnd):
    ref = min(W, H * 0.75)
    if kind == "hearts":  # 6 širdelės kyla aukštyn, siūbuodamos
        for i in range(8):
            s = ref * rnd.uniform(0.1, 0.16)
            x0 = W * rnd.uniform(0.62, 0.86)
            y0 = H * rnd.uniform(0.62, 0.72)
            x1, y1 = x0 + rnd.uniform(-0.08, 0.08) * W, y0 - H * rnd.uniform(0.25, 0.4)
            a = t + i * 0.13
            col = rnd.choice(["&H004A3BFF&", "&H007A5CFF&", "&H00A0A0FF&"])
            _ev(lines, 8, a, a + 1.7, f"\\an7\\move({_f(x0)},{_f(y0)},{_f(x1)},{_f(y1)})\\1c{col}\\bord2\\3c&H00FFFFFF&"
                f"\\shad0\\fscx30\\fscy30\\t(0,250,\\fscx100\\fscy100)\\frz{rnd.randint(-15, 15)}\\fad(80,500)\\p1",
                _heart(s))
    elif kind == "stars":  # žvaigždučių sprogimas aplink tašką
        cx, cy = W * rnd.uniform(0.3, 0.7), H * rnd.uniform(0.28, 0.4)
        for i in range(8):
            r = ref * rnd.uniform(0.025, 0.05)
            ang = 2 * math.pi * i / 8 + rnd.uniform(-0.2, 0.2)
            d = ref * rnd.uniform(0.18, 0.3)
            x1, y1 = cx + math.cos(ang) * d, cy + math.sin(ang) * d
            col = acc if i % 2 else "&H008AE6FF&"
            _ev(lines, 8, t, t + 1.2, f"\\an5\\move({_f(cx)},{_f(cy)},{_f(x1)},{_f(y1)},0,450)\\1c{col}\\bord1"
                f"\\3c&H00FFFFFF&\\shad0\\fscx20\\fscy20\\t(0,300,\\fscx120\\fscy120)\\t(0,1200,\\frz180)"
                f"\\fad(0,450)\\p1", _star(r))
        _ev(lines, 8, t, t + 0.9, f"\\an5\\pos({_f(cx)},{_f(cy)})\\1c&H00FFFFFF&\\bord0\\shad0\\blur6\\fscx10"
            f"\\fscy10\\t(0,250,\\fscx130\\fscy130)\\fad(0,500)\\p1", _star(ref * 0.08, 4, 0.25))
    elif kind == "confetti":  # konfeti krenta per visą kadrą
        cols = ["&H004A3BFF&", "&H0000D7FF&", "&H00E6A33B&", "&H0066D45A&", "&H00FF7FBF&", acc]
        for i in range(34):
            w, h = ref * rnd.uniform(0.012, 0.022), ref * rnd.uniform(0.03, 0.05)
            x0 = W * rnd.uniform(0.02, 0.98)
            a = t + rnd.uniform(0, 0.5)
            _ev(lines, 8, a, a + 2.2, f"\\an5\\move({_f(x0)},{_f(-h)},{_f(x0 + rnd.uniform(-0.1, 0.1) * W)},"
                f"{_f(H * rnd.uniform(0.55, 0.95))})\\1c{rnd.choice(cols)}\\bord0\\shad0\\frz{rnd.randint(0, 90)}"
                f"\\t(\\frz{rnd.randint(200, 720)})\\fad(0,400)\\p1", _rrect(w, h, 2))
    elif kind == "fire":  # liepsnelės kyla iš apačios
        for i in range(5):
            w = ref * rnd.uniform(0.08, 0.13)
            h = w * 1.35
            x = W * (0.08 + 0.2 * i + rnd.uniform(-0.04, 0.04))
            y = H * 0.9
            a = t + i * 0.08
            for layer, col, k in ((8, "&H00006BFF&", 1.0), (9, "&H0000D7FF&", 0.6)):
                ww, hh = w * k, h * k
                _ev(lines, layer, a, a + 1.6, f"\\an2\\pos({_f(x)},{_f(y)})\\1c{col}\\bord0\\shad0\\blur2"
                    f"\\fscy10\\t(0,250,\\fscy110)\\t(250,500,\\fscy90)\\t(500,750,\\fscy108)\\t(750,1000,\\fscy95)"
                    f"\\fad(100,400)\\p1", _flame(ww, hh))


# ---------- ranka piešti žymėjimai („nusipiešia“ iš kairės į dešinę) ----------
def _word_label(lines, t, dur, word, cx, cy, fs, rot=0):
    """Pasakytas svarbus žodis – didelis, baltas, su šešėliu (kad žymėjimas rodytų į tai, apie ką kalbama)."""
    _ev(lines, 8, t, t + dur, f"\\an5\\pos({_f(cx)},{_f(cy)})\\fn{FONT_NAME}\\fs{fs}\\frz{rot}\\1c&H00FFFFFF&"
        f"\\bord{max(3, fs // 14)}\\3c&H00101010&\\shad3\\4c&H80000000&\\fscx60\\fscy60"
        f"\\t(0,220,\\fscx110\\fscy110)\\t(220,360,\\fscx100\\fscy100)\\fad(0,300)", _ass_escape(word))


def _marks(lines, t, kind, W, H, acc, subs_y, rnd, word=""):
    ref = min(W, H * 0.75)
    th = max(4, round(ref * 0.012))
    dur = 1.8
    word = (word or "").strip().upper()[:18]
    if kind in ("circle", "arrow") and not word:  # be žodžio nebėra ką žymėti – pabraukiam titrus
        kind = "underline"
    if kind == "circle":  # ranka apvestas svarbus žodis viršutinėje kadro dalyje
        fs = round(ref * 0.085)
        tw = video_editor.text_width(FONT_NAME, fs, word)
        fs = round(fs * min(1.0, W * 0.7 / max(1, tw)))
        tw = video_editor.text_width(FONT_NAME, fs, word)
        cx, cy = W * 0.5, H * 0.2
        rx, ry = tw / 2 + fs * 0.75, fs * 1.05
        _word_label(lines, t, dur, word, cx, cy, fs, rot=rnd.choice((-3, -2, 2, 3)))
        shape = _ellipse(cx, cy, rx, ry) + " " + _ellipse(cx + rx * 0.03, cy - ry * 0.07, rx * 1.03, ry * 0.95)
        x0, x1 = cx - rx * 1.1, cx + rx * 1.1
    elif kind == "underline":
        y = H * min(0.93, subs_y + 0.055)
        w = W * 0.6
        x0 = (W - w) / 2
        shape = (f"m {_f(x0)} {_f(y)} b {_f(x0 + w * 0.3)} {_f(y - th)} {_f(x0 + w * 0.7)} {_f(y + th)} "
                 f"{_f(x0 + w)} {_f(y - th * 0.5)} l {_f(x0 + w)} {_f(y + th * 0.6)} "
                 f"b {_f(x0 + w * 0.7)} {_f(y + th * 2)} {_f(x0 + w * 0.3)} {_f(y)} {_f(x0)} {_f(y + th * 1.2)}")
        x1 = x0 + w
        _ev(lines, 7, t, t + dur, f"\\an7\\pos(0,0)\\1c{acc}\\bord1\\3c&H00101010&\\shad0"
            f"\\clip({_f(x0)},0,{_f(x0)},{H})\\t(0,350,\\clip({_f(x0)},0,{_f(x1 + 5)},{H}))\\fad(0,300)\\p1", shape)
        return
    else:  # rodyklė iš šono į svarbų žodį
        left = rnd.random() < 0.5
        fs = round(ref * 0.075)
        tw = video_editor.text_width(FONT_NAME, fs, word)
        fs = round(fs * min(1.0, W * 0.55 / max(1, tw)))
        tw = video_editor.text_width(FONT_NAME, fs, word)
        lx, ly = (W * 0.62 if left else W * 0.38), H * 0.3
        lx = min(max(lx, tw / 2 + W * 0.04), W - tw / 2 - W * 0.04)
        _word_label(lines, t + 0.3, dur - 0.3, word, lx, ly, fs)
        sx, sy = (W * 0.08, H * 0.14) if left else (W * 0.92, H * 0.14)
        ex, ey = (lx - tw / 2 - fs * 0.3, ly - fs * 0.4) if left else (lx + tw / 2 + fs * 0.3, ly - fs * 0.4)
        nx, ny = ex - sx, ey - sy
        ln = math.hypot(nx, ny)
        ux, uy = nx / ln, ny / ln
        px, py = -uy, ux
        sw = th * 0.9
        cx, cy = (sx + ex) / 2 + px * ln * 0.12, (sy + ey) / 2 + py * ln * 0.12
        shaft = (f"m {_f(sx + px * sw)} {_f(sy + py * sw)} b {_f(cx + px * sw)} {_f(cy + py * sw)} "
                 f"{_f(cx + px * sw)} {_f(cy + py * sw)} {_f(ex + px * sw)} {_f(ey + py * sw)} "
                 f"l {_f(ex - px * sw)} {_f(ey - py * sw)} b {_f(cx - px * sw)} {_f(cy - py * sw)} "
                 f"{_f(cx - px * sw)} {_f(cy - py * sw)} {_f(sx - px * sw)} {_f(sy - py * sw)}")
        hl = ref * 0.06
        head = (f"m {_f(ex + ux * hl * 0.6)} {_f(ey + uy * hl * 0.6)} "
                f"l {_f(ex - ux * hl + px * hl * 0.7)} {_f(ey - uy * hl + py * hl * 0.7)} "
                f"l {_f(ex - ux * hl - px * hl * 0.7)} {_f(ey - uy * hl - py * hl * 0.7)}")
        a, b = (min(sx, ex) - hl, max(sx, ex) + hl)
        if left:
            clip0, clip1 = f"\\clip({_f(a)},0,{_f(a)},{H})", f"\\clip({_f(a)},0,{_f(b)},{H})"
        else:
            clip0, clip1 = f"\\clip({_f(b)},0,{_f(b)},{H})", f"\\clip({_f(a)},0,{_f(b)},{H})"
        for part in (shaft, head):
            _ev(lines, 7, t, t + dur, f"\\an7\\pos(0,0)\\1c{acc}\\bord2\\3c&H00101010&\\shad0{clip0}"
                f"\\t(0,400,{clip1})\\fad(0,300)\\p1", part)
        return
    # apskritimas – kontūras (permatomas vidus) piešiamas iš kairės į dešinę
    _ev(lines, 7, t, t + dur, f"\\an7\\pos(0,0)\\1a&HFF&\\3c{acc}\\bord{th}\\shad0"
        f"\\clip({_f(x0)},0,{_f(x0)},{H})\\t(0,500,\\clip({_f(x0)},0,{_f(x1)},{H}))\\fad(0,300)\\p1", shape)


# ---------- iššokančios kortelės ----------
def _card(lines, t, end, text, idx, W, H, acc, rnd):
    ref = min(W, H * 0.75)
    fs = round(ref * 0.05)
    tw = video_editor.text_width(FONT_NAME, fs, text.upper())
    num = re.match(r"^\s*(\d+)[.)]?\s*", text)
    label = text[num.end():] if num else text
    n = num.group(1) if num else None
    tw = video_editor.text_width(FONT_NAME, fs, label.upper())
    pad = fs * 0.6
    circ = fs * 1.5 if n else 0
    w = min(W * 0.9, tw + pad * 2 + circ + (pad * 0.5 if n else 0))
    h = fs * 1.9
    left = idx % 2 == 0
    x = W * 0.06 if left else W * 0.94 - w
    y = H * (0.27 + 0.085 * (idx % 3))
    x_from = -w - 20 if left else W + 20
    mv = f"\\move({_f(x_from)},{_f(y)},{_f(x)},{_f(y)},0,280)"
    _ev(lines, 6, t, end, f"\\an7{mv}\\1c&H00FFFFFF&\\bord3\\3c&H00101010&\\shad4\\4c&H64000000&"
        f"\\fad(0,250)\\p1", _rrect(w, h, h * 0.28))
    tx = pad + circ + (pad * 0.5 if n else 0)
    if n:
        _ev(lines, 7, t, end, f"\\an7{mv}\\1c{acc}\\bord0\\shad0\\fad(0,250)\\p1",
            _ellipse(pad + circ / 2, h / 2, circ / 2, circ / 2))
        _ev(lines, 8, t, end, f"\\an5\\move({_f(x_from + pad + circ / 2)},{_f(y + h / 2)},{_f(x + pad + circ / 2)},"
            f"{_f(y + h / 2)},0,280)\\fn{FONT_NAME}\\fs{fs}\\1c&H00101010&\\bord0\\shad0\\fad(0,250)", n)
    _ev(lines, 8, t, end, f"\\an4\\move({_f(x_from + tx)},{_f(y + h / 2)},{_f(x + tx)},{_f(y + h / 2)},0,280)"
        f"\\fn{FONT_NAME}\\fs{fs}\\1c&H00101010&\\bord0\\shad0\\fad(0,250)", _ass_escape(label.upper()))


# ---------- įžanga ir pabaiga ----------
def _intro_outro(lines, W, H, duration, acc, handle, intro, outro):
    ref = min(W, H * 0.75)
    full = f"m 0 0 l {W} 0 l {W} {H} l 0 {H}"
    hd = handle.strip()
    if hd and not hd.startswith("@"):
        hd = "@" + hd
    if intro:
        e = INTRO_LEN
        _ev(lines, 10, 0, e, "\\an7\\pos(0,0)\\1c&H00261206&\\alpha&H20&\\bord0\\shad0\\fad(0,350)\\p1", full)
        if hd:
            _ev(lines, 12, 0.25, e, f"\\an5\\move({W // 2},{_f(H * 0.6)},{W // 2},{_f(H * 0.56)},0,400)\\fn{FONT_NAME}"
                f"\\fs{round(ref * 0.05)}\\1c{acc}\\bord0\\shad0\\fsp{round(ref * 0.006)}\\fad(250,300)", _ass_escape(hd))
        # aukso linija išsitiesia
        lw = W * 0.4
        _ev(lines, 12, 0.15, e, f"\\an7\\pos({_f((W - lw) / 2)},{_f(H * 0.52)})\\1c{acc}\\bord0\\shad0"
            f"\\fscx0\\t(0,450,\\fscx100)\\fad(0,300)\\p1", f"m 0 0 l {_f(lw)} 0 l {_f(lw)} 4 l 0 4")
    if outro and duration > OUTRO_LEN + 1:  # duration – su pabaiga (pabaiga pridedama po video)
        a = duration - OUTRO_LEN
        _ev(lines, 10, a, duration + 1, "\\an7\\pos(0,0)\\1c&H00261206&\\alpha&HFF&\\t(0,350,\\alpha&H08&)"
            "\\bord0\\shad0\\p1", full)
        _ev(lines, 12, a + 0.35, duration + 1, f"\\an5\\pos({W // 2},{_f(H * 0.56)})\\fn{FONT_NAME}"
            f"\\fs{round(ref * 0.07)}\\1c{acc}\\bord0\\shad0\\fscx60\\fscy60\\t(0,300,\\fscx100\\fscy100)"
            f"\\fad(300,0)", "AČIŪ!")
        if hd:
            _ev(lines, 12, a + 0.6, duration + 1, f"\\an5\\pos({W // 2},{_f(H * 0.63)})\\fn{FONT_NAME}"
                f"\\fs{round(ref * 0.045)}\\1c&H00FFFFFF&\\bord0\\shad0\\fad(300,0)", _ass_escape(hd))


def animations_ass(plan, W, H, duration, accent_rgb="E9A23B", subs_y=0.72, handle="", intro=False, outro=False,
                   seed=7, gfx=()):
    """ASS failo turinys su visomis animacijomis."""
    rnd = random.Random(seed)
    acc = _c(accent_rgb)
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
             "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
             "MarginL, MarginR, MarginV, Encoding",
             f"Style: A,{FONT_NAME},40,&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for t, kind in (plan or {}).get("stickers", []):
        if kind in STICKERS and t < duration - 0.5:
            _stickers(lines, t, kind, W, H, acc, rnd)
    for t, kind in (plan or {}).get("marks", []):
        kind, _, word = str(kind).partition(":")  # „circle:AUTOMOBILIS“ – žymimas žodis
        if kind in MARKS and t < duration - 0.5:
            _marks(lines, t, kind, W, H, acc, subs_y, rnd, word)
    cards = [(t, txt) for t, txt in (plan or {}).get("cards", []) if t < duration - 0.5 and txt.strip()]
    for i, (t, txt) in enumerate(cards):
        end = min(t + 2.6, cards[i + 1][0] if i + 1 < len(cards) else duration, duration)
        _card(lines, t, end, txt.strip()[:40], i, W, H, acc, rnd)
    for t, kind in (plan or {}).get("fx", []):
        if kind in ("flash", "leak") and t < duration - 0.5:
            _fx_ass(lines, t, kind, W, H, rnd)
    import fxpack
    for item in gfx or ():  # grafikos efektai (žinutės, atsiliepimas, grafikas, pranešimas, skaitiklis)
        if item.get("kind") in fxpack.ASS_KINDS and item["t"] < duration - 0.5:
            lines += fxpack.ass_events(item, W, H, accent_rgb)
    _intro_outro(lines, W, H, duration, acc, handle, intro, outro)
    return "\n".join(lines) + "\n"


# ---------- 🎆 Efektų mozaika ----------
def render_shatter(img, out_path, fps=30):
    """Byrančios kaladėlės: kadras (PIL, jau su filtrais) suskyla į kaladėles, kurios nubyra žemyn
    (permatomas MOV qtrle sluoksnis; po juo video tęsiasi)."""
    import os
    import subprocess
    import tempfile
    from PIL import Image, ImageDraw
    img = img.convert("RGBA")
    w, h = img.size
    cols, rows = 6, 10
    tw, th = math.ceil(w / cols), math.ceil(h / rows)
    rnd = random.Random(11)
    tiles = []
    for r in range(rows):
        for c in range(cols):
            box = (c * tw, r * th, min(w, (c + 1) * tw), min(h, (r + 1) * th))
            tile = img.crop(box)
            ImageDraw.Draw(tile).rectangle((0, 0, tile.width - 1, tile.height - 1), outline=(255, 214, 140, 160))
            tiles.append({"img": tile, "x": box[0], "y": box[1],
                          "delay": 0.12 + (rows - 1 - r) / rows * 0.35 + rnd.uniform(0, 0.15),
                          "vx": rnd.uniform(-0.25, 0.25) * w, "vy": -rnd.uniform(0.05, 0.3) * h,
                          "spin": rnd.uniform(-260, 260)})
    g = h * 2.6
    frames = round(SHATTER_LEN * fps)
    tmp = tempfile.mkdtemp()
    try:
        for fi in range(frames):
            t = fi / fps
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            for tl in tiles:
                dt = t - tl["delay"]
                if dt <= 0:
                    canvas.alpha_composite(tl["img"], (tl["x"], tl["y"]))
                    continue
                x = tl["x"] + tl["vx"] * dt
                y = tl["y"] + tl["vy"] * dt + 0.5 * g * dt * dt
                if y > h:
                    continue
                im = tl["img"].rotate(tl["spin"] * dt, expand=True, resample=Image.BILINEAR)
                canvas.alpha_composite(im, (round(x - (im.width - tl["img"].width) / 2),
                                            round(y - (im.height - tl["img"].height) / 2)))
            canvas.save(os.path.join(tmp, f"f{fi:04d}.png"), compress_level=1)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i",
                        os.path.join(tmp, "f%04d.png"), "-c:v", "qtrle", "-pix_fmt", "argb", out_path], check=True)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return out_path


def _fx_ass(lines, t, kind, W, H, rnd):
    """Blyksnis ir šviesos nutekėjimas (ASS); glitch, nespalvota ir kaladėlės – ffmpeg sluoksniai finish() metu."""
    full = f"m 0 0 l {W} 0 l {W} {H} l 0 {H}"
    if kind == "flash":
        _ev(lines, 11, t, t + 0.45, "\\an7\\pos(0,0)\\1c&H00FFFFFF&\\alpha&H00&\\t(60,450,\\alpha&HFF&)"
            "\\bord0\\shad0\\p1", full)
    elif kind == "leak":
        for i, col in enumerate(("&H003A8CFF&", "&H0066B4FF&", "&H00A0D8FF&")):
            r = W * (0.55 - 0.12 * i)
            x0, x1 = -r * 0.6 + i * 40, W + r * 0.4
            y = H * (0.25 + 0.2 * i)
            _ev(lines, 11, t + i * 0.08, t + 1.5, f"\\an5\\move({_f(x0)},{_f(y)},{_f(x1)},{_f(y - H * 0.1)})"
                f"\\1c{col}\\alpha&H70&\\bord0\\shad0\\blur{round(W * 0.06)}\\fad(300,500)\\p1",
                _ellipse(0, 0, r, r * 0.8))


# ---------- 📱 Nuotraukos skrenda į telefoną ----------
PHONE_LEN = 3.0
_PHONE_WORDS = r"^(nuotrauk|foto|galerij|telefon|prisimin|turin|instagram|tiktok|socialin)"


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def render_phone_burst(thumbs, out_path, W, H, fps=30, accent_rgb="E9A23B"):
    """Permatomas efekto sluoksnis (MOV qtrle, piešiama per pusę mažesne raiška): iš kairio telefono išskrenda
    kortelės su kadrais, pasisklaido ir sukrenta į dešinį telefoną, kurio galerija prisipildo."""
    import os
    import subprocess
    import tempfile
    from PIL import Image, ImageDraw, ImageFilter
    w, h = W // 2 // 2 * 2, H // 2 // 2 * 2
    ref = min(w, h * 0.75)
    rnd = random.Random(3)
    acc = tuple(int(accent_rgb[i:i + 2], 16) for i in (0, 2, 4))
    n = max(1, len(thumbs))
    # kortelės: kadras su baltu rėmeliu ir šešėliu
    cw = round(ref * 0.27)
    cards = []
    for i in range(14):
        im = thumbs[i % n].convert("RGB")
        ch = round(cw * 1.3)
        im = im.resize((cw, ch), Image.LANCZOS) if im.size != (cw, ch) else im
        b = max(3, cw // 22)
        card = Image.new("RGBA", (cw + 2 * b, ch + 2 * b), (255, 255, 255, 255))
        card.paste(im, (b, b))
        sh = Image.new("RGBA", (card.width + 16, card.height + 16), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((8, 10, card.width + 8, card.height + 10), fill=(0, 0, 0, 110))
        sh = sh.filter(ImageFilter.GaussianBlur(5))
        sh.alpha_composite(card, (8, 8))
        cards.append(sh)
    # telefonai
    pw = round(ref * 0.34)
    ph = round(pw * 2.05)

    def phone(screen_fill):
        img = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = pw // 7
        d.rounded_rectangle((0, 0, pw - 1, ph - 1), r, fill=(18, 18, 22, 255), outline=(90, 90, 100, 255), width=2)
        m = max(4, pw // 22)
        d.rounded_rectangle((m, m, pw - m, ph - m), r - m, fill=(0, 0, 0, 255))
        screen_fill(img, (m, m, pw - m, ph - m))
        d.rounded_rectangle((pw * 0.36, m + 4, pw * 0.64, m + 4 + pw // 12), pw // 24, fill=(0, 0, 0, 255))
        return img

    def left_screen(img, box):
        x0, y0, x1, y1 = box
        t = thumbs[0].convert("RGB").resize((x1 - x0, y1 - y0))
        mask = Image.new("L", t.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, t.width - 1, t.height - 1), pw // 9, fill=255)
        img.paste(t, (x0, y0), mask)

    grid_cells = 12

    def right_screen(filled):
        def f(img, box):
            x0, y0, x1, y1 = box
            d = ImageDraw.Draw(img)
            d.rounded_rectangle(box, pw // 9, fill=(14, 14, 16, 255))
            cols, gap = 3, 3
            cs = (x1 - x0 - gap * (cols + 1)) // cols
            top = y0 + pw // 6
            for k in range(min(filled, grid_cells)):
                cx = x0 + gap + (k % cols) * (cs + gap)
                cy = top + gap + (k // cols) * (cs + gap)
                th = thumbs[k % n].convert("RGB").resize((cs, cs))
                img.paste(th, (cx, cy))
            d.rounded_rectangle((x0 + gap, y0 + 6, x0 + gap + cs, y0 + 6 + pw // 14), 3, fill=acc + (255,))
        return f

    left_img = phone(left_screen).rotate(8, expand=True, resample=Image.BICUBIC)
    lp = (round(w * 0.03), round(h * 0.62))
    rp = (round(w * 0.97) - left_img.width, round(h * 0.62))
    lc = (lp[0] + left_img.width * 0.5, lp[1] + left_img.height * 0.35)
    rc = (rp[0] + left_img.width * 0.5, rp[1] + left_img.height * 0.4)
    plan = []
    for i in range(14):
        start = 0.35 + 0.045 * i
        target = (rnd.uniform(0.08, 0.92) * w, rnd.uniform(0.1, 0.5) * h)
        back = 1.55 + 0.05 * i
        plan.append((start, target, rnd.uniform(-28, 28), back, rnd.uniform(-1, 1)))
    frames = round(PHONE_LEN * fps)
    tmp = tempfile.mkdtemp()
    try:
        for fi in range(frames):
            t = fi / fps
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            # telefonai išnyra iš apačios ir pabaigoje nusileidžia
            rise = _ease(t / 0.35) * (1 - _ease((t - (PHONE_LEN - 0.35)) / 0.35))
            dy = round((1 - rise) * h * 0.45)
            arrived = sum(1 for st, tg, rot, bk, dr in plan if t >= bk + 0.42)
            right_img = phone(right_screen(arrived)).rotate(-8, expand=True, resample=Image.BICUBIC)
            canvas.alpha_composite(left_img, (lp[0], lp[1] + dy))
            canvas.alpha_composite(right_img, (rp[0], rp[1] + dy))
            for i, (st, tg, rot, bk, dr) in enumerate(plan):
                if t < st or t >= bk + 0.42:
                    continue
                if t < st + 0.45:  # išskrenda
                    k = _ease((t - st) / 0.45)
                    x = lc[0] + (tg[0] - lc[0]) * k
                    y = lc[1] + (tg[1] - lc[1]) * k - math.sin(k * math.pi) * h * 0.08
                    sc, ang = 0.35 + 0.65 * k, rot * k
                elif t < bk:  # pakimba ir šiek tiek plaukia
                    x, y = tg[0] + dr * (t - st) * 8, tg[1] - (t - st) * 6
                    sc, ang = 1.0, rot
                else:  # sukrenta į dešinį telefoną
                    k = _ease((t - bk) / 0.42)
                    hx, hy = tg[0] + dr * (bk - st) * 8, tg[1] - (bk - st) * 6
                    x = hx + (rc[0] - hx) * k
                    y = hy + (rc[1] + dy - hy) * k
                    sc, ang = 1.0 - 0.75 * k, rot * (1 - k)
                c = cards[i]
                im = c.resize((max(2, round(c.width * sc)), max(2, round(c.height * sc))), Image.BILINEAR)
                im = im.rotate(ang, expand=True, resample=Image.BILINEAR)
                canvas.alpha_composite(im, (round(x - im.width / 2), round(y - im.height / 2)))
            canvas.save(os.path.join(tmp, f"f{fi:04d}.png"), compress_level=1)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i",
                        os.path.join(tmp, "f%04d.png"), "-c:v", "qtrle", "-pix_fmt", "argb", out_path], check=True)
    finally:
        for f in os.listdir(tmp):
            os.unlink(os.path.join(tmp, f))
        os.rmdir(tmp)
    return out_path


# ---------- kur dėti animacijas ----------
def auto_plan(words, gap=2.6):
    """Planas BE AI: lipdukai pagal žodžius, žymėjimai ties svarbiausiais žodžiais, kortelės pagal „pirma, antra…“."""
    plan = {"stickers": [], "marks": [], "cards": [], "phone": [], "fx": []}
    last_s = last_m = -1e9
    mark_kinds = ["circle", "arrow", "underline"]
    for i, (w, a, b) in enumerate(words):
        p = video_editor.plain(w).lower().strip(".,!?…;:\"„“")
        for kind, rx in _STICKER_WORDS:
            if re.search(rx, p) and a - last_s >= gap and len(plan["stickers"]) < 5:
                plan["stickers"].append((round(a, 2), kind))
                last_s = a
                break
        if video_editor.is_key(w) and a - last_m >= 3.0 and len(plan["marks"]) < 4:
            kw = video_editor.plain(w).strip(".,!?…;:\"„“()")
            plan["marks"].append((round(a, 2), mark_kinds[len(plan["marks"]) % 3] + ":" + kw))
            last_m = a
        num = next((n for k, n in _NUMBERS.items() if p.startswith(k)), None)
        if num is None and re.fullmatch(r"\d", p):
            num = int(p)
        if num is not None and len(plan["cards"]) < 5:
            rest = []
            for x in words[i + 1:i + 4]:  # iki 3 žodžių – iki kito skaičiaus ar sakinio pabaigos
                q = video_editor.plain(x[0])
                ql = q.lower().strip(".,!?…;:")
                if any(ql.startswith(k) for k in _NUMBERS) or re.fullmatch(r"\d", ql):
                    break
                if q.strip("–—-.,:;"):
                    rest.append(q.strip(".,!?…;:–—"))
                if re.search(r"[.!?…]$", q):
                    break
            txt = " ".join(r for r in rest if r)
            if txt:
                plan["cards"].append((round(a, 2), f"{num}. {txt}"))
    last_f = -1e9  # efektų mozaika – ties naujais sakiniais, vis kitas efektas
    for ph_ in video_editor.group_phrases(list(words)):
        a = ph_[0][1]
        if a >= 1.0 and a - last_f >= 3.5 and len(plan["fx"]) < 5:
            plan["fx"].append((round(a, 2), FX_ORDER[len(plan["fx"]) % len(FX_ORDER)]))
            last_f = a
    # telefono efektas – tik kai kalbama apie nuotraukas, galeriją, turinį (kitaip jis nieko nereiškia)
    ph = next((a for w, a, b in words if re.search(_PHONE_WORDS, video_editor.plain(w).lower())), None)
    if ph is not None:
        plan["phone"] = [round(ph, 2)]
    if not plan["stickers"] and words:  # bent vienas lipdukas – ties pirmu šauktuku arba pabaigoje
        ex = next((a for w, a, b in words if video_editor.plain(w).endswith("!")), words[-1][1])
        plan["stickers"].append((round(ex, 2), "stars"))
    return plan


def ai_plan(client, words, ai_json):
    """Planas su AI: ai_json(client, system, user) -> dict."""
    lines = " ".join(f"[{a:.1f}] {video_editor.plain(w)}" for w, a, _ in list(words)[:300])
    system = ("You add tasteful animations to a short social video. From the timed transcript ([seconds] word) "
              "choose: stickers (up to 4, at least 3 s apart; kinds: " + json.dumps(STICKERS, ensure_ascii=False) +
              "), hand-drawn marks at the most important moments (up to 4, kinds: " +
              json.dumps(MARKS, ensure_ascii=False) + "; each mark circles or points at ONE key word the speaker "
              "says at that moment – give it in \"word\", 1 word, max 14 letters, from the transcript), and pop-up cards ONLY if the speaker lists points/tips/"
              "steps/prices (up to 5, text max 4 words in the transcript language, start with the number, e.g. "
              "\"1. Kokybė\"), and a moment for a 'photos fly into a phone' effect ONLY if photos, videos, gallery, "
              "memories, social media or content are actually mentioned – otherwise \"phone\": null. Everything you "
              "pick must match what is said (the topic), never decorate randomly; fewer is better than unrelated. Add "
              "up to 5 varied visual effects at "
              "the starts of new sentences, at least 3.5 s apart, each different (kinds: " +
              json.dumps(FX, ensure_ascii=False) + "). Reply only with JSON: {\"stickers\": [{\"time\": 0, \"kind\": \"hearts\"}], "
              "\"marks\": [{\"time\": 0, \"kind\": \"circle\", \"word\": \"...\"}], \"cards\": [{\"time\": 0, \"text\": \"1. ...\"}], \"phone\": null, "
              "\"fx\": [{\"time\": 0, \"kind\": \"shatter\"}]}")
    j = ai_json(client, system, {"transcript": lines})
    end = words[-1][2] if words else 0
    out = {"stickers": [], "marks": [], "cards": []}
    for key, valid, field in (("stickers", STICKERS, "kind"), ("marks", MARKS, "kind"), ("cards", None, "text"),
                              ("fx", FX, "kind")):
        for it in j.get(key, []) if isinstance(j.get(key), list) else []:
            try:
                t, v = float(it["time"]), str(it[field]).strip()
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= t <= end and v and (valid is None or v in valid):
                if key == "marks":
                    v += ":" + str(it.get("word") or "").strip()[:18]
                out[key].append((round(t, 2), v[:40]))
        out[key] = sorted(out[key])[:5]
    try:
        ph = float(j.get("phone"))
        out["phone"] = [round(ph, 2)] if 0 <= ph <= end else []
    except (TypeError, ValueError):
        out["phone"] = []
    return out
