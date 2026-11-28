"""✨ 3D akcentai: tūriniai elementai, pritaikyti prie kadro turinio.

Kiekvienas akcentas – {"kind", "t" (pradžia, s), "dur", "x", "y" (taikinys / vieta, 0..1), "size", "color", "text",
"dir"}. Piešiama ant tikrų kadrų (PIL + perspektyva): šešėlio kryptis – pagal šviesą kadre, judėjimo kryptis – pagal
laisvą vietą ar judesį kadre, veidai ir titrų juosta paliekami matomi (vietą parenka pasiūlymai, žr. suggest()).

Rūšys:
  word3d  – svarbus žodis / skaičius iškyla iš titrų kaip tūrinis užrašas (kai ištariamas)
  arrow3d – 3D rodyklė atskrenda ir pasiekia detalę tuo metu, kai ji parodoma
  ring3d  – besisukantis 3D žiedas aplink detalę
  card3d  – atsiverčianti 3D kortelė šalia detalės
  glass3d – rezultatas atskleidžiamas per įtrūkstantį stiklą (kadro pasikeitimo metu)
  flip3d  – atsiverčianti plokštuma (kadras atsiverčia kaip durys / puslapis)
  blocks3d – kadras išslysta kaladėlėmis, po juo – kitas kadras
"""
import math
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import video_editor

KINDS = {
    "word3d": "🔠 Tūrinis žodis", "arrow3d": "➡️ 3D rodyklė", "ring3d": "⭕ 3D žiedas", "card3d": "🪧 3D kortelė",
    "glass3d": "💥 Įtrūkstantis stiklas", "flip3d": "📖 Atsiverčianti plokštuma", "blocks3d": "🧱 Išslystančios kaladėlės",
}
CATEGORY = {"word3d": "word", "arrow3d": "detail", "ring3d": "detail", "card3d": "detail",
            "glass3d": "reveal", "flip3d": "reveal", "blocks3d": "reveal"}
VARIANTS = {"word": ["word3d"], "detail": ["arrow3d", "ring3d", "card3d"], "reveal": ["glass3d", "flip3d", "blocks3d"]}
LEN = {"word3d": 1.4, "arrow3d": 1.8, "ring3d": 1.8, "card3d": 2.2, "glass3d": 1.2, "flip3d": 0.9, "blocks3d": 1.0}
CUT_AT = {"glass3d": 0.35, "flip3d": 0.12, "blocks3d": 0.1}   # perėjimo dalis, kai keičiasi kadras
HIT_AT = {"arrow3d": 0.5, "ring3d": 0.15, "card3d": 0.12}      # kada elementas pasiekia / apgaubia detalę
DEFAULT_COLOR = "#E9A23B"
FONT = os.path.join(video_editor.FONT_DIR, "Montserrat_900Black.ttf")


def ease(x):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))


def back_out(x, s=1.7):
    x = max(0.0, min(1.0, x)) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def rgb(color):
    c = str(color or DEFAULT_COLOR).lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        c = DEFAULT_COLOR[1:]
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(c, k):
    """k > 0 – šviesiau, k < 0 – tamsiau."""
    return tuple(int(v + (255 - v) * k) if k > 0 else int(v * (1 + k)) for v in c)


def light_dir(img):
    """Iš kur krenta šviesa kadre (vienetinis vektorius vaizdo koordinatėmis). Šešėlis – priešinga kryptimi."""
    a = np.asarray(img.convert("L").resize((48, 85)), np.float32)
    w = np.clip(a - np.percentile(a, 70), 0, None)
    if w.sum() < 1:
        return np.array((-0.4, -0.9))
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    v = np.array(((xs * w).sum() / w.sum() / a.shape[1] - 0.5, (ys * w).sum() / w.sum() / a.shape[0] - 0.5))
    n = np.linalg.norm(v)
    return v / n if n > 0.04 else np.array((-0.4, -0.9)) / np.linalg.norm((-0.4, -0.9))


# ---------- 3D pagalbinės ----------
def rot(p, rx=0.0, ry=0.0, rz=0.0):
    x, y, z = p
    c, s = math.cos(rz), math.sin(rz)
    x, y = x * c - y * s, x * s + y * c
    c, s = math.cos(ry), math.sin(ry)
    x, z = x * c + z * s, -x * s + z * c
    c, s = math.cos(rx), math.sin(rx)
    y, z = y * c - z * s, y * s + z * c
    return np.array((x, y, z))


def persp(cx, cy, p, D):
    f = D / max(1.0, D - p[2])
    return cx + p[0] * f, cy + p[1] * f


def coeffs(src, dst):
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(m, float), np.array([c for uv in src for c in uv], float)).tolist()


def warp(img, quad, W, H):
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    x0, y0 = max(0, int(min(xs)) - 1), max(0, int(min(ys)) - 1)
    x1, y1 = min(W, int(max(xs)) + 2), min(H, int(max(ys)) + 2)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    try:
        co = coeffs([(0, 0), (img.width, 0), (img.width, img.height), (0, img.height)],
                    [(x - x0, y - y0) for x, y in quad])
    except np.linalg.LinAlgError:
        return None
    return img.transform((x1 - x0, y1 - y0), Image.PERSPECTIVE, co, Image.BICUBIC), x0, y0


def fade(img, a):
    if a >= 0.999:
        return img
    im = img.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return im


