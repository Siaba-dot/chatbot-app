#!/usr/bin/env python3
"""30 s 9:16 promo background for 'WEB sprendimai su AI' + synthesized music.
Usage: python3 promo.py FONTDIR OUT_DIR
"""
import math, random, subprocess, sys, wave
from contextlib import contextmanager
from functools import lru_cache
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, DUR = 1080, 1920, 30, 30.0
FD, OUT = sys.argv[1], sys.argv[2]
CYAN, VIOLET, YELLOW, GREEN, PINK = (34, 211, 238), (168, 85, 247), (255, 214, 10), (34, 197, 94), (244, 114, 182)
WHITE = (255, 255, 255)
SCENES = [0.0, 5.0, 7.6, 10.4, 13.2, 16.0, 18.8, 21.6, 27.2, 30.0]


@lru_cache(None)
def F(weight, size):
    name = {"black": "900Black", "bold": "700Bold"}[weight]
    return ImageFont.truetype(f"{FD}/{name}/Montserrat_{name}.ttf", size)


def ease(x):
    x = min(max(x, 0.0), 1.0); return 1 - (1 - x) ** 3


def back(x):  # ease-out with overshoot
    x = min(max(x, 0.0), 1.0); c = 1.7; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def fade(lt, a, d=0.3):
    return ease((lt - a) / d)


# ---------- static resources ----------
yy = np.linspace(0, 1, H)[:, None, None]
BASE = ((np.array([8, 10, 32]) * (1 - yy) + np.array([30, 8, 60]) * yy) * np.ones((1, W, 1))).astype(np.uint8)
gx = np.linspace(0, 1, W)[None, :, None]
GRAD = Image.fromarray(np.concatenate([(np.array(CYAN) * (1 - gx) + np.array(VIOLET) * gx) * np.ones((H, 1, 1)),
                                       np.full((H, W, 1), 255)], 2).astype(np.uint8), "RGBA")
CLEAR = Image.new("RGBA", (W, H), (0, 0, 0, 0))

rng = random.Random(7)
NODES = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(-25, 25), rng.uniform(-25, 25)) for _ in range(38)]
STARS = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0, 6.28), rng.uniform(1.5, 3.5)) for _ in range(70)]


def bounce(p, v, t, lo, hi):
    span = hi - lo; x = (p - lo + v * t) % (2 * span)
    return lo + (x if x < span else 2 * span - x)


@contextmanager
def sub(L, a):
    S = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    yield S, ImageDraw.Draw(S)
    if a < 1: S.putalpha(S.getchannel("A").point(lambda v: int(v * max(a, 0))))
    L.alpha_composite(S)


def grad_mask(L, mask):
    L.alpha_composite(Image.composite(GRAD, CLEAR, mask))


def grad_text(L, xy, txt, font, a=1.0, anchor="mm"):
    m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).text(xy, txt, font=font, fill=int(255 * a), anchor=anchor)
    grad_mask(L, m)


def grad_shape(L, fn, a=1.0):
    m = Image.new("L", (W, H), 0); fn(ImageDraw.Draw(m), int(255 * a)); grad_mask(L, m)


