"""„Pop-out“ efektas: ranka su telefonu išlenda iš nuotraukos ir uždengia komentarus po ja.

Nuotraukoje arba video turi būti telefonas su žaliu ekranu (green screen). Programa:
  1. randa žalią ekraną ir įdeda jūsų ekrano vaizdą (perspektyva pagal telefono kampą),
  2. iškerpa telefoną ir ranką (tik odą – rankovė ir marškiniai lieka nuotraukoje),
  3. sudeda įrašo vaizdą: viršuje nuotrauka, apačioje komentarai, o ranka su telefonu
     išlenda per nuotraukos kraštą ir uždengia komentarus.

Video iš nuotraukos galima gauti dviem būdais:
  - be AI: nuotrauka animuojama (ranka „išstumia“ telefoną į priekį),
  - su AI (fal.ai, Kling): nuotrauka paverčiama video pagal užklausą, o efektas
    uždedamas kiekvienam kadrui.

Paleisti galima ir iš komandinės eilutės:
  python3 popout.py NUOTRAUKA.png OUT.png [--video OUT.mp4]
"""
import base64
import math
import os
import subprocess
import tempfile
import time

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350          # 4:5 – didžiausias formatas, kurio Facebook sraute neapkarpo
SS = 2                     # komentarų dalis piešiama 2x didesnė ir sumažinama (glotnesnis tekstas)
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
SYSTEM_FONTS = [os.path.join(FONT_DIR, "Inter-{w}.otf"),
                "/usr/share/fonts/opentype/inter/Inter-{w}.otf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans{d}.ttf"]
AVATAR_COLORS = [(214, 120, 140), (90, 140, 200), (120, 170, 110), (200, 150, 80), (150, 110, 200)]

DEFAULT_PROMPT = ("The person smoothly extends their arm straight toward the camera, pushing the "
                  "smartphone closer to the lens, natural realistic hand movement, the phone screen "
                  "stays bright green and faces the viewer, static camera, background unchanged")


def font(weight, size):
    for pattern in SYSTEM_FONTS:
        path = pattern.format(w=weight, d="-Bold" if weight in ("Bold", "SemiBold") else "")
        if os.path.exists(path):
            return ImageFont.truetype(path, int(size))
    return ImageFont.load_default(size=int(size))


# ---------- Žalias ekranas ----------