def sprite3d(cv, face, side, mask, cx, cy, w, h, rx=0.0, ry=0.0, rz=0.0, z=0.0, depth=0.0, alpha=1.0,
             shadow=None, D=2000.0, layers=8):
    """Plokščias paveikslas su storiu 3D erdvėje (centras cx, cy; plotis / aukštis px). shadow = (dx, dy, blur, galia)."""
    W, H = cv.size
    corners = [(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)]
    n = rot((0, 0, 1), rx, ry, rz)
    pts = [rot(c, rx, ry, rz) + np.array((0, 0, z)) for c in corners]
    if shadow and alpha > 0.02:
        dx, dy, bl, op = shadow
        q = [persp(cx + dx, cy + dy, p * np.array((1, 1, 0)), D) for p in pts]
        r_ = warp(Image.merge("RGBA", [Image.new("L", mask.size, 0)] * 3 + [mask.point(lambda v: int(v * op * alpha))]),
                  q, W, H)
        if r_:
            paste_blur(cv, r_[0], r_[1], r_[2], bl)
    front = n[2] >= 0
    if depth > 0 and side is not None:
        for j in range(layers, 0, -1):
            off = -n * depth * j / layers * (1 if front else -1)
            q = [persp(cx, cy, p + off, D) for p in pts]
            r_ = warp(fade(side, alpha), q, W, H)
            if r_:
                cv.alpha_composite(r_[0], (r_[1], r_[2]))
    q = [persp(cx, cy, p, D) for p in pts]
    r_ = warp(fade(face if front else side, alpha), q, W, H)
    if r_:
        cv.alpha_composite(r_[0], (r_[1], r_[2]))


def paste_blur(cv, patch, x, y, blur):
    """Sulieto (šešėlio) gabalo uždėjimas – su paraštėmis, apkerpant drobės ribomis."""
    pad = int(blur * 2.5) + 2
    big = Image.new("RGBA", (patch.width + 2 * pad, patch.height + 2 * pad), (0, 0, 0, 0))
    big.paste(patch, (pad, pad))
    big = big.filter(ImageFilter.GaussianBlur(blur))
    x0, y0 = x - pad, y - pad
    cx0, cy0 = max(0, -x0), max(0, -y0)
    cx1, cy1 = min(big.width, cv.width - x0), min(big.height, cv.height - y0)
    if cx1 > cx0 and cy1 > cy0:
        cv.alpha_composite(big.crop((cx0, cy0, cx1, cy1)), (x0 + cx0, y0 + cy0))


def text_sprite(text, height, color):
    """Tūrinio užrašo veidas (spalvos gradientas + briaunų šviesa), šonas ir kaukė."""
    font = ImageFont.truetype(FONT, height)
    l, t, r, b = font.getbbox(text)
    pad = round(height * 0.14)
    w, h = r - l + 2 * pad, b - t + 2 * pad
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).text((pad - l, pad - t), text, font=font, fill=255)
    return _shade(m, rgb(color), height)


def _shade(m, c, scale):
    """Kaukė -> tūrio veidas (šviesesnis viršus, briaunų šviesa) ir tamsesnis šonas."""
    w, h = m.size
    M = np.asarray(m, np.float32) / 255
    yy = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    top, mid, bot = np.array(mix(c, 0.45)), np.array(c), np.array(mix(c, -0.3))
    k = yy[..., None]
    col = np.where(k < 0.5, top * (1 - k * 2) + mid * k * 2, mid * (2 - k * 2) + bot * (k * 2 - 1))
    bl = np.asarray(m.filter(ImageFilter.GaussianBlur(max(1, scale * 0.04))), np.float32) / 255
    gy, gx = np.gradient(bl)
    col = (col + (-(gx * 0.6 + gy) * scale * 0.9)[..., None] * 90).clip(0, 255)
    face = Image.fromarray(np.dstack([col, M * 255]).astype("uint8"), "RGBA")
    sc = mix(c, -0.45)
    side = Image.fromarray(np.dstack([np.full((h, w), sc[0]), np.full((h, w), sc[1]), np.full((h, w), sc[2]), M * 255])
                           .astype("uint8"), "RGBA")
    return face, side, m


def arrow_sprite(length, thick, color):
    """Rodyklė į dešinę (smaigalys – dešiniajame krašte)."""
    L, T = int(length), int(thick)
    m = Image.new("L", (L, T), 0)
    d = ImageDraw.Draw(m)
    head = int(T * 1.05)
    d.rounded_rectangle((0, T * 0.32, L - head + 4, T * 0.68), radius=int(T * 0.16), fill=255)
    d.polygon([(L - head, 0), (L - 1, T / 2), (L - head, T - 1)], fill=255)
    return _shade(m, rgb(color), T)


def card_sprite(text, width, color):
    W_, H_ = int(width), int(width * 0.34)
    face = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(face)
    r = int(H_ * 0.22)
    d.rounded_rectangle((0, 0, W_ - 1, H_ - 1), r, fill=(250, 250, 252, 245))
    d.rounded_rectangle((0, 0, int(W_ * 0.06) + r, H_ - 1), r, fill=rgb(color) + (255,))
    d.rectangle((int(W_ * 0.06), 0, int(W_ * 0.06) + r, H_ - 1), fill=(250, 250, 252, 245))
    txt = (text or "").upper()[:16] or "ŽIŪRĖKITE"
    size = int(H_ * 0.42)
    font = ImageFont.truetype(FONT, size)
    while font.getlength(txt) > W_ * 0.78 and size > 10:
        size -= 2
        font = ImageFont.truetype(FONT, size)
    l, t, rr, b = font.getbbox(txt)
    d.text((W_ * 0.13 - l, (H_ - (b - t)) / 2 - t), txt, font=font, fill=(28, 28, 34, 255))
    m = face.getchannel("A")
    side = Image.new("RGBA", face.size, mix(rgb(color), -0.35) + (255,))
    side.putalpha(m)
    return face, side, m


# ---------- garsas, kadrai ----------
def _frames(src, t, d, W, H, fps):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-t", f"{d:.3f}", "-vf",
                          f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fsz = W * H * 3
    out = [raw[i:i + fsz] for i in range(0, len(raw) - fsz + 1, fsz)]
    if not out:
        raise RuntimeError("Nepavyko paimti kadrų akcentui")
    return out


