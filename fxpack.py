"""Grafikos efektų paketas Reels video.

Su jūsų kadrais (iš anksto piešiamas permatomas sluoksnis, PIL → MOV qtrle): kino juosta, kortelių vėduoklė,
polaroidų lietus, galerijos tinklelis; kadras kadre (ffmpeg grandinė finish() metu).
Grafiniai (ASS vektoriai): žinutės telefone, atsiliepimo kortelė, augantis grafikas, pranešimas, skaitiklis.
Planas: [{"t": s, "kind": ..., "text": ..., "title": ..., "value": ...}] galutinio video laiku.
"""
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile

import video_editor
from video_editor import FONT_DIR, FONT_NAME, _ass_escape, _ass_time

KINDS = {
    "filmstrip": "🎞️ Kino juosta", "fan": "🃏 Kortelių vėduoklė", "polaroids": "📸 Polaroidų lietus",
    "grid": "🖼️ Galerijos tinklelis", "pip": "🔲 Kadras kadre", "chat": "💬 Žinutės telefone",
    "review": "⭐ Atsiliepimo kortelė", "chart": "📈 Augantis grafikas", "notif": "🔔 Pranešimas",
    "counter": "🔢 Skaitiklis", "reel": "🎞️ Prasisukanti kino juosta", "phone3d": "📱 Besisukantis telefonas",
    "frame3d": "🖼 Paveikslo rėmas",
}
OVERLAY_KINDS = ("filmstrip", "fan", "polaroids", "grid")
ASS_KINDS = ("chat", "review", "chart", "notif", "counter")
LEN = {"reel": 1.0, "phone3d": 2.6, "frame3d": 1.8, "filmstrip": 2.6, "fan": 2.6, "polaroids": 2.8, "grid": 2.2, "pip": 2.8, "chat": 3.2, "review": 3.2,
       "chart": 2.8, "notif": 2.8, "counter": 2.2}
SEMI = "Montserrat SemiBold"


def _f(v):
    return f"{v:.0f}"


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _font(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(FONT_DIR, video_editor.FONT_FILES[name]), max(6, round(size)))


