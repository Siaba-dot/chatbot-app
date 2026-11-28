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
import threading
import time

import animations
import fxpack
import video_editor
from PIL import Image as PILImage
from video_editor import FONT_DIR, FONT_NAME, TRAINING_FONT, _ass_escape, _ass_time, _filter_path

# Akcento spalvos: pavadinimas -> (RGB hex, teksto spalva ant jos)
ACCENTS = {
    "Gintaro gradientas": ("E9A23B", "071326"),
    "Aukso gradientas": ("D9B24C", "0B0B0C"),
    "Sidabro gradientas": ("C9CBD1", "0B0B0C"),
    "Auksas": ("E3C16F", "0B0B0C"),
    "Šampanas": ("F1E3C6", "0B0B0C"),
    "Balta": ("FFFFFF", "000000"),
    "Geltona": ("FFD60A", "000000"),
    "Raudona": ("FF3B30", "FFFFFF"),
    "Mėlyna": ("0A84FF", "FFFFFF"),
    "Rožinė": ("FF2D92", "FFFFFF"),
    "Oranžinė": ("FF8A1F", "0B0B0C"),
}



def accent_colors(accent):
    """Akcento (RGB hex, teksto spalva ant jos). Prekės ženklo spalva perduodama kaip „#RRGGBB“."""
    if isinstance(accent, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", accent):
        rgb = accent[1:].upper()
        r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4))
        return rgb, "0B0B0C" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "FFFFFF"
    return ACCENTS.get(accent, ACCENTS["Auksas"])


# Prekės ženklo logotipo vieta kadre
LOGO_POSITIONS = ("Viršuje dešinėje", "Viršuje kairėje", "Apačioje dešinėje", "Apačioje kairėje")


def logo_layer(logo, W, H, out_path):
    """Paruošia logotipą kadrui: dydis (logo["size"] – kadro pločio dalis), permatomumas (logo["opacity"]).
    Grąžina (png kelias, x, y)."""
    from PIL import Image
    im = Image.open(logo["path"]).convert("RGBA")
    lw = max(16, round(W * float(logo.get("size", 0.16))))
    lh = max(8, round(im.height * lw / im.width))
    if lh > H * 0.25:  # labai aukštas logotipas – ribojamas aukštis
        lh = round(H * 0.25)
        lw = max(8, round(im.width * lh / im.height))
    im = im.resize((lw, lh), Image.LANCZOS)
    op = max(0.1, min(1.0, float(logo.get("opacity", 0.85))))
    if op < 1:
        im.putalpha(im.getchannel("A").point(lambda v: round(v * op)))
    im.save(out_path)
    m = round(min(W, H) * 0.045)
    pos = logo.get("pos", LOGO_POSITIONS[0])
    x = W - lw - m if "dešinėje" in pos else m
    # viršuje – žemiau progreso juostos ir @vardo; apačioje – virš Reels mygtukų zonos
    y = round(H * 0.06) if "Viršuje" in pos else H - lh - round(H * (0.09 if H > W else 0.05))
    return out_path, x, y


def stamp_logo(image_path, logo):
    """Uždeda logotipą ant paveikslėlio (viršelio)."""
    from PIL import Image
    im = Image.open(image_path).convert("RGB")
    tmp = image_path + ".logo.png"
    lp, x, y = logo_layer(logo, im.width, im.height, tmp)
    with Image.open(lp) as lg:
        im.paste(lg, (x, y), lg)
    os.unlink(tmp)
    im.save(image_path, quality=92)
    return image_path


# ---------- Pabaigos kortelė: nuoroda, QR kodas, YouTube pabaigos ekrano vietos ----------
END_CARD_LEN = 3.5       # vertikaliai / kvadratu
YT_END_LEN = 10.0        # YouTube pabaigos ekranui (elementai rodomi paskutines 5–20 s)
AMBER_LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "gintaras_512.png")


def end_card_len(card, W, H):
    if not card:
        return 0.0
    return YT_END_LEN if card.get("youtube") and W > H else END_CARD_LEN


def short_link(link):
    """Nuoroda rodymui: be https:// ir galinio /."""
    return re.sub(r"^https?://", "", (link or "").strip()).rstrip("/")


def qr_matrix(link):
    """QR kodo moduliai (sąrašas eilučių iš 0/1) arba None, jei QR bibliotekos nėra."""
    try:
        import segno
    except ImportError:
        return None
    url = link.strip()
    if not re.match(r"^[a-z]+://", url, re.I):
        url = "https://" + url
    try:
        return [list(row) for row in segno.make(url, error="m", micro=False).matrix]
    except Exception:
        return None


