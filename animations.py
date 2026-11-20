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
def _marks(lines, t, kind, W, H, acc, subs_y, rnd):
    ref = min(W, H * 0.75)
    th = max(4, round(ref * 0.012))
    dur = 1.8
    if kind == "circle":
        cx, cy = W * 0.5, H * 0.42
        rx, ry = W * 0.34, H * 0.17
        shape = _ellipse(cx, cy, rx, ry) + " " + _ellipse(cx + rx * 0.04, cy - ry * 0.05, rx * 1.02, ry * 0.97)
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
    else:  # rodyklė iš šono į centrą
        left = rnd.random() < 0.5
        sx, sy = (W * 0.08, H * 0.24) if left else (W * 0.92, H * 0.24)
        ex, ey = W * 0.5 + (-1 if left else 1) * W * 0.12, H * 0.38
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
    if outro and duration > OUTRO_LEN + 2:
        a = duration - OUTRO_LEN
        _ev(lines, 10, a, duration + 1, "\\an7\\pos(0,0)\\1c&H00261206&\\alpha&HFF&\\t(0,400,\\alpha&H28&)"
            "\\bord0\\shad0\\p1", full)
        _ev(lines, 12, a + 0.35, duration + 1, f"\\an5\\pos({W // 2},{_f(H * 0.56)})\\fn{FONT_NAME}"
            f"\\fs{round(ref * 0.07)}\\1c{acc}\\bord0\\shad0\\fscx60\\fscy60\\t(0,300,\\fscx100\\fscy100)"
            f"\\fad(300,0)", "AČIŪ!")
        if hd:
            _ev(lines, 12, a + 0.6, duration + 1, f"\\an5\\pos({W // 2},{_f(H * 0.63)})\\fn{FONT_NAME}"
                f"\\fs{round(ref * 0.045)}\\1c&H00FFFFFF&\\bord0\\shad0\\fad(300,0)", _ass_escape(hd))


def animations_ass(plan, W, H, duration, accent_rgb="E9A23B", subs_y=0.72, handle="", intro=False, outro=False,
                   seed=7):
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
        if kind in MARKS and t < duration - 0.5:
            _marks(lines, t, kind, W, H, acc, subs_y, rnd)
    cards = [(t, txt) for t, txt in (plan or {}).get("cards", []) if t < duration - 0.5 and txt.strip()]
    for i, (t, txt) in enumerate(cards):
        end = min(t + 2.6, cards[i + 1][0] if i + 1 < len(cards) else duration, duration)
        _card(lines, t, end, txt.strip()[:40], i, W, H, acc, rnd)
    _intro_outro(lines, W, H, duration, acc, handle, intro, outro)
    return "\n".join(lines) + "\n"


# ---------- kur dėti animacijas ----------
def auto_plan(words, gap=2.6):
    """Planas BE AI: lipdukai pagal žodžius, žymėjimai ties svarbiausiais žodžiais, kortelės pagal „pirma, antra…“."""
    plan = {"stickers": [], "marks": [], "cards": []}
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
            plan["marks"].append((round(a, 2), mark_kinds[len(plan["marks"]) % 3]))
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
                rest.append(q.strip(".,!?…;:"))
                if re.search(r"[.!?…]$", q):
                    break
            txt = " ".join(r for r in rest if r)
            if txt:
                plan["cards"].append((round(a, 2), f"{num}. {txt}"))
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
              json.dumps(MARKS, ensure_ascii=False) + "), and pop-up cards ONLY if the speaker lists points/tips/"
              "steps/prices (up to 5, text max 4 words in the transcript language, start with the number, e.g. "
              "\"1. Kokybė\"). Reply only with JSON: {\"stickers\": [{\"time\": 0, \"kind\": \"hearts\"}], "
              "\"marks\": [{\"time\": 0, \"kind\": \"circle\"}], \"cards\": [{\"time\": 0, \"text\": \"1. ...\"}]}")
    j = ai_json(client, system, {"transcript": lines})
    end = words[-1][2] if words else 0
    out = {"stickers": [], "marks": [], "cards": []}
    for key, valid, field in (("stickers", STICKERS, "kind"), ("marks", MARKS, "kind"), ("cards", None, "text")):
        for it in j.get(key, []) if isinstance(j.get(key), list) else []:
            try:
                t, v = float(it["time"]), str(it[field]).strip()
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= t <= end and v and (valid is None or v in valid):
                out[key].append((round(t, 2), v[:40]))
        out[key] = sorted(out[key])[:5]
    return out