# ---------- background ----------
def background(t):
    lw, lh = W // 4, H // 4
    X, Y = np.meshgrid(np.arange(lw), np.arange(lh))
    glow = np.zeros((lh, lw, 3))
    for i, (col, r) in enumerate([(CYAN, 120), (VIOLET, 150), (PINK, 90)]):
        cx = lw * (0.5 + 0.38 * math.sin(t * 0.35 + i * 2.1)); cy = lh * (0.45 + 0.35 * math.cos(t * 0.27 + i * 1.3))
        glow += np.array(col)[None, None] * (np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / r ** 2) * 0.22)[..., None]
    g = np.asarray(Image.fromarray(np.clip(glow, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR))
    img = Image.fromarray(np.clip(BASE.astype(np.int16) + g, 0, 255).astype(np.uint8)).convert("RGBA")

    net = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(net)
    pts = [(bounce(x, vx, t, 0, W), bounce(y, vy, t, 0, H)) for x, y, vx, vy in NODES]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dist = math.dist(pts[i], pts[j])
            if dist < 300: d.line([pts[i], pts[j]], fill=CYAN + (int(70 * (1 - dist / 300)),), width=2)
    for x, y, ph, s in STARS:
        a = int(60 + 60 * math.sin(t * 2 + ph)); d.ellipse([x - s / 2, y - s / 2, x + s / 2, y + s / 2], fill=(200, 220, 255, a))
    for k, (x, y) in enumerate(pts):
        r = 5 + 2 * math.sin(t * 3 + k); d.ellipse([x - r, y - r, x + r, y + r], fill=CYAN + (150,))
    img.alpha_composite(net)
    return img


# ---------- scene helpers ----------
def chip(L, cx, cy, size, t, a=1.0):
    with sub(L, a) as (S, D):
        for k in range(3):  # pulsing rings
            ph = (t * 0.8 + k / 3) % 1
            r = size * 0.75 + ph * size * 0.7
            D.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CYAN + (int(160 * (1 - ph)),), width=4)
        hs = size / 2; pin = size * 0.17
        for i in range(4):
            off = -hs * 0.6 + i * hs * 0.4
            for (x1, y1, x2, y2) in [(cx + off, cy - hs, cx + off, cy - hs - pin), (cx + off, cy + hs, cx + off, cy + hs + pin),
                                     (cx - hs, cy + off, cx - hs - pin, cy + off), (cx + hs, cy + off, cx + hs + pin, cy + off)]:
                D.line([x1, y1, x2, y2], fill=CYAN + (255,), width=max(3, int(size / 40)))
                D.ellipse([x2 - 6, y2 - 6, x2 + 6, y2 + 6], fill=CYAN + (255,))
    grad_shape(L, lambda d, f: d.rounded_rectangle([cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2],
                                                   radius=size * 0.2, fill=f), a)
    with sub(L, a) as (S, D):
        D.text((cx, cy + size * 0.03), "AI", font=F("black", max(int(size * 0.48), 1)), fill=WHITE + (255,), anchor="mm")


def arrow(D, cx, base, length, up, col, w=120):
    s = -1 if up else 1; tip = base + s * length; head = min(length * 0.45, w * 1.1)
    D.polygon([(cx - w * 0.3, base), (cx + w * 0.3, base), (cx + w * 0.3, tip - s * head), (cx + w * 0.75, tip - s * head),
               (cx, tip), (cx - w * 0.75, tip - s * head), (cx - w * 0.3, tip - s * head)], fill=col)


def star_poly(cx, cy, ro, ri, n, rot):
    return [(cx + (ro if k % 2 == 0 else ri) * math.cos(rot + k * math.pi / n),
             cy + (ro if k % 2 == 0 else ri) * math.sin(rot + k * math.pi / n)) for k in range(2 * n)]


def sparkle(D, x, y, r, col):
    D.polygon([(x, y - r), (x + r * 0.25, y - r * 0.25), (x + r, y), (x + r * 0.25, y + r * 0.25),
               (x, y + r), (x - r * 0.25, y + r * 0.25), (x - r, y), (x - r * 0.25, y - r * 0.25)], fill=col)


def label(L, y, txt, a):
    with sub(L, a) as (S, D):
        D.text((W / 2, y), txt, font=F("bold", 44), fill=CYAN + (255,), anchor="mm")


# ---------- scenes (lt = local time) ----------
def s_title(L, lt, t):
    chip(L, 540, 520, int(300 * back(lt / 0.55)) or 1, t, fade(lt, 0))
    with sub(L, fade(lt, 0.6)) as (S, D):
        D.text((540, 870 + 40 * (1 - ease((lt - 0.6) / 0.4))), "WEB", font=F("black", 160), fill=WHITE + (255,), anchor="mm")
    grad_text(L, (540, 1010), "SPRENDIMAI", F("black", 118), fade(lt, 0.9))
    with sub(L, fade(lt, 1.4)) as (S, D):
        D.text((540, 1110), "su dirbtiniu intelektu", font=F("bold", 48), fill=(220, 225, 255, 255), anchor="mm")