def end_card_image(card, W, H, out_path, accent="Gintaro gradientas", _shift=None):
    """Gintarinė pabaigos kortelė (PNG, W×H): logotipas, antraštė, nuoroda ir QR kodas;
    YouTube režimu (horizontaliai) – auksiniai rėmeliai pabaigos ekrano elementams (video ir prenumeratai)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    def font(name, size):
        return ImageFont.truetype(os.path.join(FONT_DIR, name), max(8, round(size)))

    u = min(W, H) / 720 * (1.2 if H > W * 1.3 else 1.0)  # mastelis
    y, x = np.mgrid[0:H, 0:W]
    t = (y / H)[..., None]
    bg = np.array([6, 18, 38]) * (1 - t) + np.array([14, 34, 66]) * t
    glow = np.exp(-(((x - W * 0.5) / (W * 0.5)) ** 2 + ((y - H * 0.2) / (H * 0.38)) ** 2))[..., None]
    bg = bg + glow * np.array([120, 70, 10]) * 0.55
    img = Image.fromarray(np.clip(bg, 0, 255).astype("uint8")).convert("RGBA")
    d = ImageDraw.Draw(img)
    rgb = accent_colors(accent)[0]
    acc = tuple(int(rgb[i:i + 2], 16) for i in (0, 2, 4))
    honey, muted = (255, 213, 138), (180, 195, 216)
    title_col = honey if accent in GRADIENTS else acc
    m = round(18 * u)
    d.rounded_rectangle((m, m, W - m, H - m), round(18 * u), outline=acc + (210,), width=max(2, round(2 * u)))
    d.rounded_rectangle((m + round(10 * u), m + round(10 * u), W - m - round(10 * u), H - m - round(10 * u)),
                        round(14 * u), outline=honey + (90,), width=1)

    def centered(txt, f, yy, fill, max_w=None):
        size = f.size
        while max_w and d.textlength(txt, font=f) > max_w and size > 10:
            size -= 2
            f = font(os.path.basename(f.path), size)
        w = d.textlength(txt, font=f)
        d.text((W / 2 - w / 2, yy), txt, font=f, fill=fill)
        return yy + f.size * 1.25

    youtube = card.get("youtube") and W > H
    title = (card.get("title") or "").strip() or ("Ačiū, kad žiūrėjote" if youtube else "Ačiū, kad žiūrėjote!")
    link = short_link(card.get("link"))
    # logotipas: prekės ženklo arba gintaras
    lpath = card.get("logo") if card.get("logo") and os.path.exists(card.get("logo")) else AMBER_LOGO
    lg = Image.open(lpath).convert("RGBA")
    lh = round((95 if youtube else 120) * u)
    lw = round(lg.width * lh / lg.height)
    if lw > W * 0.5:
        lw = round(W * 0.5)
        lh = round(lg.height * lw / lg.width)
    lg = lg.resize((lw, lh), Image.LANCZOS)
    top = round((45 if youtube else 70) * u) + (_shift or 0)
    img.alpha_composite(lg, (W // 2 - lw // 2, top))
    yy = top + lh + round(18 * u)
    serif = "PlayfairDisplay_700Bold.ttf"
    sans = "Montserrat_600SemiBold.ttf"
    yy = centered(title, font(serif, 56 * u), yy, title_col, W * 0.86)
    if youtube:
        centered("Ž I Ū R Ė K I T E   T O L I A U", font(sans, 18 * u), yy + round(10 * u), muted)
        # vietos YouTube pabaigos ekrano elementams: video (16:9) kairėje, prenumerata (apskritimas) dešinėje
        vw = round(W * 0.405)
        vh = round(vw * 9 / 16)
        vy = round(H * 0.40)
        V = (round(W * 0.117), vy, round(W * 0.117) + vw, vy + vh)
        r = round(vh * 0.36)
        cx, cy = round(W * 0.73), vy + vh // 2
        C = (cx - r, cy - r, cx + r, cy + r)
        gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        gd.rounded_rectangle(V, round(16 * u), outline=acc + (255,), width=round(6 * u))
        gd.ellipse(C, outline=acc + (255,), width=round(6 * u))
        img.alpha_composite(gl.filter(ImageFilter.GaussianBlur(10 * u)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(V, round(14 * u), fill=(4, 12, 27, 215), outline=acc + (255,), width=max(2, round(3 * u)))
        d.ellipse(C, fill=(4, 12, 27, 215), outline=acc + (255,), width=max(2, round(3 * u)))
        for px, py in ((V[0], V[1]), (V[2], V[1]), (V[0], V[3]), (V[2], V[3])):
            d.regular_polygon((px, py, round(9 * u)), 4, fill=honey)
        if link:
            centered(link, font(sans, 26 * u), H - m - round(62 * u), honey, W * 0.8)
    else:
        qr = qr_matrix(card["link"]) if link and card.get("qr", True) else None
        if qr:
            n = len(qr)
            side = round(min(W * 0.46, H * 0.3))
            q = max(2, side // (n + 4))
            side = q * (n + 4)
            qx, qy = W // 2 - side // 2, round(yy + 34 * u)
            pad = round(10 * u)
            gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(gl).rounded_rectangle((qx - pad, qy - pad, qx + side + pad, qy + side + pad), round(22 * u),
                                                 outline=acc + (255,), width=round(8 * u))
            img.alpha_composite(gl.filter(ImageFilter.GaussianBlur(12 * u)))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((qx - pad, qy - pad, qx + side + pad, qy + side + pad), round(20 * u),
                                fill=(255, 248, 236), outline=acc, width=max(2, round(4 * u)))
            for r_, row in enumerate(qr):
                for c_, v in enumerate(row):
                    if v:
                        x0, y0 = qx + (c_ + 2) * q, qy + (r_ + 2) * q
                        d.rectangle((x0, y0, x0 + q - 1, y0 + q - 1), fill=(6, 18, 38))
            yy = qy + side + pad + round(28 * u)
            yy = centered("Nuskenuokite telefonu", font(sans, 20 * u), yy, muted)
        else:
            yy += round(30 * u)
        if link:
            yy = centered(link, font(sans, 34 * u), yy + round(6 * u), honey, W * 0.86)
        if card.get("handle"):
            yy = centered(card["handle"].strip(), font(sans, 24 * u), yy + round(8 * u), muted, W * 0.8)
        if _shift is None:  # turinys – kortelės viduryje (šiek tiek aukščiau centro)
            shift = round((H - (yy - top)) * 0.45) - top
            if abs(shift) > 4:
                return end_card_image(card, W, H, out_path, accent, _shift=shift)
    img.convert("RGB").save(out_path)
    return out_path


SERIF = "Playfair Display"
SCRIPT = "Great Vibes"

# Metaliniai gradientai (spalvų taškai nuo raidės viršaus iki apačios): akcento pavadinimas -> [(vieta, RGB)]
GRADIENTS = {
    # Baltijos gintaras: medaus šviesa viršuje, konjako tamsa per vidurį, šiltas atšvaitas apačioje
    "Gintaro gradientas": [(0.0, "FFEBB5"), (0.26, "FFC25E"), (0.46, "DB7E1F"), (0.56, "A9500E"),
                           (0.68, "EE9A35"), (0.86, "FFD488"), (1.0, "8A3A0A")],
    "Aukso gradientas": [(0.0, "FFF4C8"), (0.28, "F3D67E"), (0.48, "C99A30"), (0.56, "B07F1C"),
                         (0.68, "E9C964"), (0.86, "FBE7A2"), (1.0, "A47A1E")],
    "Sidabro gradientas": [(0.0, "FFFFFF"), (0.28, "E2E4E9"), (0.48, "9A9DA5"), (0.56, "80838C"),
                           (0.68, "CDD0D6"), (0.86, "F5F6F8"), (1.0, "6F727A")],
}

# Teksto šablonai. elegant – serifinis šriftas be dėžutės su plona linija, box – ryški dėžutė.
# Šablonai: kabliuko ir kvietimo stilius + akcentas + filtras. kind: elegant (serifinis), script (ranka rašytas),
# box (dėžutėje), bold (stambios raidės su kontūru); font – kitas šriftas, scale – teksto dydžio pataisa,
# cat – kategorija (skirtukai studijoje).
TEMPLATE_CATEGORIES = ("Prabanga", "Verslas", "Grožis", "Maistas", "Kelionės", "Šventės")
TEMPLATES = {
    "Baltijos gintaras": {"kind": "elegant", "accent": "Gintaro gradientas", "color": "Baltijos auksas",
                          "cat": "Prabanga"},
    "Prabangus auksas": {"kind": "elegant", "accent": "Aukso gradientas", "color": "Auksinė valanda",
                         "cat": "Prabanga"},
    "Ranka rašytas": {"kind": "script", "accent": "Aukso gradientas", "color": "Auksinė valanda", "cat": "Prabanga"},
    "Elegantiškas minimalizmas": {"kind": "elegant", "accent": "Sidabro gradientas", "color": "Kino",
                                  "cat": "Prabanga"},
    "Ryškus (TikTok stilius)": {"kind": "box", "accent": "Geltona", "color": "Ryškios", "cat": "Prabanga"},
    # Verslas
    "Verslo galia": {"kind": "bold", "accent": "Sidabro gradientas", "color": "Šaltos", "cat": "Verslas"},
    "Ekspertas": {"kind": "elegant", "accent": "Šampanas", "color": "Natūralios", "cat": "Verslas"},
    "Kino anonsas": {"kind": "elegant", "accent": "Oranžinė", "color": "Kino", "cat": "Verslas",
                     "look": "trailer", "effects": ["Kino juostos", "Kino grūdeliai"]},
    # Grožis
    "Grožio salonas": {"kind": "script", "font": "Dancing Script", "scale": 0.75, "accent": "Rožinė",
                       "color": "Paryžiaus rytas", "cat": "Grožis"},
    "Šampano švelnumas": {"kind": "elegant", "accent": "Šampanas", "color": "Pastelinės", "cat": "Grožis"},
    # Maistas
    "Gardžiai!": {"kind": "box", "accent": "Raudona", "color": "Ryškios", "cat": "Maistas"},
    "Kavinės jaukumas": {"kind": "script", "font": "Dancing Script", "scale": 0.75, "accent": "Auksas",
                         "color": "Vintažas", "cat": "Maistas"},
    # Kelionės
    "Nuotykis": {"kind": "bold", "accent": "Geltona", "color": "Teal & Orange", "cat": "Kelionės"},
    "Kelionių dienoraštis": {"kind": "script", "font": "Dancing Script", "scale": 0.75, "accent": "Balta",
                             "color": "Teal & Orange", "cat": "Kelionės"},
    # Šventės
    "Šventinis auksas": {"kind": "elegant", "accent": "Aukso gradientas", "color": "Auksinė valanda",
                         "cat": "Šventės"},
    "Vakarėlis": {"kind": "box", "accent": "Rožinė", "color": "Ryškios", "cat": "Šventės"},
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
    "Auksinis rėmelis": "Firminis: plona dviguba metalinė linija aplink kadrą su deimantėliais (aukso ar sidabro).",
    "Gintaro akimirka": "Firminis: pasirinktoje vietoje kadras švelniai nušvinta šilta gintaro šviesa ir truputį "
                        "priartėja – akcentas svarbiausiam žodžiui. Video ir kalba nesustoja."
}
MOMENT_LEN = 1.6  # s – kiek trunka „Gintaro akimirka“ (švytėjimas)
TEXT_EFFECTS = ("Aukso blizgesys",)  # matosi tik ant teksto – peržiūra rodoma su pavyzdiniu tekstu


def _zoompan(W, H, z, fps):
    """Priartinimas su PASTOVIU kadro dydžiu (zoompan, centre). Ankstesnis būdas (scale eval=frame + crop) keitė
    kadro dydį kiekvienam kadrui – kartu su kitais filtrais ffmpeg dėl to nulūždavo („double free or corruption“)."""
    return [f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}", "setsar=1"]


def zoom_filters(W, H, duration, fps=30):
    """Lėtas priartėjimas per visą video (10 %)."""
    d = max(1.0, duration)
    return _zoompan(W, H, f"1+0.10*it/{d:.3f}", fps)


def punch_filters(W, H, times, amp=0.07, length=0.55, fps=30):
    """Akcentų priartėjimas: ties svarbiausiais žodžiais kadras trumpam „įšoka“ arčiau (punch-in) ir grįžta."""
    times = sorted(times)[:40]
    if not times:
        return []
    z = "+".join(f"between(it,{a:.2f},{a + length:.2f})*sin(PI*(it-{a:.2f})/{length:.2f})" for a in times)
    return _zoompan(W, H, f"1+{amp}*({z})", fps)


AMBER_LOOK = ["colorbalance=rs=0.16:gs=0.05:bs=-0.2:rm=0.12:gm=0.03:bm=-0.16:rh=0.08:bh=-0.12",
              "eq=saturation=1.2:contrast=1.08:brightness=0.03", "vignette=PI/4.5"]


def moment_filter(at, length):
    """„Gintaro akimirka“: ties `at` s kadras švelniai nušvinta šilta gintaro šviesa ir vėl atšyla.
    Vienas paprastas filtras (be skaidymo ir sluoksnių) – greita ir patikima visose ffmpeg versijose."""
    a, b = at, at + length
    k = f"(between(t,{a:.3f},{b:.3f})*min(1,2.2*sin(PI*(t-{a:.3f})/{length:.3f})))"
    return (f"eq=brightness='0.06*{k}':contrast='1+0.06*{k}':saturation='1+0.28*{k}':"
            f"gamma_r='1+0.16*{k}':gamma_g='1+0.05*{k}':gamma_b='1-0.18*{k}':eval=frame")


def look_graph(inp, out, color="Natūralios", effects=(), W=1080, H=1920, duration=10.0, still=False,
               pre=(), post=(), fps=30):
    """Filtrų grandinė nuo `inp` iki `out` etikečių: spalvų filtras + efektai.
    still=True – vienam kadrui (miniatiūroms ir viršeliui): judesio efektai parodomi statiškai."""
    effects = set(effects or ())
    a = list(pre) + list(COLOR_FILTERS.get(color, []))
    if "Lėtas priartėjimas" in effects:
        a += ["crop=iw*0.88:ih*0.88", f"scale={W}:{H}"] if still else zoom_filters(W, H, duration, fps)
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
    if "Gintaro akimirka" in effects and still:  # langelio peržiūra: kaip atrodo „sustingęs“ kadras
        b += AMBER_LOOK
    b += list(post)
    if "Švytėjimas" in effects:
        sigma = max(4, round(W / 45))
        tail = ("," + ",".join(b)) if b else ""
        return (f"{inp}{','.join(a + ['format=gbrp', 'split'])}[gA][gB];"
                f"[gB]gblur=sigma={sigma},curves=all='0/0 0.5/0.35 1/1'[gC];"
                f"[gA][gC]blend=all_mode=screen:all_opacity=0.45,format=yuv420p{tail}{out}")
    return f"{inp}{','.join(a + b) or 'null'}{out}"


def still_extras(inp, out, width, height, effects, tmp, accent="Aukso gradientas", fps=25):
    """Rėmelis vienam kadrui (miniatiūroms, viršeliui, peržiūroms)."""
    chains, cur = [], inp
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


# Studijos formatai: pavadinimas -> (video_editor formatas, viršelio dydis)
STUDIO_FORMATS = {
    "9:16 · Reels, TikTok, Shorts": ("9:16", (1080, 1920)),
    "16:9 · YouTube": ("16:9", (1280, 720)),
    "1:1 · Kvadratas": ("1:1", (1080, 1080)),
    "4:5 · Instagram įrašas": ("4:5", (1080, 1350)),
}

SUBTITLE_POSITIONS = {"Viduryje": 0.62, "Žemiau": 0.72, "Apačioje": 0.78}
HOOK_POSITIONS = {"Viršuje": 0.12, "Aukščiau": 0.2, "Žemiau": 0.3}

SAMPLE_WORDS = [("Taip", 0.2, 0.6), ("atrodo", 0.6, 1.5), ("titrai", 1.5, 2.2)]
# dinamiškiems stiliams – visi žodžiai jau ištarti iki peržiūros kadro (1,2 s), paskutinis – svarbiausias
SAMPLE_FAST = [("Taip", 0.0, 0.3), ("atrodo", 0.3, 0.65), ("*titrai*", 0.65, 1.1)]


def _sample(look):
    return SAMPLE_FAST if video_editor.SUBTITLE_LOOKS.get(look, {}).get("mode") else SAMPLE_WORDS


def style_preview(frame, out_path, template="Prabangus auksas", accent="Auksas", color="Natūralios", effects=(),
                  hook="", look=None, width=270, height=480, subs_ypos=0.72, hook_ypos=0.2, subs_size=1.0,
                  text_size=1.0):
    """Šablono / titrų stiliaus peržiūra ant kadro: kabliukas (jei hook) ir titrų pavyzdys (jei look)
    taip, kaip atrodys video ~1 s (animacijos jau pasibaigusios, paryškintas antras žodis)."""
    tmp = tempfile.mkdtemp()
    try:
        post = []
        if hook.strip():
            a = os.path.join(tmp, "hook.ass")
            with open(a, "w", encoding="utf-8") as f:
                f.write(build_overlay_ass(width, height, 10, hook, 10, accent=accent, template=template,
                                          hook_ypos=hook_ypos, size=text_size))
            post.append(f"ass=filename='{_filter_path(a)}':fontsdir='{_filter_path(FONT_DIR)}'")
        if look:
            hl = _ass_color(accent_colors(accent)[0])[4:]
            a = os.path.join(tmp, "subs.ass")
            with open(a, "w", encoding="utf-8") as f:
                f.write(video_editor.build_ass(_sample(look), width, height, ypos=subs_ypos, highlight=hl,
                                               look=look, size=subs_size))
            post.append(f"ass=filename='{_filter_path(a)}':fontsdir='{_filter_path(FONT_DIR)}'")
        pre = [f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}", "setsar=1"]
        shine = "Aukso blizgesys" in (effects or ())
        if (accent in GRADIENTS or shine) and post:
            masks = []
            if look:
                a = os.path.join(tmp, "subs_mask.ass")
                with open(a, "w", encoding="utf-8") as f:
                    f.write(video_editor.build_ass(_sample(look), width, height, ypos=subs_ypos, look=look,
                                                   mask=True, size=subs_size))
                masks.append(f"ass=filename='{_filter_path(a)}':fontsdir='{_filter_path(FONT_DIR)}'")
            if hook.strip():
                masks.append(_cover_mask(tmp, width, height, hook, accent, template, hook_ypos, text_size))
            g = ";".join([look_graph("[0:v]", "[base]", color, effects, width, height, still=True, pre=pre,
                                     post=post)]
                         + gradient_chains("[base]", "[gl]", width, height, 10, 1.3, accent, masks, tmp, template,
                                           hook_ypos,
                                           shine=shine, still=True, size=text_size)
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
    "tropical_house": ("🌴 Tropical house", "Vasariška marimba ir šokių ritmas – kelionės, poilsis, vasaros akcijos."),
    "deep_house": ("🎧 Deep house", "122 BPM, gilus bosas – mada, naktinis gyvenimas, stilingi pristatymai."),
    "trap": ("🔥 Trap ir hip-hop", "808 bosas ir greiti hi-hat'ai – jaunimas, gatvės stilius, sportas."),
    "phonk": ("🏎 Phonk", "TikTok mėgstamas „cowbell“ ir sodrus bosas – automobiliai, sportas, transformacijos."),
    "reggaeton": ("💃 Reggaeton", "Karštas „dembow“ ritmas – šokiai, vakarėliai, vasara."),
    "funky": ("🕺 Funk ir disco", "Šokinėjantis bosas ir gitara – gera nuotaika, renginiai, maistas."),
    "retro_80": ("🌆 Retro 80-ieji", "Sintezatorių arpedžio – nostalgija, technologijos, naktinis miestas."),
    "motyvuojanti": ("🚀 Motyvuojanti", "Pianinas ir plojimai, kylanti nuotaika – verslas, pristatymai, pasiekimai."),
    "akustine": ("🎸 Akustinė", "Gitaros kirčiai ir plojimai – šeima, kasdienybė, rankų darbai, kavinės."),
    "kaledine": ("🎄 Kalėdinė", "Rogių skambalai ir varpeliai – Kalėdų akcijos, dovanos, šventės."),
    "spa": ("🧘 SPA ir ramybė", "Lėti pasažai be būgnų – grožio salonai, masažai, joga."),
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
SIGNATURE_EFFECTS = ("Gintaro akimirka", "Aukso blizgesys", "Auksinis rėmelis")

LENGTHS = {"Be ribos": None, "15 s": 15, "30 s": 30, "60 s": 60, "90 s": 90}


def _ass_color(rgb, alpha="00"):
    """RGB hex (FFD60A) -> ASS spalva (&HAABBGGRR)."""
    return f"&H{alpha}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}".upper()


# ---------- Debesėliai: ?, !, WOW, Hmm… – iššoka tam tikrose vietose ----------
BUBBLE_KINDS = {
    "question": {"shape": "speech", "text": "?", "title": "Klausimas"},
    "exclaim": {"shape": "burst", "text": "!", "title": "Šauktukas"},
    "wow": {"shape": "burst", "text": "WOW!", "title": "Nuostaba"},
    "hmm": {"shape": "thought", "text": "Hmm…", "title": "Abejonė"},
    "idea": {"shape": "speech", "text": "IDĖJA!", "title": "Idėja / patarimas"},
    "top": {"shape": "burst", "text": "TOP!", "title": "Geriausia"},
    "heart": {"shape": "heart", "text": "", "title": "Meilė / patinka"},
}
BUBBLE_LEN = 1.4  # s


def _f(v):
    return f"{v:.0f}"


def _ellipse(cx, cy, rx, ry):
    k = 0.5523
    return (f"m {_f(cx)} {_f(cy - ry)} b {_f(cx + k * rx)} {_f(cy - ry)} {_f(cx + rx)} {_f(cy - k * ry)} "
            f"{_f(cx + rx)} {_f(cy)} b {_f(cx + rx)} {_f(cy + k * ry)} {_f(cx + k * rx)} {_f(cy + ry)} "
            f"{_f(cx)} {_f(cy + ry)} b {_f(cx - k * rx)} {_f(cy + ry)} {_f(cx - rx)} {_f(cy + k * ry)} "
            f"{_f(cx - rx)} {_f(cy)} b {_f(cx - rx)} {_f(cy - k * ry)} {_f(cx - k * rx)} {_f(cy - ry)} "
            f"{_f(cx)} {_f(cy - ry)}")


def _bubble_shape(shape, w, h, left):
    """ASS piešinys (vietinės koordinatės 0..w, 0..h) ir teksto centras."""
    import math
    if shape == "burst":  # sprogimo žvaigždė
        n, pts = 12, []
        for i in range(n * 2):
            r = (0.5 if i % 2 == 0 else 0.34)
            a = math.pi * i / n - math.pi / 2
            pts.append((w / 2 + math.cos(a) * w * r, h / 2 + math.sin(a) * h * r))
        d = "m " + " l ".join(f"{_f(x)} {_f(y)}" for x, y in pts)
        return d, (w / 2, h / 2)
    if shape == "heart":
        d = (f"m {_f(w / 2)} {_f(h * 0.95)} b {_f(-w * 0.05)} {_f(h * 0.55)} {_f(w * 0.1)} {_f(-h * 0.05)} "
             f"{_f(w / 2)} {_f(h * 0.25)} b {_f(w * 0.9)} {_f(-h * 0.05)} {_f(w * 1.05)} {_f(h * 0.55)} "
             f"{_f(w / 2)} {_f(h * 0.95)}")
        return d, (w / 2, h / 2)
    if shape == "thought":  # minčių debesėlis + du burbuliukai
        d = _ellipse(w / 2, h * 0.42, w * 0.48, h * 0.36)
        for i, (cx, cy, rx, ry) in enumerate(((0.3, 0.2, 0.2, 0.17), (0.7, 0.22, 0.2, 0.17), (0.5, 0.12, 0.2, 0.12),
                                              (0.25, 0.6, 0.18, 0.15), (0.75, 0.6, 0.18, 0.15))):
            d += " " + _ellipse(w * cx, h * cy, w * rx, h * ry)
        bx = w * (0.22 if left else 0.78)
        d += " " + _ellipse(bx, h * 0.86, w * 0.07, h * 0.06) + " " + _ellipse(bx + (-1 if left else 1) * w * 0.08,
                                                                               h * 0.97, w * 0.04, h * 0.035)
        return d, (w / 2, h * 0.42)
    # kalbos debesėlis su uodegėle (į kalbančiojo pusę)
    d = _ellipse(w / 2, h * 0.42, w * 0.5, h * 0.4)
    tx = w * (0.3 if left else 0.7)
    tip = w * (0.12 if left else 0.88)
    tail = f"m {_f(tx - w * 0.08)} {_f(h * 0.7)} l {_f(tip)} {_f(h * 0.98)} l {_f(tx + w * 0.08)} {_f(h * 0.74)}"
    return [tail, d], (w / 2, h * 0.42)


def bubbles_ass(bubbles, width, height, accent="Aukso gradientas"):
    """Debesėlių ASS: bubbles – [(laikas s, rūšis)] galutiniame video. Debesėlis iššoka, pasvyra ir išnyksta."""
    acc = _ass_color(accent_colors(accent)[0])
    styles = [f"Style: B,{FONT_NAME},40,&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"]
    lines = _ass_header(width, height, styles)
    ref = min(width, height * 0.75)
    for i, (t, kind) in enumerate(sorted(bubbles)):
        k = BUBBLE_KINDS.get(kind)
        if not k:
            continue
        left = i % 2 == 0
        shape = k["shape"]
        w = ref * (0.34 if shape in ("speech", "thought") and len(k["text"]) > 2 else 0.26)
        h = w * (0.78 if shape != "burst" else 0.9)
        x0 = width * (0.07 if left else 0.93) - (0 if left else w)
        y0 = height * (0.3 if height > width else 0.12)
        d, (cx, cy) = _bubble_shape(shape, w, h, left)
        fill = {"burst": acc, "heart": "&H004A3BFF"}.get(shape, "&H00FFFFFF")
        rot = 8 if left else -8
        org = f"\\org({_f(x0 + w / 2)},{_f(y0 + h)})"
        anim = (f"\\fscx20\\fscy20\\t(0,140,\\fscx112\\fscy112)\\t(140,240,\\fscx100\\fscy100)"
                f"\\frz{rot}\\t(240,{round(BUBBLE_LEN * 1000)},\\frz{rot // 2})\\fad(0,220)")
        ol = max(3, round(w * 0.025))
        a, b = _ass_time(t), _ass_time(t + BUBBLE_LEN)
        # figūros piešiamos atskirai (persidengusios figūros viename piešinyje viena kitą „išpjautų“);
        # antras sluoksnis be kontūro uždengia vidines sandūrų linijas (uodegėlė, debesėlio burbulai)
        for layer, extra in ((5, f"\\3c&H00101010&\\bord{ol}\\shad{max(2, ol // 2)}"), (6, "\\bord0\\shad0")):
            for part in (d if isinstance(d, list) else [d]):
                lines.append(f"Dialogue: {layer},{a},{b},B,,0,0,0,,{{\\an7\\pos({_f(x0)},{_f(y0)}){org}"
                             f"\\1c{fill}{extra}{anim}\\p1}}" + part)
        if k["text"]:
            fs = round(h * (0.5 if len(k["text"]) <= 2 else 0.27 if len(k["text"]) <= 4 else 0.23))
            dark_fill = shape == "burst" and accent_colors(accent)[1] == "FFFFFF"  # tamsus akcentas – balta raidė
            col = "&H00FFFFFF" if dark_fill else "&H00101010"
            lines.append(f"Dialogue: 7,{a},{b},B,,0,0,0,,{{\\an5\\pos({_f(x0 + cx)},{_f(y0 + cy)}){org}\\fs{fs}"
                         f"\\1c{col}\\bord0\\shad0{anim}}}" + _ass_escape(k["text"]))
    return "\n".join(lines) + "\n"


def auto_bubbles(words, max_n=6, gap=2.5):
    """Debesėliai be AI – pagal skyrybą: klausimas -> „?“, šauktukas -> „!“ / „WOW!“."""
    out, last = [], -1e9
    for w, a, b in words:
        p = video_editor.plain(w).strip()
        kind = "question" if p.endswith("?") else ("wow" if len(out) % 2 else "exclaim") if p.endswith("!") else None
        if kind and b - last >= gap:
            out.append((round(max(0.0, b - 0.2), 2), kind))
            last = b
        if len(out) >= max_n:
            break
    return out


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


def _overlay_layout(width, height, template, hook_ypos=0.2, size=1.0):
    """Kabliuko ir CTA išdėstymas (bendras tekstui, kaukei ir gradientui). Dydžiai – nuo trumpesnės kraštinės,
    kad tiktų ir horizontaliam (YouTube) video; size – naudotojo mastelis."""
    t = TEMPLATES.get(template, TEMPLATES["Prabangus auksas"])
    kind = t["kind"]
    ref = min(width, height * 0.75) * size * t.get("scale", 1.0)
    if kind == "box":
        hsize, csize = round(ref * 0.074), round(ref * 0.07)
    elif kind == "bold":
        hsize, csize = round(ref * 0.088), round(ref * 0.075)
    elif kind == "script":
        hsize, csize = round(ref * 0.15), round(ref * 0.12)
    else:
        hsize, csize = round(ref * 0.088), round(ref * 0.075)
    hook_y = round(height * hook_ypos) + (0 if kind in ("box", "bold") else round(hsize * 0.9))
    cta_y = round(height * 0.44)
    return kind, hsize, csize, hook_y, cta_y


def build_overlay_ass(width, height, duration, hook="", hook_duration=3.0, cta="", cta_duration=2.5,
                      handle="", accent="Auksas", hook_ypos=0.2, template="Prabangus auksas", mask=False, size=1.0):
    """Kabliukas pradžioje, kvietimas veikti (CTA) pabaigoje ir @vardas viršuje.
    Šablonas „elegant“ – serifinis šriftas su plona linija ir švelniu ryškėjimu, „script“ – ranka rašytas
    kaligrafinis šriftas, „box“ – didelės raidės spalvotoje dėžutėje, kuri „iššoka“.
    mask=True – kaukė gradientui: balta tik ta dalis, kuri turi būti metalinė (be kontūrų ir šešėlių)."""
    kind, hsize, csize, hook_y, cta_y = _overlay_layout(width, height, template, hook_ypos, size)
    bg, fg = accent_colors(accent)
    acc = "&H00FFFFFF" if mask else _ass_color(bg)
    margin = round(width * 0.09)
    ref = min(width, height * 0.75)
    nsize = round(ref * 0.03)
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
    elif kind == "bold":  # stambios didžiosios raidės akcento spalva su storu tamsiu kontūru
        def bol(sz):
            return (0, 0) if mask else (max(3, round(sz * 0.11)), max(2, round(sz * 0.07)))
        styles = [
            f"Style: Hook,{FONT_NAME},{hsize},{acc},{acc},&H00000000,&H78000000,"
            f"0,0,0,0,100,100,0,0,1,{bol(hsize)[0]},{bol(hsize)[1]},5,{margin},{margin},0,1",
            f"Style: Cta,{FONT_NAME},{csize},{acc},{acc},&H00000000,&H78000000,"
            f"0,0,0,0,100,100,0,0,1,{bol(csize)[0]},{bol(csize)[1]},5,{margin},{margin},0,1",
        ]
    else:
        tfont = TEMPLATES.get(template, {}).get("font")
        font = tfont or (SCRIPT if kind == "script" else SERIF)
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
        if kind in ("box", "bold"):
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
                                 round(ref * 0.22 * size), max(2, round(ref) // 400), acc, 200))
    if cta and duration > cta_duration + 1:
        a = duration - cta_duration
        if kind in ("box", "bold"):
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
                                 round(ref * 0.16 * size), max(2, round(ref) // 400), acc, 0))
    if handle:
        label = handle.upper() if kind not in ("box", "bold") else handle
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
    c = accent_colors(accent)[0]
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

    u = min(width, height)  # vienodi atstumai ir horizontaliame, ir vertikaliame kadre
    m = u * 0.035
    alpha = np.maximum(alpha, rounded(m, u * 0.03, max(2.0, u * 0.0042)))
    alpha = np.maximum(alpha, rounded(m + u * 0.014, u * 0.02, max(1.0, u * 0.0018)) * 0.9)
    # deimantėliai viršuje ir apačioje (linija aplink juos „pertraukiama“)
    sz = u * 0.016
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


def _until(duration, fps):
    """Baigtinė trukmė pagalbiniams sluoksniams: be jos naujesnės ffmpeg versijos gali laukti be galo."""
    return f",fps={fps},trim=duration={duration:.3f}" if duration else ""


def frame_chains(inp, out, width, height, fps, tmp, accent="Aukso gradientas", duration=None):
    """Uždeda auksinį rėmelį (inp -> out)."""
    p = frame_image(os.path.join(tmp, "frame.png"), width, height, accent)
    return [f"movie='{_filter_path(p)}',loop=loop=-1:size=1:start=0{_until(duration, fps)},format=rgba[frm]",
            f"{inp}[frm]overlay=shortest=1:format=auto{out}"]


def gradient_image(path, width, height, accent, template="Prabangus auksas", hook_ypos=0.2, size=1.0):
    """Gradiento paveikslėlis (PPM). Kabliuko ir CTA srityse – metalinės juostos, sutapdintos su teksto
    eilutėmis (šviesus viršus, tamsesnė vidurio linija, blizgi apačia); likusiame kadre (titrams) – įstrižas
    blizgesys."""
    import numpy as np
    stops = grad_stops(accent)
    pos = np.array([p for p, _ in stops])
    cols = np.array([_hex(c) for _, c in stops], dtype=float)
    kind, hsize, csize, hook_y, cta_y = _overlay_layout(width, height, template, hook_ypos, size)
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
    if kind not in ("box", "bold"):  # eilutėmis sutapdintos juostos kabliukui ir CTA
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
                    hook_ypos=0.2, mask_pre=(), name="g", shine=False, still=False, size=1.0):
    """Filtrų grandinės, kurios „įlieja“ gradientą į tekstą: masks – ass filtrai, piešiantys baltą kaukę
    ant juodo fono (mask_pre – filtrai prieš juos, pvz. laiko poslinkis ar priartėjimas).
    shine – „Aukso blizgesys“: per tekstą kas 2,6 s perbėga šviesos ruožas (still – sustabdytas viduryje)."""
    grad = gradient_image(os.path.join(tmp, f"{name}.ppm"), width, height, accent, template, hook_ypos, size)
    mask_chain = ",".join(list(mask_pre) + list(masks))
    chains = [
        f"color=c=black:s={width}x{height}:r={fps}:d={duration:.3f},format=yuv420p,{mask_chain},format=gbrp[{name}m]",
        f"movie='{_filter_path(grad)}',loop=loop=-1:size=1:start=0{_until(duration, fps)},format=gbrp[{name}g0]",
        f"{base}format=gbrp[{name}b]",
    ]
    if shine:
        sh = shine_image(os.path.join(tmp, f"{name}_shine.png"), width, height)
        # Pirmas perbėgimas – kai kabliukas jau ryškus (~1 s), vėliau kas 2,6 s.
        x = "-W*0.08" if still else "if(lt(mod(t+1.6,2.6),1.1),-W+2*W*mod(t+1.6,2.6)/1.1,W)"
        chains += [f"movie='{_filter_path(sh)}',loop=loop=-1:size=1:start=0{_until(duration, fps)},format=rgba[{name}s]",
                   f"[{name}g0][{name}s]overlay=x='{x}':y=0:eval=frame:format=gbrp[{name}g]"]
    else:
        chains.append(f"[{name}g0]null[{name}g]")
    chains.append(f"[{name}b][{name}g][{name}m]maskedmerge,format=yuv420p{out}")
    return chains


def media_duration(path):
    """Bet kokio garso / video failo trukmė (s)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


