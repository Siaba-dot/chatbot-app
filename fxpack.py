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
    "counter": "🔢 Skaitiklis", "reel": "🎞️ Prasisukanti kino juosta", "phone3d": "📱 Besisukantis telefonas", "laptop3d": "💻 Užsidarantis kompiuteris", "gold3d": "✨ Auksinės raidės", "shatter3d": "💥 Dūžtantis ekranas",
    "frame3d": "🖼 Besisukantis paveikslo rėmas",
}
OVERLAY_KINDS = ("filmstrip", "fan", "polaroids", "grid")
ASS_KINDS = ("chat", "review", "chart", "notif", "counter")
LEN = {"reel": 1.0, "phone3d": 2.6, "laptop3d": 3.2, "gold3d": 2.8, "shatter3d": 2.6, "frame3d": 1.8, "filmstrip": 2.6, "fan": 2.6, "polaroids": 2.8, "grid": 2.2, "pip": 2.8, "chat": 3.2, "review": 3.2,
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
    frame_kinds = [k for k in ("phone3d", "reel", "laptop3d", "frame3d", "filmstrip", "fan", "polaroids", "grid", "pip") if k in allowed]
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
import accents  # noqa: E402 – ✨ 3D akcentai

KINDS.update(accents.KINDS)
LEN.update(accents.LEN)
SPIN_KINDS = ("phone3d", "frame3d", "laptop3d", "gold3d", "shatter3d") + tuple(accents.KINDS)
# 🎯 efektai, kuriuos galima pasirinkti konkrečioje laiko juostos vietoje (vaizdiniai – tekstas nereikalingas)
TIMELINE_KINDS = tuple(accents.KINDS) + ("gold3d", "shatter3d", "phone3d", "laptop3d", "frame3d", "reel",
                                          "filmstrip", "fan", "polaroids", "grid", "pip")


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


def render_spin(src, t, kind, out_path, W, H, fps=30, dur=None, text=""):
    """📱 Kadras „įlenda“ į realistišką telefoną (arba 🖼 paveikslo rėmą), kuris pasisuka 3D erdvėje ir grįžta.
    Grąžina video (be garso) lango trukmei – uždedamas ant pagrindinio video nuo t."""
    import math
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    if kind == "laptop3d":
        return render_laptop(src, t, out_path, W, H, fps, dur)
    if kind == "gold3d":
        return render_gold(src, t, text, out_path, W, H, fps, dur)
    if kind == "shatter3d":
        return render_shatter(src, t, out_path, W, H, fps, dur)
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


def gold_stagger(nl):
    return min(0.06, 0.18 / max(1, nl - 1))


def gold_land_times(text, dur):
    """Kada (s nuo efekto pradžios) kiekviena auksinė raidė nusileidžia ir atsistoja ant stalo."""
    word = re.sub(r"[^\w\-]", "", (text or "").replace(video_editor.KEY_MARK, "")).upper()[:12] or "WOW"
    nl = len(word)
    return [(0.2 + i * gold_stagger(nl) + 0.17 * 0.9) * dur for i in range(nl)]


def _snd_clink(rng, sr, volume=0.34):
    """Metalinis dzingtelėjimas (auksinė raidė krinta ant stalo)."""
    import numpy as np
    n = int(0.45 * sr)
    tt = np.arange(n) / sr
    pitch = 1 + 0.04 * rng.normal()
    ping = sum(a * np.sin(2 * np.pi * f * pitch * tt) * np.exp(-tt / d)
               for f, a, d in ((2350, 0.5, 0.09), (3720, 0.35, 0.06), (5310, 0.25, 0.04), (7930, 0.15, 0.025)))
    thud = 0.6 * np.sin(2 * np.pi * 150 * tt) * np.exp(-tt / 0.035)
    click = np.zeros(n)
    click[:120] = rng.normal(0, 0.5, 120) * np.linspace(1, 0, 120)
    return (ping + thud + click) * volume * (0.85 + 0.3 * rng.random())


def _snd_crack(rng, sr):
    """Stiklo įtrūkimo traškesys – trumpas aukštas spragtelėjimas."""
    import numpy as np
    n = int(0.06 * sr)
    tt = np.arange(n) / sr
    x = rng.normal(0, 1, n)
    x = np.diff(x, prepend=0) * np.exp(-tt / 0.008)
    return x * 0.18 * (0.6 + 0.8 * rng.random())


def _snd_shatter(rng, sr):
    """Dūžtantis stiklas: aukštų dažnių triukšmo pliūpsnis + daug smulkių šukių skambesių ir pabyrų."""
    import numpy as np
    n = int(1.3 * sr)
    tt = np.arange(n) / sr
    burst = np.diff(rng.normal(0, 1, n), prepend=0) * (np.exp(-tt / 0.07) * 0.8 + np.exp(-tt / 0.35) * 0.15)
    low = np.sin(2 * np.pi * 90 * tt) * np.exp(-tt / 0.05) * 0.5
    y = burst * 0.5 + low
    for _ in range(70):  # šukių skambėjimas ir byrėjimas ant stalo
        t0 = abs(rng.normal(0, 0.28)) + rng.random() * 0.1
        m = int(0.12 * sr)
        a = int(t0 * sr)
        if a + m >= n:
            continue
        tk = np.arange(m) / sr
        f = 2800 + rng.random() * 6500
        dec = 0.015 + 0.05 * rng.random()
        y[a:a + m] += np.sin(2 * np.pi * f * tk) * np.exp(-tk / dec) * (0.05 + 0.18 * rng.random()) * np.exp(-t0 * 1.5)
    return y * 0.38


def _snd_close(rng, sr):
    """Užsidarantis nešiojamo kompiuterio dangtis: duslus „tukt“ + trumpas magneto spragtelėjimas."""
    import numpy as np
    n = int(0.35 * sr)
    tt = np.arange(n) / sr
    thud = np.sin(2 * np.pi * 95 * tt) * np.exp(-tt / 0.05) * 0.7 + np.sin(2 * np.pi * 210 * tt) * np.exp(-tt / 0.03) * 0.4
    knock = np.sin(2 * np.pi * 820 * tt) * np.exp(-tt / 0.012) * 0.25
    air = rng.normal(0, 1, n) * np.exp(-tt / 0.02) * 0.08
    clk = np.zeros(n)
    a = int(0.012 * sr)
    m = int(0.006 * sr)
    clk[a:a + m] = np.diff(rng.normal(0, 1, m), prepend=0) * 0.35
    return (thud + knock + air + clk) * 0.55


def _snd_whoosh(rng, sr):
    """Švelnus „švyst“ – oro srautas su kylančiu tonu."""
    import numpy as np
    n = int(0.45 * sr)
    tt = np.arange(n) / sr
    env = np.sin(np.pi * np.clip(tt / 0.45, 0, 1)) ** 2
    x = np.cumsum(rng.normal(0, 1, n))
    x = x - np.convolve(x, np.ones(40) / 40, mode="same")  # be žemų dažnių
    return x / (np.abs(x).max() + 1e-6) * env * 0.22


def _snd_pop(rng, sr):
    import numpy as np
    n = int(0.16 * sr)
    tt = np.arange(n) / sr
    f = 900 * np.exp(-tt * 18) + 250
    return np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt / 0.05) * 0.35