# ---------- rūšių piešimas: f(kadras, u, būsena) -> kadras ----------
def _word(it, W, H, frames, n, fps):
    size = float(it.get("size") or 1.0)
    text = re.sub(r"[^\w%€$+\-.,!?]", "", str(it.get("text") or "").replace(video_editor.KEY_MARK, "")).upper()[:14] or "WOW"
    hgt = int(H * 0.095 * size)
    face, side, mask = text_sprite(text, hgt, it.get("color"))
    k = min(1.0, W * 0.9 / face.width)
    w, h = face.width * k, face.height * k
    X, Y = float(it.get("x", 0.5)) * W, float(it.get("y", 0.6)) * H
    light = light_dir(Image.frombytes("RGB", (W, H), frames[0]))
    sh = (-light[0] * H * 0.022 * size, -light[1] * H * 0.022 * size + H * 0.01, H * 0.01, 0.55)

    def draw(fr, u):
        a = back_out(u / 0.28)
        b = ease((u - 0.8) / 0.2)
        if u <= 0 or b >= 1:
            return fr
        cv = fr.convert("RGBA")
        y = Y + (1 - min(1, a)) * H * 0.11 + b * H * 0.06   # iškyla iš titrų ir grįžta į juos
        sc = max(0.05, (0.4 + 0.6 * a) * (1 - 0.45 * b))
        rx = math.radians(75) * (1 - min(1.0, a)) - math.radians(55) * b
        ry = math.radians(13) * math.sin(2 * math.pi * u * 0.9) * (1 - b)
        sprite3d(cv, face, side, mask, X, y, w * sc, h * sc, rx=rx, ry=ry, depth=h * sc * 0.22,
                 alpha=min(1.0, u / 0.1) * (1 - b), shadow=sh, D=H * 2.2)
        return cv.convert("RGB")
    return draw


def _arrow(it, W, H, frames, n, fps):
    size = float(it.get("size") or 1.0)
    T = np.array((float(it.get("x", 0.5)) * W, float(it.get("y", 0.5)) * H))
    side_from = it.get("dir") or ("right" if T[0] < W / 2 else "left")
    S = np.array((W * 1.25 if side_from == "right" else -W * 0.25, T[1] + H * 0.22))
    R = W * 0.06 * size
    v = T - S
    P = T - v / np.linalg.norm(v) * R
    perp = np.array((-v[1], v[0])) / np.linalg.norm(v)
    C = (S + P) / 2 + perp * W * 0.12 * (1 if side_from == "right" else -1)
    L, TH = W * 0.36 * size, W * 0.11 * size
    face, side, mask = arrow_sprite(L * 2, TH * 2, it.get("color"))
    light = light_dir(Image.frombytes("RGB", (W, H), frames[0]))
    sh = (-light[0] * H * 0.03 * size, -light[1] * H * 0.03 * size + H * 0.012, H * 0.012, 0.5)
    uh = HIT_AT["arrow3d"]

    def bez(p):
        return (1 - p) ** 2 * S + 2 * (1 - p) * p * C + p ** 2 * P

    def draw(fr, u):
        if u <= 0:
            return fr
        out = ease((u - 0.85) / 0.15)
        if out >= 1:
            return fr
        p = min(1.0, back_out(u / uh, 1.1))
        tip = bez(min(1.0, p))
        tang = bez(min(1.0, p) + 1e-3) - bez(max(0.0, min(1.0, p) - 1e-3))
        ang = math.atan2(tang[1], tang[0]) if np.linalg.norm(tang) > 1e-6 else math.atan2(v[1], v[0])
        if u > uh:  # pasiekė – du švelnūs „bakstelėjimai“
            ang = math.atan2(P[1] - C[1], P[0] - C[0])
            poke = 0.18 * abs(math.sin((u - uh) * 13)) * math.exp(-(u - uh) * 4)
            tip = P - np.array((math.cos(ang), math.sin(ang))) * R * poke * 2
        ctr = tip - np.array((math.cos(ang), math.sin(ang))) * L / 2
        cv = fr.convert("RGBA")
        sprite3d(cv, face, side, mask, ctr[0], ctr[1], L, TH, rx=math.radians(30), ry=math.radians(8) * math.sin(u * 9),
                 rz=ang, depth=TH * 0.3, alpha=min(1.0, u / 0.08) * (1 - out), shadow=sh, D=H * 2.0)
        return cv.convert("RGB")
    return draw