CRASH_SIGNS = ("corrupted", "double free", "free()", "malloc", "segmentation", "aborted", "core dumped")


# Serveryje (REELS_MAX_RENDERS=1) vienu metu kuriamas tiek video – kiti palaukia eilėje (RAM neperpildoma)
_RENDER_SLOTS = threading.BoundedSemaphore(int(os.environ["REELS_MAX_RENDERS"])) \
    if os.environ.get("REELS_MAX_RENDERS", "").isdigit() and int(os.environ["REELS_MAX_RENDERS"]) > 0 else None


def _run(cmd, total, progress, what, stall=12.0, hard=180.0):
    """Kaip _run_once; jei ffmpeg nulūžta (vidinė atminties klaida – pasitaiko kai kuriose versijose su keliomis
    gijomis), automatiškai kartojama viena gija."""
    if _RENDER_SLOTS is not None:
        with _RENDER_SLOTS:
            return _run_unlocked(cmd, total, progress, what, stall, hard)
    return _run_unlocked(cmd, total, progress, what, stall, hard)


def _run_unlocked(cmd, total, progress, what, stall=12.0, hard=180.0):
    try:
        return _run_once(cmd, total, progress, what, stall, hard)
    except RuntimeError as e:
        msg = str(e).lower()
        if "užstrigo" in msg or not any(x in msg for x in CRASH_SIGNS):
            raise
        return _run_once(cmd, total, progress, what, stall, hard, threads="1")