def _snd_tap(rng, sr):
    import numpy as np
    n = int(0.08 * sr)
    tt = np.arange(n) / sr
    return (np.sin(2 * np.pi * 520 * tt) * 0.5 + rng.normal(0, 0.2, n)) * np.exp(-tt / 0.015) * 0.3


def sfx_wav(events, out_path, sr=44100):
    """Garso efektai pagal laiką: events = [(laikas s, "clink" | "crack" | "shatter")] -> WAV."""
    import wave
    import numpy as np
    total = (max(t for t, _ in events) if events else 0) + 1.5
    y = np.zeros(int(total * sr), np.float32)
    rng = np.random.default_rng(9)
    for t0, kind in events:
        snd = {"clink": _snd_clink, "crack": _snd_crack, "shatter": _snd_shatter,
               "close": _snd_close, "whoosh": _snd_whoosh, "pop": _snd_pop, "tap": _snd_tap}[kind](rng, sr)
        a = int(t0 * sr)
        y[a:a + len(snd)] += snd[: len(y) - a]
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return out_path


def sfx_events(items, speed=1.0):
    """3D efektų garsai (absoliutus laikas sumontuotame video): auksinių raidžių kritimas, stiklo dūžis."""
    ev = []
    for it in items:
        t, d = it["t"] * speed, float(it.get("dur") or LEN[it["kind"]]) * speed
        if it["kind"] in accents.KINDS:
            ev += accents.sfx(it, t, d)
        elif it["kind"] == "gold3d":
            ev += [(t + x, "clink") for x in gold_land_times(it.get("text", ""), d)]
        elif it["kind"] == "shatter3d":
            ev += [(t + d * (SHATTER_AT - 0.2 + 0.19 * k / 6), "crack") for k in range(7)]
            ev.append((t + d * SHATTER_AT, "shatter"))
        elif it["kind"] == "laptop3d":  # dangtis užsidaro
            ev.append((t + d * LAPTOP_CLOSE_AT, "close"))
    return ev


def apply_spins(path, items, out_path, W, H, fps, tmp, speed=1.0):
    """Įdeda 3D efektus į video (prieš spalvas, titrus ir kt. – jie piešiami ant viršaus kaip įprasta)."""
    rendered = []
    for i, it in enumerate(items):
        t = it["t"] * speed
        clip = os.path.join(tmp, f"spin{i}.mp4")
        if it["kind"] in accents.KINDS:  # ✨ 3D akcentas su savo vieta, dydžiu, spalva ir trukme
            accents.render(path, t, it, clip, W, H, fps, float(it.get("dur") or LEN[it["kind"]]) * speed)
        else:
            render_spin(path, t, it["kind"], clip, W, H, fps, LEN[it["kind"]] * speed, it.get("text", ""))
        rendered.append((t, clip))
    if not rendered:
        return path
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", path]
    chain, last = [], "0:v"
    for k, (t, clip) in enumerate(rendered, 1):
        cmd += ["-i", clip]
        chain.append(f"[{k}:v]setpts=PTS-STARTPTS+{t:.3f}/TB[s{k}];[{last}][s{k}]overlay=eof_action=pass[o{k}]")
        last = f"o{k}"
    amap, acodec = ["-map", "0:a?"], ["-c:a", "copy"]  # garsas nekeičiamas; efektų garsai įmaišomi apdailoje
    cmd += ["-filter_complex", ";".join(chain), "-map", f"[{last}]", *amap, "-c:v", "libx264", "-preset",
            "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", *acodec, out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("Nepavyko įdėti 3D efekto: " + r.stderr[-300:])
    return out_path


# ======================= 💻 nešiojamas kompiuteris: atitolsta → užsidaro → nuskrenda tolyn =======================
# Tikras 3D modelis: korpusas ir dangtis – dėžės su storiu; kiekviena plokštuma apšviečiama pagal kryptį į šviesą,
# matomos tik į žiūrovą atsuktos pusės, piešiama nuo tolimiausių (dailininko algoritmas).
def _rot_x(p, a):
    import math
    x, y, z = p
    c, s = math.cos(a), math.sin(a)
    return x, y * c - z * s, y * s + z * c


def _rot_y(p, a):
    import math
    x, y, z = p
    c, s = math.cos(a), math.sin(a)
    return x * c + z * s, y, -x * s + z * c


def _rot_z(p, a):
    import math
    x, y, z = p
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c, z


LAPTOP_CLOSE_AT = 0.565  # efekto dalis, kai dangtis užsidaro


def _laptop_track(u):
    """(mastelis, ekrano perėjimas 0..1, žiūrėjimas iš viršaus, dangtis, nuskridimas 0..1, video grįžimas)."""
    import math
    e = lambda x: 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))  # noqa: E731
    z = e(u / 0.24)
    return (1 - 0.36 * z, z, math.radians(27) * z, math.radians(91) * e((u - 0.3) / 0.27),
            max(0.0, min(1.0, (u - 0.6) / 0.3)), e((u - 0.86) / 0.14))