# ======================= sluoksniai su kadrais (PIL) =======================
def _framed(img, cw, ch, border, bottom=0):
    from PIL import Image, ImageDraw, ImageFilter
    im = img.convert("RGB").resize((cw, ch), Image.LANCZOS)
    card = Image.new("RGBA", (cw + 2 * border, ch + 2 * border + bottom), (255, 255, 255, 255))
    card.paste(im, (border, border))
    sh = Image.new("RGBA", (card.width + 18, card.height + 18), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((9, 12, card.width + 9, card.height + 12), fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(6))
    sh.alpha_composite(card, (9, 9))
    return sh


def _paste(canvas, im, cx, cy, ang=0.0, scale=1.0, alpha=1.0):
    from PIL import Image
    if scale != 1.0:
        im = im.resize((max(2, round(im.width * scale)), max(2, round(im.height * scale))), Image.BILINEAR)
    if ang:
        im = im.rotate(ang, expand=True, resample=Image.BILINEAR)
    if alpha < 0.999:
        a = im.getchannel("A").point(lambda v: round(v * max(0.0, alpha)))
        im = im.copy()
        im.putalpha(a)
    canvas.alpha_composite(im, (round(cx - im.width / 2), round(cy - im.height / 2)))


def render_overlay(kind, thumbs, out_path, W, H, fps=30, accent_rgb="E9A23B", text=""):
    """Permatomas efekto sluoksnis per pusę raiškos (uždedamas su scale=W:H)."""
    from PIL import Image, ImageDraw
    w, h = W // 2 // 2 * 2, H // 2 // 2 * 2
    ref = min(w, h * 0.75)
    rnd = random.Random(5)
    n = max(1, len(thumbs))
    dur = LEN[kind]
    frames = round(dur * fps)
    fade = lambda t: min(1.0, t / 0.25, (dur - t) / 0.3)  # noqa: E731
    prep = {}
    if kind == "filmstrip":  # juosta su skylutėmis, kadrai joje, prabėga per ekraną
        ch = round(h * 0.17)
        cw = round(ch * 0.62) if h > w else round(ch * 1.6)
        pad = round(ch * 0.2)
        k = 9
        sw = k * (cw + pad) + pad
        strip = Image.new("RGBA", (sw, ch + 2 * pad), (16, 14, 12, 255))
        d = ImageDraw.Draw(strip)
        hole = max(3, pad // 2)
        for x in range(pad // 2, sw, hole * 3):
            d.rounded_rectangle((x, pad // 4, x + hole * 1.6, pad // 4 + hole), 2, fill=(230, 220, 200, 255))
            d.rounded_rectangle((x, ch + pad + pad // 4, x + hole * 1.6, ch + pad + pad // 4 + hole), 2,
                                fill=(230, 220, 200, 255))
        for i in range(k):
            strip.paste(thumbs[i % n].convert("RGB").resize((cw, ch)), (pad + i * (cw + pad), pad))
        prep["strip"] = strip.rotate(-7, expand=True, resample=Image.BICUBIC)
    elif kind in ("fan", "polaroids"):
        cw = round(ref * (0.36 if kind == "fan" else 0.34))
        chh = round(cw * (1.3 if kind == "fan" else 1.0))
        b = max(3, cw // 18)
        prep["cards"] = [_framed(thumbs[i % n], cw, chh, b, (round(cw * 0.22) if kind == "polaroids" else 0))
                         for i in range(7 if kind == "fan" else 6)]
        if kind == "polaroids":
            prep["targets"] = [(w * 0.5 + rnd.uniform(-0.18, 0.18) * w, h * 0.4 + rnd.uniform(-0.08, 0.08) * h,
                                rnd.uniform(-20, 20)) for _ in prep["cards"]]
    elif kind == "grid":
        g = round(ref * 0.02)
        cw, chh = (w - 4 * g) // 3, (h - 4 * g) // 3
        prep["tiles"] = [thumbs[i % n].convert("RGB").resize((cw, chh), Image.LANCZOS).convert("RGBA")
                         for i in range(9)]
        prep["g"], prep["cw"], prep["ch"] = g, cw, chh
    tmp = tempfile.mkdtemp()
    try:
        for fi in range(frames):
            t = fi / fps
            cv = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            if kind == "filmstrip":
                st = prep["strip"]
                x = w + st.width / 2 - (w + st.width) * (t / dur)
                _paste(cv, st, x, h * 0.42, alpha=fade(t))
            elif kind == "fan":
                op = _ease(t / 0.55) * (1 - _ease((t - (dur - 0.5)) / 0.5))
                px, py = w / 2, h * 0.98 + (1 - min(1.0, t / 0.3)) * h * 0.2
                R = h * 0.36
                cards = prep["cards"]
                for i, c in enumerate(cards):
                    a = (-36 + 72 * i / (len(cards) - 1)) * op
                    rad = math.radians(a)
                    _paste(cv, c, px + math.sin(rad) * R, py - math.cos(rad) * R, -a, alpha=min(1.0, t / 0.2))
            elif kind == "polaroids":
                for i, (c, (tx, ty, rot)) in enumerate(zip(prep["cards"], prep["targets"])):
                    st = 0.12 + i * 0.22
                    if t < st:
                        continue
                    k = _ease((t - st) / 0.45)
                    y = -c.height + (ty + c.height) * k
                    _paste(cv, c, tx, y, rot * (0.4 + 0.6 * k), 1.25 - 0.25 * k,
                           alpha=1.0 - _ease((t - (dur - 0.35)) / 0.35))
            elif kind == "grid":
                g, cw, chh = prep["g"], prep["cw"], prep["ch"]
                bg_a = min(1.0, t / 0.2, (dur - t) / 0.25)
                ImageDraw.Draw(cv).rectangle((0, 0, w, h), fill=(6, 18, 38, round(235 * max(0.0, bg_a))))
                order = [4, 0, 1, 2, 5, 8, 7, 6, 3]
                for oi, idx in enumerate(order):
                    st = 0.05 * oi
                    k = _ease((t - st) / 0.3) * (1 - _ease((t - (dur - 0.35 + 0.02 * oi)) / 0.3))
                    if k <= 0.01:
                        continue
                    r, c = divmod(idx, 3)
                    cx = g + c * (cw + g) + cw / 2
                    cy = g + r * (chh + g) + chh / 2
                    _paste(cv, prep["tiles"][idx], cx, cy, 0, 0.6 + 0.4 * k, alpha=k)
            cv.save(os.path.join(tmp, f"f{fi:04d}.png"), compress_level=1)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i",
                        os.path.join(tmp, "f%04d.png"), "-c:v", "qtrle", "-pix_fmt", "argb", out_path], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_path


def device_png(out_path, W, H):
    """„Kadras kadre“ prietaisas (telefonas vertikaliam, monitorius horizontaliam video), permatomas ekranas.
    Grąžina (kelias, ekrano dėžutė x, y, w, h)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if H > W:
        sw = round(W * 0.56) // 2 * 2
        sh = round(sw * H / W) // 2 * 2
        sx, sy = (W - sw) // 2, round(H * 0.17)
        b = round(sw * 0.045)
        d.rounded_rectangle((sx - b, sy - b, sx + sw + b, sy + sh + b), round(sw * 0.12), fill=(18, 18, 22, 255),
                            outline=(120, 120, 130, 255), width=3)
        d.rounded_rectangle((sx + sw * 0.36, sy - b * 0.6, sx + sw * 0.64, sy + b * 0.2), b // 2, fill=(0, 0, 0, 255))
    else:
        sw = round(W * 0.62) // 2 * 2
        sh = round(sw * H / W) // 2 * 2
        sx, sy = (W - sw) // 2, round(H * 0.12)
        b = round(sw * 0.025)
        d.rounded_rectangle((sx - b, sy - b, sx + sw + b, sy + sh + b), b, fill=(18, 18, 22, 255),
                            outline=(120, 120, 130, 255), width=3)
        d.polygon([(W / 2 - sw * 0.08, sy + sh + b), (W / 2 + sw * 0.08, sy + sh + b),
                   (W / 2 + sw * 0.12, sy + sh + b + H * 0.07), (W / 2 - sw * 0.12, sy + sh + b + H * 0.07)],
                  fill=(30, 30, 36, 255))
    d.rectangle((sx, sy, sx + sw - 1, sy + sh - 1), fill=(0, 0, 0, 0))
    img.save(out_path)
    return out_path, (sx, sy, sw, sh)


def pip_chains(inp, out, t, W, H, fps, device_path, box, name="pp"):
    """Kadras kadre: lango metu video sumažėja į prietaiso ekraną, aplink – sulietas tamsesnis tas pats vaizdas."""
    sx, sy, sw, sh = box
    a, d = t, LEN["pip"]
    return [
        f"{inp}split[{name}m][{name}c]",
        f"[{name}c]trim=start={a:.3f}:end={a + d:.3f},setpts=PTS-STARTPTS,split[{name}b][{name}s]",
        f"[{name}b]scale={W // 4 // 2 * 2}:{H // 4 // 2 * 2},boxblur=8:2,eq=brightness=-0.18:saturation=0.8,"
        f"scale={W}:{H},setsar=1[{name}bg]",
        f"[{name}s]scale={sw}:{sh},setsar=1[{name}sm]",
        f"[{name}bg][{name}sm]overlay={sx}:{sy}[{name}x]",
        f"movie='{device_path}',loop=loop=-1:size=1:start=0,fps={fps},trim=duration={d + 0.5:.3f},format=rgba[{name}dv]",
        f"[{name}x][{name}dv]overlay=0:0:shortest=1,format=yuva420p,fade=t=in:st=0:d=0.3:alpha=1,"
        f"fade=t=out:st={d - 0.3:.3f}:d=0.3:alpha=1,setpts=PTS+{a:.3f}/TB[{name}o]",
        f"[{name}m][{name}o]overlay=eof_action=pass:format=auto{out}",
    ]


def reel_geometry(W, H):
    """Prasisukančios kino juostos matmenys: šoninės juostos plotis, kadro aukštis, tarpas, kopijų skaičius."""
    bw = round(W * 0.09) // 2 * 2
    fw = W - 2 * bw
    fh = round(fw * H / W) // 2 * 2
    gap = round(H * 0.035) // 2 * 2
    return bw, fw, fh, gap, 4


def reel_png(out_path, W, H):
    """Kino juostos „skylutės“ šoninėse juostose (permatomas paveikslėlis per visą juostos aukštį)."""
    from PIL import Image, ImageDraw
    bw, fw, fh, gap, n = reel_geometry(W, H)
    th = n * (fh + gap)
    img = Image.new("RGBA", (W, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    hw, hh = round(bw * 0.42), round(bw * 0.3)
    step = round(hh * 2.1)
    for x0 in ((bw - hw) // 2, W - bw + (bw - hw) // 2):
        for y in range(step // 2, th, step):
            d.rounded_rectangle((x0, y, x0 + hw, y + hh), max(2, hh // 4), fill=(235, 230, 220, 255))
    for k in range(n):  # plonas rėmelis aplink kiekvieną kadrą
        y = k * (fh + gap) + gap // 2
        d.rectangle((bw - 2, y - 2, bw + fw + 1, y + fh + 1), outline=(40, 40, 40, 255), width=2)
    img.save(out_path)
    return out_path


def reel_chains(inp, out, t, W, H, fps, png_path, name="rl"):
    """🎞️ Prasisukanti kino juosta: vaizdas tampa kino juosta, kuri greitai prasisuka (su judesio suliejimu)."""
    bw, fw, fh, gap, n = reel_geometry(W, H)
    a, d = t, LEN["reel"]
    span = 2 * (fh + gap)
    return [
        f"{inp}split[{name}m][{name}c]",
        f"[{name}c]trim=start={a:.3f}:end={a + d:.3f},setpts=PTS-STARTPTS,scale={fw}:{fh},setsar=1,"
        f"pad={fw}:{fh + gap}:0:{gap // 2}:black,split={n}" + "".join(f"[{name}{i}]" for i in range(n)),
        "".join(f"[{name}{i}]" for i in range(n)) + f"vstack=inputs={n},pad={W}:ih:{bw}:0:black[{name}st]",
        f"movie='{png_path}',loop=loop=-1:size=1:start=0,fps={fps},trim=duration={d + 0.3:.3f},format=rgba[{name}h]",
        f"[{name}st][{name}h]overlay=0:0:shortest=1,crop={W}:{H}:0:'{span}*(0.5-0.5*cos(PI*min(t/{d:.3f}\\,1)))',"
        f"gblur=sigma=0.5:sigmaV=9,format=yuva420p,setpts=PTS+{a:.3f}/TB[{name}o]",
        f"[{name}m][{name}o]overlay=eof_action=pass:format=auto{out}",
    ]


# ======================= grafiniai (ASS) =======================
def _rrect(w, h, r):
    return (f"m {_f(r)} 0 l {_f(w - r)} 0 b {_f(w)} 0 {_f(w)} 0 {_f(w)} {_f(r)} l {_f(w)} {_f(h - r)} "
            f"b {_f(w)} {_f(h)} {_f(w)} {_f(h)} {_f(w - r)} {_f(h)} l {_f(r)} {_f(h)} b 0 {_f(h)} 0 {_f(h)} 0 "
            f"{_f(h - r)} l 0 {_f(r)} b 0 0 0 0 {_f(r)} 0")


def _circle(r):
    k = 0.5523
    return (f"m {_f(r)} 0 b {_f(r + k * r)} 0 {_f(2 * r)} {_f(r - k * r)} {_f(2 * r)} {_f(r)} "
            f"b {_f(2 * r)} {_f(r + k * r)} {_f(r + k * r)} {_f(2 * r)} {_f(r)} {_f(2 * r)} "
            f"b {_f(r - k * r)} {_f(2 * r)} 0 {_f(r + k * r)} 0 {_f(r)} b 0 {_f(r - k * r)} {_f(r - k * r)} 0 {_f(r)} 0")


def _star(r):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = math.pi * i / 5 - math.pi / 2
        pts.append((r + math.cos(a) * rr, r + math.sin(a) * rr))
    return "m " + " l ".join(f"{_f(x)} {_f(y)}" for x, y in pts)


def _wrap(text, font, size, max_w):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        nxt = (cur + " " + wd).strip()
        if cur and video_editor.text_width(font, size, nxt) > max_w:
            lines.append(cur)
            cur = wd
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines[:4]


def _c(rgb):
    return f"&H00{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&".upper()


def _light(rgb):
    r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b > 150


def ass_events(item, W, H, accent_rgb):
    """ASS eilutės vienam grafiniam efektui (stilius „A“, \\an7 koordinatės)."""
    t, kind = item["t"], item["kind"]
    d = LEN[kind]
    ref = min(W, H * 0.75)
    acc = _c(accent_rgb)
    acc_txt = "&H00101010&" if _light(accent_rgb) else "&H00FFFFFF&"
    out = []

    def ev(layer, a, b, tags, text):
        out.append(f"Dialogue: {layer},{_ass_time(max(0.0, a))},{_ass_time(b)},A,,0,0,0,,{{{tags}}}{text}")

    e = t + d
    if kind == "chat":  # klausimas (kairėje, pilkas) ir atsakymas (dešinėje, akcento spalva)
        q = (item.get("title") or "Ar tikrai taip galima?").strip()
        ans = (item.get("text") or "Taip! Parodysiu kaip 👇").replace("👇", "").strip()
        fs = round(ref * 0.056)
        maxw = W * 0.66
        y = H * 0.2
        for i, (msg, left) in enumerate(((q, True), (ans, False))):
            lines = _wrap(msg, SEMI, fs, maxw)
            tw = max(video_editor.text_width(SEMI, fs, ln) for ln in lines)
            pad = fs * 0.7
            bw, bh = tw + 2 * pad, len(lines) * fs * 1.3 + pad * 1.4
            x = W * 0.07 if left else W * 0.93 - bw
            a = t + (0.15 if left else 1.1)
            if not left:  # „rašo…“ taškeliai prieš atsakymą
                dw, dh = fs * 2.8, fs * 1.6
                ev(7, t + 0.55, a, f"\\an7\\pos({_f(W * 0.93 - dw)},{_f(y)})\\1c{acc}\\bord0\\shad0\\fad(120,80)\\p1",
                   _rrect(dw, dh, dh / 2))
                for k in range(3):
                    ev(8, t + 0.55, a, f"\\an5\\pos({_f(W * 0.93 - dw + dw * (0.28 + 0.22 * k))},{_f(y + dh / 2)})"
                       f"\\1c{acc_txt}\\bord0\\shad0\\alpha&H80&\\t({k * 150},{k * 150 + 200},\\alpha&H00&)\\p1",
                       _circle(fs * 0.16))
            col = "&H00EDEDED&" if left else acc
            tcol = "&H00151515&" if left else acc_txt
            mv = f"\\move({_f(x + (-40 if left else 40))},{_f(y)},{_f(x)},{_f(y)},0,200)"
            ev(7, a, e, f"\\an7{mv}\\1c{col}\\bord0\\shad3\\4c&H64000000&\\fad(150,250)\\p1", _rrect(bw, bh, fs * 0.8))
            for li, ln in enumerate(lines):
                ev(8, a, e, f"\\an7\\move({_f(x + pad + (-40 if left else 40))},{_f(y + pad * 0.7 + li * fs * 1.3)},"
                   f"{_f(x + pad)},{_f(y + pad * 0.7 + li * fs * 1.3)},0,200)\\fn{SEMI}\\fs{fs}\\1c{tcol}\\bord0\\shad0"
                   f"\\fad(150,250)", _ass_escape(ln))
            y += bh + fs * 0.8
    elif kind == "review":  # atsiliepimo kortelė: avataras, vardas, žvaigždutės, citata
        quote = (item.get("text") or "Labai rekomenduoju – puikus darbas!").strip()
        name = (item.get("title") or "Klientė").strip()
        fs = round(ref * 0.052)
        cw = W * 0.88
        lines = _wrap(f"„{quote}“", "Playfair Display Italic", fs * 1.05, cw - fs * 2)
        ch = fs * 4.6 + len(lines) * fs * 1.45
        x, y = (W - cw) / 2, H * 0.2
        mv = f"\\move({_f(x)},{_f(y - 30)},{_f(x)},{_f(y)},0,250)"
        ev(6, t, e, f"\\an7{mv}\\1c&H00FFFFFF&\\bord0\\shad4\\4c&H64000000&\\fad(200,300)\\p1", _rrect(cw, ch, fs))
        r = fs * 1.1
        ev(7, t, e, f"\\an7\\move({_f(x + fs)},{_f(y - 30 + fs * 0.8)},{_f(x + fs)},{_f(y + fs * 0.8)},0,250)"
           f"\\1c{acc}\\bord0\\shad0\\fad(200,300)\\p1", _circle(r))
        ev(8, t, e, f"\\an5\\move({_f(x + fs + r)},{_f(y - 30 + fs * 0.8 + r)},{_f(x + fs + r)},{_f(y + fs * 0.8 + r)},0,250)"
           f"\\fn{FONT_NAME}\\fs{round(fs * 1.1)}\\1c{acc_txt}\\bord0\\shad0\\fad(200,300)", _ass_escape(name[:1].upper()))
        ev(8, t, e, f"\\an4\\pos({_f(x + fs * 1.6 + 2 * r)},{_f(y + fs * 0.8 + r * 0.55)})\\fn{FONT_NAME}\\fs{fs}"
           f"\\1c&H00151515&\\bord0\\shad0\\fad(200,300)", _ass_escape(name))
        for k in range(5):  # žvaigždutės užsipildo po vieną
            sx = x + fs * 1.6 + 2 * r + k * fs * 1.25
            sy = y + fs * 0.8 + r * 1.1
            ev(8, t, e, f"\\an7\\pos({_f(sx)},{_f(sy)})\\1c&H00D0D0D0&\\bord0\\shad0\\fad(200,300)\\p1", _star(fs * 0.5))
            ev(9, t + 0.35 + k * 0.15, e, f"\\an7\\pos({_f(sx)},{_f(sy)})\\1c&H0016B8F5&\\bord0\\shad0"
               f"\\fscx30\\fscy30\\t(0,180,\\fscx100\\fscy100)\\fad(0,300)\\p1", _star(fs * 0.5))
        for li, ln in enumerate(lines):
            ev(8, t + 0.25, e, f"\\an7\\pos({_f(x + fs)},{_f(y + fs * 3.6 + li * fs * 1.45)})\\fnPlayfair Display\\i1"
               f"\\fs{round(fs * 1.05)}\\1c&H00303030&\\bord0\\shad0\\fad(250,300)", _ass_escape(ln))
    elif kind == "chart":  # stulpeliai išauga, viršuje – reikšmė
        val = (item.get("value") or "+50%").strip()
        label = (item.get("title") or "").strip()
        fs = round(ref * 0.06)
        cw, ch = W * 0.7, H * 0.26
        x, y = (W - cw) / 2, H * 0.2
        ev(6, t, e, f"\\an7\\pos({_f(x)},{_f(y)})\\1c&H00261206&\\alpha&H30&\\bord0\\shad0\\fad(200,300)\\p1",
           _rrect(cw, ch, fs * 0.6))
        heights = [0.28, 0.42, 0.58, 0.9]
        bw = cw * 0.14
        for i, hk in enumerate(heights):
            bx = x + cw * 0.12 + i * (cw * 0.76 - bw) / 3
            bh = (ch - fs * 2.6) * hk
            col = acc if i == 3 else "&H00B0A090&"
            ev(7, t + 0.1 + i * 0.12, e, f"\\an1\\pos({_f(bx)},{_f(y + ch - fs * 0.6)})\\1c{col}\\bord0\\shad0"
               f"\\fscy0\\t(0,450,\\fscy100)\\fad(0,300)\\p1", _rrect(bw, bh, bw * 0.15))
        ev(8, t + 0.65, e, f"\\an5\\pos({_f(W / 2)},{_f(y + fs * 1.1)})\\fn{FONT_NAME}\\fs{round(fs * 1.4)}\\1c{acc}"
           f"\\bord2\\3c&H00101010&\\shad0\\fscx40\\fscy40\\t(0,200,\\fscx100\\fscy100)\\fad(0,300)", _ass_escape(val))
        if label:
            ev(8, t + 0.65, e, f"\\an5\\pos({_f(W / 2)},{_f(y + ch + fs * 0.9)})\\fn{SEMI}\\fs{round(fs * 0.85)}"
               f"\\1c&H00FFFFFF&\\bord2\\3c&H00101010&\\shad0\\fad(150,300)", _ass_escape(label[:40]))
    elif kind == "notif":  # telefono pranešimas viršuje
        title = (item.get("title") or "Naujas užsakymas!").strip()
        body = (item.get("text") or "Klientas ką tik užsisakė jūsų paslaugą").strip()
        fs = round(ref * 0.048)
        bw, bh = W * 0.92, fs * 4.2
        x, y = (W - bw) / 2, H * 0.06
        mv = f"\\move({_f(x)},{_f(-bh - 20)},{_f(x)},{_f(y)},0,300)"
        ev(9, t, e, f"\\an7{mv}\\1c&H00F4F4F4&\\alpha&H10&\\bord0\\shad4\\4c&H64000000&\\t({_f(d * 1000 - 300)},"
           f"{_f(d * 1000)},\\alpha&HFF&)\\p1", _rrect(bw, bh, fs * 1.1))
        ic = fs * 2.3
        ev(10, t, e, f"\\an7\\move({_f(x + fs * 0.8)},{_f(-bh - 20 + fs * 0.95)},{_f(x + fs * 0.8)},{_f(y + fs * 0.95)},0,300)"
           f"\\1c{acc}\\bord0\\shad0\\fad(0,300)\\p1", _rrect(ic, ic, ic * 0.24))
        tx = x + fs * 1.6 + ic
        for txt, yy, fnt, col, size in ((title, fs * 1.05, FONT_NAME, "&H00151515&", fs),
                                        (body, fs * 2.45, SEMI, "&H00404040&", round(fs * 0.9)),
                                        ("dabar", fs * 1.05, SEMI, "&H00909090&", round(fs * 0.8))):
            xx = x + bw - fs * 0.9 if txt == "dabar" else tx
            an = "\\an6" if txt == "dabar" else "\\an4"
            ln = _wrap(txt, fnt, size, bw - (tx - x) - fs * 3)[0] if txt != "dabar" else txt
            ev(10, t, e, f"{an}\\move({_f(xx)},{_f(-bh - 20 + yy)},{_f(xx)},{_f(y + yy)},0,300)\\fn{fnt}\\fs{size}"
               f"\\1c{col}\\bord0\\shad0\\fad(0,300)", _ass_escape(ln))
    elif kind == "counter":  # skaičius greitai suka iki paminėto
        raw = str(item.get("value") or "100")
        m = re.search(r"\d[\d\s.,]*", raw)
        num = int(re.sub(r"\D", "", m.group(0))) if m else 100
        suffix = raw[m.end():].strip() if m else ""
        label = (item.get("title") or "").strip()
        fs = round(ref * 0.16)
        steps = 24
        cx, cy = W / 2, H * 0.34
        for k in range(steps):
            v = round(num * _ease((k + 1) / steps))
            a = t + 1.1 * k / steps
            b = t + 1.1 * (k + 1) / steps if k < steps - 1 else e
            pop = "\\fscx120\\fscy120\\t(0,200,\\fscx100\\fscy100)\\fad(0,300)" if k == steps - 1 else ""
            ev(8, a, b, f"\\an5\\pos({_f(cx)},{_f(cy)})\\fn{FONT_NAME}\\fs{fs}\\1c{acc}\\bord{max(3, fs // 18)}"
               f"\\3c&H00101010&\\shad3{pop}", f"{v:,}".replace(",", " ") + (" " + _ass_escape(suffix) if suffix else ""))
        if label:
            ev(8, t + 0.2, e, f"\\an5\\pos({_f(cx)},{_f(cy + fs * 0.85)})\\fn{FONT_NAME}\\fs{round(fs * 0.3)}"
               f"\\1c&H00FFFFFF&\\bord3\\3c&H00101010&\\shad0\\fad(200,300)", _ass_escape(label.upper()[:30]))
    return out


# ======================= kur ir kokius efektus dėti =======================
def auto_plan(words, allowed, busy=(), limit=4, gap=4.0):
    """Planas BE AI: pagal žodžius (skaičiai, %, klausimai, atsiliepimai, užsakymai…), likusiems – efektai su kadrais."""
    allowed = [k for k in allowed if k in KINDS]
    if not allowed or not words:
        return []
    plain = [video_editor.plain(w) for w, _, _ in words]
    sents, cur = [], []
    for i, (w, a, b) in enumerate(words):
        cur.append(i)
        if re.search(r"[.!?…]$", plain[i]):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    text_of = lambda idx: " ".join(plain[i] for i in idx).strip()  # noqa: E731
    plan, used = [], set()

    def free(t):
        return all(abs(t - x) >= gap for x in [p["t"] for p in plan] + list(busy))

    for si, idx in enumerate(sents):
        a = words[idx[0]][1]
        s = text_of(idx)
        low = s.lower()
        cand = None
        num = re.search(r"(\d[\d\s]*)\s*(%|proc|kart)", low)
        big = re.search(r"\b(\d{2,6})\b", s)
        if "chart" in allowed and "chart" not in used and num:
            cand = {"kind": "chart", "value": ("+" if "%" in low or "proc" in low else "×") + num.group(1).strip()
                    + ("%" if "%" in low or "proc" in low else ""), "title": s[:40]}
        elif "counter" in allowed and "counter" not in used and big:
            after = s[big.end():].split()
            cand = {"kind": "counter", "value": big.group(1), "title": after[0] if after else ""}
        elif "chat" in allowed and "chat" not in used and s.endswith("?") and si + 1 < len(sents):
            cand = {"kind": "chat", "title": s, "text": text_of(sents[si + 1])}
        elif "review" in allowed and "review" not in used and re.search(r"atsiliep|rekomend|klient|patink", low):
            cand = {"kind": "review", "text": s, "title": "Klientė"}
        elif "notif" in allowed and "notif" not in used and re.search(r"užsakym|pranešim|žinut|pirk|registr", low):
            cand = {"kind": "notif", "title": "Naujas užsakymas!", "text": s}
        if cand and free(a):
            cand["t"] = round(a, 2)
            plan.append(cand)
            used.add(cand["kind"])
    frame_kinds = [k for k in ("phone3d", "reel", "frame3d", "filmstrip", "fan", "polaroids", "grid", "pip") if k in allowed]
    for idx in sents[1:]:  # likusios vietos – efektai su kadrais, vis kitokie
        if len(plan) >= limit or not frame_kinds:
            break
        a = words[idx[0]][1]
        k = next((x for x in frame_kinds if x not in used), None)
        if k and free(a):
            plan.append({"kind": k, "t": round(a, 2)})
            used.add(k)
    return sorted(plan, key=lambda p: p["t"])[:limit]


def ai_plan(client, words, allowed, ai_json, busy=(), limit=4):
    lines = " ".join(f"[{a:.1f}] {video_editor.plain(w)}" for w, a, _ in list(words)[:300])
    kinds = {k: v for k, v in KINDS.items() if k in allowed}
    system = ("You are a motion designer for short social videos. From the timed transcript choose up to "
              f"{limit} graphic effects (at least 4 s apart, each kind at most once, fitting what is said). Kinds: "
              + json.dumps(kinds, ensure_ascii=False) + ". For chat: title = the question, text = short answer; "
              "review: text = short client quote, title = client first name; chart: value like \"+50%\" or \"×3\", "
              "title = short label; notif: title = short notification title, text = body; counter: value = the "
              "number (+ unit), title = what is counted; others need no text. Use chart/counter ONLY for numbers the "
              "speaker really says, review ONLY for a real client opinion, chat ONLY for a real question, notif ONLY "
              "for orders/messages/sign-ups – never invent; if nothing fits, return fewer effects. Texts in the transcript language "
              "with correct diacritics, short. Reply only with JSON: {\"effects\": [{\"time\": 0, \"kind\": \"\", "
              "\"title\": \"\", \"text\": \"\", \"value\": \"\"}]}")
    j = ai_json(client, system, {"transcript": lines, "avoid_times": list(busy)})
    end = words[-1][2] if words else 0
    out = []
    for it in j.get("effects", []) if isinstance(j.get("effects"), list) else []:
        try:
            t, k = float(it["time"]), str(it["kind"])
        except (KeyError, TypeError, ValueError):
            continue
        if k in kinds and 0 <= t <= end and all(abs(t - p["t"]) >= 3.5 for p in out):
            out.append({"t": round(t, 2), "kind": k, **{f: str(it.get(f, ""))[:120] for f in ("title", "text", "value")}})
    return sorted(out, key=lambda p: p["t"])[:limit]


# ======================= 📱 3D telefonas / 🖼 paveikslo rėmas (kadrai piešiami PIL – realistiška perspektyva) ========
SPIN_KINDS = ("phone3d", "frame3d")


def _persp_coeffs(src, dst):
    """PIL PERSPECTIVE koeficientai: išvesties taškas -> įvesties taškas (dst – kur atsiduria src kampai)."""
    import numpy as np
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(m, dtype=float)
    b = np.array([p for uv in src for p in uv], dtype=float)
    return np.linalg.solve(a, b).tolist()


def _proj(pts, ang, cx, cy, dist):
    """3D taškai (x, y, z) pasukti apie vertikalią ašį ir suprojektuoti į ekraną."""
    import math
    c, s = math.cos(ang), math.sin(ang)
    out = []
    for x, y, z in pts:
        xr, zr = x * c + z * s, -x * s + z * c
        f = dist / (dist - zr)
        out.append((cx + xr * f, cy + y * f))
    return out


def _spin_track(u, kind="frame3d"):
    """Animacija (0..1): mastelis, pasukimo kampas (rad) ir kiek grįžta tikras video (0..1).
    📱 telefonas: sumažėja → apsisuka 360° apie savo ašį → mažėdamas dingsta, po juo vėl matosi video.
    🖼 rėmas: išsitraukia → pasisuka į abi puses → grįžta per visą ekraną."""
    import math
    e = lambda x: 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))  # noqa: E731
    small = 0.6
    if kind == "phone3d":
        if u < 0.2:
            sc = 1 - (1 - small) * e(u / 0.2)
        else:
            sc = small * (1 - e((u - 0.55) / 0.35)) if u > 0.55 else small
        ang = 2 * math.pi * e((u - 0.15) / 0.6)
        return sc, ang, e((u - 0.8) / 0.2)
    if u < 0.2:
        sc = 1 - (1 - small) * e(u / 0.2)
    elif u > 0.8:
        sc = small + (1 - small) * e((u - 0.8) / 0.2)
    else:
        sc = small * (1 + 0.015 * math.sin((u - 0.2) * 9))
    k = max(0.0, min(1.0, (u - 0.14) / 0.72))
    ang = math.radians(48) * math.sin(2 * math.pi * k) * (1 - 0.35 * k) * (1 if 0 < k < 1 else 0)
    return sc, ang, 0.0


def _phone_back(fw, fh, W):
    """Telefono nugarėlė (matoma apsisukus): matinis grafitas, kamerų blokas su trimis objektyvais."""
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np
    r = round(W * 0.13)
    gy = np.linspace(0, 1, fh)[:, None] * np.ones((1, fw))
    gx = np.linspace(0, 1, fw)[None, :] * np.ones((fh, 1))
    lum = 52 + 22 * (1 - gy) - 14 * gx
    img = Image.fromarray(np.dstack([lum * 0.95, lum * 0.97, lum, np.full_like(lum, 255)]).astype("uint8"), "RGBA")
    mask = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fw - 1, fh - 1), r, fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, fw - 3, fh - 3), r - 2, outline=(150, 152, 160, 255), width=3)
    # kamerų blokas (žiūrint iš nugaros – kairėje viršuje; paveiksle veidrodiškai – dešinėje)
    bs = round(fw * 0.4)
    x1, y1 = fw - round(fw * 0.05), round(fw * 0.05)
    x0, y0 = x1 - bs, y1
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((x0, y0 + 6, x0 + bs, y0 + bs + 6), round(bs * 0.24), fill=(0, 0, 0, 120))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    d.rounded_rectangle((x0, y0, x0 + bs, y0 + bs), round(bs * 0.24), fill=(70, 72, 78, 255),
                        outline=(120, 122, 130, 255), width=2)
    lr = bs * 0.2
    for lx, ly in ((0.3, 0.28), (0.3, 0.72), (0.72, 0.5)):
        cx_, cy_ = x0 + bs * (1 - lx), y0 + bs * ly
        d.ellipse((cx_ - lr, cy_ - lr, cx_ + lr, cy_ + lr), fill=(28, 28, 32, 255), outline=(150, 152, 160, 255), width=3)
        d.ellipse((cx_ - lr * 0.55, cy_ - lr * 0.55, cx_ + lr * 0.55, cy_ + lr * 0.55), fill=(10, 12, 22, 255))
        d.ellipse((cx_ - lr * 0.3, cy_ - lr * 0.4, cx_ - lr * 0.05, cy_ - lr * 0.15), fill=(90, 110, 160, 255))
    fl = bs * 0.07  # blykstė
    d.ellipse((x0 + bs * 0.28 - fl, y0 + bs * 0.5 - fl, x0 + bs * 0.28 + fl, y0 + bs * 0.5 + fl), fill=(235, 225, 200, 255))
    return img


def _phone_front(screen, W, H, kind, fade=1.0):
    """Priekinė telefono / rėmo pusė su įdėtu kadru. Grąžina (paveikslas, rėmo storis px)."""
    from PIL import Image, ImageDraw, ImageFilter
    if kind == "phone3d":
        b = round(W * 0.035)
        img = Image.new("RGBA", (W + 2 * b, H + 2 * b), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = max(2, round(W * 0.13 * fade))
        d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, fill=(24, 24, 27, 255))  # korpusas
        d.rounded_rectangle((2, 2, img.width - 3, img.height - 3), r - 2, outline=(150, 152, 160, 255), width=3)
        mask = Image.new("L", screen.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), round(r * 0.78), fill=255)
        img.paste(screen, (b, b), mask)
        isl_w, isl_h = round(W * 0.27), round(W * 0.075)  # „dinaminė sala“
        d.rounded_rectangle((img.width / 2 - isl_w / 2, b + isl_h * 0.5, img.width / 2 + isl_w / 2, b + isl_h * 1.5),
                            isl_h // 2, fill=(0, 0, 0, round(255 * fade)))
        return img, b
    b = round(W * 0.075)  # 🖼 paauksuotas medinis rėmas
    img = Image.new("RGBA", (W + 2 * b, H + 2 * b), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(b):
        t = i / b
        col = (int(96 + 120 * (1 - abs(t - 0.45) * 2)), int(62 + 80 * (1 - abs(t - 0.45) * 2)), int(24 + 30 * t), 255)
        d.rectangle((i, i, img.width - 1 - i, img.height - 1 - i), outline=col)
    img.paste(screen, (b, b))
    edge = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(edge).rectangle((b - 3, b - 3, b + W + 2, b + H + 2), outline=(40, 22, 8, 255), width=4)
    img.alpha_composite(edge.filter(ImageFilter.GaussianBlur(2)))
    return img, b


def render_spin(src, t, kind, out_path, W, H, fps=30, dur=None):
    """📱 Kadras „įlenda“ į realistišką telefoną (arba 🖼 paveikslo rėmą), kuris pasisuka 3D erdvėje ir grįžta.
    Grąžina video (be garso) lango trukmei – uždedamas ant pagrindinio video nuo t."""
    import math
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    d = dur or LEN[kind]
    n = round(d * fps)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-t", f"{d:.3f}", "-vf",
                          f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fsz = W * H * 3
    frames = [raw[i:i + fsz] for i in range(0, len(raw) - fsz + 1, fsz)][:n]
    if not frames:
        raise RuntimeError("Nepavyko paimti kadrų efektui")
    bg = Image.new("RGB", (W, H))
    gy = np.linspace(0, 1, H)[:, None]
    gx = np.abs(np.linspace(-1, 1, W))[None, :]
    lum = (38 - 18 * gy - 10 * gx).clip(10, 60)
    bg = Image.fromarray(np.dstack([lum * 0.9, lum * 0.92, lum]).astype("uint8"))
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                             "-pix_fmt", "yuv420p", out_path], stdin=subprocess.PIPE)
    for i in range(n):
        fr = Image.frombytes("RGB", (W, H), frames[min(i, len(frames) - 1)])
        u = i / max(1, n - 1)
        sc, ang, back_fade = _spin_track(u, kind)
        if sc < 0.02 or back_fade > 0.995:  # telefonas dingo – tik tamsus fonas, pereinantis į video
            mix = Image.blend(bg, fr, back_fade)
            proc.stdin.write(mix.tobytes())
            continue
        if sc > 0.995 and abs(math.sin(ang)) < 0.005 and math.cos(ang) > 0:  # pilnas ekranas – tiesiog kadras (sklandi pradžia ir pabaiga)
            proc.stdin.write(fr.tobytes())
            continue
        front, b = _phone_front(fr.convert("RGBA"), W, H, kind, min(1.0, (1 - sc) / 0.15))
        fw, fh = front.size
        # masteliuojam taip, kad esant sc = 1 ekranas (be rėmo) uždengtų visą kadrą
        k = sc * W / W
        hw, hh = fw / 2 * k, fh / 2 * k
        thick = fw * k * (0.075 if kind == "phone3d" else 0.06)  # korpuso storis (mastelis kartu su telefonu)
        cx, cy, dist = W / 2, H / 2 - H * 0.02 * (1 - sc) / 0.4, H * 2.4
        back = kind == "phone3d" and math.cos(ang) < 0  # apsisukęs – matoma nugarėlė (ji per korpuso storį toliau)
        zf = -thick if back else 0
        corners = [(-hw, -hh, zf), (hw, -hh, zf), (hw, hh, zf), (-hw, hh, zf)]
        dst = _proj(corners, ang, cx, cy, dist)
        if back:
            front = _phone_back(fw, fh, W)
        cv = bg.copy().convert("RGBA")
        if sc < 0.995:  # šešėlis po telefonu
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sw = hw * abs(math.cos(ang)) * 1.05
            ImageDraw.Draw(sh).ellipse((cx - sw, cy + hh * 0.92, cx + sw, cy + hh * 1.08), fill=(0, 0, 0, 150))
            cv.alpha_composite(sh.filter(ImageFilter.GaussianBlur(W * 0.03)))
        if abs(math.sin(ang)) > 0.01:  # matomas šonas (korpuso storis) su mygtukais, šešėliuotas juostomis
            side = 1 if math.sin(ang) < 0 else -1
            x = side * hw
            sd = ImageDraw.Draw(cv)
            ys = 0.94 if kind == "phone3d" else 1.0
            steps = 10
            for j in range(steps):  # apvalus šonas: šviesesnis viduryje, tamsesni kraštai
                z0, z1 = -thick * j / steps, -thick * (j + 1) / steps
                q = _proj([(x, -hh * ys, z0), (x, hh * ys, z0), (x, hh * ys, z1), (x, -hh * ys, z1)], ang, cx, cy, dist)
                lt = 1 - abs((j + 0.5) / steps - 0.4) * 1.4
                base = (78, 80, 88) if kind == "phone3d" else (110, 70, 28)
                sd.polygon(q, fill=tuple(int(c * (0.55 + 0.75 * lt)) for c in base) + (255,))
            if kind == "phone3d":
                btns = ((-0.56, -0.46), (-0.40, -0.26), (-0.22, -0.08)) if side < 0 else ((-0.38, -0.16),)
                for y0, y1 in btns:
                    bp = _proj([(x + side * 3, hh * y0, -thick * 0.3), (x + side * 3, hh * y1, -thick * 0.3),
                                (x + side * 3, hh * y1, -thick * 0.7), (x + side * 3, hh * y0, -thick * 0.7)],
                               ang, cx, cy, dist)
                    sd.polygon(bp, fill=(150, 152, 160, 255), outline=(60, 60, 66, 255))
        src_pts = [(0, 0), (fw, 0), (fw, fh), (0, fh)]
        warped = front.transform((W, H), Image.PERSPECTIVE, _persp_coeffs(src_pts, dst), Image.BICUBIC)
        if kind == "phone3d" and sc < 0.995:  # stiklo atspindys, kuris slenka sukantis
            gl = Image.new("L", (W, H), 0)
            off = W * (0.5 + math.sin(ang) * 1.4)
            ImageDraw.Draw(gl).polygon([(off - W * 0.35, 0), (off - W * 0.15, 0), (off + W * 0.25, H),
                                        (off + W * 0.05, H)], fill=46)
            gl = gl.filter(ImageFilter.GaussianBlur(W * 0.04))
            a = warped.getchannel("A")
            glare = Image.new("RGBA", (W, H), (255, 255, 255, 0))
            glare.putalpha(Image.fromarray(np.minimum(np.asarray(gl), np.asarray(a))))
            warped.alpha_composite(glare)
        cv.alpha_composite(warped)
        out = cv.convert("RGB")
        if back_fade > 0.005:  # telefonui tolstant vėl išryškėja tikras video
            out = Image.blend(out, fr, back_fade)
        proc.stdin.write(out.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("Nepavyko sukurti 3D efekto")
    return out_path


def apply_spins(path, items, out_path, W, H, fps, tmp, speed=1.0):
    """Įdeda 3D efektus į video (prieš spalvas, titrus ir kt. – jie piešiami ant viršaus kaip įprasta)."""
    rendered = []
    for i, it in enumerate(items):
        t = it["t"] * speed
        clip = os.path.join(tmp, f"spin{i}.mp4")
        render_spin(path, t, it["kind"], clip, W, H, fps, LEN[it["kind"]] * speed)
        rendered.append((t, clip))
    if not rendered:
        return path
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", path]
    chain, last = [], "0:v"
    for k, (t, clip) in enumerate(rendered, 1):
        cmd += ["-i", clip]
        chain.append(f"[{k}:v]setpts=PTS-STARTPTS+{t:.3f}/TB[s{k}];[{last}][s{k}]overlay=eof_action=pass[o{k}]")
        last = f"o{k}"
    cmd += ["-filter_complex", ";".join(chain), "-map", f"[{last}]", "-map", "0:a?", "-c:v", "libx264", "-preset",
            "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "copy", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("Nepavyko įdėti 3D efekto: " + r.stderr[-300:])
    return out_path