def _run_once(cmd, total, progress, what, stall=12.0, hard=180.0, threads=None):
    """Paleidžia ffmpeg ir rodo eigą. Apsauga nuo užstrigimo (kai kurios ffmpeg versijos video pabaigoje laukia
    pagalbinių sluoksnių): jei eiga nebejuda `stall` s, o video jau beveik baigtas – ffmpeg tvarkingai sustabdomas
    (q, failas išsaugomas); jei nejuda `hard` s – nutraukiamas su aiškia klaida."""
    import threading
    proc = video_editor.popen(video_editor.limit_threads(cmd, threads), stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    state = {"t": 0.0, "seen": time.time()}
    errbuf = []
    threading.Thread(target=lambda: errbuf.append(proc.stderr.read()), daemon=True).start()

    def reader():
        for line in proc.stdout:
            m = re.match(r"out_time_us=(\d+)", line)
            if m:
                t = int(m.group(1)) / 1e6
                if t > state["t"]:
                    state["t"], state["seen"] = t, time.time()
    th = threading.Thread(target=reader, daemon=True)
    th.start()
    stopped_at, killed = None, False
    while proc.poll() is None:
        time.sleep(0.25)
        if progress and total > 0:
            progress(min(1.0, state["t"] / total))
        idle = time.time() - state["seen"]
        # koduotojas laiko kelias sekundes kadrų „žiūrai į priekį“, todėl „beveik baigtas“ – su atsarga
        near_end = total > 0 and state["t"] >= min(total - 1.5, total * 0.85)
        if stopped_at is None and ((near_end and idle > stall) or idle > hard):
            try:
                proc.stdin.write("q")
                proc.stdin.flush()
                proc.stdin.close()
            except Exception:
                pass
            stopped_at = time.time()
        elif stopped_at is not None and time.time() - stopped_at > 10:
            proc.kill()
            killed = True
            break
    proc.wait()
    th.join(timeout=2)
    time.sleep(0.1)
    err = "".join(errbuf)
    if killed:
        raise RuntimeError(f"{what}: ffmpeg užstrigo ir buvo nutrauktas (pasiekta {state['t']:.1f} iš {total:.1f} s).")
    if proc.returncode != 0 and not (stopped_at and proc.returncode in (0, 255)):
        if proc.returncode < 0 and not err.strip():  # nulūžo be pranešimo (signalas)
            err = f"ffmpeg aborted (signal {-proc.returncode})"
        # diagnostikai – į serverio žurnalą (Streamlit Cloud: Manage app → logs)
        import sys as _sys
        try:
            gi = cmd.index("-filter_complex_script") + 1
            with open(cmd[gi], encoding="utf-8") as gf:
                graph_txt = gf.read()
        except Exception:
            graph_txt = ""
        print(f"[ffmpeg klaida] kodas={proc.returncode} gijos={threads}\n{' '.join(map(str, cmd))}\n"
              f"{graph_txt}\n{err[-1500:]}", file=_sys.stderr, flush=True)
        raise RuntimeError(f"{what}:\n{err[-2000:]}")
    return {"stopped_early": bool(stopped_at), "reached": state["t"]}


def finish(path, out_path, hook="", hook_duration=3.0, cta="", cta_duration=2.5, handle="",
           accent="Auksas", template="Prabangus auksas", music=None, music_volume=0.25, ducking=True, max_length=None, speed=1.0,
           color="Auksinė valanda", progress_bar="Viršuje", progress=None, effects=(), preview=False,
           subs_words=None, subs_look="modern", subs_ypos=0.72, hook_ypos=0.2, subs_size=1.0, text_size=1.0,
           music_blocks=None, voiceover=None, clip_gain=1.0, moment_at=None, moment_len=MOMENT_LEN, punch=False,
           logo=None, end_card=None, bubbles=None, anims=None, subs_burn=False, subs_highlight="0AD6FF"):
    """Reels apdaila ant sumontuoto video. Grąžina {"duration", "width", "height"}.
    voiceover – įgarsinimas (balso failas, galima ir video): skamba visu garsumu (sustiprintas, išvalytas),
    natūraliu greičiu nuo pradžios; clip_gain – video klipų garso garsumas (0 – išjungtas); muzika patyli po balsu.
    Jei įgarsinimas ilgesnis už video – paskutinis kadras prailginamas.
    Gradiento akcentui (GRADIENTS) metalas „įliejamas“ į kabliuką, CTA ir paryškintą titrų žodį
    (subs_words – sumontuoto video titrų žodžiai, subs_look – jų išvaizda)."""
    info = video_editor.probe(path)
    W, H, fps = info["width"], info["height"], info["fps"]
    speed = max(0.5, min(2.0, float(speed or 1.0)))
    duration = info["duration"] / speed
    # „Gintaro akimirka“ – švytėjimas galutinio video laike (ne per arti pradžios / pabaigos)
    moment = "Gintaro akimirka" in (effects or ()) and moment_at is not None and duration > 1.0
    if moment:  # per toli nurodyta vieta – priartinama prie pabaigos
        lim = min(duration, max_length) if max_length else duration
        moment_at = max(0.1, min(float(moment_at), lim - moment_len - 0.1))
    extend = 0.0
    if voiceover:
        vo_dur = media_duration(voiceover)
        if vo_dur + 0.3 > duration:
            extend = vo_dur + 0.3 - duration
            duration += extend
    trimmed = bool(max_length) and duration > max_length + 0.05
    if trimmed:
        duration = float(max_length)
    # Pabaigos kortelė prisideda po video (trukmės riba jai netaikoma); kvietimas veikti tada rodomas kortelėje
    card_len = end_card_len(end_card, W, H)
    if card_len:
        end_card = dict(end_card, title=end_card.get("title") or cta)
        cta = ""
    # Animuota pabaiga („AČIŪ!“) – taip pat PO video (kad neuždengtų paskutinio sakinio), jei nėra pabaigos kortelės
    outro_len = 0.0
    phone_times = []
    fx_list = []
    gfx = []
    if anims and anims.get("outro") and not card_len:
        outro_len = animations.OUTRO_LEN
    total = duration + card_len + outro_len

    tmp = tempfile.mkdtemp()
    try:
        ass = os.path.join(tmp, "reels.ass")
        with open(ass, "w", encoding="utf-8") as f:
            f.write(build_overlay_ass(W, H, duration, hook, hook_duration, cta, cta_duration, handle, accent,
                                      hook_ypos=hook_ypos, template=template, size=text_size))

        pre = [f"setpts=PTS/{speed:.4f}"] if abs(speed - 1) > 0.001 else []
        if extend > 0.01:  # įgarsinimas ilgesnis – paskutinis kadras palaikomas ilgiau
            pre.append(f"tpad=stop_mode=clone:stop_duration={extend:.3f}")
        if card_len or outro_len:  # vieta kortelei / pabaigai (po ja – sustingęs paskutinis kadras)
            pre.append(f"tpad=stop_mode=clone:stop_duration={card_len + outro_len + 0.5:.3f}")
        post = [f"ass=filename='{_filter_path(ass)}':fontsdir='{_filter_path(FONT_DIR)}'"]
        gold = next((g for g in (anims or {}).get("gfx", []) if g.get("kind") == "gold3d"), None)
        if gold and subs_words:  # ✨ kol auksinės raidės ekrane – titrų nėra; po to tas pats žodis tampa titru
            g0, g1 = gold["t"], gold["t"] + fxpack.LEN["gold3d"] * speed
            rest = [w for w in subs_words if not (g0 - 0.05 <= w[1] < g1)]
            first = next((w for w in subs_words if w[1] >= g0 - 0.05), None)
            if first:
                nxt = next((w[1] for w in rest if w[1] >= g1), g1 + 1.0)
                rest.append((first[0], g1, max(g1 + 0.3, min(g1 + 0.9, nxt))))
            subs_words = sorted(rest, key=lambda w: w[1])
        if subs_burn and subs_words:  # titrai piešiami čia – jau galutiniu laiku (po greičio pakeitimo), todėl
            # animacijos sutampa su auksiniu žodžio sluoksniu (kitaip pagreitinus jos prasilenkia)
            sp = os.path.join(tmp, "subs.ass")
            with open(sp, "w", encoding="utf-8") as f:
                f.write(video_editor.build_ass([(w, a0 / speed, b0 / speed) for w, a0, b0 in subs_words], W, H,
                                               subs_ypos, subs_highlight, subs_look, size=subs_size))
            post.insert(0, f"ass=filename='{_filter_path(sp)}':fontsdir='{_filter_path(FONT_DIR)}'")
        if bubbles:  # debesėliai (laikai – montažo laiku, todėl dalinami iš greičio)
            bb = [(t / speed, k) for t, k in bubbles if t / speed < duration - 0.3]
            if bb:
                bp = os.path.join(tmp, "bubbles.ass")
                with open(bp, "w", encoding="utf-8") as f:
                    f.write(bubbles_ass(bb, W, H, accent))
                post.append(f"ass=filename='{_filter_path(bp)}':fontsdir='{_filter_path(FONT_DIR)}'")
        if anims:  # animacijos: lipdukai, žymėjimai, kortelės, įžanga / pabaiga (laikai – montažo laiku)
            pl = {k: [(t / speed, v) for t, v in anims.get("plan", {}).get(k, [])]
                  for k in ("stickers", "marks", "cards", "fx")}
            fx_list = [(t, k) for t, k in pl["fx"] if t < duration - 0.6]
            gfx = [dict(it, t=it["t"] / speed) for it in anims.get("gfx", [])
                   if it["t"] / speed < duration - fxpack.LEN.get(it.get("kind"), 2.5) * 0.6]
            spins = [it for it in gfx if it["kind"] in fxpack.SPIN_KINDS][:3]
            if spins:  # 📱 / 🖼 3D efektai įdedami į patį vaizdą – spalvos, titrai ir kt. ant viršaus
                path = fxpack.apply_spins(path, spins, os.path.join(tmp, "spins.mp4"), W, H, fps, tmp, speed)
            for t, k in fx_list:  # glitch ir nespalvota akimirka – laiko lange (pastovus kadro dydis)
                if k == "glitch":
                    e = f"enable='between(t,{t:.3f},{t + animations.GLITCH_LEN:.3f})'"
                    pre += [f"rgbashift=rh=-16:bh=16:rv=5:bv=-5:{e}", f"noise=alls=28:allf=t:{e}"]
                elif k == "bw":  # po spalvų filtro (kitaip filtras vėl nuspalvintų), prieš titrus
                    post.insert(0, f"hue=s=0:enable='between(t,{t:.3f},{t + animations.BW_LEN:.3f})'")
            phone_times = [t / speed for t in anims.get("plan", {}).get("phone", [])
                           if t / speed < duration - animations.PHONE_LEN * 0.6][:2]
            ap = os.path.join(tmp, "anims.ass")
            with open(ap, "w", encoding="utf-8") as f:
                f.write(animations.animations_ass(pl, W, H, duration + outro_len, accent_colors(accent)[0], subs_ypos,
                                                  anims.get("handle") or handle, anims.get("intro"),
                                                  anims.get("outro") and not card_len, gfx=gfx))
            post.append(f"ass=filename='{_filter_path(ap)}':fontsdir='{_filter_path(FONT_DIR)}'")
        # svarbiausių žodžių (*žodis*) laikai galutiniame video – akcentų priartėjimui
        punches = []
        if punch and subs_words:
            punches = [a0 / speed for w, a0, _ in subs_words if video_editor.is_key(w)]
        vfps = round(fps * speed, 3)  # po pagreitinimo (setpts) kadrų dažnis didesnis – zoompan turi jį žinoti
        punch_f = punch_filters(W, H, punches, fps=vfps)
        if moment:  # akimirkos metu kadras švelniai priartėja (titrai – kartu su vaizdu)
            punch_f += punch_filters(W, H, [moment_at], amp=0.06, length=moment_len, fps=vfps)
        pre += punch_f
        graph = [look_graph("[0:v]", "[base]", color, effects, W, H, duration, pre=pre, post=post, fps=vfps)]
        vout = "[base]"
        if moment:
            graph.append(f"[base]{moment_filter(moment_at, moment_len)}[mbase]")
            vout = "[mbase]"
        shine = "Aukso blizgesys" in (effects or ())
        if accent in GRADIENTS or shine:
            masks = []
            if subs_words:
                sw = [(w, a0 / speed, b0 / speed) for w, a0, b0 in subs_words]
                sm = os.path.join(tmp, "subs_mask.ass")
                with open(sm, "w", encoding="utf-8") as f:
                    f.write(video_editor.build_ass(sw, W, H, ypos=subs_ypos, look=subs_look, mask=True,
                                                   size=subs_size))
                masks.append(f"ass=filename='{_filter_path(sm)}':fontsdir='{_filter_path(FONT_DIR)}'")
                if not subs_burn:
                    masks += punch_f  # titrai sumontuoti anksčiau – „įšoka“ kartu su vaizdu
                    if "Lėtas priartėjimas" in (effects or ()):  # titrai sumontuoti anksčiau – priartėja su vaizdu
                        masks += zoom_filters(W, H, duration, fps)
            om = os.path.join(tmp, "overlay_mask.ass")
            with open(om, "w", encoding="utf-8") as f:
                f.write(build_overlay_ass(W, H, duration, hook, hook_duration, cta, cta_duration, "", accent,
                                          hook_ypos=hook_ypos, template=template, mask=True, size=text_size))
            masks.append(f"ass=filename='{_filter_path(om)}':fontsdir='{_filter_path(FONT_DIR)}'")
            graph += gradient_chains(vout, "[gold]", W, H, fps, total + 1, accent, masks, tmp, template,
                                     hook_ypos=hook_ypos, shine=shine, size=text_size)
            vout = "[gold]"
        inputs = ["-i", path]

        def add_input(*args):
            n = sum(1 for x in inputs if x == "-i")
            inputs.extend(args)
            return n

        thumbs = []
        if anims and (phone_times or any(it["kind"] in fxpack.OVERLAY_KINDS for it in gfx)):  # kadrai kortelėms
            tdir = os.path.join(tmp, "thumbs")
            os.makedirs(tdir, exist_ok=True)
            src_dur = max(1.0, info["duration"])
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf",
                            f"fps=12/{src_dur:.3f},scale=360:-2", "-frames:v", "12", os.path.join(tdir, "t%02d.jpg")],
                           check=False)
            thumbs = [PILImage.open(os.path.join(tdir, f)) for f in sorted(os.listdir(tdir))]
        for gi_, it in enumerate([x for x in gfx if x["kind"] == "pip"][:1]):  # 🔲 kadras kadre
            dp, box = fxpack.device_png(os.path.join(tmp, "device.png"), W, H)
            graph += fxpack.pip_chains(vout, f"[pipo{gi_}]", it["t"], W, H, fps, _filter_path(dp), box, f"pp{gi_}")
            vout = f"[pipo{gi_}]"
        for gi_, it in enumerate([x for x in gfx if x["kind"] == "reel"][:3]):  # 🎞️ prasisukanti kino juosta
            rp = fxpack.reel_png(os.path.join(tmp, f"reel{gi_}.png"), W, H)
            graph += fxpack.reel_chains(vout, f"[rlo{gi_}]", it["t"], W, H, fps, _filter_path(rp), f"rl{gi_}")
            vout = f"[rlo{gi_}]"
        for gi_, it in enumerate([x for x in gfx if x["kind"] in fxpack.OVERLAY_KINDS][:4]):  # efektai su kadrais
            if not thumbs:
                break
            op_ = fxpack.render_overlay(it["kind"], thumbs, os.path.join(tmp, f"gfx{gi_}.mov"), W, H, fps,
                                        accent_colors(accent)[0])
            k_ = add_input("-i", op_)
            graph.append(f"[{k_}:v]scale={W}:{H},format=yuva420p,setpts=PTS-STARTPTS+{it['t']:.3f}/TB[gx{gi_}]")
            graph.append(f"{vout}[gx{gi_}]overlay=eof_action=pass:format=auto[gxo{gi_}]")
            vout = f"[gxo{gi_}]"
        if anims and phone_times:  # 📱 nuotraukos skrenda į telefoną – kortelėse video kadrai
            if thumbs:
                bp_ = animations.render_phone_burst(thumbs, os.path.join(tmp, "phone.mov"), W, H, fps,
                                                    accent_colors(accent)[0])
                for pi_, pt in enumerate(phone_times):
                    k = add_input("-i", bp_)
                    graph.append(f"[{k}:v]scale={W}:{H},format=yuva420p,"
                                 f"setpts=PTS-STARTPTS+{max(0.0, pt - 0.4):.3f}/TB[ph{pi_}]")
                    graph.append(f"{vout}[ph{pi_}]overlay=eof_action=pass:format=auto[pho{pi_}]")
                    vout = f"[pho{pi_}]"
        for si_, (t, k) in enumerate([x for x in fx_list if x[1] == "shatter"][:3]):  # 🧱 byrančios kaladėlės
            snap = os.path.join(tmp, f"snap{si_}.jpg")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{min(t * speed, info['duration'] - 0.1):.3f}",
                            "-i", path, "-frames:v", "1", snap], check=False)
            if os.path.exists(snap):
                graded = thumbnail(snap, os.path.join(tmp, f"snapg{si_}.jpg"), color, [e for e in (effects or ())
                                   if e in ("Ryškumas", "Vinjetė", "Švytėjimas", "Kino juostos")],
                                   W // 2 // 2 * 2, H // 2 // 2 * 2, accent)
                sp_ = animations.render_shatter(PILImage.open(graded), os.path.join(tmp, f"shatter{si_}.mov"), fps)
                k_ = add_input("-i", sp_)
                graph.append(f"[{k_}:v]scale={W}:{H},format=yuva420p,setpts=PTS-STARTPTS+{t:.3f}/TB[sh{si_}]")
                graph.append(f"{vout}[sh{si_}]overlay=eof_action=pass:format=auto[sho{si_}]")
                vout = f"[sho{si_}]"
        if anims and (anims.get("intro") or (anims.get("outro") and not card_len)):  # logotipas įžangoje / pabaigoje
            lsrc = (logo or {}).get("path") if logo and os.path.exists((logo or {}).get("path", "")) else AMBER_LOGO
            lp_, _, _ = logo_layer({"path": lsrc, "size": 0.26, "opacity": 1.0}, W, H, os.path.join(tmp, "alogo.png"))
            windows = []
            if anims.get("intro"):
                windows.append((0.0, animations.INTRO_LEN))
            if outro_len:
                windows.append((duration, outro_len + 1))
            for wi, (st0, ln) in enumerate(windows):
                k = add_input("-loop", "1", "-framerate", str(fps), "-t", f"{ln:.3f}", "-i", lp_)
                fo = "" if wi else f",fade=t=out:st={ln - 0.35:.3f}:d=0.35:alpha=1"
                graph.append(f"[{k}:v]format=yuva420p,fade=t=in:st=0:d=0.35:alpha=1{fo},"
                             f"setpts=PTS-STARTPTS+{st0:.3f}/TB[al{wi}]")
                graph.append(f"{vout}[al{wi}]overlay=x=(W-w)/2:y='H*0.47-h-{round(H * 0.03)}*min(1,(t-{st0:.3f})/0.4)'"
                             f":eof_action=pass:format=auto[alo{wi}]")
                vout = f"[alo{wi}]"
        if card_len:  # pabaigos kortelė: švelniai išryškėja ties video pabaiga; rėmelis – virš jos
            cp = end_card_image(end_card, W, H, os.path.join(tmp, "end_card.png"), accent)
            k = add_input("-loop", "1", "-framerate", str(fps), "-t", f"{card_len + 1:.3f}", "-i", cp)
            graph.append(f"[{k}:v]format=yuva420p,fade=t=in:st=0:d=0.6:alpha=1,"
                         f"setpts=PTS-STARTPTS+{duration:.3f}/TB[card]")
            graph.append(f"{vout}[card]overlay=eof_action=pass:format=auto[carded]")
            vout = "[carded]"
        if "Auksinis rėmelis" in (effects or ()):
            graph += frame_chains(vout, "[framed]", W, H, fps, tmp, accent, duration=total + 1)
            vout = "[framed]"
        if logo and logo.get("path") and os.path.exists(logo["path"]):  # prekės ženklo logotipas
            lp, lx, ly = logo_layer(logo, W, H, os.path.join(tmp, "logo.png"))
            k = add_input("-loop", "1", "-framerate", str(fps), "-t", f"{total + 1:.3f}", "-i", lp)
            graph.append(f"{vout}[{k}:v]overlay=x={lx}:y={ly}:shortest=1:format=auto"
                         + (f":enable='lt(t,{duration:.3f})'" if card_len else "") + "[branded]")
            vout = "[branded]"
        if trimmed and not card_len:
            graph.append(f"{vout}fade=t=out:st={total - 0.5:.3f}:d=0.5[faded]")
            vout = "[faded]"
        if progress_bar in ("Viršuje", "Apačioje"):
            bh = max(6, round(H * 0.006)) // 2 * 2
            y = 0 if progress_bar == "Viršuje" else H - bh
            bg = accent_colors(accent)[0]
            graph.append(f"color=c=0x{bg}:s={W}x{bh}:r={fps}:d={total + 1:.3f}[bar]")
            graph.append(f"{vout}[bar]overlay=x='-w+w*t/{total:.3f}':y={y}:shortest=1[vout]")
            vout = "[vout]"

        speech = []  # kalbos šaltiniai (klipų garsas, įgarsinimas) – pagal juos patyli muzika
        if info["has_audio"] and clip_gain > 0.001:
            a = ["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
            if abs(speed - 1) > 0.001:
                a.append(f"atempo={speed:.4f}")
            if abs(clip_gain - 1) > 0.001:
                a.append(f"volume={clip_gain:.3f}")
            graph.append("[0:a:0]" + ",".join(a) + "[clipa]")
            speech.append("[clipa]")
        if voiceover:
            k = add_input("-i", voiceover)
            # įgarsinimas: nukerpam ūžesį, sumažinam triukšmą, suvienodinam garsumą (telefono įrašai būna tylūs)
            graph.append(f"[{k}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                         f"highpass=f=80,afftdn=nr=12:nf=-40,loudnorm=I=-15:TP=-1.5:LRA=11,"
                         f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                         f"apad=whole_dur={total + 1:.3f},atrim=duration={total + 1:.3f}[vo]")
            speech.append("[vo]")
        voice = None
        if len(speech) == 2:
            graph.append(f"{speech[0]}{speech[1]}amix=inputs=2:duration=longest:normalize=0[voice]")
            voice = "[voice]"
        elif speech:
            voice = speech[0]
        aout = voice
        blocks = [b for b in (music_blocks or []) if b["end"] - b["start"] >= 0.3 and b["start"] < total]
        if blocks:
            # Muzikos takelis: kiekvienas blokas skamba tik savo vietoje (su švelniu įėjimu / išėjimu)
            parts = []
            for j, blk in enumerate(blocks):
                k = add_input("-stream_loop", "-1", "-i", blk["path"])
                start = max(0.0, blk["start"])
                length = max(0.3, min(blk["end"], total) - start)
                fi, fo = min(0.6, length / 3), min(0.9, length / 3)
                vol = music_volume * blk.get("vol", 100) / 100
                graph.append(f"[{k}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                             f"atrim=duration={length:.3f},asetpts=PTS-STARTPTS,volume={vol:.3f},"
                             f"afade=t=in:st=0:d={fi:.3f},afade=t=out:st={length - fo:.3f}:d={fo:.3f},"
                             f"adelay=delays={round(start * 1000)}:all=1[mb{j}]")
                parts.append(f"[mb{j}]")
            mixed = "".join(parts) + (f"amix=inputs={len(parts)}:duration=longest:normalize=0," if len(parts) > 1
                                      else "anull,")
            graph.append(f"{mixed}apad=whole_dur={total + 1:.3f},atrim=duration={total + 1:.3f}[music]")
            music = True
        elif music:
            k = add_input("-stream_loop", "-1", "-i", music)
            graph.append(f"[{k}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                         f"volume={music_volume:.3f},afade=t=in:st=0:d=0.8,atrim=duration={total + 1:.3f}[music]")
        if music:
            if voice and ducking:
                graph.append(f"{voice}asplit=2[v1][v2]")
                graph.append("[music][v2]sidechaincompress=threshold=0.015:ratio=8:attack=30:release=500[duck]")
                graph.append(f"[v1][duck]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95,"
                             f"atrim=duration={total + 1:.3f}[mix]")
                aout = "[mix]"
            elif voice:
                graph.append(f"{voice}[music]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95,"
                             f"atrim=duration={total + 1:.3f}[mix]")
                aout = "[mix]"
            else:
                aout = "[music]"
        if aout and (music or trimmed) and total > 2:
            graph.append(f"{aout}afade=t=out:st={total - 0.8:.3f}:d=0.8[aend]")
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
                "-r", str(fps), "-movflags", "+faststart", "-t", f"{total:.3f}", out_path]
        _run(cmd, total, progress, "Nepavyko paruošti Reels")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return {"duration": total, "width": W, "height": H, "trimmed": trimmed}


def _cover_mask(tmp, width, height, hook, accent, template, ypos=0.42, size=1.0):
    p = os.path.join(tmp, "cover_mask.ass")
    with open(p, "w", encoding="utf-8") as f:
        f.write(build_overlay_ass(width, height, 10, hook, 10, accent=accent, hook_ypos=ypos, template=template,
                                  mask=True, size=size))
    return f"ass=filename='{_filter_path(p)}':fontsdir='{_filter_path(FONT_DIR)}'"


def make_cover(path, out_path, at=0.5, hook="", accent="Auksas", template="Prabangus auksas",
               handle="", width=1080, height=1920, color=None, effects=(), text_size=1.0):
    """Viršelis (JPG, numatytai 1080×1920): kadras iš video (arba nuotrauka) su filtru, efektais ir kabliuku per vidurį."""
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
                                          hook_ypos=0.42, template=template, size=text_size))
            post.append(f"ass=filename='{_filter_path(ass)}':fontsdir='{_filter_path(FONT_DIR)}'")
        fx = [e for e in effects if e != "Šviesos blyksnis"]
        shine = "Aukso blizgesys" in fx
        if (accent in GRADIENTS or shine) and post and hook.strip():
            g = ";".join([look_graph("[0:v]", "[base]", color, fx, width, height, still=True, pre=pre, post=post)]
                         + gradient_chains("[base]", "[cv]", width, height, 25, 10, accent, [_cover_mask(
                             tmp, width, height, hook, accent, template, 0.42, text_size)], tmp, template, 0.42,
                             mask_pre=["setpts=PTS+5/TB"], shine=shine, still=True, size=text_size))
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