def s_browser(L, lt, t):
    label(L, 270, "SVETAINĖS KŪRIMAS", fade(lt, 0))
    x0, y0, x1, y1 = 170, 340, 910, 1080
    with sub(L, fade(lt, 0)) as (S, D):
        D.rounded_rectangle([x0, y0, x1, y1], radius=36, fill=(18, 22, 58, 240), outline=CYAN + (180,), width=3)
        D.rounded_rectangle([x0, y0, x1, y0 + 70], radius=36, fill=(32, 38, 84, 255))
        D.rectangle([x0, y0 + 40, x1, y0 + 70], fill=(32, 38, 84, 255))
        for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
            D.ellipse([x0 + 30 + i * 40, y0 + 22, x0 + 56 + i * 40, y0 + 48], fill=c + (255,))
        D.rounded_rectangle([x0 + 170, y0 + 18, x1 - 40, y0 + 52], radius=17, fill=(14, 18, 46, 255))
    steps = [0.25, 0.55, 0.85, 1.05, 1.35, 1.65]
    with sub(L, fade(lt, steps[0])) as (S, D):  # nav
        D.rounded_rectangle([x0 + 40, y0 + 100, x0 + 200, y0 + 140], radius=10, fill=CYAN + (255,))
        for i in range(3): D.rounded_rectangle([x1 - 330 + i * 100, y0 + 112, x1 - 260 + i * 100, y0 + 128], radius=8, fill=(120, 130, 190, 255))
    grad_shape(L, lambda d, f: d.rounded_rectangle([x0 + 40, y0 + 170, x1 - 40, y0 + 400], radius=24, fill=f), fade(lt, steps[1]))
    with sub(L, fade(lt, steps[1] + 0.15)) as (S, D):
        D.text((540, y0 + 285), "JŪSŲ VERSLAS", font=F("black", 62), fill=WHITE + (255,), anchor="mm")
    with sub(L, fade(lt, steps[2])) as (S, D):
        D.rounded_rectangle([x0 + 40, y0 + 430, x1 - 140, y0 + 455], radius=12, fill=(200, 205, 240, 255))
    with sub(L, fade(lt, steps[3])) as (S, D):
        D.rounded_rectangle([x0 + 40, y0 + 475, x1 - 260, y0 + 500], radius=12, fill=(140, 150, 200, 255))
    with sub(L, fade(lt, steps[4])) as (S, D):
        D.rounded_rectangle([x0 + 40, y0 + 530, x0 + 300, y0 + 590], radius=30, fill=YELLOW + (255,))
        D.text((x0 + 170, y0 + 561), "PIRKTI", font=F("black", 30), fill=(20, 20, 40, 255), anchor="mm")
    with sub(L, fade(lt, steps[5])) as (S, D):
        for i in range(3):
            cx = x0 + 40 + i * 225
            D.rounded_rectangle([cx, y0 + 620, cx + 200, y0 + 710], radius=18, fill=(40, 48, 100, 255), outline=VIOLET + (255,), width=2)
    # AI "building" sparkle hopping between elements
    targets = [(x0 + 200, y0 + 120), (x1 - 60, y0 + 190), (x1 - 140, y0 + 440), (x1 - 260, y0 + 488), (x0 + 300, y0 + 560), (x1 - 60, y0 + 640)]
    k = max([i for i, s in enumerate(steps) if lt >= s] or [0])
    a = targets[max(k - 1, 0)]; b = targets[k]; p = ease((lt - steps[k]) / 0.25)
    with sub(L, fade(lt, 0.2)) as (S, D):
        sparkle(D, a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p, 34 + 6 * math.sin(t * 12), YELLOW + (255,))