def find_screen(rgb):
    """Randa žalią telefono ekraną. Grąžina 4 kampus (tl, tr, br, bl) arba None."""
    a = rgb.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    green = (g > 120) & (g > r + 50) & (g > b + 50)
    ys, xs = np.nonzero(green)
    if len(xs) < 2000:
        return None, green
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    w, h = x1 - x0, y1 - y0

    def fit(keys, along_rows, pick):
        pts = []
        for k in keys:
            sel = (ys == k) if along_rows else (xs == k)
            if sel.sum() >= 3:
                pts.append((k, pick((xs if along_rows else ys)[sel])))
        pts = np.array(pts, float)
        return np.polyfit(pts[:, 0], pts[:, 1], 1)

    rows = range(y0 + h // 6, y1 - h // 6)
    left, right = fit(rows, True, np.min), fit(rows, True, np.max)
    # viršų matuojame tik kraštuose – viduryje gali būti „notch“
    top = fit(list(range(x0 + w // 12, x0 + w // 5)) + list(range(x1 - w // 5, x1 - w // 12)),
              False, np.min)
    bottom = fit(range(x0 + w // 6, x1 - w // 6), False, np.max)

    def cross(v, hz):   # x = v0*y + v1 ; y = h0*x + h1
        y = (hz[0] * v[1] + hz[1]) / (1 - hz[0] * v[0])
        return np.array([v[0] * y + v[1], y])

    quad = np.array([cross(left, top), cross(right, top), cross(right, bottom), cross(left, bottom)])
    quad += np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])
    return quad, green


def perspective_coeffs(dst_quad, src_size, margin=0):
    """Koeficientai PIL PERSPECTIVE: kadro taškas -> ekrano vaizdo taškas."""
    sw, sh = src_size
    src = [(margin, margin), (sw - margin, margin), (sw - margin, sh - margin), (margin, sh - margin)]
    A, B = [], []
    for (x, y), (u, v) in zip(dst_quad, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return tuple(np.linalg.solve(np.array(A, float), np.array(B, float)))


def render_screen(title="Automatizacijos", status="Veikia 24/7",
                  items=("Užklausa gauta", "Atsakymas išsiųstas", "Sąskaita sukurta", "Įrašyta į CRM"),
                  big_label="Šią savaitę sutaupyta", big_value="12 val.", big_note="≈ 1,5 darbo dienos",
                  size=(600, 1260)):
    """Telefono ekrano vaizdas (galima pakeisti savo įkeltu paveikslėliu)."""
    sw, sh = size
    s = Image.new("RGB", size, (244, 245, 250))
    d = ImageDraw.Draw(s)
    d.text((44, 95), title, font=font("Bold", 44), fill=(20, 24, 50))
    d.ellipse((46, 168, 70, 192), fill=(40, 200, 120))
    d.text((84, 163), status, font=font("Medium", 30), fill=(60, 140, 95))
    colors = [(255, 189, 46), (150, 110, 255), (40, 200, 160), (90, 150, 250)]
    for i, text in enumerate(list(items)[:4]):
        y = 240 + i * 140
        d.rounded_rectangle((34, y, sw - 34, y + 120), 28, fill="white")
        d.ellipse((58, y + 28, 122, y + 92), fill=colors[i % 4])
        d.line((75, y + 61, 86, y + 72, 106, y + 50), fill="white", width=8)
        d.text((146, y + 24), text, font=font("SemiBold", 33), fill=(25, 25, 35))
        d.text((146, y + 70), f"prieš {1 + i // 2} min.", font=font("Regular", 25), fill=(130, 130, 140))
    d.rounded_rectangle((34, 830, sw - 34, 1150), 36, fill=(80, 70, 230))
    d.text((70, 868), big_label, font=font("Medium", 32), fill=(215, 212, 255))
    d.text((66, 920), big_value, font=font("Bold", 120), fill="white")
    d.text((70, 1080), big_note, font=font("Medium", 30), fill=(215, 212, 255))
    return s


def replace_screen(img, screen, quad=None):
    """Įdeda ekrano vaizdą vietoj žalio ekrano. Grąžina (vaizdas, telefono kaukė) arba (img, None)."""
    rgb = np.asarray(img.convert("RGB"))
    if quad is None:
        quad, green = find_screen(rgb)
    else:
        _, green = find_screen(rgb)
    if quad is None:
        return img.convert("RGB"), None, None
    sw, sh = 600, int(600 * max(1.2, (np.linalg.norm(quad[3] - quad[0]) / max(1, np.linalg.norm(quad[1] - quad[0])))))
    scr = screen.convert("RGB").resize((sw, sh), Image.LANCZOS)
    coef = perspective_coeffs(quad, (sw, sh))
    warped = scr.transform(img.size, Image.PERSPECTIVE, coef, Image.BICUBIC)
    gmask = Image.fromarray((green * 255).astype("uint8")).filter(ImageFilter.MaxFilter(3)) \
        .filter(ImageFilter.GaussianBlur(1))
    out = img.convert("RGB").copy()
    out.paste(warped, (0, 0), gmask)
    # nuvalome žalią atspindį aplink ekrano kraštą
    o = np.asarray(out).astype(np.int16)
    near = np.asarray(gmask.filter(ImageFilter.MaxFilter(9))) > 0
    o[..., 1] = np.where(near, np.minimum(o[..., 1], np.maximum(o[..., 0], o[..., 2]) + 10), o[..., 1])
    out = Image.fromarray(o.clip(0, 255).astype("uint8"))
    # telefono korpusas: ekranas + rėmelis su suapvalintais kampais (perspektyvoje)
    m = 0.06 * sw
    body = Image.new("L", (int(sw + 2 * m), int(sh + 2 * m)), 0)
    ImageDraw.Draw(body).rounded_rectangle((0, 0, body.width - 1, body.height - 1), int(0.16 * sw), fill=255)
    pmask = body.transform(img.size, Image.PERSPECTIVE, perspective_coeffs(quad, body.size, margin=m),
                           Image.BILINEAR)
    return out, pmask, quad


# ---------- Rankos iškirpimas ----------

def hand_mask(img, phone_mask, quad):
    """Telefonas + prie jo prisiliečianti oda (pirštai, plaštaka, dilbis). Marškiniai neįeina."""
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    skin = (cb > 77) & (cb < 130) & (cr > 133) & (cr < 175) & (r > 60)

    x0, y0 = quad[:, 0].min(), quad[:, 1].min()
    x1, y1 = quad[:, 0].max(), quad[:, 1].max()
    pw, ph = x1 - x0, y1 - y0
    region = np.zeros(skin.shape, bool)
    ry0, ry1 = int(max(0, y0 - 0.15 * ph)), int(min(skin.shape[0], y1 + 0.35 * ph))
    rx0, rx1 = int(max(0, x0 - 0.9 * pw)), int(min(skin.shape[1], x1 + 0.35 * pw))
    region[ry0:ry1, rx0:rx1] = True
    phone = np.asarray(phone_mask) > 127

    cand = Image.fromarray(((skin & region) | phone).astype("uint8") * 255)
    cand = cand.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))   # užlopome skyles
    cand = cand.point(lambda v: 255 if v > 127 else 0)
    # paliekame tik tai, kas susijungę su telefonu (veidas ir kt. neįeina)
    ys, xs = np.nonzero(phone)
    seed = (int(xs.mean()), int(ys.mean()))
    ImageDraw.floodfill(cand, seed, 128)
    arm = np.asarray(cand) == 128
    # rankovė: siaura juosta aplink dilbį (tik žemiau pirštų), liemuo neįeina
    q = 4
    small = Image.fromarray(arm.astype("uint8") * 255).resize((arm.shape[1] // q, arm.shape[0] // q))
    k = max(3, int(0.12 * pw / q) | 1)
    sleeve = np.asarray(small.filter(ImageFilter.MaxFilter(k)).resize((arm.shape[1], arm.shape[0]))) > 127
    sleeve[: int(y1 - 0.3 * ph)] = False
    below = np.nonzero(arm[int(y1):].any(axis=0))[0]        # dilbio plotis po telefonu
    if len(below):
        sleeve[:, : max(0, int(below.min() - 0.15 * pw))] = False
        sleeve[:, int(below.max() + 0.15 * pw):] = False
    else:
        sleeve[:] = False
    m = (arm | (sleeve & region)).astype(np.float32)
    # dilbio apačią išblukiname, kad neliktų kirpimo linijos
    fade0, fade1 = y1 + 0.12 * ph, ry1
    yy = np.arange(m.shape[0])[:, None]
    m *= np.clip((fade1 - yy) / max(1, fade1 - fade0), 0, 1)
    m = np.maximum(m, phone.astype(np.float32))
    return Image.fromarray((m * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(1.5))


# ---------- Įrašo maketas ----------

def _thumb(d, cx, cy, r):
    P = lambda *v: tuple(int(a) for a in v)
    d.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill=(32, 120, 243))
    k = r / 20
    d.rectangle(P(cx - 11 * k, cy - 2 * k, cx - 6 * k, cy + 10 * k), fill="white")
    d.rounded_rectangle(P(cx - 4 * k, cy - 3 * k, cx + 10 * k, cy + 10 * k), int(3 * k), fill="white")
    d.polygon(P(cx - 4 * k, cy - k, cx + k, cy - 12 * k, cx + 5 * k, cy - 11 * k, cx + 3 * k, cy - 2 * k),
              fill="white")


def _heart(d, cx, cy, r):
    P = lambda *v: tuple(int(a) for a in v)
    d.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill=(243, 62, 88))
    k = r / 20
    d.ellipse(P(cx - 10 * k, cy - 8 * k, cx, cy + 2 * k), fill="white")
    d.ellipse(P(cx, cy - 8 * k, cx + 10 * k, cy + 2 * k), fill="white")
    d.polygon(P(cx - 10 * k, cy - 2 * k, cx + 10 * k, cy - 2 * k, cx, cy + 10 * k), fill="white")


def comments_panel(top, reactions="247", comment_count="18 komentarų", comments=()):
    """Balta įrašo apačia: reakcijos, mygtukai ir komentarai (vardai anonimizuoti)."""
    c = Image.new("RGB", (W * SS, H * SS), "white")
    d = ImageDraw.Draw(c)
    S = lambda *v: tuple(int(a * SS) for a in v)
    y = top
    _heart(d, 84 * SS, (y + 42) * SS, 20 * SS)
    d.ellipse(S(26, y + 20, 72, y + 66), fill="white")
    _thumb(d, 49 * SS, (y + 43) * SS, 20 * SS)
    d.text(S(118, y + 43), str(reactions), font=font("Regular", 29 * SS), fill=(100, 100, 105), anchor="lm")
    d.text(S(1050, y + 43), comment_count, font=font("Regular", 29 * SS), fill=(100, 100, 105), anchor="rm")
    d.line(S(30, y + 86, 1050, y + 86), fill=(228, 228, 232), width=2 * SS)
    for i, t in enumerate(["Patinka", "Komentuoti", "Bendrinti"]):
        d.text(S(180 + i * 360, y + 128), t, font=font("Medium", 30 * SS), fill=(95, 95, 100), anchor="mm")
    d.line(S(30, y + 170, 1050, y + 170), fill=(228, 228, 232), width=2 * SS)
    cy = y + 200
    f_text, f_small = font("Regular", 29 * SS), font("Medium", 23 * SS)
    for i, (text, when, likes) in enumerate(comments):
        if cy + 120 > H:
            break
        col = AVATAR_COLORS[i % len(AVATAR_COLORS)]
        d.ellipse(S(30, cy, 100, cy + 70), fill=col)
        d.text(S(65, cy + 35), "ALGRMS"[i % 6], font=font("Bold", 30 * SS), fill="white", anchor="mm")
        tw = min(d.textlength(text, font=f_text) / SS, 860)
        d.rounded_rectangle(S(118, cy - 4, 118 + tw + 44, cy + 92), 26 * SS, fill=(240, 242, 245))
        d.rounded_rectangle(S(140, cy + 12, 260, cy + 34), 8 * SS, fill=(205, 208, 214))   # vardo vieta
        d.text(S(140, cy + 46), text, font=f_text, fill=(40, 40, 45))
        d.text(S(140, cy + 104), f"{when}   Patinka   Atsakyti".strip(), font=f_small, fill=(125, 125, 130))
        if str(likes).strip() not in ("", "0"):
            bx = 118 + tw + 14
            d.rounded_rectangle(S(bx, cy + 72, bx + 82, cy + 108), 18 * SS, fill="white",
                                outline=(225, 225, 230), width=SS)
            _thumb(d, (bx + 20) * SS, (cy + 90) * SS, 13 * SS)
            d.text(S(bx + 40, cy + 90), str(likes), font=font("Regular", 22 * SS), fill=(90, 90, 95),
                   anchor="lm")
        cy += 145
    return c.resize((W, H), Image.LANCZOS)


class Layout:
    """Kur kerpama nuotrauka ir kur yra ranka – nustatoma iš pirmo kadro ir nekeičiama."""

    def __init__(self, size, quad, comments, reactions, comment_count):
        self.k = W / size[0]
        cx, cy = quad[:, 0].mean(), quad[:, 1].mean()
        ph = quad[:, 1].max() - quad[:, 1].min()
        # nuotraukos kraštas kerta apatinę telefono dalį
        self.border = int(min(size[1] * 0.75, cy + 0.15 * ph))
        self.border = max(self.border, int(size[1] * 0.35))
        self.ph_px = int(self.border * self.k)
        self.anchor = (cx, cy)
        self.panel = comments_panel(self.ph_px, reactions, comment_count, comments)
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).rectangle((0, self.ph_px, W, H), fill=255)
        self.below = sh

    def compose(self, img, mask, scale=1.12, reveal=1.0):
        c = self.panel.copy()
        top = img.crop((0, 0, img.width, self.border)).resize((W, self.ph_px), Image.LANCZOS)
        c.paste(top, (0, 0))
        k = self.k * scale
        layer = img.convert("RGB").copy()
        layer.putalpha(mask)
        a = layer.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
        ax = int(self.anchor[0] * self.k - self.anchor[0] * k)
        ay = int(self.anchor[1] * self.k - self.anchor[1] * k)
        m = a.getchannel("A")
        if reveal < 1:     # ranka dar nuotraukos viduje – rodoma tik iki tam tikros eilutės
            lim = self.ph_px + int(reveal * (H - self.ph_px))
            g = Image.new("L", a.size, 255)
            gd = ImageDraw.Draw(g)
            for i in range(40):
                yy = lim - ay - i
                if 0 <= yy < a.height:
                    gd.line((0, yy, a.width, yy), fill=int(255 * i / 40))
            if lim - ay < a.height:
                gd.rectangle((0, max(0, lim - ay), a.width, a.height), fill=0)
            m = ImageChops.multiply(m, g)
        sh = Image.new("L", (W, H), 0)
        sh.paste(m.point(lambda v: int(v * 0.45)), (ax + 26, ay + 40))
        c.paste((0, 0, 0), (0, 0), ImageChops.multiply(sh.filter(ImageFilter.GaussianBlur(26)), self.below))
        c.paste(a, (ax, ay), m)
        return c


# ---------- Rezultatai ----------

class NoGreenScreen(Exception):
    pass


def prepare(img, screen):
    out, pmask, quad = replace_screen(img, screen)
    if pmask is None:
        raise NoGreenScreen("Nuotraukoje nerastas telefonas su žaliu ekranu.")
    return out, hand_mask(out, pmask, quad), quad


def _encoder(path, fps):
    return subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-movflags", "+faststart", path], stdin=subprocess.PIPE)


def make_from_photo(photo, screen, comments, reactions="247", comment_count="18 komentarų",
                    still_path=None, video_path=None, seconds=6.0, fps=30, progress=None):
    """Iš nuotraukos: paveikslėlis ir (pasirinktinai) animuotas video be AI."""
    img, mask, quad = prepare(photo.convert("RGB"), screen)
    lay = Layout(img.size, quad, comments, reactions, comment_count)
    if still_path:
        lay.compose(img, mask, 1.12).save(still_path)
    if video_path:
        enc = _encoder(video_path, fps)
        n = int(seconds * fps)
        for f in range(n):
            t = f / fps
            u = max(0.0, t - 0.8)
            if t < 0.8:
                s, rv = 1.0, 0.0
            else:
                s = 1.0 + 0.13 * (1 - math.exp(-4.5 * u) * math.cos(4.0 * u))   # spyruokliškas judesys
                rv = 1 - (1 - min(1.0, u / 0.7)) ** 2
            if t > 2.2:
                s += 0.012 * math.sin(2 * math.pi * (t - 2.2) / 2.5)
            enc.stdin.write(lay.compose(img, mask, s, rv).tobytes())
            if progress:
                progress((f + 1) / n)
        enc.stdin.close()
        enc.wait()


def make_from_video(src, screen, comments, out_path, reactions="247", comment_count="18 komentarų",
                    progress=None):
    """Efektas kiekvienam video kadrui (pvz. AI sugeneruotam video)."""
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height,avg_frame_rate,nb_frames", "-of", "csv=p=0", src],
                          capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h = int(info[0]), int(info[1])
    num, den = info[2].split("/")
    fps = round(int(num) / int(den)) if int(den) else 24
    total = int(info[3]) if len(info) > 3 and info[3].isdigit() else 0
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", src, "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = _encoder(out_path, fps)
    lay, last_quad, f = None, None, 0
    while True:
        buf = dec.stdout.read(w * h * 3)
        if len(buf) < w * h * 3:
            break
        frame = Image.frombuffer("RGB", (w, h), buf)
        img, pmask, quad = replace_screen(frame, screen)
        if pmask is None and last_quad is not None:   # ekranas trumpam neaptiktas – imame ankstesnį
            img, pmask, quad = replace_screen(frame, screen, last_quad)
        if pmask is None:
            if lay is None:
                continue   # kol telefonas nepasirodė, kadrų neturime kur dėti
            mask = Image.new("L", img.size, 0)
        else:
            mask = hand_mask(img, pmask, quad)
            last_quad = quad
        if lay is None:
            lay = Layout(img.size, quad, comments, reactions, comment_count)
        enc.stdin.write(lay.compose(img, mask, 1.1).tobytes())
        f += 1
        if progress and total:
            progress(min(1.0, f / total))
    dec.wait()
    enc.stdin.close()
    enc.wait()
    if lay is None:
        raise NoGreenScreen("Video nerastas telefonas su žaliu ekranu.")


# ---------- AI video (fal.ai, Kling) ----------

FAL_MODEL = "fal-ai/kling-video/v2.1/standard/image-to-video"


def generate_ai_video(photo_bytes, prompt, fal_key, duration="5", status=None, timeout=900):
    """Nuotrauka + užklausa -> video (mp4 baitai) per fal.ai Kling modelį."""
    import requests
    headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}
    img = Image.open(_bytes_io(photo_bytes)).convert("RGB")
    img.thumbnail((1536, 1536))
    buf = _bytes_io()
    img.save(buf, "JPEG", quality=92)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    r = requests.post(f"https://queue.fal.run/{FAL_MODEL}", headers=headers, timeout=60,
                      json={"prompt": prompt, "image_url": data_uri, "duration": str(duration),
                            "negative_prompt": "blur, distort, low quality, text, watermark"})
    r.raise_for_status()
    job = r.json()
    status_url, response_url = job["status_url"], job["response_url"]
    start = time.time()
    while time.time() - start < timeout:
        s = requests.get(status_url, headers=headers, timeout=30).json()
        state = s.get("status")
        if status:
            status(state, time.time() - start)
        if state == "COMPLETED":
            break
        if state in ("FAILED", "ERROR"):
            raise RuntimeError(f"AI video nepavyko: {s}")
        time.sleep(5)
    else:
        raise TimeoutError("AI video generavimas užtruko per ilgai.")
    res = requests.get(response_url, headers=headers, timeout=60).json()
    url = (res.get("video") or {}).get("url")
    if not url:
        raise RuntimeError(f"AI atsakyme nėra video: {res}")
    return requests.get(url, timeout=300).content


def _bytes_io(data=None):
    import io
    return io.BytesIO(data) if data is not None else io.BytesIO()


DEFAULT_COMMENTS = [("Ar galima automatizuoti sąskaitų išrašymą?", "15 min.", "12"),
                    ("Ar tinka mažam verslui su keliais darbuotojais?", "32 min.", "8"),
                    ("Kiek laiko užtrunka viską sujungti?", "1 val.", "5")]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("out_png")
    ap.add_argument("--video", help="taip pat sukurti animuotą video (be AI)")
    ap.add_argument("--from-video", help="uždėti efektą šiam video (pvz. AI sugeneruotam)")
    a = ap.parse_args()
    scr = render_screen()
    if a.from_video:
        make_from_video(a.from_video, scr, DEFAULT_COMMENTS, a.out_png)
    else:
        make_from_photo(Image.open(a.photo), scr, DEFAULT_COMMENTS, still_path=a.out_png, video_path=a.video)