def _ai_json(client, system, user, temperature=0.4):
    """Užklausa OpenAI, atsakymas – JSON (bandomi keli modeliai)."""
    last = None
    for m in video_editor.TRANSLATE_MODELS:
        try:
            r = client.chat.completions.create(
                model=m, temperature=temperature, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(user, ensure_ascii=False)}])
            return json.loads(r.choices[0].message.content)
        except Exception as e:  # modelis nepasiekiamas – bandom kitą
            last = e
    raise RuntimeError(f"Dirbtinis intelektas neatsakė: {last}")


def transcript_lines(words, speed=1.0, limit=300):
    """Kalba su laikais galutiniame video: „[3.2] žodis“ (dirbtiniam intelektui)."""
    return " ".join(f"[{a / speed:.1f}] {video_editor.plain(w)}" for w, a, _ in list(words)[:limit])


def ai_direct(client, request, settings, options, words=(), speed=1.0):
    """✨ AI režisierius: naudotojo prašymas (bet kokia kalba) -> nustatymų pakeitimai.
    settings – dabartiniai nustatymai, options – leistinos reikšmės. Grąžina {"changes": {...}, "summary": str}."""
    system = (
        "You are the creative director of a luxury Reels/Shorts video editing studio. The user describes in "
        "Lithuanian (or another language) how the video should change. Change ONLY the settings needed to "
        "fulfil the request, using ONLY the allowed values listed in `options` (copy them exactly). "
        "Numbers must be within the given ranges. `effects` is the complete new list of effects. "
        "To highlight a moment with a warm amber glow (\"Gintaro akimirka\"), add that effect and set `moment_at` in seconds "
        "of the final video – use the transcript times ([seconds] word) to find words the user mentions. "
        "Texts (hook, cta) must be short, catchy, in the language of the transcript (default Lithuanian) "
        "with correct diacritics. If something cannot be done with these settings, say so in the summary. "
        'Reply only with JSON: {"changes": {"setting": value, ...}, "summary": "1-3 short sentences in '
        'Lithuanian: what you changed and why"}')
    user = {"request": request, "current": settings, "options": options,
            "transcript": transcript_lines(words, speed)}
    j = _ai_json(client, system, user)
    ch = j.get("changes") if isinstance(j.get("changes"), dict) else {}
    return {"changes": ch, "summary": str(j.get("summary", "")).strip()}