def _ring(it, W, H, frames, n, fps):
    size = float(it.get("size") or 1.0)
    X, Y = float(it.get("x", 0.5)) * W, float(it.get("y", 0.5)) * H
    R = W * 0.11 * size
    c = rgb(it.get("color"))
    light = light_dir(Image.frombytes("RGB", (W, H), frames[0]))
    tube = max(3, W * 0.017 * size)

    def draw(fr, u):
        a = back_out(u / 0.2)
        out = ease((u - 0.85) / 0.15)
        if u <= 0 or out >= 1:
            return fr
        cv = fr.convert("RGBA")
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        rr = R * max(0.05, a)
        yy = Y - (1 - min(1, a)) * H * 0.08
        rx, ry, spin = math.radians(64), math.radians(16) * math.sin(2 * math.pi * u * 0.7), u * 7
        pts = []
        for k in range(97):
            th = 2 * math.pi * k / 96
            p = rot((rr * math.cos(th), rr * math.sin(th), 0), rx, ry)
            pts.append((X + p[0] * (H * 2 / (H * 2 - p[2])), yy + p[1] * (H * 2 / (H * 2 - p[2])), p[2], th))
        alpha = (1 - out)
        # šešėlis ant kadro – priešinga šviesai kryptimi
        shl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shl).line([(x - light[0] * tube * 2.5, y - light[1] * tube * 2.5 + tube * 1.5)
                                  for x, y, _, _ in pts], fill=(0, 0, 0, int(70 * alpha)), width=int(tube * 1.6))
        cv.alpha_composite(shl.filter(ImageFilter.GaussianBlur(tube * 2.2)))
        for front in (False, True):  # galinė pusė (už objekto) – tamsesnė ir plonesnė
            for (x0, y0, z0, th), (x1, y1, z1, _) in zip(pts, pts[1:]):
                if (z0 + z1 > 0) != front:
                    continue
                lit = 0.55 + 0.45 * math.sin(th + spin)  # bėganti šviesa – sukimosi įspūdis
                col = mix(c, 0.35 * lit) if front else mix(c, -0.35)
                d.line([(x0, y0), (x1, y1)], fill=col + (int(255 * alpha * (1 if front else 0.75)),),
                       width=int(tube * (1.0 if front else 0.7)))
        glow = lay.filter(ImageFilter.GaussianBlur(tube * 1.2))
        cv.alpha_composite(fade(glow, 0.6))
        cv.alpha_composite(lay)
        return cv.convert("RGB")
    return draw


def _card(it, W, H, frames, n, fps):
    size = float(it.get("size") or 1.0)
    T = np.array((float(it.get("x", 0.5)) * W, float(it.get("y", 0.5)) * H))
    cw = W * 0.42 * size
    face, side, mask = card_sprite(it.get("text"), cw * 2, it.get("color"))
    ch = cw * face.height / face.width
    side_to = it.get("dir") or ("left" if T[0] > W / 2 else "right")
    gap = W * 0.09 * size
    cx = T[0] - gap - cw / 2 if side_to == "left" else T[0] + gap + cw / 2
    cx = min(W - cw / 2 - 8, max(cw / 2 + 8, cx))
    cy = min(H * 0.85, max(H * 0.1, T[1] - H * 0.06 * size))
    light = light_dir(Image.frombytes("RGB", (W, H), frames[0]))
    sh = (-light[0] * H * 0.025, -light[1] * H * 0.025 + H * 0.012, H * 0.012, 0.45)
    c = rgb(it.get("color"))

    def draw(fr, u):
        a = back_out(u / 0.22, 1.2)
        out = ease((u - 0.86) / 0.14)
        if u <= 0 or out >= 1:
            return fr
        cv = fr.convert("RGBA")
        al = min(1.0, u / 0.08) * (1 - out)
        d = ImageDraw.Draw(cv)
        ex = cx + (cw / 2 if side_to == "left" else -cw / 2)
        d.line([(ex, cy), (T[0], T[1])], fill=c + (int(220 * al * min(1, a)),), width=max(2, int(W * 0.005)))
        rr = W * 0.012 * size
        d.ellipse((T[0] - rr, T[1] - rr, T[0] + rr, T[1] + rr), fill=c + (int(255 * al),), outline=(255, 255, 255, int(220 * al)),
                  width=max(1, int(rr * 0.35)))
        ry = math.radians(90) * (1 - min(1.0, a)) * (-1 if side_to == "left" else 1) - math.radians(90) * out
        bob = math.sin(u * 7) * H * 0.004
        sprite3d(cv, face, side, mask, cx, cy + bob, cw, ch, rx=math.radians(6), ry=ry, depth=ch * 0.12,
                 alpha=al, shadow=sh, D=H * 2.0, layers=5)
        return cv.convert("RGB")
    return draw


def _reveal_base(it, frames, n, W, H):
    kind = it["kind"]
    i_cut = max(0, min(n - 1, round(CUT_AT[kind] * (n - 1))))
    # tikroji kadro pasikeitimo vieta – didžiausias gretimų kadrų skirtumas šalia numatytos (kadrų laikai apvalinami)
    lo, hi = max(1, i_cut - 5), min(n - 1, i_cut + 5)
    small = [np.asarray(Image.frombytes("RGB", (W, H), frames[i]).convert("L").resize((36, 64)), np.float32)
             for i in range(lo - 1, hi + 1)]
    diffs = [float(np.abs(small[j + 1] - small[j]).mean()) for j in range(len(small) - 1)]
    if diffs and max(diffs) > 12:
        i_cut = lo + int(np.argmax(diffs))
    frozen = Image.frombytes("RGB", (W, H), frames[max(0, i_cut - 1)])
    return i_cut, frozen