def bubble(L, lt, at, y, lines, right, a=1.0):
    k = fade(lt, at, 0.25) * a
    if k <= 0: return
    f = F("bold", 38); w = max(ImageDraw.Draw(CLEAR).textlength(s, font=f) for s in lines) + 64
    h = 48 * len(lines) + 40; x = 850 - w if right else 230
    dy = 30 * (1 - ease((lt - at) / 0.3))
    if right:
        grad_shape(L, lambda d, fi: d.rounded_rectangle([x, y + dy, x + w, y + h + dy], radius=34, fill=fi), k)
    with sub(L, k) as (S, D):
        if not right: D.rounded_rectangle([x, y + dy, x + w, y + h + dy], radius=34, fill=(52, 58, 100, 255))
        for i, s in enumerate(lines):
            D.text((x + 32, y + dy + 20 + i * 48), s, font=f, fill=WHITE + (255,), anchor="la")


def s_chat(L, lt, t):
    label(L, 270, "AI CHATBOTAS", fade(lt, 0))
    with sub(L, fade(lt, 0)) as (S, D):
        D.rounded_rectangle([190, 330, 890, 1090], radius=48, fill=(16, 20, 52, 235), outline=CYAN + (170,), width=3)
        D.line([190, 450, 890, 450], fill=(60, 70, 130, 255), width=2)
        D.text((350, 372), "AI asistentas", font=F("bold", 40), fill=WHITE + (255,), anchor="la")
        D.ellipse([350, 422, 366, 438], fill=GREEN + (255,))
        D.text((376, 430), "online", font=F("bold", 28), fill=GREEN + (255,), anchor="lm")
    grad_shape(L, lambda d, f: d.ellipse([230, 352, 320, 442], fill=f), fade(lt, 0))
    with sub(L, fade(lt, 0)) as (S, D):
        D.text((275, 398), "AI", font=F("black", 36), fill=WHITE + (255,), anchor="mm")
    bubble(L, lt, 0.3, 500, ["Ar dirbate šeštadienį?"], False)
    if 0.8 <= lt < 1.4:
        with sub(L, fade(lt, 0.8, 0.15)) as (S, D):
            D.rounded_rectangle([690, 640, 850, 710], radius=34, fill=(52, 58, 100, 255))
            for i in range(3):
                yy_ = 675 - 10 * max(0, math.sin(t * 10 - i * 0.8))
                D.ellipse([722 + i * 38 - 10, yy_ - 10, 722 + i * 38 + 10, yy_ + 10], fill=(200, 210, 255, 255))
    bubble(L, lt, 1.4, 640, ["Taip! Dirbame 10–16 val.", "Užregistruoti jus?"], True)
    bubble(L, lt, 2.1, 840, ["Taip, ačiū!"], False)


def s_auto(L, lt, t):
    grad_text(L, (540, 360), "AUTOMATIZACIJA", F("black", 80), fade(lt, 0))
    for i, txt in enumerate(["Užklausos", "Rezervacijos", "Atsakymai klientams"]):
        at = 0.2 + 0.35 * i; k = fade(lt, at); dx = -120 * (1 - ease((lt - at) / 0.35))
        y = 480 + i * 175
        with sub(L, k) as (S, D):
            D.rounded_rectangle([150 + dx, y, 930 + dx, y + 140], radius=30, fill=(24, 30, 72, 240), outline=(80, 90, 160, 255), width=2)
            D.text((300 + dx, y + 70), txt, font=F("bold", 46), fill=WHITE + (255,), anchor="lm")
            c = back((lt - at - 0.45) / 0.3)
            if c > 0:
                r = 42 * c
                D.ellipse([220 + dx - r, y + 70 - r, 220 + dx + r, y + 70 + r], fill=GREEN + (255,))
                D.line([(200 + dx, y + 72), (215 + dx, y + 88), (243 + dx, y + 54)], fill=WHITE + (255,), width=int(9 * c) or 1, joint="curve")
            else:
                D.ellipse([180 + dx, y + 30, 260 + dx, y + 110], outline=(120, 130, 190, 255), width=4)