def ai_hooks(client, words=(), topic="", text=""):
    """3–5 kabliukų pasiūlymai pagal kalbą / temą."""
    system = ("You write scroll-stopping hooks for Instagram Reels. Based on the spoken text (or topic), write 5 "
              "different short hooks (max 7 words each) in the language of the text (default Lithuanian, correct "
              "diacritics): curiosity, benefit, number, question, bold claim. "
              'Reply only with JSON: {"hooks": ["..."]}')
    spoken = " ".join(video_editor.plain(w[0]) for w in words)[:3000] or text[:3000]
    j = _ai_json(client, system, {"spoken_text": spoken, "topic": topic}, temperature=0.8)
    return [str(h).strip().strip('"„“') for h in j.get("hooks", []) if str(h).strip()][:5]


def ai_key_word_indices(client, words):
    """Svarbiausių žodžių numeriai (AI): ne daugiau kaip ~1 per 2,5 s, tik prasminiai žodžiai."""
    if not words:
        return []
    numbered = [f"{i}:{video_editor.plain(w)}" for i, (w, _, _) in enumerate(words[:400])]
    dur = max(1.0, words[-1][2] - words[0][1])
    n = max(1, min(25, round(dur / 2.6)))
    system = ("You edit subtitles for viral short videos. From the numbered words, choose the most important words "
              f"to emphasize visually (up to {n}): key numbers, product names, strong emotional or benefit words – "
              "never filler words, pronouns or prepositions. Spread them across the video. "
              'Reply only with JSON: {"indices": [numbers]}')
    j = _ai_json(client, system, {"words": " ".join(numbered)}, temperature=0.2)
    out = []
    for i in j.get("indices", []):
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(words) and i not in out:
            out.append(i)
    return sorted(out)[:n]