def _glass(it, W, H, frames, n, fps):
    i_cut, frozen = _reveal_base(it, frames, n, W, H)
    u_cut = i_cut / max(1, n - 1)
    I = (float(it.get("x", 0.5)) * W, float(it.get("y", 0.45)) * H)
    rng = np.random.default_rng(int(I[0] * 7 + I[1]))
    S = max(W, H)
    na = 12
    angs = np.sort(rng.random(na) * 2 * math.pi)
    rings = [0.0, 0.06, 0.15, 0.28, 0.45, 0.7, 1.6]
    rad = [[r * (1 + (0.25 * (rng.random() - 0.5) if 0 < r < 1.5 else 0)) for _ in range(na)] for r in rings]
    import fxpack
    shards = []
    fz = frozen.convert("RGBA")
    for i in range(len(rings) - 1):
        for j in range(na):
            a0, a1 = angs[j], angs[(j + 1) % na] + (2 * math.pi if j == na - 1 else 0)
            P = lambda r, a: (I[0] + r * S * math.cos(a), I[1] + r * S * math.sin(a))  # noqa: E731
            pts = [P(rad[i][j], a0), P(rad[i][(j + 1) % na], a1), P(rad[i + 1][(j + 1) % na], a1), P(rad[i + 1][j], a0)]
            pts = fxpack._clip_poly(pts[1:] if i == 0 else pts, W, H)
            if len(pts) < 3 or abs(fxpack._poly_area(pts)) < W * H * 0.0003:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            box = (int(min(xs)), int(min(ys)), int(math.ceil(max(xs))) + 1, int(math.ceil(max(ys))) + 1)
            m = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
            ImageDraw.Draw(m).polygon([(x - box[0], y - box[1]) for x, y in pts], fill=255)
            patch = fz.crop(box)
            patch.putalpha(m)
            ImageDraw.Draw(patch).polygon([(x - box[0], y - box[1]) for x, y in pts], outline=(240, 248, 255, 200))
            c = (sum(xs) / len(xs), sum(ys) / len(ys))
            dv = np.array((c[0] - I[0], c[1] - I[1]))
            dist = float(np.linalg.norm(dv)) or 1.0
            shards.append(dict(poly=pts, box=box, patch=patch, c=c, dist=dist, dv=dv / dist,
                               rel=0.06 * min(1.0, dist / (S * 0.6)), vz=H * (0.8 + 1.6 * rng.random()),
                               sp=W * (0.3 + 0.9 * rng.random()), axis=rng.normal(0, 1, 3), w=5 + 9 * rng.random()))
    D = H * 1.8
    dur = n / fps

    def draw(fr, u):
        if u < 0.04:
            return fr
        if u < u_cut:  # įtrūkimai plinta nuo smūgio taško
            cv = fr.convert("RGBA")
            d = ImageDraw.Draw(cv)
            grow = ease((u - 0.04) / max(0.05, u_cut - 0.04)) * S * 0.9
            for s_ in shards:
                pts = s_["poly"] + [s_["poly"][0]]
                for a_, b_ in zip(pts, pts[1:]):
                    if math.dist(a_, I) <= grow and math.dist(b_, I) <= grow:
                        d.line([a_, b_], fill=(20, 24, 30, 110), width=3)
                        d.line([a_, b_], fill=(240, 248, 255, 220), width=1)
            return cv.convert("RGB")
        cv = fr.convert("RGBA")  # po stiklu – jau kitas kadras
        tau_all = (u - u_cut) * dur
        if tau_all < 0.06:  # smūgio blyksnis
            fl = Image.new("RGBA", (W, H), (255, 255, 255, int(90 * (1 - tau_all / 0.06))))
            cv.alpha_composite(fl)
        for s_ in sorted(shards, key=lambda s: s["dist"], reverse=True):
            tau = tau_all - s_["rel"] * dur
            x0, y0, x1, y1 = s_["box"]
            if tau <= 0:
                cv.alpha_composite(s_["patch"], (x0, y0))
                continue
            ax = s_["axis"] / np.linalg.norm(s_["axis"])
            ang = s_["w"] * tau
            cxy = np.array(s_["c"])
            pos = np.array((cxy[0] - W / 2 + s_["dv"][0] * s_["sp"] * tau, cxy[1] - H / 2 + s_["dv"][1] * s_["sp"] * tau
                            + 0.5 * H * 1.2 * tau * tau, s_["vz"] * tau))
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            Rm = np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K
            q = []
            for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                p = pos + Rm @ np.array((px - cxy[0], py - cxy[1], 0.0))
                q.append(persp(W / 2, H / 2, p, D))
            r_ = warp(s_["patch"], q, W, H)
            if r_:
                cv.alpha_composite(fade(r_[0], max(0.0, 1 - tau / (dur * 0.9))), (r_[1], r_[2]))
        return cv.convert("RGB")
    return draw


def _flip(it, W, H, frames, n, fps):
    i_cut, frozen = _reveal_base(it, frames, n, W, H)
    u_cut = i_cut / max(1, n - 1)
    dirn = it.get("dir") or "left"
    fz = frozen.convert("RGBA")
    D = H * 1.7

    def draw(fr, u):
        if u < u_cut:
            return fr
        k = ease((u - u_cut) / (1 - u_cut))
        ang = math.radians(105) * k
        cv = fr.convert("RGBA")
        # plokštuma sukasi apie kraštą (vyrį); kampai – 3D, perspektyva iš kadro centro
        if dirn in ("left", "right"):
            hx = -W / 2 if dirn == "left" else W / 2
            sgn = 1 if dirn == "left" else -1
            pts = []
            for x, y in ((-W / 2, -H / 2), (W / 2, -H / 2), (W / 2, H / 2), (-W / 2, H / 2)):
                dx = x - hx
                pts.append(np.array((hx + dx * math.cos(ang), y, -sgn * dx * math.sin(ang))))  # tolsta nuo žiūrovo
        else:
            hy = -H / 2 if dirn == "up" else H / 2
            sgn = 1 if dirn == "up" else -1
            pts = []
            for x, y in ((-W / 2, -H / 2), (W / 2, -H / 2), (W / 2, H / 2), (-W / 2, H / 2)):
                dy = y - hy
                pts.append(np.array((x, hy + dy * math.cos(ang), -sgn * dy * math.sin(ang))))
        # šešėlis ant kito kadro prie vyrio
        sh = Image.new("L", (W, H), 0)
        a = int(150 * math.sin(min(ang, math.pi / 2)) * (1 - k * 0.6))
        g = np.linspace(1, 0, 256) ** 1.5 * a
        line = Image.fromarray(g.astype("uint8")[None, :].repeat(4, 0))
        if dirn in ("left", "right"):
            band = line.resize((int(W * 0.5), H))
            if dirn == "right":
                band = band.transpose(Image.FLIP_LEFT_RIGHT)
            sh.paste(band, (0 if dirn == "left" else W - band.width, 0))
        else:
            band = line.transpose(Image.ROTATE_270).resize((W, int(H * 0.4)))
            if dirn == "down":
                band = band.transpose(Image.FLIP_TOP_BOTTOM)
            sh.paste(band, (0, 0 if dirn == "up" else H - band.height))
        black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        black.putalpha(sh)
        cv.alpha_composite(black)
        q = [persp(W / 2, H / 2, p, D) for p in pts]
        face = fz if ang < math.pi / 2 else Image.new("RGBA", fz.size, (40, 40, 46, 255))
        r_ = warp(face, q, W, H)
        if r_:
            pa = np.asarray(r_[0], np.float32)
            pa[..., :3] *= 1 - 0.4 * math.sin(min(ang, math.pi / 2))  # nusisukusi plokštuma tamsėja
            cv.alpha_composite(Image.fromarray(pa.clip(0, 255).astype("uint8"), "RGBA"), (r_[1], r_[2]))
        return cv.convert("RGB")
    return draw