def _brushed(w, h, base, rnd_seed=3):
    """Šlifuoto aliuminio tekstūra (horizontalūs brūkšniai + švelnus gradientas)."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(rnd_seed)
    streak = rng.normal(0, 1, (1, w)).repeat(h, 0) * 0.6 + rng.normal(0, 1, (h, w)) * 1.2
    gy = np.linspace(0, 1, h)[:, None]
    lum = base + 14 * (1 - gy) + streak
    rgb = np.dstack([lum * 0.97, lum * 0.985, lum]).clip(0, 255)
    return Image.fromarray(np.dstack([rgb, np.full((h, w), 255)]).astype("uint8"), "RGBA")


def _laptop_base(bw, bd):
    from PIL import ImageDraw
    img = _brushed(bw, bd, 186)
    d = ImageDraw.Draw(img)
    kx0, ky0, kx1, ky1 = bw * 0.12, bd * 0.06, bw * 0.88, bd * 0.52
    d.rounded_rectangle((kx0 - 4, ky0 - 4, kx1 + 4, ky1 + 4), bw * 0.012, fill=(120, 122, 128, 255))  # įdubimas
    d.rounded_rectangle((kx0, ky0, kx1, ky1), bw * 0.01, fill=(26, 27, 30, 255))
    rows, cols = 6, 14
    w, h = (kx1 - kx0) / cols, (ky1 - ky0) / rows
    for r in range(rows):
        c = 0
        while c < cols:
            span = 6 if (r == rows - 1 and c == 4) else 1
            x0, y0 = kx0 + c * w + 2, ky0 + r * h + 2
            x1, y1 = kx0 + (c + span) * w - 2, ky0 + (r + 1) * h - 2
            d.rounded_rectangle((x0, y0 + 1, x1, y1 + 1), 3, fill=(8, 8, 9, 255))  # šešėlis
            d.rounded_rectangle((x0, y0, x1, y1 - 1), 3, fill=(36, 37, 41, 255))
            d.line((x0 + 3, y0 + 1, x1 - 3, y0 + 1), fill=(62, 63, 68, 255))  # klavišo briauna šviesoje
            c += span
    for sx in (bw * 0.045, bw * 0.925):  # garsiakalbių grotelės
        for yy in range(int(ky0), int(ky1), 6):
            for xx in range(0, int(bw * 0.03), 6):
                d.ellipse((sx + xx, yy, sx + xx + 2, yy + 2), fill=(70, 72, 78, 255))
    d.rounded_rectangle((bw * 0.32, bd * 0.6, bw * 0.68, bd * 0.93), bw * 0.015, fill=(196, 198, 204, 255),
                        outline=(140, 142, 148, 255), width=2)
    d.rounded_rectangle((bw * 0.42, bd * 0.0, bw * 0.58, bd * 0.02), 3, fill=(90, 92, 98, 255))  # vyrio išpjova
    return img


def _laptop_lid_back(lw, lh):
    from PIL import Image, ImageDraw
    img = _brushed(lw, lh, 178, 5)
    m = Image.new("L", (lw, lh), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, lw - 1, lh - 1), round(lw * 0.025), fill=255)
    img.putalpha(m)
    return img


def _warp(img, quad, W, H):
    """Tekstūra į keturkampį – tik jo ribose (greičiau). Grąžina (gabalas, x0, y0) arba None."""
    from PIL import Image
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    x0, y0 = max(0, int(min(xs)) - 1), max(0, int(min(ys)) - 1)
    x1, y1 = min(W, int(max(xs)) + 2), min(H, int(max(ys)) + 2)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    src = [(0, 0), (img.width, 0), (img.width, img.height), (0, img.height)]
    try:
        co = _persp_coeffs(src, [(x - x0, y - y0) for x, y in quad])
    except Exception:
        return None
    return img.transform((x1 - x0, y1 - y0), Image.PERSPECTIVE, co, Image.BICUBIC), x0, y0


def render_laptop(src, t, out_path, W, H, fps=30, dur=None):
    """💻 Kadras atitolsta ir tampa nešiojamo kompiuterio (ant stalo) ekranu, dangtis užsidaro, kompiuteris pakyla
    ir nuskrenda tolyn virš stalo – vėl matosi video. Piešiama didesne raiška ir sumažinama (lygūs kraštai)."""
    import math
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    d = dur or LEN["laptop3d"]
    n = round(d * fps)
    W0, H0 = W, H
    ss = 1.5 if W0 < 1000 else 1.25  # supersampling
    W, H = round(W0 * ss) // 2 * 2, round(H0 * ss) // 2 * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-t", f"{d:.3f}", "-vf",
                          f"scale={W0}:{H0}:force_original_aspect_ratio=increase,crop={W0}:{H0},fps={fps}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fsz = W0 * H0 * 3
    frames = [raw[i:i + fsz] for i in range(0, len(raw) - fsz + 1, fsz)][:n]
    if not frames:
        raise RuntimeError("Nepavyko paimti kadrų efektui")
    e = lambda x: 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))  # noqa: E731
    yy, xx = np.mgrid[0:H, 0:W]
    vign = (1 - 0.42 * (((xx - W * 0.4) / (W * 0.9)) ** 2 + ((yy - H * 0.4) / (H * 0.85)) ** 2)).clip(0.5, 1)
    bgc = Image.fromarray((np.dstack([vign * 104, vign * 108, vign * 114])).astype("uint8")).convert("RGBA")
    tile = _stone(520, 520)
    table = Image.new("RGBA", (520 * 6, 520 * 10))  # smulki faktūra, pakartota per visą stalą
    for ty_ in range(10):
        for tx_ in range(6):
            table.paste(tile.transpose(Image.FLIP_LEFT_RIGHT) if (tx_ + ty_) % 2 else tile, (tx_ * 520, ty_ * 520))
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W0}x{H0}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                             "-pix_fmt", "yuv420p", out_path], stdin=subprocess.PIPE)
    sw_end = W * 0.84  # atitolus ekranas gulsčias (16:10)
    sh_end = sw_end * 10 / 16
    tw = int(W * 0.9)
    base_img = _laptop_base(tw, int(tw * 0.68))
    bm = Image.new("L", base_img.size, 0)
    ImageDraw.Draw(bm).rounded_rectangle((0, 0, base_img.width - 1, base_img.height - 1), round(tw * 0.03), fill=255)
    base_img.putalpha(bm)
    back_img = _laptop_lid_back(tw, int(tw * 0.66))
    L = np.array([-0.4, -0.8, 0.45])
    L = L / np.linalg.norm(L)
    alu = (186, 188, 194)
    prev = None
    for i in range(n):
        fr0 = Image.frombytes("RGB", (W0, H0), frames[min(i, len(frames) - 1)])
        u = i / max(1, n - 1)
        sc, morph, tilt, lid, fly, back_fade = _laptop_track(u)
        if back_fade > 0.995 or morph < 0.002:
            proc.stdin.write(fr0.tobytes())
            continue
        fr = fr0.resize((W, H), Image.BICUBIC)
        sw = round(W + (sw_end - W) * morph)  # ekranas: nuo viso kadro iki gulsčio ekrano
        sh = round(H + (sh_end - H) * morph)
        b = round(W * 0.02 * morph) + 1
        chin = round(W * 0.03 * morph)
        lw, lh = sw + 2 * b, sh + 2 * b + chin
        # ekrane – visas stačias video, šonuose jo sulieta kopija (kaip tikrame kompiuterio ekrane)
        cov = max(sw / W, sh / H)
        bgk = fr.resize((max(sw, round(W * cov)), max(sh, round(H * cov))))
        bgk = bgk.crop(((bgk.width - sw) // 2, (bgk.height - sh) // 2, (bgk.width - sw) // 2 + sw,
                        (bgk.height - sh) // 2 + sh)).filter(ImageFilter.GaussianBlur(max(1, sw * 0.03)))
        bgk = Image.blend(bgk, Image.new("RGB", bgk.size, (0, 0, 0)), 0.35 * morph)
        con = min(sw / W, sh / H)
        fit = fr.resize((max(1, round(W * con)), max(1, round(H * con))))
        bgk.paste(fit, ((sw - fit.width) // 2, (sh - fit.height) // 2))
        front = Image.new("RGBA", (lw, lh), (10, 10, 12, 255))
        front.paste(bgk, (b, b))
        fd = ImageDraw.Draw(front)
        fd.ellipse((lw / 2 - b * 0.16, b * 0.38, lw / 2 + b * 0.16, b * 0.7), fill=(36, 40, 56, 255))
        fm = Image.new("L", front.size, 0)
        ImageDraw.Draw(fm).rounded_rectangle((0, 0, lw - 1, lh - 1), max(1, round(lw * 0.025 * morph)), fill=255)
        front.putalpha(fm)
        lt, bt = lw * 0.011, lw * 0.028  # dangčio ir korpuso storis
        bw, bd = lw * 1.02, lh * 0.98
        rr = lw * 0.025 * morph  # suapvalinimas – šonai trumpesni per kampus
        hinge_y = sh / 2 + b + chin
        dist = H * 1.9
        away = (fly ** 2.2) * lh * 14  # nuskrenda tolyn virš stalo
        lift = lh * 0.45 * e(fly * 1.6)
        yaw = math.radians(16) * morph + math.radians(28) * e(fly)
        piv_z = bd / 2

        def tr(p, on_lid=False, normal=False, still=False):
            x, y, z = p
            if on_lid:
                x, y, z = _rot_x((x, y, z), -lid)
            if not still:  # kompiuterio judesys (pasisukimas, pakilimas, nuskridimas); stalas nejuda
                if normal:
                    x, y, z = _rot_y((x, y, z), yaw)
                else:
                    x, y, z = _rot_y((x, y, z - piv_z), yaw)
                    z += piv_z - away
                    y -= lift
            if normal:
                return np.array(_rot_x((x, y, z), -tilt))
            x, y, z = (x + lw * 0.1 * morph) * sc, y * sc, z * sc  # kompiuteris kadro centre
            x, y, z = _rot_x((x, y, z), -tilt)
            return np.array((x, y + hinge_y * sc - H * 0.06 * morph, z))

        def proj(v):
            f = dist / max(1.0, dist - v[2])
            return W / 2 + v[0] * f, H / 2 + v[1] * f

        cv = bgc.copy()
        # stalas (nejuda) ir kompiuterio šešėlis ant jo
        tq = [proj(tr(p, still=True)) for p in ((-lw * 4.5, bt, -lh * 22), (lw * 4.5, bt, -lh * 22), (lw * 4.5, bt, lh * 6),
                                                 (-lw * 4.5, bt, lh * 6))]
        w_ = _warp(table, tq, W, H)
        if w_:  # lengvas suliejimas – be raibulių tolumoje (ir kaip kameros gylio ryškumas)
            cv.alpha_composite(w_[0].filter(ImageFilter.GaussianBlur(1.4 * ss)), (w_[1], w_[2]))
        cv = Image.fromarray((np.asarray(cv.convert("RGB"), np.float32) * vign[..., None] * 1.06).clip(0, 255)
                             .astype("uint8")).convert("RGBA")
        x0, x1 = -bw / 2, bw / 2
        zb, zf = -bt * 0.4, bd
        if morph > 0.05:
            def foot(p):
                x, y, z = _rot_y((p[0], p[1], p[2] - piv_z), yaw)
                return proj(tr((x, bt, z + piv_z - away), still=True))
            gap = lift / lh
            sq = [foot((x0, 0, zb)), foot((x1, 0, zb)), foot((x1, 0, zf)), foot((x0, 0, zf))]
            shl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(shl).polygon(sq, fill=(0, 0, 0, int(165 * morph * (1 - min(1, gap * 1.4)) * (1 - fly))))
            cv.alpha_composite(shl.filter(ImageFilter.GaussianBlur(max(2, W * (0.012 + 0.05 * gap) * sc))))
        lx0, lx1 = -lw / 2, lw / 2
        faces = [
            ([(x0, 0, zb), (x1, 0, zb), (x1, 0, zf), (x0, 0, zf)], (0, -1, 0), False, base_img, 0.45),
            ([(x0 + rr, 0, zf), (x1 - rr, 0, zf), (x1 - rr, bt, zf), (x0 + rr, bt, zf)], (0, 0, 1), False, alu, 0.5),
            ([(x0, 0, zb + rr), (x0, 0, zf - rr), (x0, bt, zf - rr), (x0, bt, zb + rr)], (-1, 0, 0), False, alu, 0.5),
            ([(x1, 0, zf - rr), (x1, 0, zb + rr), (x1, bt, zb + rr), (x1, bt, zf - rr)], (1, 0, 0), False, alu, 0.5),
            ([(x1 - rr, 0, zb), (x0 + rr, 0, zb), (x0 + rr, bt, zb), (x1 - rr, bt, zb)], (0, 0, -1), False, alu, 0.3),
            ([(lx0, -lh, 0), (lx1, -lh, 0), (lx1, 0, 0), (lx0, 0, 0)], (0, 0, 1), True, front, 0.0),
            ([(lx1, -lh, -lt), (lx0, -lh, -lt), (lx0, 0, -lt), (lx1, 0, -lt)], (0, 0, -1), True, back_img, 0.55),
            ([(lx0 + rr, -lh, -lt), (lx1 - rr, -lh, -lt), (lx1 - rr, -lh, 0), (lx0 + rr, -lh, 0)], (0, -1, 0), True, alu, 0.5),
            ([(lx0, -lh + rr, -lt), (lx0, -lh + rr, 0), (lx0, -rr, 0), (lx0, -rr, -lt)], (-1, 0, 0), True, alu, 0.5),
            ([(lx1, -lh + rr, 0), (lx1, -lh + rr, -lt), (lx1, -rr, -lt), (lx1, -rr, 0)], (1, 0, 0), True, alu, 0.5),
        ]
        drawn = []
        for pts, nrm_, on_lid, tex, gloss in faces:
            vs = [tr(p, on_lid) for p in pts]
            c = sum(vs) / 4
            nv = tr(nrm_, on_lid, normal=True)
            view = np.array((0, 0, dist)) - c
            if float(nv @ view) <= 0:
                continue
            vd = view / np.linalg.norm(view)
            diff = max(0.0, float(nv @ L))
            hv = (L + vd) / np.linalg.norm(L + vd)
            spec = max(0.0, float(nv @ hv)) ** 30 * gloss
            depth = c[2] + (lt * sc * 3 if on_lid else 0)
            drawn.append((depth, [proj(v) for v in vs], tex, diff, spec))
        drawn.sort(key=lambda x: x[0])
        for _, q, tex, diff, spec in drawn:
            is_screen = tex is front
            shade = (0.96 + 0.06 * diff) * (0.55 + 0.45 * (1 - lid / math.radians(91))) if is_screen \
                else (0.5 + 0.6 * diff)
            if isinstance(tex, Image.Image):
                w_ = _warp(tex, q, W, H)
                if not w_:
                    continue
                patch, px, py = w_
                a = np.asarray(patch, dtype=np.float32)
                a[..., :3] = (a[..., :3] * shade + 255 * spec).clip(0, 255)
                cv.alpha_composite(Image.fromarray(a.astype("uint8"), "RGBA"), (px, py))
                if is_screen and morph > 0.05:  # stiklo atspindys
                    gl = Image.new("L", patch.size, 0)
                    pw, ph = patch.size
                    off = pw * (0.25 + 0.8 * lid / math.radians(91))
                    ImageDraw.Draw(gl).polygon([(off - pw * 0.32, 0), (off - pw * 0.12, 0), (off + pw * 0.12, ph),
                                                (off - pw * 0.08, ph)], fill=int(32 * morph))
                    gl = Image.fromarray(np.minimum(np.asarray(gl.filter(ImageFilter.GaussianBlur(pw * 0.05))),
                                                    np.asarray(patch.getchannel("A"))))
                    glare = Image.new("RGBA", patch.size, (255, 255, 255, 0))
                    glare.putalpha(gl)
                    cv.alpha_composite(glare, (px, py))
            else:
                col = tuple(int(min(255, c * shade + 255 * spec)) for c in tex) + (255,)
                ImageDraw.Draw(cv).polygon(q, fill=col)
        out = cv.convert("RGB").resize((W0, H0), Image.LANCZOS)
        if fly > 0.02 and prev is not None:  # judesio suliejimas skrendant
            out = Image.blend(out, prev, 0.15)
        prev = out
        if back_fade > 0.005:
            out = Image.blend(out, fr0, back_fade)
        proc.stdin.write(out.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("Nepavyko sukurti 3D efekto")
    return out_path


# ======================= ✨ auksinės raidės: iš telefono ekrano ant stalo išslysta pirmas žodis =======================
def _wood(w, h, seed=11):
    """Tamsaus riešuto stalviršis (procedūrinė medienos rievių tekstūra)."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]
    warp = np.sin(y * 5 + rng.random() * 6) * 0.008 + np.sin(y * 23) * 0.002
    grain = np.sin((x + warp) * 140 + np.sin(y * 4) * 3) * 0.5 + 0.5
    fine = rng.normal(0, 1, (1, w)).repeat(h, 0) * 0.35 + rng.normal(0, 1, (h, w)) * 0.25
    lum = 0.55 + 0.25 * grain + 0.05 * fine
    rgb = np.dstack([92 * lum, 60 * lum, 38 * lum]).clip(0, 255)
    return Image.fromarray(np.dstack([rgb, np.full((h, w), 255)]).astype("uint8"), "RGBA")