def mark_indices(words, indices, min_gap=1.2):
    """Pažymi nurodytus žodžius *žodis* (per arti vienas kito – praleidžiami)."""
    out, last = list(words), -1e9
    for i in sorted(indices):
        w, a, b = out[i]
        if a - last < min_gap or not re.search(r"\w", w):
            continue
        m = re.match(r"^(\W*)(.*?)(\W*)$", w, flags=re.UNICODE)
        out[i] = (f"{m.group(1)}{video_editor.KEY_MARK}{m.group(2)}{video_editor.KEY_MARK}{m.group(3)}", a, b)
        last = a
    return out


def ai_ideas(client, niche, extra="", n=5):
    """💡 Reels idėjos su paruoštu tekstu (sufleriui). Grąžina [{title, hook, script, cta, shot}]."""
    system = ("You are a top Lithuanian social media strategist. For the given business / niche, write "
              f"{n} different Instagram Reels ideas in Lithuanian with correct diacritics. Mix formats: tips list, "
              "common mistake, before/after, behind the scenes, answer to a client question, myth vs truth, story. "
              "For each: title (max 6 words), hook (first spoken sentence, max 9 words, scroll-stopping), script "
              "(what to say on camera after the hook, 3–6 short natural spoken sentences, 20–40 seconds, simple "
              "words, no hashtags or emojis), cta (short call to action), shot (one short tip what to show on camera). "
              'Reply only with JSON: {"ideas": [{"title": "", "hook": "", "script": "", "cta": "", "shot": ""}]}')
    j = _ai_json(client, system, {"niche": niche, "notes": extra}, temperature=0.9)
    out = []
    for it in j.get("ideas", []):
        if isinstance(it, dict) and str(it.get("script", "")).strip():
            out.append({k: str(it.get(k, "")).strip() for k in ("title", "hook", "script", "cta", "shot")})
    return out[:n]