def s_seo(L, lt, t):
    grad_text(L, (540, 360), "TURINYS + SEO", F("black", 84), fade(lt, 0))
    heights = [140, 230, 330, 450, 590]; base = 1060
    tops = []
    for i, hgt in enumerate(heights):
        g = ease((lt - 0.2 - i * 0.15) / 0.6); x = 200 + i * 145
        grad_shape(L, lambda d, f, x=x, g=g, hgt=hgt: d.rounded_rectangle([x, base - max(hgt * g, 8), x + 100, base], radius=18, fill=f),
                   fade(lt, 0.1 + i * 0.15, 0.2))
        tops.append((x + 50, base - hgt * g - 40))
    with sub(L, fade(lt, 1.3)) as (S, D):
        D.line([(170, base + 6), (910, base + 6)], fill=(150, 160, 210, 255), width=4)
        g = ease((lt - 1.3) / 0.7); n = 1 + g * (len(tops) - 1); i = int(n); pts = tops[:i] + ([] if i >= len(tops) else
              [(tops[i - 1][0] + (tops[i][0] - tops[i - 1][0]) * (n - i), tops[i - 1][1] + (tops[i][1] - tops[i - 1][1]) * (n - i))])
        if len(pts) > 1: D.line(pts, fill=YELLOW + (255,), width=10, joint="curve")
        for p in pts: D.ellipse([p[0] - 12, p[1] - 12, p[0] + 12, p[1] + 12], fill=YELLOW + (255,))
        if g >= 1: sparkle(D, tops[-1][0] + 50, tops[-1][1] - 40, 40 + 8 * math.sin(t * 10), YELLOW + (255,))


def s_growth(L, lt, t):
    for i, (txt, up, col) in enumerate([("KLIENTAI", True, GREEN), ("RUTINA", False, PINK)]):
        at = 0.1 + 0.4 * i; cx = 300 + i * 480
        with sub(L, fade(lt, at)) as (S, D):
            D.rounded_rectangle([cx - 210, 380, cx + 210, 1060], radius=40, fill=(22, 28, 70, 240), outline=col + (200,), width=4)
            D.text((cx, 460), txt, font=F("black", 56), fill=WHITE + (255,), anchor="mm")
            D.text((cx, 990), "DAUGIAU" if up else "MAŽIAU", font=F("bold", 40), fill=col + (255,), anchor="mm")
            g = back((lt - at - 0.2) / 0.6)
            if g > 0:
                if up: arrow(D, cx, 900, 360 * g, True, col + (255,), 150)
                else: arrow(D, cx, 560, 360 * g, False, col + (255,), 150)


def s_night(L, lt, t):
    with sub(L, fade(lt, 0)) as (S, D):
        for k, (x, y) in enumerate([(220, 380), (850, 330), (300, 760), (800, 820), (160, 600), (930, 600), (640, 300)]):
            r = 16 + 8 * math.sin(t * 4 + k * 1.7); sparkle(D, x, y, r, (255, 240, 180, 255))
    m = Image.new("L", (W, H), 0); dm = ImageDraw.Draw(m); r = 170 * back(lt / 0.5); cx, cy = 540, 560
    dm.ellipse([cx - r, cy - r, cx + r, cy + r], fill=int(255 * fade(lt, 0)))
    dm.ellipse([cx - r + r * 0.55, cy - r - r * 0.25, cx + r + r * 0.55, cy + r - r * 0.25], fill=0)
    moon = Image.new("RGBA", (W, H), YELLOW + (0,)); moon.putalpha(m)
    L.alpha_composite(moon.filter(ImageFilter.GaussianBlur(18))); L.alpha_composite(moon)
    grad_text(L, (540, 930), "24/7", F("black", 200), fade(lt, 0.5))
    with sub(L, fade(lt, 0.9)) as (S, D):
        D.text((540, 1070), "jūsų svetainė dirba", font=F("bold", 46), fill=WHITE + (255,), anchor="mm")