def _stone(w, h, seed=21):
    """Šviesiai pilkas grūdėtas (odos / akmens) stalviršis su reljefu, apšviestu iš viršaus."""
    import numpy as np
    from PIL import Image, ImageFilter
    rng = np.random.default_rng(seed)
    n = Image.fromarray((rng.random((h, w)) * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(1.6))
    a = np.asarray(n, np.float32)
    gy, gx = np.gradient(a)
    lum = 116 + (-gy * 1.4 - gx * 0.6) * 3.2 + rng.normal(0, 1.5, (h, w))
    rgb = np.dstack([lum * 0.96, lum * 0.99, lum * 1.04]).clip(0, 255)
    return Image.fromarray(np.dstack([rgb, np.full((h, w), 255)]).astype("uint8"), "RGBA")


def _gold_text(text, height, full=None):
    """Šlifuoto aukso raidės: (veidas su briaunų šviesa, šonas, kaukė). full – viso žodžio aukščio riboms."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    font = ImageFont.truetype(os.path.join(video_editor.FONT_DIR, "Montserrat_900Black.ttf"), height)
    l, t, r, b = font.getbbox(text)
    if full:
        _, t, _, b = font.getbbox(full)
    pad = round(height * 0.12)
    w, h = r - l + 2 * pad, b - t + 2 * pad
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).text((pad - l, pad - t), text, font=font, fill=255)
    M = np.asarray(m, dtype=np.float32) / 255
    yy = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    stops = [(0, (232, 194, 120)), (0.5, (208, 164, 90)), (1, (178, 134, 64))]  # matinis satininis auksas
    rgb = np.zeros((h, w, 3), np.float32)
    for (a0, c0), (a1, c1) in zip(stops, stops[1:]):
        k = ((yy - a0) / (a1 - a0)).clip(0, 1)[..., None]
        sel = ((yy >= a0) & (yy <= a1))[..., None]
        rgb = np.where(sel, np.array(c0) * (1 - k) + np.array(c1) * k, rgb)
    rng = np.random.default_rng(4)
    rgb += (rng.normal(0, 1, (1, w)).repeat(h, 0) * 5 + rng.normal(0, 1, (h, w)) * 3)[..., None]  # šlifavimas
    bl = np.asarray(m.filter(ImageFilter.GaussianBlur(height * 0.03)), dtype=np.float32) / 255
    gy_, gx_ = np.gradient(bl)
    bevel = (-(gx_ * 0.6 + gy_ * 1.0) * height * 0.9)[..., None]  # briaunos: šviesa iš viršaus kairės
    rgb = (rgb + bevel * 70).clip(0, 255)
    face = Image.fromarray(np.dstack([rgb, M * 255]).astype("uint8"), "RGBA")
    side = Image.fromarray(np.dstack([np.full((h, w), 196), np.full((h, w), 154), np.full((h, w), 82), M * 255])
                           .astype("uint8"), "RGBA")
    return face, side, m


def _gold_letters(text, height):
    """Kiekviena raidė atskirai (tas pats aukštis ir gradientas), su vieta žodyje: [(veidas, šonas, kaukė, x px)], plotis."""
    from PIL import ImageFont
    font = ImageFont.truetype(os.path.join(video_editor.FONT_DIR, "Montserrat_900Black.ttf"), height)
    out, x = [], 0.0
    for i, ch in enumerate(text):
        x = font.getlength(text[:i])
        if ch.strip():
            face, side, m = _gold_text(ch, height, full=text)
            out.append((face, side, m, x + font.getbbox(ch)[0] - round(height * 0.12)))
    return out, font.getlength(text)


def render_gold(src, t, text, out_path, W, H, fps=30, dur=None):
    """✨ Kadras atitolsta – tai telefonas ant stalo; iš ekrano krašto išslysta stambios šlifuoto aukso 3D raidės
    (pirmas ištartas žodis), atsistoja, trumpam atsispindi telefono stikle, tada vėl grįžta video."""
    import math
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    d = dur or LEN["gold3d"]
    n = round(d * fps)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-t", f"{d:.3f}", "-vf",
                          f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fsz = W * H * 3
    frames = [raw[i:i + fsz] for i in range(0, len(raw) - fsz + 1, fsz)][:n]
    if not frames:
        raise RuntimeError("Nepavyko paimti kadrų efektui")
    word = re.sub(r"[^\w\-]", "", (text or "").replace(video_editor.KEY_MARK, "")).upper()[:12] or "WOW"
    face, side, mask = _gold_text(word, 260)
    letters, word_w = _gold_letters(word, 260)
    table = _stone(2000, 2600)
    e = lambda x: 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))  # noqa: E731
    yy, xx = np.mgrid[0:H, 0:W]
    vign = (1 - 0.4 * (((xx - W * 0.4) / (W * 0.9)) ** 2 + ((yy - H * 0.35) / (H * 0.8)) ** 2)).clip(0.55, 1)
    bgc = Image.fromarray((np.dstack([vign * 108, vign * 112, vign * 118])).astype("uint8"))
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                             "-pix_fmt", "yuv420p", out_path], stdin=subprocess.PIPE)
    L = np.array([-0.35, -0.8, 0.5])
    L = L / np.linalg.norm(L)
    dist = H * 2.0
    for i in range(n):
        fr = Image.frombytes("RGB", (W, H), frames[min(i, len(frames) - 1)])
        u = i / max(1, n - 1)
        z = e(u / 0.26)
        back = e((u - 0.84) / 0.16)
        if z < 0.002:
            proc.stdin.write(fr.tobytes())
            continue
        if back > 0.995:
            proc.stdin.write(fr.tobytes())
            continue
        sc = (1 - 0.3 * z) * (1 + 0.12 * max(0.0, u - 0.15))  # kamera visą laiką lėtai artėja
        tilt = math.radians(42) * z
        ty = -H * 0.24 * z
        front, b = _phone_front(fr.convert("RGBA"), W, H, "phone3d", min(1.0, z / 0.15))
        fw, fh = front.size
        pt = fw * 0.07

        def tr(p):
            x, y, zz = p[0] * sc, p[1] * sc, p[2] * sc
            x, y, zz = _rot_x((x, y, zz), tilt)
            return np.array((x, y + ty, zz))

        def proj(v):
            f = dist / (dist - v[2])
            return W / 2 + v[0] * f, H / 2 + v[1] * f

        def nrm(v):
            return np.array(_rot_x(v, tilt))

        def visible(pts, nv):
            c = sum(pts) / len(pts)
            return float(nv @ (np.array((0, 0, dist)) - c)) > 0

        cv = bgc.copy().convert("RGBA")
        # stalviršis (su prožektoriaus šviesa)
        tq = [proj(tr(p)) for p in ((-fw * 2.6, -fh * 2.4, -pt), (fw * 2.6, -fh * 2.4, -pt),
                                     (fw * 2.6, fh * 2.6, -pt), (-fw * 2.6, fh * 2.6, -pt))]
        w_ = _warp(table, tq, W, H)
        if w_:
            cv.alpha_composite(w_[0], (w_[1], w_[2]))
        cv = Image.fromarray((np.asarray(cv.convert("RGB"), np.float32) * vign[..., None] * 1.05).clip(0, 255)
                             .astype("uint8")).convert("RGBA")
        # telefono šešėlis ant stalo
        sq = [proj(tr(p)) for p in ((-fw / 2 + 8, -fh / 2 + 18, -pt), (fw / 2 + 8, -fh / 2 + 18, -pt),
                                     (fw / 2 + 16, fh / 2 + 30, -pt), (-fw / 2 + 16, fh / 2 + 30, -pt))]
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).polygon(sq, fill=(0, 0, 0, int(120 * z)))
        cv.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(2, W * 0.02))))
        # telefono šonai
        pt_ = pt
        r = fw * 0.1
        for pts, nv in (([(-fw / 2 + r, fh / 2, 0), (fw / 2 - r, fh / 2, 0), (fw / 2 - r, fh / 2, -pt),
                          (-fw / 2 + r, fh / 2, -pt)], (0, 1, 0)),
                        ([(fw / 2, -fh / 2 + r, 0), (fw / 2, fh / 2 - r, 0), (fw / 2, fh / 2 - r, -pt),
                          (fw / 2, -fh / 2 + r, -pt)], (1, 0, 0)),
                        ([(-fw / 2, -fh / 2 + r, 0), (-fw / 2, fh / 2 - r, 0), (-fw / 2, fh / 2 - r, -pt),
                          (-fw / 2, -fh / 2 + r, -pt)], (-1, 0, 0))):
            vs = [tr(p) for p in pts]
            nv_ = nrm(nv)
            if visible(vs, nv_):
                sh_ = 0.4 + 0.7 * max(0.0, float(nv_ @ L))
                ImageDraw.Draw(cv).polygon([proj(v) for v in vs], fill=tuple(int(c * sh_) for c in (176, 170, 160)) + (255,))
        scr_q = [proj(tr(p)) for p in ((-fw / 2, -fh / 2, 0), (fw / 2, -fh / 2, 0), (fw / 2, fh / 2, 0),
                                       (-fw / 2, fh / 2, 0))]
        w_ = _warp(front, scr_q, W, H)
        if w_:
            cv.alpha_composite(w_[0], (w_[1], w_[2]))
        # raidės: po vieną greitai viena paskui kitą išslysta iš ekrano apačios ant stalo ir atsistoja
        tw2 = fw * 0.36  # raidės – apie du trečdalius telefono pločio
        th = min(tw2 * 2 * face.height / face.width, fh * 0.24)
        ppx = th / face.height  # pasaulio vienetai vienam raidės paveikslo taškui
        x_start = -word_w * ppx / 2
        nl = len(letters)
        stagger = gold_stagger(nl)  # visas žodis susidėlioja ~per 0,5 s
        items = []
        for li, (lf, ls, lm, lx) in enumerate(letters):
            uu = (u - 0.2 - li * stagger) / 0.17  # vienos raidės laikas 0..1
            if uu <= 0:
                continue
            k_out = e(uu / 0.75)
            yb = fh / 2 - th * 0.35 + th * 1.9 * k_out
            zb = -pt * e((yb - fh / 2) / (th * 0.2) + 0.5)
            if uu < 1:
                a = math.radians(90) * min(1.0, e((uu - 0.3) / 0.7) * 1.1)
            else:
                a = math.radians(90) * (1 + 0.1 * math.cos((uu - 1) * 7) * math.exp(-(uu - 1) * 2.5))
            vis = e(uu / 0.25)
            x0 = x_start + lx * ppx
            lw_ = lf.width * ppx
            cx_ = x0 + lw_ / 2
            cx_ *= 0.3 + 0.7 * k_out  # startuoja ekrano ribose, išslysdama prasiskleidžia į savo vietą
            items.append((yb, lf, ls, lm, cx_ - lw_ / 2, cx_ + lw_ / 2, yb, zb, a, vis))
        items.sort(key=lambda it: it[0])
        for _, lf, ls, lm, xl, xr, yb, zb, a, vis in items:
            top_off = np.array((0, -math.cos(a), math.sin(a))) * th
            n_l = np.array((0, math.sin(a), math.cos(a)))
            base_l, base_r = np.array((xl, yb, zb)), np.array((xr, yb, zb))
            quad = [base_l + top_off, base_r + top_off, base_r, base_l]
            sl = th * 0.55 * math.sin(a)  # šešėlis už raidės
            if sl > 2:
                shq = [proj(tr(p)) for p in ((xl, yb - sl, -pt), (xr, yb - sl, -pt), (xr + 6, yb, -pt), (xl + 6, yb, -pt))]
                w_ = _warp(Image.merge("RGBA", [Image.new("L", lm.size, 0)] * 3 + [lm.point(lambda v: v * 0.6 * vis)]),
                           shq, W, H)
                if w_:
                    cv.alpha_composite(w_[0].filter(ImageFilter.GaussianBlur(4)), (w_[1], w_[2]))
            refl = 0.45 * vis * (1 - e((u - 0.6) / 0.2))  # atspindys telefono stikle – tik ekrano ribose, trumpam
            if refl > 0.01:
                mq = [proj(tr(np.array((p[0], p[1], -p[2])))) for p in quad]
                w_ = _warp(lf, mq, W, H)
                if w_:
                    patch, px, py = w_
                    m = Image.new("L", patch.size, 0)
                    ImageDraw.Draw(m).polygon([(x - px, y - py) for x, y in scr_q], fill=int(255 * refl))
                    patch.putalpha(Image.fromarray(np.minimum(np.asarray(patch.getchannel("A")), np.asarray(m))))
                    cv.alpha_composite(patch, (px, py))
            ext = th * 0.2  # storis – sluoksniai nuo galo
            diff = max(0.0, float(nrm(n_l) @ L))
            for j in range(8, 0, -1):
                off = -n_l * ext * j / 8
                w_ = _warp(ls, [proj(tr(p + off)) for p in quad], W, H)
                if w_:
                    p_ = np.asarray(w_[0], np.float32)
                    p_[..., :3] *= 0.75 + 0.35 * (1 - j / 8)
                    p_[..., 3] *= vis
                    cv.alpha_composite(Image.fromarray(p_.clip(0, 255).astype("uint8"), "RGBA"), (w_[1], w_[2]))
            f2 = lf.copy()  # blizgesio juosta, perbėganti per visą žodį
            band = Image.new("L", f2.size, 0)
            bx = (-0.3 + 1.6 * e((u - 0.55) / 0.3)) * (xr - x_start * -1 - x_start) / ppx - (xl - x_start) / ppx
            ImageDraw.Draw(band).polygon([(bx, 0), (bx + th * 0.5 / ppx * 0.3, 0), (bx - th * 0.2 / ppx * 0.3, f2.height),
                                          (bx - th * 0.7 / ppx * 0.3, f2.height)], fill=60)
            band = Image.fromarray(np.minimum(np.asarray(band.filter(ImageFilter.GaussianBlur(f2.height * 0.05))),
                                              np.asarray(lm)))
            white = Image.new("RGBA", f2.size, (255, 248, 225, 0))
            white.putalpha(band)
            f2.alpha_composite(white)
            w_ = _warp(f2, [proj(tr(p)) for p in quad], W, H)
            if w_:
                p_ = np.asarray(w_[0], np.float32)
                p_[..., :3] *= 0.8 + 0.4 * diff
                p_[..., 3] *= vis
                cv.alpha_composite(Image.fromarray(p_.clip(0, 255).astype("uint8"), "RGBA"), (w_[1], w_[2]))
        out = cv.convert("RGB")
        if back > 0.005:
            out = Image.blend(out, fr, back)
        proc.stdin.write(out.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("Nepavyko sukurti 3D efekto")
    return out_path


# ======================= 💥 dūžtantis ekranas: įtrūkimai → 3D šukės išlekia → po jomis kitas kadras =======================
def _clip_poly(poly, W, H):
    """Sutherland–Hodgman: daugiakampis apkerpamas stačiakampiu [0,W]x[0,H]."""
    def clip(pts, inside, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            if inside(b):
                if not inside(a):
                    out.append(inter(a, b))
                out.append(b)
            elif inside(a):
                out.append(inter(a, b))
        return out

    def ix(x0):
        return lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / ((b[0] - a[0]) or 1e-9))

    def iy(y0):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / ((b[1] - a[1]) or 1e-9), y0)
    for ins, it in ((lambda p: p[0] >= 0, ix(0)), (lambda p: p[0] <= W, ix(W)),
                    (lambda p: p[1] >= 0, iy(0)), (lambda p: p[1] <= H, iy(H))):
        poly = clip(poly, ins, it)
        if not poly:
            return []
    return poly


def _shards(W, H, seed=5):
    """Ekrano stiklo šukės: radialiniai įtrūkimai ir žiedai nuo smūgio taško. Grąžina (smūgio taškas, [daugiakampiai])."""
    import math
    import numpy as np
    rng = np.random.default_rng(seed)
    I = (W * 0.7, H * 0.74)
    S = max(W, H)
    na = 13
    angs = np.sort(rng.random(na) * 2 * math.pi)
    rings = [0.0, 0.05, 0.13, 0.25, 0.4, 0.6, 0.9, 1.6]
    rad = [[r * (1 + (0.25 * (rng.random() - 0.5) if 0 < r < 1.5 else 0)) for _ in range(na)] for r in rings]
    polys = []
    for i in range(len(rings) - 1):
        for j in range(na):
            a0, a1 = angs[j], angs[(j + 1) % na] + (2 * math.pi if j == na - 1 else 0)
            pts = [(I[0] + rad[i][j] * S * math.cos(a0), I[1] + rad[i][j] * S * math.sin(a0)),
                   (I[0] + rad[i][(j + 1) % na] * S * math.cos(a1), I[1] + rad[i][(j + 1) % na] * S * math.sin(a1)),
                   (I[0] + rad[i + 1][(j + 1) % na] * S * math.cos(a1), I[1] + rad[i + 1][(j + 1) % na] * S * math.sin(a1)),
                   (I[0] + rad[i + 1][j] * S * math.cos(a0), I[1] + rad[i + 1][j] * S * math.sin(a0))]
            if i == 0:
                pts = pts[1:]
            p = _clip_poly(pts, W, H)
            if len(p) >= 3 and abs(_poly_area(p)) > W * H * 0.0004:
                polys.append(p)
    return I, polys


def _poly_area(p):
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def _rotm(axis, ang):
    import numpy as np
    x, y, z = axis / np.linalg.norm(axis)
    c, s = np.cos(ang), np.sin(ang)
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


SHATTER_AT = 0.42  # efekto dalis, kai stiklas subyra (kadrų sandūra)


def render_shatter(src, t, out_path, W, H, fps=30, dur=None):
    """💥 Kadras atitolsta – telefonas ant stalo; stiklu pasklinda įtrūkimai, ekranas subyra į 3D šukes su
    kadro gabalais, kurios išlekia, o po jomis jau rodomas kitas kadras. Tada vėl per visą ekraną."""
    import math
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    d = dur or LEN["shatter3d"]
    n = round(d * fps)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-t", f"{d:.3f}", "-vf",
                          f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fsz = W * H * 3
    frames = [raw[i:i + fsz] for i in range(0, len(raw) - fsz + 1, fsz)][:n]
    if not frames:
        raise RuntimeError("Nepavyko paimti kadrų efektui")
    i_sh = max(0, min(len(frames) - 1, round(SHATTER_AT * (n - 1)) - 1))
    frozen = Image.frombytes("RGB", (W, H), frames[i_sh]).convert("RGBA")  # kadras, kuris subyra
    I, polys = _shards(W, H)
    rng = np.random.default_rng(8)
    S = max(W, H)
    shards = []
    for p in polys:
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(math.ceil(max(xs))), int(math.ceil(max(ys)))
        x1, y1 = max(x1, x0 + 2), max(y1, y0 + 2)
        m = Image.new("L", (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(m).polygon([(q[0] - x0, q[1] - y0) for q in p], fill=255)
        patch = frozen.crop((x0, y0, x1, y1))
        patch.putalpha(m)
        ImageDraw.Draw(patch).polygon([(q[0] - x0, q[1] - y0) for q in p], outline=(235, 245, 255, 190))
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        dv = np.array((cx - I[0], cy - I[1]))
        dist_ = float(np.linalg.norm(dv))
        dv = dv / (dist_ or 1)
        spd = W * (0.5 + 0.9 * rng.random()) * (1.3 - 0.6 * min(1, dist_ / (S * 0.7)))
        shards.append(dict(poly=p, box=(x0, y0, x1, y1), patch=patch, mask=m, c=(cx, cy),
                           rel=SHATTER_AT + 0.1 * min(1.0, dist_ / (S * 0.75)),
                           v=np.array((dv[0] * spd, dv[1] * spd, W * (0.6 + 1.1 * rng.random()))),
                           axis=rng.normal(0, 1, 3), w=4 + 8 * rng.random(), dist=dist_))
    table = _stone(2000, 2600)
    e = lambda x: 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))  # noqa: E731
    yy, xx = np.mgrid[0:H, 0:W]
    vign = (1 - 0.4 * (((xx - W * 0.4) / (W * 0.9)) ** 2 + ((yy - H * 0.35) / (H * 0.8)) ** 2)).clip(0.55, 1)
    bgc = Image.fromarray((np.dstack([vign * 108, vign * 112, vign * 118])).astype("uint8"))
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                             "-pix_fmt", "yuv420p", out_path], stdin=subprocess.PIPE)
    L = np.array([-0.35, -0.8, 0.5])
    L = L / np.linalg.norm(L)
    dist = H * 2.0
    for i in range(n):
        fr = Image.frombytes("RGB", (W, H), frames[min(i, len(frames) - 1)])
        u = i / max(1, n - 1)
        z = e(u / 0.22) * (1 - e((u - 0.8) / 0.2))
        if z < 0.002:
            proc.stdin.write(fr.tobytes())
            continue
        sc = (1 - 0.3 * z) * (1 + 0.1 * max(0.0, u - 0.15) * z)
        tilt = math.radians(36) * z
        ty = -H * 0.03 * z
        # ekrano tekstūra: gyvas kadras + dar nenukritusios šukės (sustingęs kadras) su įtrūkimais
        scr = fr.convert("RGBA")
        if u >= SHATTER_AT - 0.2:
            grow = e((u - (SHATTER_AT - 0.2)) / 0.18) * S * 1.1
            stay = [s_ for s_ in shards if u < s_["rel"]]
            if u >= SHATTER_AT - 1.0 / n:
                for s_ in stay:
                    scr.alpha_composite(s_["patch"], s_["box"][:2])
            cr = ImageDraw.Draw(scr)
            for s_ in shards:
                if s_["dist"] > grow or u >= s_["rel"]:
                    continue
                pts = s_["poly"] + [s_["poly"][0]]
                for a_, b_ in zip(pts, pts[1:]):
                    if math.dist(a_, I) <= grow and math.dist(b_, I) <= grow:
                        cr.line([a_, b_], fill=(20, 24, 30, 120), width=3)
                        cr.line([a_, b_], fill=(235, 245, 255, 210), width=1)
        front, b = _phone_front(scr, W, H, "phone3d", min(1.0, z / 0.15))
        fw, fh = front.size
        pt = fw * 0.07

        def tr(p):
            x, y, zz = p[0] * sc, p[1] * sc, p[2] * sc
            x, y, zz = _rot_x((x, y, zz), tilt)
            return np.array((x, y + ty, zz))

        def proj(v):
            f = dist / max(1.0, dist - v[2])
            return W / 2 + v[0] * f, H / 2 + v[1] * f

        cv = bgc.copy().convert("RGBA")
        tq = [proj(tr(p)) for p in ((-fw * 2.6, -fh * 2.4, -pt), (fw * 2.6, -fh * 2.4, -pt),
                                     (fw * 2.6, fh * 2.6, -pt), (-fw * 2.6, fh * 2.6, -pt))]
        w_ = _warp(table, tq, W, H)
        if w_:
            cv.alpha_composite(w_[0], (w_[1], w_[2]))
        cv = Image.fromarray((np.asarray(cv.convert("RGB"), np.float32) * vign[..., None] * 1.05).clip(0, 255)
                             .astype("uint8")).convert("RGBA")
        sq = [proj(tr(p)) for p in ((-fw / 2 + 8, -fh / 2 + 18, -pt), (fw / 2 + 8, -fh / 2 + 18, -pt),
                                     (fw / 2 + 16, fh / 2 + 30, -pt), (-fw / 2 + 16, fh / 2 + 30, -pt))]
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).polygon(sq, fill=(0, 0, 0, int(120 * z)))
        cv.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(2, W * 0.02))))
        r = fw * 0.1
        for pts, nv in (([(-fw / 2 + r, fh / 2, 0), (fw / 2 - r, fh / 2, 0), (fw / 2 - r, fh / 2, -pt),
                          (-fw / 2 + r, fh / 2, -pt)], (0, 1, 0)),
                        ([(fw / 2, -fh / 2 + r, 0), (fw / 2, fh / 2 - r, 0), (fw / 2, fh / 2 - r, -pt),
                          (fw / 2, -fh / 2 + r, -pt)], (1, 0, 0)),
                        ([(-fw / 2, -fh / 2 + r, 0), (-fw / 2, fh / 2 - r, 0), (-fw / 2, fh / 2 - r, -pt),
                          (-fw / 2, -fh / 2 + r, -pt)], (-1, 0, 0))):
            vs = [tr(p) for p in pts]
            nv_ = np.array(_rot_x(nv, tilt))
            c_ = sum(vs) / 4
            if float(nv_ @ (np.array((0, 0, dist)) - c_)) > 0:
                k_ = 0.4 + 0.7 * max(0.0, float(nv_ @ L))
                ImageDraw.Draw(cv).polygon([proj(v) for v in vs], fill=tuple(int(c * k_) for c in (176, 170, 160)) + (255,))
        scr_q = [proj(tr(p)) for p in ((-fw / 2, -fh / 2, 0), (fw / 2, -fh / 2, 0), (fw / 2, fh / 2, 0),
                                       (-fw / 2, fh / 2, 0))]
        w_ = _warp(front, scr_q, W, H)
        if w_:
            cv.alpha_composite(w_[0], (w_[1], w_[2]))
        # išlėkusios šukės (3D: skrieja nuo smūgio taško, sukasi, krenta)
        fly = []
        for s_ in shards:
            if u < s_["rel"]:
                continue
            tau = (u - s_["rel"]) * d
            R = _rotm(s_["axis"], s_["w"] * tau)
            x0, y0, x1, y1 = s_["box"]
            loc = lambda px, py: np.array((b + px - fw / 2, b + py - fh / 2, 0.0))  # noqa: E731
            c0 = loc(*s_["c"])
            pos = c0 + s_["v"] * tau + np.array((0, 0, -W * 1.6)) * tau * tau * 0.5
            corners = [pos + R @ (loc(px, py) - c0) for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            vs = [tr(p) for p in corners]
            fly.append((float(sum(v[2] for v in vs)) / 4, vs, R, s_))
        fly.sort(key=lambda x: x[0])
        for _, vs, R, s_ in fly:
            q = [proj(v) for v in vs]
            w_ = _warp(s_["patch"], q, W, H)
            if not w_:
                continue
            nloc = R @ np.array((0, 0, 1.0))
            nv_ = np.array(_rot_x(nloc, tilt))
            facing = float(nv_[2]) > 0
            hv = L + np.array((0, 0, 1.0))
            spec = max(0.0, float(nv_ @ (hv / np.linalg.norm(hv)))) ** 16
            a = np.asarray(w_[0], np.float32)
            if facing:
                a[..., :3] = (a[..., :3] * (0.85 + 0.25 * spec) + 160 * spec).clip(0, 255)
            else:  # matoma šukės nugarėlė – blyškesnis, melsvas stiklas
                a[..., :3] = (a[..., :3] * 0.55 + np.array((120, 150, 175)) * 0.45).clip(0, 255)
            cv.alpha_composite(Image.fromarray(a.astype("uint8"), "RGBA"), (w_[1], w_[2]))
        out = cv.convert("RGB")
        if z < 0.999:
            out = Image.blend(fr, out, min(1.0, z * 1.2))
        proc.stdin.write(out.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("Nepavyko sukurti 3D efekto")
    return out_path