def template_ideas(niche):
    """💡 Idėjos BE dirbtinio intelekto – patikrinti Reels formatai su jūsų sritimi."""
    x = (niche or "mano sritis").strip()
    return [
        {"title": "3 patarimai", "hook": f"3 patarimai, kuriuos turi žinoti kiekvienas – {x}",
         "script": f"Pirmas patarimas – pradėkite nuo paprasčiausio dalyko, kurį galite padaryti šiandien. "
                   f"Antras – neskubėkite, kokybė svarbiau už greitį. Trečias – klauskite specialisto, "
                   f"kai abejojate. Būtent taip dirbame ir mes – {x}.",
         "cta": "Išsaugok, kad nepamirštum!", "shot": "Kalbėkite į kamerą, ties kiekvienu patarimu parodykite pirštais skaičių."},
        {"title": "Dažniausia klaida", "hook": "Šią klaidą daro beveik visi",
         "script": f"Dažniausia klaida, kurią matau kasdien – noras viską padaryti iš karto. "
                   f"Rezultatas tada nedžiugina. Mano patarimas – vienas žingsnis vienu metu. "
                   f"Taip dirbdami pasiekiame geriausių rezultatų – {x}.",
         "cta": "Parašyk, ar tau tai pažįstama 👇", "shot": "Pradėkite rimtu veidu, pabaigoje nusišypsokite."},
        {"title": "Prieš ir po", "hook": "Pažiūrėk, koks skirtumas!",
         "script": f"Štai kaip atrodė pradžioje. O štai rezultatas po mūsų darbo. "
                   f"Visas paslaptis – kruopštumas ir patirtis. Toks yra mūsų kasdienis darbas – {x}.",
         "cta": "Nori tokio rezultato? Rašyk žinutę!", "shot": "Pirmiausia parodykite „prieš“, tada – „po“ (du įrašai)."},
        {"title": "Užkulisiai", "hook": "Taip atrodo mūsų diena iš vidaus",
         "script": f"Rytas prasideda nuo kavos ir plano. Tada – darbas, kurį labai mylime. "
                   f"Kiekviena detalė svarbi, todėl skiriame laiko kiekvienam klientui. Tai mes – {x}.",
         "cta": "Sek, kad pamatytum daugiau!", "shot": "Kelios trumpos scenos: atvykimas, darbas, rezultatas."},
        {"title": "Atsakau į klausimą", "hook": "Klientai dažniausiai klausia būtent to",
         "script": f"Dažniausias klausimas, kurį girdžiu – nuo ko pradėti? Atsakymas paprastas: "
                   f"nuo pokalbio. Pasakykite, ko norite, o mes pasiūlysime geriausią sprendimą. "
                   f"Tam ir esame – {x}.",
         "cta": "Užduok savo klausimą komentaruose!", "shot": "Parodykite klausimą ekrane, tada atsakykite į kamerą."},
    ]


def ai_bubbles(client, words, max_n=6):
    """AI parenka vietas debesėliams (laikai – kaip žodžių): [(laikas, rūšis)]."""
    kinds = {k: v["title"] for k, v in BUBBLE_KINDS.items()}
    system = ("You add playful comic speech bubbles to a short social video. From the timed transcript ([seconds] "
              f"word), choose up to {max_n} moments (at least 2.5 s apart) where a bubble adds emotion: a question, "
              "surprise, doubt, a tip/idea, the best part, love. Use only these kinds: "
              + json.dumps(kinds, ensure_ascii=False) +
              '. Reply only with JSON: {"bubbles": [{"time": seconds, "kind": "question"}]}')
    j = _ai_json(client, system, {"transcript": transcript_lines(words)}, temperature=0.4)
    out, last = [], -1e9
    end = words[-1][2] if words else 0
    for b in sorted(j.get("bubbles", []), key=lambda x: float(x.get("time", 0)) if isinstance(x, dict) else 0):
        try:
            t, k = float(b["time"]), str(b["kind"])
        except (KeyError, TypeError, ValueError):
            continue
        if k in BUBBLE_KINDS and 0 <= t <= end and t - last >= 2.0:
            out.append((round(t, 2), k))
            last = t
    return out[:max_n]


def ai_moment(client, words, speed=1.0):
    """Svarbiausia video akimirka (s galutiniame video) – „Gintaro akimirkai“."""
    system = ("Find the single most impactful moment in this short video's speech – the key reveal, number, "
              "result or emotional peak – where a 1.6 s warm amber glow with a gentle zoom would add emphasis. Times are in "
              "[seconds]. Reply only with JSON: {\"time\": seconds, \"word\": \"the word\", \"why\": "
              "\"short reason in Lithuanian\"}")
    j = _ai_json(client, system, {"transcript": transcript_lines(words, speed)}, temperature=0.2)
    return float(j.get("time", 0)), str(j.get("word", "")), str(j.get("why", ""))


CATEGORY_TAGS = {
    "Prabanga": ["#prabanga", "#stilius", "#elegancija", "#luxury"],
    "Verslas": ["#verslas", "#smulkusverslas", "#verslasLietuvoje", "#marketingas", "#business"],
    "Grožis": ["#grozis", "#groziopatarimai", "#savipriezura", "#beauty"],
    "Maistas": ["#maistas", "#receptai", "#skanu", "#food"],
    "Kelionės": ["#keliones", "#atostogos", "#lietuvoskeliones", "#travel"],
    "Šventės": ["#sventes", "#dovanos", "#vakarelis", "#celebration"],
}
CATEGORY_EMOJI = {"Prabanga": "✨", "Verslas": "💼", "Grožis": "💄", "Maistas": "🍽️", "Kelionės": "✈️",
                  "Šventės": "🎉"}
BASE_TAGS = ["#reels", "#lietuva", "#instagramreels", "#reelsinstagram", "#fyp"]


def _tag(text):
    t = re.sub(r"[^\w]", "", text.lower(), flags=re.UNICODE)
    return "#" + t if len(t) >= 3 else ""


def simple_caption(text="", hook="", topic="", cta="", category="Prabanga", words=()):
    """Aprašymas ir grotažymės BE dirbtinio intelekto: iš kabliuko, temos, kalbos ir svarbiausių žodžių.
    Grąžina tą pačią struktūrą kaip write_caption()."""
    emoji = CATEGORY_EMOJI.get(category, "✨")
    sentences = [x.strip() for x in re.split(r"(?<=[.!?…])\s+", (text or "").strip()) if len(x.strip()) > 3]
    first = hook.strip() or topic.strip() or (sentences[0] if sentences else "")
    lines = []
    if first:
        lines.append(f"{first[:110].rstrip()} {emoji}")
    extra = next((x for x in sentences if x != first), "")
    if extra:
        lines.append(extra[:140])
    lines.append(cta.strip() + " 👇" if cta.strip() else "Išsaugok, kad nepamirštum! 💾")
    lines.append("Ką manai? Parašyk komentaruose 💬")
    tags = []
    for t in ([_tag(topic)] + [_tag(w) for w in topic.split()[:3]]
              + [_tag(video_editor.plain(w)) for w, _, _ in words if video_editor.is_key(w)][:3]
              + CATEGORY_TAGS.get(category, []) + BASE_TAGS):
        if t and t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    return {"caption": "\n".join(lines), "hashtags": tags[:12], "hooks": [], "simple": True}


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