def s_offer(L, lt, t):
    m = ease((lt - 2.8) / 0.4); sc = (1 - 0.22 * m) * back(lt / 0.5); cy = 590 - 110 * m
    with sub(L, fade(lt, 0)) as (S, D):
        D.polygon(star_poly(540, cy, 280 * sc, 240 * sc, 18, t * 0.4), fill=YELLOW + (255,))
        D.text((540, cy - 30 * sc), "NEMOKAMA", font=F("black", max(int(70 * sc), 1)), fill=(20, 16, 50, 255), anchor="mm")
        D.text((540, cy + 45 * sc), "KONSULTACIJA", font=F("black", max(int(48 * sc), 1)), fill=(20, 16, 50, 255), anchor="mm")
    if lt >= 2.8:
        k = fade(lt, 3.0); bs = max(back((lt - 3.0) / 0.4), 0.05)
        bw, bh, by = 640 * bs, 130 * bs, 940
        click = 4.0; press = 0.94 if click <= lt < click + 0.15 else 1.0
        bw, bh = bw * press, bh * press
        grad_shape(L, lambda d, f: d.rounded_rectangle([540 - bw / 2, by - bh / 2, 540 + bw / 2, by + bh / 2], radius=int(bh / 2) - 1, fill=f), k)
        with sub(L, k) as (S, D):
            D.text((540, by), "RAŠYKITE MUMS", font=F("black", max(int(56 * bs * press), 1)), fill=WHITE + (255,), anchor="mm")
            if lt >= click:  # ripple
                ph = min((lt - click) / 0.8, 1); rr = 80 + ph * 300
                D.ellipse([700 - rr, by + 20 - rr, 700 + rr, by + 20 + rr], outline=WHITE + (int(200 * (1 - ph)),), width=6)
            p = ease((lt - 3.3) / 0.7); cx = 900 - 200 * p; cy2 = 1180 - 160 * p  # cursor
            if lt >= 3.3:
                D.polygon([(cx, cy2), (cx, cy2 + 70), (cx + 18, cy2 + 54), (cx + 32, cy2 + 84), (cx + 44, cy2 + 78),
                           (cx + 30, cy2 + 50), (cx + 54, cy2 + 50)], fill=WHITE + (255,), outline=(20, 20, 40, 255))


def s_end(L, lt, t):
    chip(L, 540, 520, int(230 * back(lt / 0.5)) or 1, t, fade(lt, 0))
    with sub(L, fade(lt, 0.3)) as (S, D):
        D.text((540, 790), "WEB", font=F("black", 140), fill=WHITE + (255,), anchor="mm")
    grad_text(L, (540, 915), "SPRENDIMAI", F("black", 112), fade(lt, 0.5))
    with sub(L, fade(lt, 0.8)) as (S, D):
        D.text((540, 1020), "Išmanios svetainės su AI", font=F("bold", 46), fill=(220, 225, 255, 255), anchor="mm")


FUNCS = [s_title, s_browser, s_chat, s_auto, s_seo, s_growth, s_night, s_offer, s_end]


def frame(fi):
    t = fi / FPS; img = background(t)
    for i, fn in enumerate(FUNCS):
        a, b = SCENES[i], SCENES[i + 1]
        if not (a <= t < b): continue
        L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); fn(L, t - a, t)
        out = 1.0 if i == len(FUNCS) - 1 else min(1, (b - t) / 0.25)
        if out < 1: L.putalpha(L.getchannel("A").point(lambda v: int(v * out)))
        glow = L.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(8)).resize((W, H), Image.BILINEAR)
        glow.putalpha(glow.getchannel("A").point(lambda v: int(v * 0.7)))
        img.alpha_composite(glow); img.alpha_composite(L)
    if t > DUR - 0.6:  # fade to black
        k = (DUR - t) / 0.6; img = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), img, max(k, 0))
    return img.convert("RGB").tobytes()