def _blocks(it, W, H, frames, n, fps):
    i_cut, frozen = _reveal_base(it, frames, n, W, H)
    u_cut = i_cut / max(1, n - 1)
    dirn = it.get("dir") or "right"
    cols, rows = (5, 9) if H >= W else (9, 5)
    tw, th = W / cols, H / rows
    fz = frozen.convert("RGBA")
    rng = np.random.default_rng(11)
    tiles = []
    for r in range(rows):
        for c in range(cols):
            box = (int(c * tw), int(r * th), int((c + 1) * tw), int((r + 1) * th))
            order = {"right": (cols - 1 - c) / cols, "left": c / cols, "down": (rows - 1 - r) / rows,
                     "up": r / rows}[dirn]
            tiles.append(dict(box=box, img=fz.crop(box), delay=order * 0.45 + rng.random() * 0.12,
                              rz=(rng.random() - 0.5) * 0.6, tilt=0.4 + 0.5 * rng.random()))
    vec = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}[dirn]
    D = H * 1.8

    def draw(fr, u):
        if u < u_cut:
            return fr
        k = (u - u_cut) / (1 - u_cut)
        cv = fr.convert("RGBA")
        for tl in tiles:
            x0, y0, x1, y1 = tl["box"]
            p = max(0.0, min(1.0, (k - tl["delay"]) / 0.45))
            if p <= 0:
                cv.alpha_composite(tl["img"], (x0, y0))
                continue
            e = p * p
            cxy = np.array(((x0 + x1) / 2 - W / 2 + vec[0] * e * W * 1.3, (y0 + y1) / 2 - H / 2 + vec[1] * e * H * 1.1,
                            W * 0.3 * math.sin(math.pi * p)))
            rx = tl["tilt"] * e * (vec[1] or 0.6)
            ry = tl["tilt"] * e * (vec[0] or 0.6)
            q = [persp(W / 2, H / 2, cxy + rot((px, py, 0), rx, ry, tl["rz"] * e), D)
                 for px, py in ((-(x1 - x0) / 2, -(y1 - y0) / 2), ((x1 - x0) / 2, -(y1 - y0) / 2),
                                ((x1 - x0) / 2, (y1 - y0) / 2), (-(x1 - x0) / 2, (y1 - y0) / 2))]
            sq = [(x + W * 0.02 * p, y + H * 0.02 * p) for x, y in q]  # šešėlis ant kito kadro
            shl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(shl).polygon(sq, fill=(0, 0, 0, int(90 * (1 - p))))
            cv.alpha_composite(shl)
            r_ = warp(tl["img"], q, W, H)
            if r_:
                cv.alpha_composite(r_[0], (r_[1], r_[2]))
        return cv.convert("RGB")
    return draw


DRAW = {"word3d": _word, "arrow3d": _arrow, "ring3d": _ring, "card3d": _card, "glass3d": _glass, "flip3d": _flip,
        "blocks3d": _blocks}