# ---------- music ----------
def music(path):
    sr = 48000; n = int(sr * DUR); out = np.zeros(n)
    bpm = 112; beat = 60 / bpm; bar = 4 * beat
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G

    def add(sig, start):
        i = int(start * sr); j = min(n, i + len(sig))
        if i < n: out[i:j] += sig[: j - i]

    nb = int(DUR / bar) + 1
    for b in range(nb):
        ch = chords[b % 4]; tt = np.arange(int(bar * sr)) / sr
        env = np.minimum(1, tt / 0.4) * np.minimum(1, (bar - tt) / 0.3)
        pad = sum(np.sin(2 * np.pi * hz(m) * d * tt) * 0.5 + 0.15 * np.sin(4 * np.pi * hz(m) * d * tt)
                  for m in ch for d in (0.997, 1.003))
        add(pad * env * 0.05, b * bar)
        for k in range(8):  # arpeggio 8ths
            st = b * bar + k * beat / 2; m = ch[[0, 1, 2, 1][k % 4]] + 12 + (12 if k in (3, 7) else 0)
            ta = np.arange(int(0.4 * sr)) / sr
            add((np.sin(2 * np.pi * hz(m) * ta) + 0.3 * np.sin(4 * np.pi * hz(m) * ta)) * np.exp(-ta * 9) * 0.07, st)
        for k in range(4):  # bass
            st = b * bar + k * beat; tb = np.arange(int(beat * sr)) / sr
            if st >= 1.2: add(np.tanh(2 * np.sin(2 * np.pi * hz(ch[0] - 24) * tb)) * np.exp(-tb * 3) * 0.12, st)
    total = int(DUR / beat)
    for k in range(total):
        st = k * beat
        if st >= 2.4 and st < DUR - 1.0:  # kick
            tk = np.arange(int(0.35 * sr)) / sr; f = 45 + 90 * np.exp(-tk * 30)
            add(np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tk * 9) * 0.45, st)
        if st >= 5.0 and st < DUR - 1.0:  # hats
            th = np.arange(int(0.08 * sr)) / sr; nz = np.diff(np.random.default_rng(k).standard_normal(len(th) + 1))
            add(nz * np.exp(-th * 60) * 0.05, st + beat / 2)
    for s in SCENES[1:-1]:  # whoosh into each scene
        tw = np.arange(int(0.5 * sr)) / sr; nz = np.random.default_rng(int(s * 10)).standard_normal(len(tw))
        nz = np.convolve(nz, np.ones(12) / 12, "same")
        add(nz * np.sin(np.pi * tw / 0.5) ** 2 * 0.18, s - 0.35)
    tt = np.arange(n) / sr
    out *= np.minimum(1, tt / 0.6) * np.minimum(1, (DUR - tt) / 1.6)
    out = out / np.abs(out).max() * 0.85
    st = np.stack([out, np.roll(out, 240)], 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((st * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    only = [float(x) for x in sys.argv[3:]]
    if only:  # preview stills
        for s in only:
            Image.frombytes("RGB", (W, H), frame(int(s * FPS))).save(f"{OUT}/prev_{s:05.2f}.jpg", quality=85)
        sys.exit()
    music(f"{OUT}/music.wav")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", f"{OUT}/music.wav", "-c:v", "libx264", "-crf", "17",
                           "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
                           f"{OUT}/bg.mp4"], stdin=subprocess.PIPE)
    with Pool(4) as p:
        for i, b in enumerate(p.imap(frame, range(int(DUR * FPS)), chunksize=4)):
            ff.stdin.write(b)
            if i % 150 == 0: print("frame", i, flush=True)
    ff.stdin.close(); ff.wait()