def render(src, t, it, out_path, W, H, fps=30, dur=None):
    """Akcento atkarpa (be garso) nuo t: kadrai su 3D elementu."""
    d = float(dur or it.get("dur") or LEN[it["kind"]])
    n = max(2, round(d * fps))
    frames = _frames(src, t, d, W, H, fps)[:n]
    n = len(frames)
    draw = DRAW[it["kind"]](it, W, H, frames, n, fps)
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                             "-pix_fmt", "yuv420p", out_path], stdin=subprocess.PIPE)
    for i, raw in enumerate(frames):
        fr = Image.frombytes("RGB", (W, H), raw)
        proc.stdin.write(draw(fr, i / max(1, n - 1)).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("Nepavyko sukurti 3D akcento")
    return out_path


def sfx(it, t, d):
    """Akcento garsai: [(laikas, rūšis)]."""
    k = it["kind"]
    if k == "word3d":
        return [(t + d * 0.05, "pop")]
    if k == "arrow3d":
        return [(t + d * 0.05, "whoosh"), (t + d * HIT_AT[k], "tap")]
    if k in ("ring3d", "card3d"):
        return [(t + d * 0.03, "whoosh")]
    if k == "glass3d":
        return [(t + d * (0.05 + (CUT_AT[k] - 0.05) * j / 5), "crack") for j in range(6)] + [(t + d * CUT_AT[k], "shatter")]
    if k == "flip3d":
        return [(t + d * CUT_AT[k], "whoosh")]
    if k == "blocks3d":
        return [(t + d * (CUT_AT[k] + 0.08 * j), "tap") for j in range(6)]
    return []


# ======================= 🔎 pasiūlymai pagal klipo turinį =======================
DETAIL_RE = re.compile(r"^(štai|čia|šit|šis|ši|šią|mygtuk|paspausk|spausk|produkt|prek|žiūrėk|pažiūrėk|matot|matote|"
                       r"nuorod|naujien|kolekcij|dėžut|programėl|svetain|meniu|kain|pristat)", re.I)
RESULT_RE = re.compile(r"^(rezultat|prieš|pokyt|skirtum|galutin|baigt|atrodo|transformacij|virsta|tapo|gavosi|po)$|"
                       r"^(rezultat|pokyt|skirtum|transformacij)", re.I)
_CASCADE = None


def faces(img):
    """Veidai kadre [(x0, y0, x1, y1)] 0..1 (OpenCV Haar). Akcentai jų neuždengia."""
    global _CASCADE
    try:
        import cv2
        if _CASCADE is None:
            _CASCADE = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
        g = np.asarray(img.convert("L"))
        k = 360 / max(g.shape)
        g = cv2.resize(g, (int(g.shape[1] * k), int(g.shape[0] * k)))
        found = _CASCADE.detectMultiScale(g, 1.1, 5, minSize=(24, 24))
        H_, W_ = g.shape
        return [(x / W_, y / H_, (x + w) / W_, (y + h) / H_) for x, y, w, h in found]
    except Exception:
        return []


def saliency_target(img, face_boxes, subs_y):
    """Ryškiausia detalė (kraštai + spalvos kontrastas), ne ant veido, ne titrų juostoje, ne prie kraštų.
    Grąžina (x, y, stiprumas) arba None."""
    w, h = (36, 64) if img.height >= img.width else (64, 36)
    a = np.asarray(img.convert("RGB").resize((w, h)), np.float32)
    lum = a.mean(axis=2)
    gy, gx = np.gradient(lum)
    edges = np.hypot(gx, gy)
    contrast = np.linalg.norm(a - a.reshape(-1, 3).mean(axis=0), axis=2)
    sal = edges / (edges.max() + 1e-6) * 0.5 + contrast / (contrast.max() + 1e-6) * 0.5
    sal = np.asarray(Image.fromarray((sal * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(2)), np.float32)
    ys, xs = np.mgrid[0:h, 0:w]
    yn, xn = (ys + 0.5) / h, (xs + 0.5) / w
    mask = (xn > 0.08) & (xn < 0.92) & (yn > 0.1) & (yn < 0.9) & (np.abs(yn - subs_y) > 0.08)
    for x0, y0, x1, y1 in face_boxes:
        mx, my = (x1 - x0) * 0.35, (y1 - y0) * 0.45
        mask &= ~((xn > x0 - mx) & (xn < x1 + mx) & (yn > y0 - my) & (yn < y1 + my * 2))
    if not mask.any():
        return None
    s = np.where(mask, sal, 0)
    i = int(np.argmax(s))
    peak, mean = float(s.flat[i]), float(sal[mask].mean()) + 1e-6
    # visa ryški sritis aplink piką (ne tik jos kraštas): centras ir dydis
    py, px = divmod(i, w)
    win = np.zeros_like(mask)
    win[max(0, py - h // 6):py + h // 6 + 1, max(0, px - w // 4):px + w // 4 + 1] = True
    blob = win & (s >= peak * 0.55)
    if blob.sum() >= 2:
        cx, cy = float(xn[blob].mean()), float(yn[blob].mean())
        ext = float(max(xn[blob].max() - xn[blob].min(), (yn[blob].max() - yn[blob].min()) * h / w))
    else:
        cx, cy, ext = float(xn.flat[i]), float(yn.flat[i]), 0.2
    saliency_target.extent = ext
    return cx, cy, peak / mean


def motion_dir(a, b):
    """Judėjimo kryptis tarp dviejų kadrų ("left" | "right" | None) – perėjimai juda ta pačia kryptimi."""
    try:
        import cv2
        ga = np.float32(np.asarray(a.convert("L").resize((160, 284))))
        gb = np.float32(np.asarray(b.convert("L").resize((160, 284))))
        (dx, dy), resp = cv2.phaseCorrelate(ga, gb)
        if resp > 0.1 and abs(dx) > 1.0:
            return "right" if dx > 0 else "left"
    except Exception:
        pass
    return None


def _overlaps(box, faces_, pad=0.02):
    x0, y0, x1, y1 = box
    return any(not (x1 < f[0] - pad or x0 > f[2] + pad or y1 < f[1] - pad or y0 > f[3] + pad) for f in faces_)


def suggest(prep, settings, project_id="", grab=None):
    """3D akcentų pasiūlymai pagal klipo turinį (kalbą, kadrus, kadrų pasikeitimus). Laikai – peržiūros (galutinio
    video) sekundės. grab(t_montažo) -> PIL kadras."""
    import hashlib

    import reels_studio
    speed = float(settings.get("speed") or 1.0)
    subs_y = reels_studio.SUBTITLE_POSITIONS.get(settings.get("subs_pos"), 0.72)
    color = "#" + reels_studio.accent_colors(settings.get("accent") or "Auksas")[0]
    words = [tuple(w) for w in prep["analysis"].get("words") or []]
    seed = int(hashlib.sha1(str(project_id).encode()).hexdigest()[:6], 16)
    keep = prep["analysis"].get("keep") or [(0.0, prep["analysis"]["info"]["duration"])]
    end = max(sum(b - a for a, b in keep), words[-1][2] if words else 0.0)  # sumontuoto video trukmė
    out = []
    cache = {}

    def frame(t):
        k = round(t, 1)
        if k not in cache:
            cache[k] = grab(t)
        return cache[k]

    def free(start, dur):  # montažo laikas; neturi persidengti su jau pasiūlytais (±0,2 s)
        return all(start + dur + 0.2 <= x["t"] * speed or start >= (x["t"] + x["dur"]) * speed + 0.2 for x in out)

    def add(sug, at, why):
        sug.update(t=round(max(0.0, at) / speed, 2), why=why, id=f"s{len(out)}")
        sug.setdefault("size", 1.0)
        sug.setdefault("color", color)
        sug["variants"] = VARIANTS[CATEGORY[sug["kind"]]]
        sug["cat"] = CATEGORY[sug["kind"]]
        out.append(sug)

    # 🔠 pabrėžti žodžiai ir skaičiai – iškyla iš titrų tuo metu, kai ištariami
    marked = video_editor.mark_key_words(words)
    cands = []
    for w, a, b in marked:
        core = re.sub(r"[^\w%€$+\-]", "", w.replace(video_editor.KEY_MARK, ""))
        if not core:
            continue
        num = bool(re.search(r"\d", core))
        if num or video_editor.is_key(w):
            cands.append((0 if num else 1, a, core))
    used = []
    for _, a, core in sorted(cands)[:6]:
        if len(used) >= 3 or any(abs(a - u) < 4.0 for u in used):
            continue
        fb = faces(frame(a)) if grab else []
        y = subs_y - 0.12
        for cand_y in (subs_y - 0.12, min(0.9, subs_y + 0.13), 0.24):
            if not _overlaps((0.12, cand_y - 0.06, 0.88, cand_y + 0.06), fb):
                y = cand_y
                break
        used.append(a)
        add({"kind": "word3d", "x": 0.5, "y": round(y, 3), "text": core, "dur": LEN["word3d"]}, a - 0.08,
            f"pabrėžtas {'skaičius' if re.search(r'[0-9]', core) else 'žodis'} „{core}“ – iškyla, kai ištariamas")
    # 💥 rezultatas – atskleidžiamas kadro pasikeitimo metu
    clips_spans = prep.get("spans") or []
    cuts = [sp[1] for sp in clips_spans[:-1] if sp]
    scored = []
    for c in cuts:
        near = [w for w, a, _ in words if c - 3.0 <= a <= c + 1.0 and RESULT_RE.match(re.sub(r"[^\w]", "", w.lower()))]
        scored.append((0 if near else 1, c, near))
    order = VARIANTS["reveal"][seed % 3:] + VARIANTS["reveal"][:seed % 3]
    rv = 0
    for pri, c, near in sorted(scored):
        if rv >= 2 or (pri and rv >= 1) or c > end - 0.5:
            continue
        kind = next((k_ for k_ in order[rv % 3:] + order[:rv % 3] if free(c - CUT_AT[k_] * LEN[k_], LEN[k_])), None)
        if kind is None:
            continue
        dur = LEN[kind]
        sug = {"kind": kind, "dur": dur, "x": 0.5, "y": 0.42}
        if grab:
            a_img, b_img = frame(max(0.0, c - 0.15)), frame(c + 0.25)
            d_ = motion_dir(b_img, frame(c + 0.55)) or ("right" if (seed + rv) % 2 else "left")
            sug["dir"] = d_
            tgt = saliency_target(a_img, faces(a_img), subs_y)
            if tgt and kind == "glass3d":
                sug["x"], sug["y"] = round(tgt[0], 3), round(tgt[1], 3)
        add(sug, c - CUT_AT[kind] * dur, ("rezultatas („" + near[0].strip(",.!?") + "“)" if near else "kadro pasikeitimas")
            + " – atskleidžiamas tiksliai kadrui keičiantis")
        rv += 1
    # ➡️ rodoma detalė – rodyklė / žiedas / kortelė pasiekia ją, kai ji parodoma
    moments = [(a, w) for w, a, b in words if DETAIL_RE.match(re.sub(r"[^\w]", "", w.lower()))]
    moments += [(sp[0] + 0.5, None) for sp in clips_spans[1:] if sp]
    det = 0
    order = VARIANTS["detail"][seed % 3:] + VARIANTS["detail"][:seed % 3]
    for m, w in sorted(moments):
        if det >= 2 or not grab or m > end - 1.0:
            continue
        img = frame(m)
        fb = faces(img)
        tgt = saliency_target(img, fb, subs_y)
        if not tgt or tgt[2] < 1.8:
            continue
        # po „štai…“ detalė rodoma per artimiausią sekundę – momentas gali pasislinkti iki 1 s
        pick = next(((k_, m + off) for off in (0.0, 0.4, 0.8, 1.0) for k_ in order[det % 3:] + order[:det % 3]
                     if m + off <= end - 1.0 and free(m + off - HIT_AT[k_] * LEN[k_], LEN[k_])), None)
        if pick is None:
            continue
        kind, m = pick
        x, y = tgt[0], tgt[1]
        size = round(min(1.8, max(0.7, getattr(saliency_target, "extent", 0.2) / 0.2)), 2)
        side = "right" if x < 0.5 else "left"
        if fb and _overlaps((0.0, y - 0.1, 0.5, y + 0.1) if side == "left" else (0.5, y - 0.1, 1.0, y + 0.1), fb):
            side = "left" if side == "right" else "right"
        nxt = [re.sub(r"[^\w]", "", ww) for ww, aa, _ in words if m - 0.1 <= aa <= m + 2.0]
        text = max(nxt, key=len) if nxt else ""
        dur = LEN[kind]
        add({"kind": kind, "x": round(x, 3), "y": round(y, 3), "size": size, "dir": side if kind == "arrow3d" else
             ("left" if side == "right" else "right"), "text": text, "dur": dur}, m - HIT_AT[kind] * dur,
            "rodoma detalė" + (f" („{w.strip(',.!?')}“)" if w else " naujame kadre") + " – elementas ją pasiekia, kai ji parodoma")
        det += 1
    out.sort(key=lambda s: s["t"])
    keep_, last = [], -1e9  # akcentai nepersidengia
    for s in out:
        if s["t"] >= last:
            keep_.append(s)
            last = s["t"] + s["dur"] + 0.2
    return keep_
