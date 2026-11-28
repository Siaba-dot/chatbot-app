"""Reels studijos API serveris (1 etapas) – būsimos naršyklės programos (React) pagrindas.

Paleidimas:  uvicorn api.server:app --host 0.0.0.0 --port 8000
Dokumentacija naršyklėje: /api/docs

Prisijungimas – tie patys klientai kaip studijoje (secrets.toml [users.*]). Projektai saugomi
REELS_DATA_DIR/projects/<naudotojas>/<projektas>/ (project.json + įkelti failai + sukurti video), todėl
išlieka ir perkrovus serverį – tai „Mano projektų“ pagrindas.
"""
import base64
import hashlib
import hmac
import json
import os
import pickle
import re
import secrets as _secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import accounts  # noqa: E402
import clips_ui  # noqa: E402
import engine  # noqa: E402
import reels_studio  # noqa: E402
import video_editor  # noqa: E402

DATA = accounts.DATA_DIR
PROJECTS = os.path.join(DATA, "projects")
TOKEN_DAYS = 30
MAX_UPLOAD = int(os.environ.get("REELS_MAX_UPLOAD_MB", "450")) * 1024 * 1024
AI_PLANS = ("premium", "admin")

app = FastAPI(title="Reels montavimo studija API", version="1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None)
_jobs = {}
_jobs_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=int(os.environ.get("REELS_API_WORKERS", "2")))


# ---------- prisijungimas ----------
def _secret():
    path = os.path.join(DATA, "api_secret")
    if os.environ.get("REELS_API_SECRET"):
        return os.environ["REELS_API_SECRET"].encode()
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        os.makedirs(DATA, exist_ok=True)
        key = _secrets.token_bytes(32)
        with open(path, "wb") as f:
            f.write(key)
        os.chmod(path, 0o600)
        return key


def make_token(username):
    body = base64.urlsafe_b64encode(json.dumps({"u": username, "exp": int(time.time()) + TOKEN_DAYS * 86400})
                                    .encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_token(token):
    try:
        body, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return data["u"] if data["exp"] > time.time() else None
    except Exception:
        return None


def _user_info(username):
    cfg = accounts.users().get(username)
    if not cfg or cfg.get("active", True) is False:
        return None
    plan = accounts.effective_plan(cfg)
    minutes = None if plan == "admin" else float(cfg.get("minutes", accounts.DEFAULT_MINUTES))
    left = None if minutes is None else max(0.0, minutes - accounts.used_minutes(username))
    return {"username": username, "name": cfg.get("name") or username, "plan": plan,
            "plan_title": accounts.PLANS[plan] + (" 🎁 bandymas" if accounts.in_trial(cfg) else ""), "ai": plan in AI_PLANS and bool(clips_ui.configured_key()),
            "pexels": bool(stock_provider()), "stock": STOCK.get(stock_provider() or "", ""),
            "gemini": plan in AI_PLANS and bool(stock_key("gemini")),
            "veo": plan in AI_PLANS and bool(stock_key("gemini")),
            "minutes_left": left,
            "ai_clips_left": accounts.left(username, "ai_clips"),
            "voice_chars_left": accounts.left(username, "voice_chars"),
            "auto_videos_left": accounts.left(username, "auto_videos"),
            "limits": accounts.limits_for(username), "contact": app_settings()["contact"],
            "billing": app_settings()["billing"] and username in accounts.managed_users(),
            "subscribed": bool((accounts.managed_users().get(username) or {}).get("stripe_subscription")),
            "price_label": app_settings().get("price_label", ""),
            "trial_until": cfg.get("trial_until") if accounts.in_trial(cfg) else None}


def current_user(authorization: str = Header(None), token: str = Query(None)):
    """Žetonas – „Authorization: Bearer …“ arba ?token=… (video žymei <video src>)."""
    raw = (authorization or "").removeprefix("Bearer ").strip() or (token or "")
    username = read_token(raw) if raw else None
    user = _user_info(username) if username else None
    if not user:
        raise HTTPException(401, "Prisijunkite iš naujo")
    return user


def openai_client(user):
    if user["plan"] not in AI_PLANS:
        return None
    key = clips_ui.configured_key()
    if not key:
        return None
    import openai
    return openai.OpenAI(api_key=key)


class Login(BaseModel):
    username: str
    password: str


# ---------- 📝 Savarankiška registracija ----------
def app_settings():
    """Administratoriaus nustatymai: registracija (įjungta / išjungta), kontaktas Premium planui."""
    try:
        with open(os.path.join(DATA, "app_settings.json"), encoding="utf-8") as f:
            st_ = json.load(f)
    except (OSError, ValueError):
        st_ = {}
    out = {"registration": st_.get("registration", True), "contact": st_.get("contact") or accounts.contact()}
    for k in SETTINGS_TEXT:
        out[k] = st_.get(k, "")
    try:
        out["trial_days"] = max(0, min(60, int(st_.get("trial_days", 7))))
    except (TypeError, ValueError):
        out["trial_days"] = 7
    out["mail"] = bool(stock_key("brevo") and out.get("mail_from"))
    out["billing"] = bool(stock_key("stripe") and out.get("stripe_price"))
    return out


# Tekstiniai administratoriaus nustatymai: veiklos duomenys (taisyklėms), el. laiškų siuntėjas, Stripe kaina
SETTINGS_TEXT = ("biz_name", "biz_code", "biz_address", "biz_email", "mail_from", "mail_name",
                 "stripe_price", "price_label")


@app.get("/api/public/settings")
def public_settings():
    return dict(app_settings(), limits=accounts.DEFAULT_LIMITS, minutes=accounts.DEFAULT_MINUTES)


class SettingsAdmin(BaseModel):
    registration: bool | None = None
    trial_days: int | None = None
    contact: str | None = None
    biz_name: str | None = None
    biz_code: str | None = None
    biz_address: str | None = None
    biz_email: str | None = None
    mail_from: str | None = None
    mail_name: str | None = None
    stripe_price: str | None = None
    price_label: str | None = None


@app.put("/api/admin/settings")
def admin_settings(body: SettingsAdmin, user=Depends(current_user)):
    if user["plan"] != "admin":
        raise HTTPException(403, "Tik administratoriui")
    cur = app_settings()
    if body.registration is not None:
        cur["registration"] = body.registration
    if body.contact is not None:
        cur["contact"] = body.contact.strip()[:200]
    if body.trial_days is not None:
        cur["trial_days"] = max(0, min(60, int(body.trial_days)))
    for k in SETTINGS_TEXT:
        v = getattr(body, k)
        if v is not None:
            cur[k] = v.strip()[:300]
    os.makedirs(DATA, exist_ok=True)
    keep = {k: cur[k] for k in ("registration", "contact", "trial_days", *SETTINGS_TEXT)}
    with open(os.path.join(DATA, "app_settings.json"), "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False)
    return app_settings()


class RegisterBody(BaseModel):
    name: str
    email: str
    password: str
    consent: bool = False   # sutikimas su taisyklėmis ir privatumo politika
    website: str = ""  # „medaus puodas“ robotams – žmonės šio lauko nemato


_reg_log = {}


@app.post("/api/register")
def register(body: RegisterBody, request: Request):
    if not app_settings()["registration"]:
        raise HTTPException(403, "Registracija šiuo metu išjungta – kreipkitės į studijos administratorių.")
    ip = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _reg_log.get(ip, []) if now - t < 3600]
    if body.website or len(recent) >= 5:
        time.sleep(1.0)
        raise HTTPException(429, "Per daug bandymų – pabandykite vėliau.")
    email = body.email.strip().lower()
    if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", email) or len(email) > 80:
        raise HTTPException(400, "Įrašykite tikrą el. pašto adresą.")
    if len(body.password) < 8:
        raise HTTPException(400, "Slaptažodis – bent 8 simboliai.")
    if not body.name.strip():
        raise HTTPException(400, "Įrašykite savo vardą arba įmonės pavadinimą.")
    if not body.consent:
        raise HTTPException(400, "Pažymėkite, kad sutinkate su taisyklėmis ir privatumo politika.")
    if email in accounts.users():
        raise HTTPException(400, "Šis el. paštas jau užregistruotas – prisijunkite.")
    managed = accounts.managed_users()
    days = app_settings()["trial_days"]
    managed[email] = {"plan": "basic", "name": body.name.strip()[:80], "email": email, "created": now,
                      "self_registered": True, "consent": now, "password_hash": accounts.hash_password(body.password)}
    if days:  # 🎁 nemokamas Premium bandymas, vėliau – automatiškai Pagrindinis planas
        managed[email]["trial_until"] = now + days * 86400
    accounts.save_managed_users(managed)
    _reg_log[ip] = recent + [now]
    st_ = app_settings()
    if st_["mail"]:  # sveikinimas klientui ir žinutė administratorei
        _mail_bg(email, "Sveiki atvykę į Reels montavimo studiją ✨",
                 f"<p>Sveiki, {_esc(body.name.strip())},</p><p>jūsų paskyra sukurta. Prisijungimo vardas – "
                 f"<b>{_esc(email)}</b>.</p>" + (
                     f"<p>🎁 <b>{days} dienas Premium – nemokamai:</b> išbandykite AI titrus iš kalbos, natūralius "
                     "lietuviškus AI balsus ir AI kadrus. Po bandymo paskyra lieka su nemokamu Pagrindiniu planu – "
                     "niekas automatiškai nenuskaičiuojama.</p>" if days else
                     "<p>Jūsų planas – <b>Pagrindinis</b>. AI funkcijos (titrai iš kalbos, "
                     "lietuviški AI balsai, AI kadrai) – Premium plane.</p>"))
        if st_.get("biz_email"):
            _mail_bg(st_["biz_email"], f"Nauja registracija: {body.name.strip()[:60]}",
                     f"<p>Užsiregistravo naujas klientas: <b>{_esc(body.name.strip())}</b> ({_esc(email)}).</p>")
    return {"token": make_token(email), "user": _user_info(email)}


@app.post("/api/login")
def login(body: Login):
    name = accounts.check_password(body.username, body.password)
    if not name:
        time.sleep(1.0)  # lėtina slaptažodžių spėliojimą
        raise HTTPException(401, "Neteisingas prisijungimo vardas arba slaptažodis")
    return {"token": make_token(name), "user": _user_info(name)}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


# ---------- administravimas ----------
def admin_user(user=Depends(current_user)):
    if user["plan"] != "admin":
        raise HTTPException(403, "Tik administratoriui")
    return user


@app.get("/api/admin/openai")
def openai_status(user=Depends(admin_user)):
    k = clips_ui.configured_key()
    return {"set": bool(k), "tail": k[-4:] if k else ""}


class KeyBody(BaseModel):
    key: str


@app.post("/api/admin/openai")
def openai_save(body: KeyBody, user=Depends(admin_user)):
    """Raktas patikrinamas ir išsaugomas serveryje (tas pats failas kaip senosios studijos administravime)."""
    key = body.key.strip()
    if key:
        if not key.startswith("sk-"):
            raise HTTPException(400, "Raktas turi prasidėti „sk-“")
        try:
            import openai
            openai.OpenAI(api_key=key).models.list()
        except Exception as e:
            raise HTTPException(400, f"Raktas neveikia ({type(e).__name__}) – patikrinkite, ar nukopijavote visą.")
    clips_ui.save_key(key)
    return openai_status(user)


# ---------- 🎞 Nemokami video intarpai: Pexels arba Pixabay ----------
STOCK = {"pexels": "Pexels", "pixabay": "Pixabay"}


def stock_key(provider):
    env = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY", "gemini": "GEMINI_API_KEY",
           "brevo": "BREVO_API_KEY", "stripe": "STRIPE_SECRET_KEY", "stripe_whsec": "STRIPE_WEBHOOK_SECRET"}[provider]
    if os.environ.get(env):
        return os.environ[env].strip()
    try:
        with open(os.path.join(DATA, provider + "_key"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def pexels_key():  # suderinamumui
    return stock_key("pexels")


def stock_provider():
    """Kuris šaltinis naudojamas: Pexels (jei yra raktas), kitaip Pixabay. None – nė vieno."""
    return next((p for p in STOCK if stock_key(p)), None)


def _http_json(url, headers=None, what="Šaltinis"):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "ReelsStudija/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        code = getattr(e, "code", None)
        if code in (400, 401, 403):
            raise HTTPException(400, f"{what} raktas neveikia – patikrinkite, ar nukopijavote visą.")
        raise HTTPException(502, f"{what} nepasiekiamas ({e})")


def _pexels(path, params=None, key=None):
    import urllib.parse
    key = key or stock_key("pexels")
    if not key:
        raise HTTPException(400, "Pexels raktas neįrašytas.")
    return _http_json("https://api.pexels.com" + path + ("?" + urllib.parse.urlencode(params) if params else ""),
                      {"Authorization": key}, "Pexels")


def _pixabay(params, key=None):
    import urllib.parse
    key = key or stock_key("pixabay")
    if not key:
        raise HTTPException(400, "Pixabay raktas neįrašytas.")
    return _http_json("https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": key, **params}),
                      what="Pixabay")


def _orientation(fmt):
    return {"16:9": "landscape", "1:1": "square"}.get(fmt, "portrait")


def _pexels_brief(v):
    return {"provider": "pexels", "id": v["id"], "image": v.get("image"), "duration": v.get("duration"),
            "width": v.get("width"), "height": v.get("height"), "user": (v.get("user") or {}).get("name", ""),
            "url": v.get("url")}


def _pixabay_files(v):
    return [dict(f, quality=q) for q, f in (v.get("videos") or {}).items() if f and f.get("url") and f.get("width")]


def _pixabay_brief(v):
    files = _pixabay_files(v)
    big = max(files, key=lambda f: f["width"] * f["height"]) if files else {}
    thumb = next((f.get("thumbnail") for q in ("medium", "small", "tiny", "large")
                  for f in [(v.get("videos") or {}).get(q) or {}] if f.get("thumbnail")), None)
    if not thumb and v.get("picture_id"):
        thumb = f"https://i.vimeocdn.com/video/{v['picture_id']}_295x166.jpg"
    return {"provider": "pixabay", "id": v["id"], "image": thumb, "duration": v.get("duration"),
            "width": big.get("width"), "height": big.get("height"), "user": v.get("user", ""),
            "url": v.get("pageURL"), "likes": v.get("likes") or 0, "downloads": v.get("downloads") or 0}


def stock_search(q, fmt="9:16", page=1, per_page=18, provider=None):
    provider = provider or stock_provider()
    if not provider:
        raise HTTPException(400, "Video intarpų raktas neįrašytas (administratorius: „Mano projektai“).")
    if provider == "pexels":
        j = _pexels("/videos/search", {"query": q[:80], "orientation": _orientation(fmt), "per_page": per_page,
                                       "page": max(1, min(page, 20)), "size": "medium"})
        vids = [_pexels_brief(v) for v in j.get("videos", [])]
    else:  # Pixabay neturi orientacijos filtro – tinkamos formos video rodom pirmus
        j = _pixabay({"q": q[:80], "per_page": max(3, min(per_page, 200)), "page": max(1, min(page, 20)),
                      "safesearch": "true", "video_type": "film"})  # be animacijų – tik tikri kadrai
        vids = [_pixabay_brief(v) for v in j.get("hits", [])]
        want = _orientation(fmt)
        shape = lambda v: ("portrait" if (v["height"] or 0) > (v["width"] or 0) * 1.1 else  # noqa: E731
                           "landscape" if (v["width"] or 0) > (v["height"] or 0) * 1.1 else "square")
        vids.sort(key=lambda v: shape(v) != want)
    return [v for v in vids if (v.get("duration") or 0) >= 2]


def stock_download(user, pid, provider, vid, fmt):
    """Parsisiunčia tinkamiausią failą (~1080p, ne didesnį nei reikia) į projektą. Grąžina (kelias, aprašas)."""
    import urllib.request
    target = 1920 if fmt in ("9:16", "16:9") else 1350
    if provider == "pixabay":
        hits = _pixabay({"id": int(vid)}).get("hits") or []
        if not hits:
            raise HTTPException(404, "Šio video nerasta")
        v = hits[0]
        files = [{"link": f["url"], "width": f["width"], "height": f["height"]} for f in _pixabay_files(v)]
        brief = _pixabay_brief(v)
    else:
        v = _pexels(f"/videos/videos/{int(vid)}")
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")
                 and f.get("width") and f.get("height")]
        brief = _pexels_brief(v)
    if not files:
        raise HTTPException(404, "Šio video failo nerasta")
    files.sort(key=lambda f: (max(f["width"], f["height"]) > 2200, abs(max(f["width"], f["height"]) - target)))
    d = os.path.join(_pdir(user, pid), "broll")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{provider[:2]}{int(vid)}.mp4")
    if not os.path.exists(path):
        req = urllib.request.Request(files[0]["link"], headers={"User-Agent": "ReelsStudija/1.0"})
        tmp = path + ".part"
        with urllib.request.urlopen(req, timeout=90) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        os.replace(tmp, path)
    return path, brief


def _brevo_check(key):
    """Brevo rakto patikra. Ribotas (Restricted) raktas su tik „Transactional email“ teise
    neturi prieigos prie /account – tada tikrinam per transakcinių laiškų statistiką."""
    import urllib.request
    if not key.startswith("xkeysib-"):
        raise HTTPException(400, "Brevo API raktas prasideda „xkeysib-“. (SMTP raktas „xsmtpsib-“ netinka.)")
    msg = ""
    for url in ("https://api.brevo.com/v3/smtp/statistics/aggregatedReport",
                "https://api.brevo.com/v3/account"):
        req = urllib.request.Request(url, headers={"User-Agent": "ReelsStudija/1.0", "api-key": key,
                                                   "accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
            return
        except Exception as e:
            code = getattr(e, "code", None)
            if code is None:
                raise HTTPException(502, f"Brevo nepasiekiamas ({e})")
            try:
                msg = json.loads(e.read().decode()).get("message", "") or msg
            except Exception:
                pass
    low = msg.lower()
    if "ip" in low and ("unrecogni" in low or "authori" in low):
        raise HTTPException(400, "Brevo blokuoja serverio IP. Brevo: Security → Authorized IPs pridėkite "
                                 "2.31.169.169 arba išjunkite IP blokavimą. (" + msg + ")")
    raise HTTPException(400, "Brevo raktas neveikia" + (f": {msg}" if msg else "") +
                        ". Patikrinkite, ar nukopijavote visą raktą ir ar „Transactional email“ teisė – „All“.")


def _key_status(provider):
    k = stock_key(provider)
    return {"set": bool(k), "tail": k[-4:] if k else ""}


def _key_save(provider, key):
    key = key.strip()
    if key:  # patikrinam prieš išsaugant
        if provider == "gemini":
            _http_json("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                       {"x-goog-api-key": key}, "Google (Gemini)")
        elif provider == "brevo":
            _brevo_check(key)
        elif provider == "stripe":
            if not key.startswith(("sk_", "rk_")):
                raise HTTPException(400, "Stripe slaptasis raktas prasideda „sk_live_“ arba „sk_test_“.")
            _http_json("https://api.stripe.com/v1/balance", {"Authorization": "Bearer " + key}, "Stripe")
        elif provider == "stripe_whsec":
            if not key.startswith("whsec_"):
                raise HTTPException(400, "Webhook raktas prasideda „whsec_“.")
        elif provider == "pexels":
            _pexels("/videos/search", {"query": "nature", "per_page": 1}, key=key)
        else:
            _pixabay({"q": "nature", "per_page": 3}, key=key)
    path = os.path.join(DATA, provider + "_key")
    os.makedirs(DATA, exist_ok=True)
    if key:
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
        os.chmod(path, 0o600)
    elif os.path.exists(path):
        os.remove(path)
    return _key_status(provider)


@app.get("/api/admin/pexels")
def pexels_status(user=Depends(admin_user)):
    return _key_status("pexels")


@app.post("/api/admin/pexels")
def pexels_save(body: KeyBody, user=Depends(admin_user)):
    return _key_save("pexels", body.key)


@app.get("/api/admin/gemini")
def gemini_status(user=Depends(admin_user)):
    return _key_status("gemini")


@app.post("/api/admin/gemini")
def gemini_save(body: KeyBody, user=Depends(admin_user)):
    return _key_save("gemini", body.key)


# ---------- 👑 Klientų valdymas ----------
def _admin_row(name, cfg):
    plan = str(cfg.get("plan", "basic")).lower()
    lim = accounts.limits_for(name)
    return {"username": name, "name": cfg.get("name") or name, "plan": plan,
            "active": cfg.get("active", True) is not False, "source": cfg.get("source", "managed"),
            "minutes": None if plan == "admin" else float(cfg.get("minutes", accounts.DEFAULT_MINUTES)),
            "ai_clips": lim["ai_clips"], "voice_chars": lim["voice_chars"], "auto_videos": lim["auto_videos"],
            "used": {"minutes": round(accounts.used(name, "minutes"), 1), "ai_clips": int(accounts.used(name, "ai_clips")),
                     "voice_chars": int(accounts.used(name, "voice_chars")),
                     "auto_videos": int(accounts.used(name, "auto_videos"))},
            "created": cfg.get("created"), "email": cfg.get("email"), "self_registered": bool(cfg.get("self_registered")),
            "subscribed": bool(cfg.get("stripe_subscription")),
            "trial_until": cfg.get("trial_until") if accounts.in_trial(cfg) else None}


@app.get("/api/admin/users")
def admin_users(user=Depends(admin_user)):
    rows = [_admin_row(n, c) for n, c in accounts.users().items()]
    return {"users": sorted(rows, key=lambda r: (r["plan"] != "admin", r["username"])),
            "defaults": accounts.DEFAULT_LIMITS, "default_minutes": accounts.DEFAULT_MINUTES}


class UserBody(BaseModel):
    username: str | None = None
    name: str | None = None
    password: str | None = None
    plan: str | None = None
    active: bool | None = None
    minutes: float | None = None
    ai_clips: int | None = None
    voice_chars: int | None = None
    auto_videos: int | None = None


def _apply(cfg, body):
    if body.name is not None:
        cfg["name"] = body.name.strip()[:80]
    if body.plan is not None:
        if body.plan not in ("basic", "premium", "admin"):
            raise HTTPException(400, "Netinkamas planas")
        if body.plan != cfg.get("plan", "basic"):
            cfg.pop("trial_until", None)   # planą pakeitė administratorė – bandymas baigiasi
        cfg["plan"] = body.plan
    if body.active is not None:
        cfg["active"] = bool(body.active)
    for k in ("minutes", "ai_clips", "voice_chars", "auto_videos"):
        v = getattr(body, k)
        if v is not None:
            cfg[k] = max(0, v)
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "Slaptažodis – bent 8 simboliai")
        cfg["password_hash"] = accounts.hash_password(body.password)
        cfg.pop("password", None)
    return cfg


@app.post("/api/admin/users")
def admin_add_user(body: UserBody, user=Depends(admin_user)):
    name = (body.username or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._@+-]{2,79}", name):
        raise HTTPException(400, "Prisijungimo vardas: 3–40 mažųjų raidžių, skaičių, . _ @ -")
    if name in accounts.users():
        raise HTTPException(400, "Toks prisijungimo vardas jau yra")
    if not body.password:
        raise HTTPException(400, "Įveskite slaptažodį")
    managed = accounts.managed_users()
    managed[name] = _apply({"plan": "premium", "created": time.time()}, body)
    accounts.save_managed_users(managed)
    return _admin_row(name, dict(managed[name], source="managed"))


@app.put("/api/admin/users/{name}")
def admin_edit_user(name: str, body: UserBody, user=Depends(admin_user)):
    managed = accounts.managed_users()
    if name not in managed:
        raise HTTPException(400, "Šis klientas aprašytas serverio secrets.toml – jį keisti galima tik ten.")
    if name == user["username"] and (body.active is False or (body.plan and body.plan != "admin")):
        raise HTTPException(400, "Negalite išjungti ar pažeminti savęs")
    managed[name] = _apply(managed[name], body)
    accounts.save_managed_users(managed)
    return _admin_row(name, dict(managed[name], source="managed"))


@app.delete("/api/admin/users/{name}")
def admin_delete_user(name: str, user=Depends(admin_user)):
    managed = accounts.managed_users()
    if name not in managed:
        raise HTTPException(400, "Šis klientas aprašytas serverio secrets.toml – jį pašalinti galima tik ten.")
    managed.pop(name)
    accounts.save_managed_users(managed)
    return {"ok": True}  # kliento projektai serveryje lieka (jei sugrąžintumėte – viskas vietoje)


@app.get("/api/admin/models")
def admin_models(user=Depends(admin_user)):
    """Diagnostika: visi Google (Gemini) modeliai, kuriuos leidžia įrašytas raktas."""
    key = stock_key("gemini")
    if not key:
        raise HTTPException(400, "Google raktas neįrašytas")
    try:
        return {"models": engine.gemini_models(key)}
    except RuntimeError as e:
        raise HTTPException(502, str(e)[:300])


@app.get("/api/admin/pixabay")
def pixabay_status(user=Depends(admin_user)):
    return _key_status("pixabay")


@app.post("/api/admin/pixabay")
def pixabay_save(body: KeyBody, user=Depends(admin_user)):
    return _key_save("pixabay", body.key)


@app.get("/api/stock/search")
@app.get("/api/pexels/search")
def stock_search_api(q: str, fmt: str = "9:16", page: int = 1, user=Depends(current_user)):
    p = stock_provider()
    return {"videos": stock_search(q, fmt, page), "provider": p, "provider_name": STOCK.get(p, "")}


class BrollBody(BaseModel):
    pexels_id: int                  # video id šaltinyje
    provider: str | None = None     # pexels | pixabay (None – kuris įjungtas)
    t: float = 0.0
    d: float = 2.5
    query: str = ""
    as_clip: bool = False
    mode: str = "card"              # card | split | full
    pos: str = "auto"               # kortelės vieta: auto (be veido) | tl | tr


@app.post("/api/projects/{pid}/broll")
def add_broll(pid: str, body: BrollBody, user=Depends(current_user)):
    proj = _load(user, pid)
    provider = body.provider if body.provider in STOCK else stock_provider()
    if not provider:
        raise HTTPException(400, "Video intarpų raktas neįrašytas.")
    path, brief = stock_download(user, pid, provider, body.pexels_id, proj["settings"]["format"])
    proj = _load(user, pid)
    name = STOCK[provider]
    if body.as_clip:  # kaip įprastas įrašas (pvz. video be filmavimo: kadrai + AI įgarsinimas)
        clip_path = os.path.join(_pdir(user, pid), "clips", f"{provider[:2]}{body.pexels_id}_{uuid.uuid4().hex[:4]}.mp4")
        os.makedirs(os.path.dirname(clip_path), exist_ok=True)
        shutil.copy(path, clip_path)
        clip = engine.add_clip(clip_path, f"{name} · {brief['user'] or body.pexels_id}")
        clip["id"] = uuid.uuid4().hex[:10]
        clip["audio"] = "none" if clip["audio"] != "speech" else clip["audio"]
        proj["clips"].append(clip)
        proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    else:
        proj.setdefault("broll", []).append({
            "id": uuid.uuid4().hex[:8], "provider": provider, "pexels_id": body.pexels_id,
            "t": round(max(0.0, body.t), 2), "d": round(max(1.0, min(6.0, body.d)), 2), "query": body.query[:60],
            "mode": body.mode if body.mode in engine.BROLL_MODES else "card",
            "pos": body.pos if body.pos in ("auto", "tl", "tr") else "auto",
            "image": brief["image"], "user": brief["user"], "url": brief["url"], "path": path})
        proj["broll"].sort(key=lambda b: b["t"])
    _save(user, proj)
    return _public(proj)


class BrollEdit(BaseModel):
    t: float | None = None
    d: float | None = None
    mode: str | None = None
    pos: str | None = None


@app.put("/api/projects/{pid}/broll/{bid}")
def edit_broll(pid: str, bid: str, body: BrollEdit, user=Depends(current_user)):
    proj = _load(user, pid)
    for b in proj.get("broll", []):
        if b["id"] == bid:
            if body.t is not None:
                b["t"] = round(max(0.0, body.t), 2)
            if body.d is not None:
                b["d"] = round(max(1.0, min(6.0, body.d)), 2)
            if body.mode in engine.BROLL_MODES:
                b["mode"] = body.mode
            if body.pos in ("auto", "tl", "tr"):
                b["pos"] = body.pos
    proj["broll"].sort(key=lambda b: b["t"])
    _save(user, proj)
    return _public(proj)


@app.delete("/api/projects/{pid}/broll/{bid}")
def delete_broll(pid: str, bid: str, user=Depends(current_user)):
    proj = _load(user, pid)
    proj["broll"] = [b for b in proj.get("broll", []) if b["id"] != bid]
    _save(user, proj)
    return _public(proj)


@app.post("/api/projects/{pid}/broll/auto")
def auto_broll(pid: str, mode: str = "card", user=Depends(current_user)):
    """AI pagal tai, ką sakote, parenka 3–4 momentus ir nemokamus video kadrus jiems."""
    proj = _load(user, pid)
    client = openai_client(user)
    if client is None:
        raise HTTPException(400, "Automatiniams intarpams reikia AI (Premium). Galite ieškoti ir įterpti ranka.")
    if not proj.get("words"):
        raise HTTPException(400, "Pirmiausia paruoškite titrus (💬 Titrai → Paruošti titrus).")
    provider = stock_provider()
    if not provider:
        raise HTTPException(400, "Video intarpų raktas neįrašytas.")
    lines = " ".join(f"[{a:.1f}] {video_editor.plain(w)}" for w, a, _ in proj["words"][:300])
    end = proj["words"][-1][2]
    j = reels_studio._ai_json(client, (
        "You pick B-roll cutaways for a short talking video. From the timed transcript choose 3-4 moments (not in the "
        "first 2.5 s, at least 4 s apart) where a stock video would illustrate what is said. For each give an "
        "English stock-video search query of 1-3 concrete, visual words (e.g. 'winter tires', 'coffee'), "
        "duration 2-3.5 s. Reply only JSON: {\"broll\": [{\"time\": 0, \"duration\": 2.5, \"query\": \"...\"}]}"),
        {"transcript": lines})
    used = {(b.get("provider", "pexels"), b["pexels_id"]) for b in proj.get("broll", [])}
    added = 0
    for it in (j.get("broll") or [])[:4]:
        try:
            t, dur, q = float(it["time"]), float(it.get("duration", 2.5)), str(it["query"])[:60]
        except (KeyError, TypeError, ValueError):
            continue
        if not (1.5 <= t <= end - 1.0):
            continue
        res = stock_search(q, proj["settings"]["format"], 1, 8, provider)
        cand = [v for v in res if (provider, v["id"]) not in used and (v.get("duration") or 0) >= 3]
        if not cand:
            continue
        used.add((provider, cand[0]["id"]))
        add_broll(pid, BrollBody(pexels_id=cand[0]["id"], provider=provider, t=t, d=min(dur, end - t), query=q,
                                 mode=mode if mode in engine.BROLL_MODES else "card"), user)
        added += 1
    proj = _load(user, pid)
    if not added:
        raise HTTPException(404, "Tinkamų intarpų nerasta – pabandykite ieškoti ranka.")
    return _public(proj)


# ---------- 🎬 Google Veo: AI sukurti intarpai ----------
class VeoBody(BaseModel):
    prompt: str
    t: float = 0.0
    d: float = 3.0
    mode: str = "card"
    pos: str = "auto"
    as_clip: bool = False
    replace: str | None = None   # kadro id: automatiškai parinktą vaizdą pakeisti AI sukurtu


def _veo_prompt_en(client, prompt):
    """Veo geriausiai supranta angliškai – aprašymas išverčiamas (jei yra AI), kitaip siunčiamas kaip yra."""
    if client is None or re.fullmatch(r"[\x00-\x7F]+", prompt):
        return prompt
    try:
        j = reels_studio._ai_json(client, (
            "Translate this stock-video shot description to concise, vivid English for a text-to-video model "
            "(one sentence, concrete visuals, camera and light). Reply only JSON: {\"en\": \"...\"}"),
            {"text": prompt})
        return str(j.get("en") or prompt)[:500]
    except Exception:
        return prompt


VEO_HQ = True  # AI kadrai – geresnės kokybės Google modeliu (1080p, iki 8 s)


def _run_veo(jid, user, pid, body):
    try:
        key = stock_key("gemini")
        proj = _load(user, pid)
        fmt = proj["settings"]["format"]
        prompt = _veo_prompt_en(openai_client(user), body.prompt)
        d = os.path.join(_pdir(user, pid), "broll")
        os.makedirs(d, exist_ok=True)
        vid = uuid.uuid4().hex[:8]
        path = os.path.join(d, f"veo_{vid}.mp4")
        _job_update(jid, progress=0.05)
        engine.veo_generate(key, prompt, "16:9" if fmt == "16:9" else "9:16", path, hq=VEO_HQ,
                            status=lambda m: _job_update(jid, message=m, progress=0.15))
        _job_update(jid, message="Dedu kadrą į projektą…", progress=0.9)  # sustabdžius – čia nutrūksta
        thumb = path + ".thumb.jpg"
        reels_studio.grab_frame(path, thumb, at=1.0)
        accounts.add_usage(user["username"], "ai_clips", 1)
        _library_add(user, path, body.prompt, fmt)  # 📚 kad būtų galima naudoti ir kituose Reels'uose
        proj = _load(user, pid)
        old = next((c for c in proj["clips"] if c["id"] == body.replace), None) if body.replace else None
        if old is not None:  # scenos vaizdas -> AI kadras (ta pati vieta, tas pats ilgis kiek įmanoma)
            want = (old["trim"][1] - old["trim"][0]) if old.get("trim") else old["duration"]
            cpath = os.path.join(_pdir(user, pid), "clips", old["id"] + "_ai.mp4")
            os.makedirs(os.path.dirname(cpath), exist_ok=True)
            if engine._ffmpeg(["-i", path, "-an", "-c:v", "copy", cpath]).returncode != 0:  # be AI garso
                shutil.copy(path, cpath)
            clip = engine.add_clip(cpath, "✨ AI · " + body.prompt[:40])
            clip.update(id=old["id"], scene=old.get("scene"), visual=old.get("visual"), query=old.get("query"),
                        ai_scene=True)
            if want < clip["duration"] - 0.05:
                clip["trim"] = [0.0, round(want, 3)]
            if old.get("sound"):
                clip["sound"] = old["sound"]
            if old.get("auto") and old["path"].startswith(_pdir(user, pid)) and os.path.exists(old["path"]):
                os.unlink(old["path"])
            proj["clips"] = [clip if c["id"] == old["id"] else c for c in proj["clips"]]
            proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
        elif body.as_clip:
            clip = engine.add_clip(path, "AI kadras · " + body.prompt[:40])
            clip["id"] = uuid.uuid4().hex[:10]
            proj["clips"].append(clip)
            proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
        else:
            proj.setdefault("broll", []).append({
                "id": vid, "provider": "veo", "pexels_id": 0, "t": round(max(0.0, body.t), 2),
                "d": round(max(1.0, min(8.0, body.d)), 2), "query": "AI: " + body.prompt[:50],
                "mode": body.mode if body.mode in engine.BROLL_MODES else "card",
                "pos": body.pos if body.pos in ("auto", "tl", "tr") else "auto",
                "image": f"/api/projects/{pid}/broll/{vid}/thumb", "user": "Google Veo", "url": "", "path": path})
            proj["broll"].sort(key=lambda b: b["t"])
        _save(user, proj)
        _job_update(jid, status="done", progress=1.0, message="AI kadras paruoštas ✅")
    except (Exception, JobCancelled) as e:
        if jid in _cancelled or isinstance(e, JobCancelled):
            _job_update(jid, status="cancelled", message="Sustabdyta")
            return
        traceback.print_exc()
        _job_update(jid, status="error", message=str(e)[:300])


# ---------- 📚 Mano AI kadrai: biblioteka (sumokėta vieną kartą – naudojama visur) ----------
def _lib_dir(user):
    return os.path.join(DATA, "library", re.sub(r"[^\w.@-]", "_", user["username"]))


def _lib_load(user):
    try:
        with open(os.path.join(_lib_dir(user), "library.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _lib_save(user, items):
    d = _lib_dir(user)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "library.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, "library.json"))


def _library_add(user, path, prompt, fmt, created=None, backfill=True):
    """Kadro kopija į naudotojo biblioteką (atskirai nuo projekto – ištrynus projektą, kadras lieka)."""
    if backfill:
        _library_backfill(user)  # pirmiausia – anksčiau sukurti kadrai (kad nesidubliuotų)
    items = _lib_load(user)
    lid = uuid.uuid4().hex[:10]
    d = _lib_dir(user)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, lid + ".mp4")
    shutil.copy(path, dst)
    try:
        reels_studio.grab_frame(dst, dst + ".thumb.jpg", at=1.0)
    except Exception:
        traceback.print_exc()
    try:
        dur = round(video_editor.media_duration(dst), 1)
    except Exception:
        dur = None
    items.insert(0, {"id": lid, "prompt": prompt[:200], "format": fmt, "duration": dur,
                     "created": created or time.time()})
    _lib_save(user, items)
    return lid


def _library_backfill(user):
    """Anksčiau sukurti AI kadrai (projektuose) – į biblioteką vieną kartą."""
    marker = os.path.join(_lib_dir(user), ".backfilled")
    if os.path.exists(marker):
        return
    os.makedirs(_lib_dir(user), exist_ok=True)
    open(marker, "w").close()
    root = os.path.join(PROJECTS, re.sub(r"[^\w.@-]", "_", user["username"]))
    for pid in os.listdir(root) if os.path.isdir(root) else []:
        try:
            proj = _load(user, pid)
        except HTTPException:
            continue
        for b in proj.get("broll", []):
            if b.get("provider") == "veo" and os.path.exists(b.get("path", "")):
                _library_add(user, b["path"], (b.get("query") or "AI kadras").removeprefix("AI: "),
                             proj["settings"].get("format", "9:16"), backfill=False)


@app.get("/api/library")
def library(user=Depends(current_user)):
    _library_backfill(user)
    return {"items": [it for it in _lib_load(user) if os.path.exists(os.path.join(_lib_dir(user), it["id"] + ".mp4"))]}


def _lib_file(user, lid, thumb=False):
    lid = re.sub(r"[^a-f0-9]", "", lid)
    path = os.path.join(_lib_dir(user), lid + ".mp4" + (".thumb.jpg" if thumb else ""))
    if not lid or not os.path.exists(path):
        raise HTTPException(404, "Kadras nerastas")
    return path


@app.get("/api/library/{lid}/thumb")
def library_thumb(lid: str, user=Depends(current_user)):
    return FileResponse(_lib_file(user, lid, True), media_type="image/jpeg")


@app.get("/api/library/{lid}/video")
def library_video(lid: str, user=Depends(current_user)):
    return FileResponse(_lib_file(user, lid), media_type="video/mp4")


@app.delete("/api/library/{lid}")
def library_delete(lid: str, user=Depends(current_user)):
    path = _lib_file(user, lid)
    for f in (path, path + ".thumb.jpg"):
        if os.path.exists(f):
            os.unlink(f)
    _lib_save(user, [it for it in _lib_load(user) if it["id"] != lid])
    return {"ok": True}


class LibUse(BaseModel):
    lid: str
    t: float = 0.0
    d: float = 3.0
    mode: str = "card"
    pos: str = "auto"
    as_clip: bool = False


@app.post("/api/projects/{pid}/broll/library")
def use_library(pid: str, body: LibUse, user=Depends(current_user)):
    """Kadras iš bibliotekos – į projektą (kopija), be jokio naujo mokesčio."""
    src = _lib_file(user, body.lid)
    meta = next((it for it in _lib_load(user) if it["id"] == body.lid), {})
    proj = _load(user, pid)
    d = os.path.join(_pdir(user, pid), "broll")
    os.makedirs(d, exist_ok=True)
    vid = uuid.uuid4().hex[:8]
    path = os.path.join(d, f"veo_{vid}.mp4")
    shutil.copy(src, path)
    if os.path.exists(src + ".thumb.jpg"):
        shutil.copy(src + ".thumb.jpg", path + ".thumb.jpg")
    if body.as_clip:
        clip = engine.add_clip(path, "AI kadras · " + meta.get("prompt", "")[:40])
        clip["id"] = uuid.uuid4().hex[:10]
        proj["clips"].append(clip)
        proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    else:
        proj.setdefault("broll", []).append({
            "id": vid, "provider": "veo", "pexels_id": 0, "t": round(max(0.0, body.t), 2),
            "d": round(max(1.0, min(8.0, body.d)), 2), "query": "AI: " + meta.get("prompt", "")[:50],
            "mode": body.mode if body.mode in engine.BROLL_MODES else "card",
            "pos": body.pos if body.pos in ("auto", "tl", "tr") else "auto",
            "image": f"/api/projects/{pid}/broll/{vid}/thumb", "user": "Mano AI kadras", "url": "", "path": path,
            "from_library": True})
        proj["broll"].sort(key=lambda b: b["t"])
    _save(user, proj)
    return _public(proj)


@app.post("/api/projects/{pid}/broll/veo")
def veo_broll(pid: str, body: VeoBody, user=Depends(current_user)):
    """🎬 AI sukuria video kadrą pagal aprašymą (Google Veo, 1–3 min., fone)."""
    _load(user, pid)
    if accounts.left(user["username"], "ai_clips") == 0:
        lim = accounts.limits_for(user["username"])["ai_clips"]
        raise HTTPException(403, f"Šio mėnesio AI kadrų limitas išnaudotas ({lim}). Naudokite kadrus iš „📚 Mano AI "
                                 "kadrai“ – jie nemokami – arba kreipkitės į studijos administratorių.")
    if user["plan"] not in AI_PLANS:
        raise HTTPException(400, "AI kadrai – Premium plane.")
    if not stock_key("gemini"):
        raise HTTPException(400, "Reikia Google (Gemini) rakto – „Mano projektai“ → Google raktas.")
    if len(body.prompt.strip()) < 5:
        raise HTTPException(400, "Aprašykite kadrą plačiau (pvz. „kava pilama į puodelį, saulėtas rytas“).")
    with _jobs_lock:
        if any(j["user"] == user["username"] and j["kind"] == "veo" and j["status"] in ("queued", "running")
               for j in _jobs.values()):
            raise HTTPException(429, "Palaukite – ankstesnis AI kadras dar kuriamas.")
        jid = uuid.uuid4().hex[:12]
        _jobs[jid] = {"id": jid, "user": user["username"], "project": pid, "kind": "veo", "status": "running",
                      "progress": 0.0, "message": "Siunčiu užklausą Google…", "created": time.time(), "result": None}
    threading.Thread(target=_run_veo, args=(jid, user, pid, body), daemon=True).start()
    return _jobs[jid]


@app.get("/api/projects/{pid}/broll/{bid}/thumb")
def broll_thumb(pid: str, bid: str, user=Depends(current_user)):
    path = os.path.join(_pdir(user, pid), "broll", f"veo_{re.sub(r'[^a-f0-9]', '', bid)}.mp4.thumb.jpg")
    if not os.path.exists(path):
        raise HTTPException(404, "Nėra")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/projects/{pid}/broll/veo_ideas")
def veo_ideas(pid: str, user=Depends(current_user)):
    """AI pagal tai, ką sakote, pasiūlo 3 AI kadrų aprašymus (ties sakiniais)."""
    proj = _load(user, pid)
    client = openai_client(user)
    if client is None:
        raise HTTPException(400, "Pasiūlymams reikia OpenAI rakto. Aprašymą galite parašyti patys.")
    if not proj.get("words"):
        raise HTTPException(400, "Pirmiausia paruoškite titrus (💬 Titrai → Paruošti titrus).")
    lines = " ".join(f"[{a:.1f}] {video_editor.plain(w)}" for w, a, _ in proj["words"][:300])
    j = reels_studio._ai_json(client, (
        "Suggest 3 short AI-generated cutaway shots for this talking video (moments at least 4 s apart, not in the "
        "first 2 s). For each: time (s), a vivid one-sentence visual description in Lithuanian (what the camera "
        "shows; no people talking to camera, no text). Reply only JSON: "
        "{\"ideas\": [{\"time\": 0, \"prompt\": \"...\"}]}"), {"transcript": lines})
    out = []
    for it in (j.get("ideas") or [])[:3]:
        try:
            out.append({"t": round(float(it["time"]), 2), "prompt": str(it["prompt"])[:200]})
        except (KeyError, TypeError, ValueError):
            continue
    return {"ideas": out}


# ---------- 🎙 AI įgarsinimas ----------
@app.get("/api/voice_sample/{voice}")
def voice_sample(voice: str, user=Depends(current_user)):
    if voice not in engine.VOICES and voice not in engine.GEMINI_VOICES:
        raise HTTPException(404, "Nėra tokio balso")
    path = os.path.join(DATA, "voice_samples", f"v{engine.TTS_VERSION}_" + voice.replace(":", "_") + ".mp3")
    if not os.path.exists(path):
        if user["plan"] not in AI_PLANS:
            raise HTTPException(400, "Balsų pavyzdžiams reikia AI (Premium).")
        client = openai_client(user)
        if not voice.startswith("g:") and client is None:
            raise HTTPException(400, "OpenAI balsams reikia OpenAI rakto.")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            engine.tts(client, "Sveiki! Taip skambės jūsų Reels įgarsinimas. Ar patinka mano balsas?", voice, path,
                       gemini_key=stock_key("gemini"))
        except RuntimeError as e:
            raise HTTPException(400, str(e))
    return FileResponse(path, media_type="audio/mpeg")


def _voice_for(voice):
    """Google balsas, kai nėra Google rakto, pakeičiamas OpenAI balsu (kad video vis tiek būtų sukurtas)."""
    v = voice or "g:Kore"
    if v.startswith("g:") and not stock_key("gemini"):
        return "coral"
    return v


def _voice_quota(user, text):
    """AI įgarsinimo simbolių limitas (tik kai kuriamas naujas įgarsinimas)."""
    lft = accounts.left(user["username"], "voice_chars")
    if lft is not None and len(text) > lft:
        lim = accounts.limits_for(user["username"])["voice_chars"]
        raise PermissionError(f"Šio mėnesio AI įgarsinimo limitas ({lim} simbolių) – liko {int(lft)}. "
                              "Sutrumpinkite tekstą arba kreipkitės į studijos administratorių.")


@app.post("/api/projects/{pid}/voiceover_preview")
def voiceover_preview(pid: str, user=Depends(current_user)):
    """▶ Išklausyti tikrąjį įgarsinimą (tas pats failas bus naudojamas video – antrą kartą nemokama)."""
    proj = _load(user, pid)
    vo = dict(proj["settings"].get("voiceover") or {})
    vo["voice"] = _voice_for(vo.get("voice"))
    text = str(vo.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "Įrašykite įgarsinimo tekstą.")
    if user["plan"] not in AI_PLANS:
        raise HTTPException(400, "AI įgarsinimas – Premium plane.")
    client = openai_client(user)
    google = str(vo.get("voice", "")).startswith("g:")
    if (google and not stock_key("gemini")) or (not google and client is None):
        raise HTTPException(400, "Šiam balsui nėra rakto.")
    key = hashlib.sha1((engine.TTS_VERSION + "|" + vo["text"] + "|" + vo.get("voice", "") + "|" +
                        proj["settings"]["subtitle_language"]).encode()).hexdigest()[:12]
    path = os.path.join(_pdir(user, pid), f"vo_{key}.mp3")
    if not os.path.exists(path):
        try:
            _voice_quota(user, text)
            engine.tts(client, text, _voice_for(vo.get("voice")), path, proj["settings"]["subtitle_language"],
                       gemini_key=stock_key("gemini"))
            accounts.add_usage(user["username"], "voice_chars", len(text))
        except (RuntimeError, PermissionError) as e:
            raise HTTPException(400, str(e))
    return {"file": f"vo_{key}.mp3", "text": text, "voice": vo.get("voice")}


@app.get("/api/projects/{pid}/voiceover/{name}")
def voiceover_file(pid: str, name: str, user=Depends(current_user)):
    if not re.fullmatch(r"(vo|aud)_[a-f0-9]{12}\.mp3", name):
        raise HTTPException(404, "Nėra")
    path = os.path.join(_pdir(user, pid), name)
    if not os.path.exists(path):
        raise HTTPException(404, "Nėra")
    return FileResponse(path, media_type="audio/mpeg")


class VoiceTextBody(BaseModel):
    topic: str
    seconds: int = 30


@app.post("/api/projects/{pid}/voice_text")
def gen_voice_text(pid: str, body: VoiceTextBody, user=Depends(current_user)):
    proj = _load(user, pid)
    client = openai_client(user)
    if client is None:
        raise HTTPException(400, "Teksto rašymui reikia AI (Premium).")
    text = engine.voice_text(client, body.topic[:300], proj["settings"]["subtitle_language"],
                             max(10, min(90, body.seconds)))
    if not text:
        raise HTTPException(502, "AI tekstas neparašytas – pabandykite dar kartą.")
    return {"text": text}


# ---------- ✨ Scenarijai pagal verslo sritį + automatinis video ----------
import scripts  # noqa: E402


@app.get("/api/scripts/options")
def scripts_options():
    return {"sectors": {k: v[0] for k, v in scripts.SECTORS.items()}, "goals": scripts.GOALS,
            "lengths": list(scripts.LENGTHS)}


class ScriptBody(BaseModel):
    sector: str = "kita"
    goal: str = "pristatymas"
    topic: str = ""
    seconds: int = 30
    offset: int = 0
    avoid: list[str] = []


@app.post("/api/projects/{pid}/scripts")
def gen_scripts(pid: str, body: ScriptBody, user=Depends(current_user)):
    """3 skirtingi tekstų variantai sufleriui / įgarsinimui (AI – Premium, be AI – šablonai)."""
    proj = _load(user, pid)
    sector = body.sector if body.sector in scripts.SECTORS else "kita"
    goal = body.goal if body.goal in scripts.GOALS else "pristatymas"
    secs = max(10, min(90, int(body.seconds)))
    topic = body.topic.strip()[:300]
    client = openai_client(user)
    if client is not None:
        try:
            v = scripts.ai_variants(client, reels_studio._ai_json, sector, goal, topic, secs, 3,
                                    video_editor.LANGUAGES.get(proj["settings"]["subtitle_language"], "Lithuanian"),
                                    [str(a)[:120] for a in body.avoid])
            if v:
                return {"variants": v, "ai": True}
        except Exception as e:  # AI nepavyko – grąžinam šablonus
            print("AI scenarijai nepavyko:", e, file=sys.stderr)
    return {"variants": scripts.template_variants(sector, goal, topic, secs, 3, body.offset,
                                                  [str(a)[:120] for a in body.avoid]), "ai": False}


class PromptBody(BaseModel):
    prompt: str


@app.post("/api/projects/{pid}/prompt_plan")
def prompt_plan(pid: str, body: PromptBody, user=Depends(current_user)):
    """✨ „Aprašykite video“: AI iš laisvo teksto suplanuoja visą video (tekstas, scenos, vaizdai)."""
    proj = _load(user, pid)
    if len(body.prompt.strip()) < 10:
        raise HTTPException(400, "Aprašykite plačiau: kam skirtas video, apie ką, kokia nuotaika ir trukmė.")
    client = openai_client(user)
    if client is None:
        raise HTTPException(400, "Video pagal aprašymą kuria AI – tai Premium funkcija.")
    try:
        return scripts.plan_from_prompt(client, reels_studio._ai_json, body.prompt,
                                        video_editor.LANGUAGES.get(proj["settings"]["subtitle_language"], "Lithuanian"))
    except ValueError as e:
        raise HTTPException(502, str(e))


class AutoVideoBody(BaseModel):
    sector: str = "kita"
    text: str
    scenes: list[dict] = []
    voice: str | None = None   # AI įgarsinimas (Premium); None – be balso, tik titrai ir muzika


def _stock_used_path(user):
    return os.path.join(DATA, "stock_used", re.sub(r"[^\w.@-]", "_", user["username"]) + ".json")


def _stock_used(user):
    try:
        with open(_stock_used_path(user), encoding="utf-8") as f:
            return [tuple(x) for x in json.load(f)]
    except (OSError, ValueError):
        return []


def _stock_used_add(user, items):
    """Įsimenam, kuriuos vaizdus klientas jau gavo – kituose jo video jie nebesikartos (paskutiniai 600)."""
    hist = [x for x in _stock_used(user) if x not in items] + list(items)
    os.makedirs(os.path.dirname(_stock_used_path(user)), exist_ok=True)
    with open(_stock_used_path(user), "w", encoding="utf-8") as f:
        json.dump([list(x) for x in hist[-600:]], f)


def _stock_score(v, rank, fmt, want):
    """Kokybės balas: paieškos vieta (aktualumas), forma, raiška, populiarumas, trukmė."""
    w, h = v.get("width") or 0, v.get("height") or 0
    shape = "portrait" if h > w * 1.1 else "landscape" if w > h * 1.1 else "square"
    sc = -rank * 1.5
    sc += 6 if shape == _orientation(fmt) else (2 if shape == "square" else 0)
    sc += 3 if max(w, h) >= 1900 else (1.5 if max(w, h) >= 1270 else -4)
    sc += min(4.0, (v.get("likes") or 0) / 60) + min(3.0, (v.get("downloads") or 0) / 4000)
    sc += 2 if (v.get("duration") or 0) >= want else -3
    return sc


def _ai_pick(client, cands, scene, query):
    """Premium: AI pažiūri kandidatų miniatiūras ir išrenka labiausiai scenai tinkantį ir gražiausią kadrą."""
    content = [{"type": "text", "text": (
        "Pick the best stock video thumbnail for this scene of a short, high-quality business Reel. Prefer: clearly "
        "matches the scene, attractive, professional, sharp, natural light, real people/products (no cartoons, no "
        "cheap-looking or odd shots, no visible logos/text). Scene: " + (scene or "")[:300] + f" | search: {query}. "
        "Rate how good the BEST one is for a premium-looking Reel on a 1-10 scale (10 = beautiful, sharp, perfectly "
        "fitting; 7 = acceptable; below 6 = amateur, off-topic or ugly). "
        f"Reply only JSON: {{\"best\": <index 0-{len(cands) - 1}>, \"ok\": true/false, \"score\": <1-10>}} "
        "(ok=false if none fits).")}]
    for i, v in enumerate(cands):
        content.append({"type": "text", "text": f"#{i}"})
        content.append({"type": "image_url", "image_url": {"url": v["image"], "detail": "low"}})
    for m in ("gpt-4.1-mini", "gpt-4o-mini"):
        try:
            r = client.chat.completions.create(model=m, temperature=0, response_format={"type": "json_object"},
                                               messages=[{"role": "user", "content": content}])
            j = json.loads(r.choices[0].message.content)
            i = int(j.get("best", -1))
            try:
                score = float(j.get("score", 7))
            except (TypeError, ValueError):
                score = 7.0
            return (cands[i] if 0 <= i < len(cands) else None), bool(j.get("ok", True)), score
        except Exception as e:
            print("AI vaizdo parinkimas nepavyko:", e, file=sys.stderr)
    return None, True, 0.0


def _pick_stock(q, fmt, provider, want, exclude, client=None, scene="", min_score=None):
    """Geriausias vaizdas scenai: aktualiausi ir kokybiškiausi kandidatai (ne atsitiktiniai), be jau naudotų.
    Premium – AI dar pažiūri miniatiūras ir išrenka tinkamiausią. Grąžina None, jei nieko tinkamo."""
    import random
    cand, seen = [], set()
    for page in (1, 2):
        try:
            res = stock_search(q, fmt, page, 20, provider)
        except HTTPException:
            res = []
        for v in res:
            if v["id"] not in seen and (provider, v["id"]) not in exclude:
                seen.add(v["id"])
                cand.append(v)
        if len(cand) >= 15:
            break
    if not cand:
        return None
    def shape(v):
        w, h = v.get("width") or 0, v.get("height") or 0
        return "portrait" if h > w * 1.1 else "landscape" if w > h * 1.1 else "square"
    same = [v for v in cand if shape(v) == _orientation(fmt)]
    if len(same) >= 4:  # užtenka tinkamos formos – kitokios formos (bus apkarpyti) nenaudojam
        cand = same
    ranked = sorted(enumerate(cand), key=lambda iv: -_stock_score(iv[1], iv[0], fmt, want))
    top = [v for _, v in ranked[:8]]
    if client is not None and len(top) > 1 and all(v.get("image") for v in top):
        best, ok, score = _ai_pick(client, top, scene, q)
        if min_score is not None:  # griežtas režimas (AI režisierius) – tik tikrai kokybiški kadrai
            return best if (best is not None and ok and score >= min_score) else None
        if best is not None and ok:
            return best
        if best is not None and not ok:
            return None if len(cand) > 3 else best  # nieko tinkamo – bandysim kitą paiešką
    if min_score is not None:
        return None  # be AI įvertinimo kokybės garantuoti negalima
    return random.choice(top[:3])  # truputis įvairovės tarp geriausių


def _run_auto_video(jid, user, pid, body):
    try:
        proj = _load(user, pid)
        d = _pdir(user, pid)
        fmt = proj["settings"]["format"]
        provider = stock_provider()
        text = body.text.strip()[:3000]
        scenes = [{"text": str(sc.get("text", "")).strip()[:600], "query": str(sc.get("query", "")).strip()[:60],
                   "visual": str(sc.get("visual", "")).strip()[:400]}
                  for sc in body.scenes if str(sc.get("text", "")).strip()] or scripts.scenes_for(text, body.sector)
        pool = scripts.SECTORS.get(body.sector, scripts.SECTORS["kita"])[3]
        for i, sc in enumerate(scenes):
            sc["query"] = sc["query"] or pool[i % len(pool)]
        settings = dict(proj["settings"])
        total = None
        if body.voice:  # 🎙 įgarsinimas – iš anksto, kad žinotume tikslią trukmę (tas pats failas bus naudojamas video)
            _job_update(jid, message="Kuriu AI įgarsinimą…", progress=0.05)
            client = openai_client(user)
            lang = settings["subtitle_language"]
            key = hashlib.sha1((engine.TTS_VERSION + "|" + text + "|" + body.voice + "|" + lang).encode()).hexdigest()[:12]
            vo_path = os.path.join(d, f"vo_{key}.mp3")
            if not os.path.exists(vo_path):
                _voice_quota(user, text)
                engine.tts(client, text, body.voice, vo_path, lang, gemini_key=stock_key("gemini"))
                accounts.add_usage(user["username"], "voice_chars", len(text))
            total = video_editor.media_duration(vo_path) * settings.get("speed", 1.0) + 0.6
            settings["voiceover"] = {"on": True, "text": text, "voice": body.voice}
            settings["clip_gain"] = 0
        else:
            settings["voiceover"] = dict(settings.get("voiceover") or {}, on=False)
            settings["subtitle_text"] = text
            total = max(6.0, len(text.split()) / 2.3 + 1.0)
        weights = [max(1, len(sc["text"])) for sc in scenes]
        need = [total * w / sum(weights) for w in weights]
        # ankstesni automatiškai sudėti kadrai pakeičiami naujais (jūsų pačių įkelta medžiaga lieka)
        for c in [c for c in proj["clips"] if c.get("auto")]:
            if c["path"].startswith(d) and os.path.exists(c["path"]):
                os.unlink(c["path"])
        proj["clips"] = [c for c in proj["clips"] if not c.get("auto")]
        cdir = os.path.join(d, "clips")
        os.makedirs(cdir, exist_ok=True)
        history = set(_stock_used(user))
        ai_client = openai_client(user)  # Premium – AI peržiūri kandidatus
        used, carry, added, picked = set(), 0.0, 0, []
        for i, sc in enumerate(scenes):
            want = need[i] + carry
            _job_update(jid, message=f"Ieškau vaizdo {i + 1}/{len(scenes)}: „{sc['query']}“…",
                        progress=0.15 + 0.8 * i / len(scenes))
            best = None
            for q, excl, cl in ((sc["query"], history | used, ai_client), (pool[i % len(pool)], history | used, ai_client),
                                (sc["query"], used, None)):  # paskutinis bandymas – bet koks tinkamas
                best = _pick_stock(q, fmt, provider, want, excl, cl, sc["text"])
                if best:
                    break
            if not best:
                carry = want
                continue
            used.add((provider, best["id"]))
            picked.append((provider, best["id"]))
            src, _ = stock_download(user, pid, provider, best["id"], fmt)
            cid = uuid.uuid4().hex[:10]
            path = os.path.join(cdir, cid + ".mp4")
            # be originalaus garso (stock garsas nereikalingas – bus balsas ar muzika)
            if engine._ffmpeg(["-i", src, "-an", "-c:v", "copy", path]).returncode != 0:
                shutil.copy(src, path)
            clip = engine.add_clip(path, f"🎞 {sc['query']}")
            dur = clip["duration"]
            use = min(dur, max(1.5, want))
            if use < dur - 0.05:
                clip["trim"] = [0.0, round(use, 3)]
            carry = max(0.0, want - use)
            clip.update(id=cid, auto=True, scene=sc["text"][:200], visual=sc.get("visual") or "", query=sc["query"])
            proj["clips"].append(clip)
            added += 1
        if not added:
            raise ValueError("Tinkamų vaizdų nerasta – pabandykite kitą variantą arba įkelkite savo medžiagą.")
        _stock_used_add(user, picked)
        accounts.add_usage(user["username"], "auto_videos", 1)
        proj["auto_src"] = {"sector": body.sector, "text": text, "scenes": scenes, "voice": body.voice}
        if not settings.get("music"):
            music = scripts.SECTORS.get(body.sector, scripts.SECTORS["kita"])[4]
            settings["music"] = music if music in reels_studio.music_library() else None
        settings["subtitles"] = True
        proj["settings"] = engine.settings_with_defaults(settings)
        proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
        _save(user, proj)
        _job_update(jid, status="done", progress=1.0, message=f"Sudėta {added} vaizdų ✅", result={"clips": added})
    except Exception as e:
        _job_update(jid, status="error", message=str(e)[:300])


@app.post("/api/projects/{pid}/auto_video/reshuffle")
def auto_video_reshuffle(pid: str, user=Depends(current_user)):
    """🔄 Kiti vaizdai tam pačiam tekstui ir balsui (balsas – iš kešo, nemokamai)."""
    src = _load(user, pid).get("auto_src")
    if not src:
        raise HTTPException(400, "Šiame projekte dar nėra automatiškai sudėto video.")
    return auto_video(pid, AutoVideoBody(**src), user)


@app.post("/api/projects/{pid}/auto_video")
def auto_video(pid: str, body: AutoVideoBody, user=Depends(current_user)):
    """🎬 Video iš scenarijaus: kiekvienai scenai parenkamas vaizdas, pridedamas balsas (arba titrai ir muzika)."""
    _load(user, pid)
    if not body.text.strip():
        raise HTTPException(400, "Nėra teksto.")
    if not stock_provider():
        raise HTTPException(400, "Vaizdų paieškos raktas (Pixabay) neįrašytas – kreipkitės į administratorių.")
    lft = accounts.left(user["username"], "auto_videos")
    if lft is not None and lft < 1:
        lim = accounts.limits_for(user["username"])["auto_videos"]
        raise HTTPException(400, f"Šio mėnesio automatinių video limitas ({lim}) išnaudotas. Galite įkelti ar nufilmuoti "
                                 "savo medžiagą" + (" arba pereiti į Premium." if user["plan"] == "basic" else "."))
    if body.voice:
        if user["plan"] not in AI_PLANS:
            raise HTTPException(400, "AI įgarsinimas – Premium plane. Galite kurti video be balso – su titrais ir muzika.")
        google = body.voice.startswith("g:")
        if body.voice not in engine.VOICES and body.voice not in engine.GEMINI_VOICES:
            raise HTTPException(400, "Nežinomas balsas")
        if (google and not stock_key("gemini")) or (not google and openai_client(user) is None):
            raise HTTPException(400, "Šiam balsui nėra rakto.")
        lft = accounts.left(user["username"], "voice_chars")
        if lft is not None and len(body.text.strip()) > lft:
            raise HTTPException(400, f"Šio mėnesio AI įgarsinimo limitas – liko {int(lft)} simbolių. Sutrumpinkite tekstą.")
    with _jobs_lock:
        if any(j["user"] == user["username"] and j["kind"] == "auto" and j["status"] in ("queued", "running")
               for j in _jobs.values()):
            raise HTTPException(429, "Palaukite – ankstesnis video dar dėliojamas.")
        jid = uuid.uuid4().hex[:12]
        _jobs[jid] = {"id": jid, "user": user["username"], "project": pid, "kind": "auto", "status": "running",
                      "progress": 0.0, "message": "Pradedu…", "created": time.time(), "result": None}
    threading.Thread(target=_run_auto_video, args=(jid, user, pid, body), daemon=True).start()
    return _jobs[jid]


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/options")
def options():
    return engine.options()


# ---------- projektai ----------
def _safe_id(pid):
    if not re.fullmatch(r"[a-f0-9]{12}", pid or ""):
        raise HTTPException(404, "Projektas nerastas")
    return pid


def _pdir(user, pid):
    return os.path.join(PROJECTS, re.sub(r"[^\w.@-]", "_", user["username"]), _safe_id(pid))


def _load(user, pid):
    path = os.path.join(_pdir(user, pid), "project.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        raise HTTPException(404, "Projektas nerastas")


def _save(user, proj):
    d = _pdir(user, proj["id"])
    os.makedirs(d, exist_ok=True)
    proj["updated"] = time.time()
    tmp = os.path.join(d, "project.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, "project.json"))


def _prep_path(user, pid):
    return os.path.join(_pdir(user, pid), "prep.pkl")


def _load_prep(user, proj):
    """Paruošta medžiaga (analizėje – numpy masyvai, todėl laikoma atskirai, ne JSON)."""
    if not proj.get("prepared"):
        return None
    try:
        with open(_prep_path(user, proj["id"]), "rb") as f:
            prep = pickle.load(f)
        return prep if os.path.exists(prep["src"]) else None
    except (OSError, pickle.PickleError, EOFError, KeyError):
        return None


def _save_prep(user, proj, prep):
    with open(_prep_path(user, proj["id"]), "wb") as f:
        pickle.dump(prep, f)
    proj["prepared"] = True
    proj["words"] = [[w, round(float(a), 3), round(float(b), 3)] for w, a, b in prep["analysis"]["words"]]
    proj["lines"] = [[round(float(a), 3), round(float(b), 3), t] for a, b, t in
                     video_editor.edit_lines(prep["analysis"]["words"])]
    proj["line_texts"] = None  # naudotojo pataisyti sakiniai
    kt = proj.pop("keep_texts", None)
    if kt and len(kt) == len(proj["lines"]):
        proj["line_texts"] = kt
    proj["clip_spans"] = {c["id"]: sp for c, sp in zip(proj.get("clips", []), prep.get("spans") or []) if sp}


def _public(proj):
    """Projekto vaizdas naršyklei – be vidinių failų kelių."""
    p = dict(proj)
    p["clips"] = [{k: ({kk: vv for kk, vv in v.items() if kk != "path"} if k == "sound" and isinstance(v, dict) else v)
                   for k, v in c.items() if k not in ("path",)} for c in proj.get("clips", [])]
    p["broll"] = [{k: v for k, v in b.items() if k not in ("path",)} for b in proj.get("broll", [])]
    p.setdefault("prepared", False)
    p.setdefault("words", None)
    p.pop("plan_cache", None)  # vidinis kūrimo planas (kad galutinis video sutaptų su peržiūra)
    p["has_original"] = bool(p.pop("original", None))  # 🪄 yra pradinė versija (prieš automatinį montažą)
    return p


class NewProject(BaseModel):
    title: str = ""
    settings: dict = {}


@app.get("/api/projects")
def list_projects(user=Depends(current_user)):
    root = os.path.join(PROJECTS, re.sub(r"[^\w.@-]", "_", user["username"]))
    out = []
    for pid in os.listdir(root) if os.path.isdir(root) else []:
        try:
            p = _load(user, pid)
        except HTTPException:
            continue
        out.append({"id": p["id"], "title": p["title"], "updated": p["updated"], "clips": len(p["clips"]),
                    "outputs": p.get("outputs", {})})
    return sorted(out, key=lambda p: -p["updated"])


@app.post("/api/projects")
def create_project(body: NewProject, user=Depends(current_user)):
    proj = {"id": uuid.uuid4().hex[:12], "title": body.title.strip()[:80] or "Naujas Reels",
            "created": time.time(), "settings": engine.settings_with_defaults(body.settings), "clips": [],
            "prepared": False, "words": None, "outputs": {}}
    _save(user, proj)
    return _public(proj)


@app.get("/api/projects/{pid}")
def get_project(pid: str, user=Depends(current_user)):
    return _public(_load(user, pid))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str, user=Depends(current_user)):
    _load(user, pid)
    shutil.rmtree(_pdir(user, pid), ignore_errors=True)
    return {"ok": True}


class SettingsBody(BaseModel):
    settings: dict
    title: str | None = None


@app.put("/api/projects/{pid}/settings")
def update_settings(pid: str, body: SettingsBody, user=Depends(current_user)):
    proj = _load(user, pid)
    old = proj["settings"]
    proj["settings"] = engine.settings_with_defaults(dict(old, **body.settings))
    # pasikeitus formatui, perėjimui ar kalbai – medžiagą reikės paruošti iš naujo
    if any(proj["settings"].get(k) != old.get(k) for k in ("format", "fit", "transition", "remove_silence", "subtitles",
                                                             "subtitle_language", "subtitle_text")):
        proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    if body.title is not None:
        proj["title"] = body.title.strip()[:80] or proj["title"]
    _save(user, proj)
    return _public(proj)


@app.post("/api/projects/{pid}/clips")
def upload_clip(pid: str, file: UploadFile = File(...), recorded: bool = Form(False), user=Depends(current_user)):
    proj = _load(user, pid)
    d = os.path.join(_pdir(user, pid), "clips")
    os.makedirs(d, exist_ok=True)
    cid = uuid.uuid4().hex[:10]
    ext = os.path.splitext(file.filename or "")[1].lower()[:6] or (".webm" if recorded else ".mp4")
    path = os.path.join(d, cid + ext)
    size = 0
    with open(path, "wb") as f:
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD:
                f.close()
                os.unlink(path)
                raise HTTPException(413, "Failas per didelis")
            f.write(chunk)
    try:
        clip = engine.add_clip(path, file.filename, recorded)
    except ValueError as e:
        if os.path.exists(path):
            os.unlink(path)
        raise HTTPException(400, str(e))
    clip["id"] = cid
    proj["clips"].append(clip)
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


@app.delete("/api/projects/{pid}/clips/{cid}")
def delete_clip(pid: str, cid: str, user=Depends(current_user)):
    proj = _load(user, pid)
    for c in [c for c in proj["clips"] if c["id"] == cid]:
        shared = any(o["path"] == c["path"] for o in proj["clips"] if o["id"] != cid)  # padalintas įrašas
        if not shared and c["path"].startswith(_pdir(user, pid)) and os.path.exists(c["path"]):
            os.unlink(c["path"])
    proj["clips"] = [c for c in proj["clips"] if c["id"] != cid]
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


# ---------- ✂ Karpymas (kaip CapCut / Instagram) ----------
def _clip(proj, cid):
    c = next((c for c in proj["clips"] if c["id"] == cid), None)
    if not c:
        raise HTTPException(404, "Įrašas nerastas")
    if c.get("image"):
        raise HTTPException(400, "Nuotraukos karpyti nereikia")
    return c


class TrimBody(BaseModel):
    start: float
    end: float


@app.put("/api/projects/{pid}/clips/{cid}/trim")
def trim_clip(pid: str, cid: str, body: TrimBody, user=Depends(current_user)):
    proj = _load(user, pid)
    c = _clip(proj, cid)
    a, b = max(0.0, body.start), min(c["duration"], body.end)
    if b - a < 0.3:
        raise HTTPException(400, "Palikite bent 0,3 s")
    c["trim"] = None if a <= 0.01 and b >= c["duration"] - 0.01 else [round(a, 3), round(b, 3)]
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


class SoundBody(BaseModel):
    kind: str = "none"          # none | music | voice
    track: str | None = None    # muzika iš bibliotekos
    text: str | None = None     # kadro įgarsinimo tekstas
    voice: str | None = None
    volume: int = 100           # parinkto garso garsumas, %
    orig: int = 100             # kadro originalaus garso garsumas, %


@app.put("/api/projects/{pid}/clips/{cid}/sound")
def clip_sound(pid: str, cid: str, body: SoundBody, user=Depends(current_user)):
    """🎵 Kadrui skirta muzika arba įgarsinimas (skamba tik per tą kadrą)."""
    proj = _load(user, pid)
    c = next((c for c in proj["clips"] if c["id"] == cid), None)
    if not c:
        raise HTTPException(404, "Įrašas nerastas")
    vol, orig = max(0, min(200, int(body.volume))), max(0, min(200, int(body.orig)))
    if body.kind == "none":
        c.pop("sound", None)
    elif body.kind == "music":
        if body.track not in reels_studio.music_library():
            raise HTTPException(400, "Tokios muzikos nėra")
        c["sound"] = {"kind": "music", "track": body.track, "volume": vol, "orig": orig}
    elif body.kind == "file":  # įkeltas garsas – keičiami tik garsumai
        cur = c.get("sound") or {}
        if cur.get("kind") != "file":
            raise HTTPException(400, "Pirmiausia įkelkite garso failą.")
        cur.update(volume=vol, orig=orig)
        c["sound"] = cur
    elif body.kind == "voice":
        text = (body.text or "").strip()[:1500]
        voice = _voice_for(body.voice)
        if not text:
            raise HTTPException(400, "Įrašykite, ką balsas turi pasakyti.")
        if user["plan"] not in AI_PLANS:
            raise HTTPException(400, "AI įgarsinimas – Premium plane.")
        if voice not in engine.VOICES and voice not in engine.GEMINI_VOICES:
            raise HTTPException(400, "Nežinomas balsas")
        client = openai_client(user)
        google = voice.startswith("g:")
        if (google and not stock_key("gemini")) or (not google and client is None):
            raise HTTPException(400, "Šiam balsui nėra rakto.")
        lang = proj["settings"].get("subtitle_language", "lt")
        key = hashlib.sha1((engine.TTS_VERSION + "|" + text + "|" + voice + "|" + lang).encode()).hexdigest()[:12]
        path = os.path.join(_pdir(user, pid), f"vo_{key}.mp3")
        if not os.path.exists(path):
            try:
                _voice_quota(user, text)
                engine.tts(client, text, voice, path, lang, gemini_key=stock_key("gemini"))
                accounts.add_usage(user["username"], "voice_chars", len(text))
            except (RuntimeError, PermissionError) as e:
                raise HTTPException(400, str(e))
        c["sound"] = {"kind": "voice", "text": text, "voice": voice, "path": path, "file": f"vo_{key}.mp3",
                      "length": round(video_editor.media_duration(path), 1), "volume": vol, "orig": orig}
    else:
        raise HTTPException(400, "Netinkamas garso tipas")
    if proj.get("line_texts"):  # pataisyti titrai – atstatomi po naujo paruošimo, jei sakinių skaičius nepasikeis
        proj["keep_texts"] = proj["line_texts"]
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


@app.post("/api/projects/{pid}/clips/{cid}/sound_upload")
def clip_sound_upload(pid: str, cid: str, file: UploadFile = File(...), voice: bool = Form(False),
                      user=Depends(current_user)):
    """⬆ Sava muzika ar balso įrašas kadrui (MP3, M4A, WAV, MP4…) – garsas ištraukiamas ir sutvarkomas."""
    proj = _load(user, pid)
    c = next((c for c in proj["clips"] if c["id"] == cid), None)
    if not c:
        raise HTTPException(404, "Įrašas nerastas")
    d = _pdir(user, pid)
    tmp = os.path.join(d, "upload_" + uuid.uuid4().hex[:8])
    size = 0
    with open(tmp, "wb") as f:
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > 200 * 1024 * 1024:
                f.close()
                os.unlink(tmp)
                raise HTTPException(413, "Failas per didelis (iki 200 MB)")
            f.write(chunk)
    try:
        h = hashlib.sha1(open(tmp, "rb").read(1 << 22) + str(size).encode()).hexdigest()[:12]
        name = f"aud_{h}.mp3"
        out = os.path.join(d, name)
        if not os.path.exists(out):
            r = engine._ffmpeg(["-i", tmp, "-vn", "-ac", "2", "-ar", "48000", "-c:a", "libmp3lame", "-b:a", "192k", out])
            if r.returncode != 0 or not os.path.exists(out):
                raise HTTPException(400, "Garso nepavyko perskaityti – įkelkite MP3, M4A, WAV arba MP4 failą su garsu.")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    length = video_editor.media_duration(out)
    if length < 0.3:
        raise HTTPException(400, "Faile nėra garso.")
    old = c.get("sound") or {}
    c["sound"] = {"kind": "file", "voice": bool(voice), "path": out, "file": name,
                  "name": os.path.splitext(file.filename or "garsas")[0][:60], "length": round(length, 1),
                  "volume": 100, "orig": int(old.get("orig", 0 if voice else (100 if c.get("audio") == "speech" else 30)))}
    if proj.get("line_texts"):
        proj["keep_texts"] = proj["line_texts"]
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


class SplitBody(BaseModel):
    at: float


@app.post("/api/projects/{pid}/clips/{cid}/split")
def split_clip(pid: str, cid: str, body: SplitBody, user=Depends(current_user)):
    """Padalinti įrašą į dvi dalis (tas pats failas, skirtingi apkarpymai) – dalis galima perdėlioti ar ištrinti."""
    proj = _load(user, pid)
    c = _clip(proj, cid)
    a, b = c.get("trim") or (0.0, c["duration"])
    if not (a + 0.3 <= body.at <= b - 0.3):
        raise HTTPException(400, "Padalinkite ne arčiau nei 0,3 s nuo krašto")
    second = dict(c, id=uuid.uuid4().hex[:10], trim=[round(body.at, 3), round(b, 3)])
    c["trim"] = [round(a, 3), round(body.at, 3)]
    i = proj["clips"].index(c)
    proj["clips"].insert(i + 1, second)
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


@app.get("/api/projects/{pid}/clips/{cid}/preview")
def clip_preview(pid: str, cid: str, user=Depends(current_user)):
    """Lengva peržiūros kopija (MP4, ~640 px) – groja bet kurioje naršyklėje, ir iPhone."""
    c = _clip(_load(user, pid), cid)
    out = c["path"] + ".preview.mp4"
    if not os.path.exists(out):
        tmp = out + ".part.mp4"
        r = subprocess.run(video_editor.limit_threads(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", c["path"], "-vf", "scale=-2:'min(640,ih)',format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k",
             "-movflags", "+faststart", tmp]), capture_output=True, text=True)
        if r.returncode != 0:
            raise HTTPException(500, "Nepavyko paruošti peržiūros")
        os.replace(tmp, out)
    return FileResponse(out, media_type="video/mp4")


@app.get("/api/projects/{pid}/clips/{cid}/frame")
def clip_frame(pid: str, cid: str, t: float = 0.0, user=Depends(current_user)):
    """Vienas kadras karpymo lange (rodomas iškart, kol telefonas dar neužkrovė video)."""
    c = _clip(_load(user, pid), cid)
    t = max(0.0, min(float(c.get("duration") or 0) - 0.05, round(t, 1)))
    out = f"{c['path']}.f{int(t * 10)}.jpg"
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", c["path"],
                        "-vf", "scale=-2:'min(480,ih)'", "-frames:v", "1", "-q:v", "4", out], capture_output=True)
        if not os.path.exists(out):
            raise HTTPException(500, "Nepavyko paimti kadro")
    return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/projects/{pid}/clips/{cid}/strip")
def clip_strip(pid: str, cid: str, user=Depends(current_user)):
    """Kadrų juosta karpymui: 12 kadrų vienoje eilėje."""
    c = _clip(_load(user, pid), cid)
    out = c["path"] + ".strip.jpg"
    if not os.path.exists(out):
        n = 12
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", c["path"], "-vf",
                        f"fps={n}/{max(0.5, c['duration']):.3f},scale=-2:96,tile={n}x1", "-frames:v", "1", out],
                       capture_output=True)
        if not os.path.exists(out):
            raise HTTPException(500, "Nepavyko paruošti kadrų juostos")
    return FileResponse(out, media_type="image/jpeg")


class ClipOrder(BaseModel):
    order: list[str]


@app.put("/api/projects/{pid}/clips/order")
def reorder_clips(pid: str, body: ClipOrder, user=Depends(current_user)):
    proj = _load(user, pid)
    by_id = {c["id"]: c for c in proj["clips"]}
    proj["clips"] = [by_id[i] for i in body.order if i in by_id] + [c for c in proj["clips"]
                                                                     if c["id"] not in body.order]
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


# ---------- darbai (paruošimas ir video kūrimas fone) ----------
class JobCancelled(BaseException):  # ne Exception – kad jo „nepagautų“ vidiniai „except Exception“
    pass


_cancelled = set()  # naudotojo sustabdyti darbai


def _job_update(jid, **kw):
    """Darbo eiga. Kai darbas sustabdytas, eigos atnaujinimas (iš darbo gijos) nutraukia darbą."""
    if "status" not in kw and jid in _cancelled:
        raise JobCancelled()
    with _jobs_lock:
        _jobs[jid].update(kw)


def _finish_cancelled(jid):
    video_editor.kill_active()  # tos pačios gijos ffmpeg procesai
    _job_update(jid, status="cancelled", message="Sustabdyta")


def _run_job(jid, user, pid, kind, quick, words):
    try:
        proj = _load(user, pid)
        d = _pdir(user, pid)
        client = openai_client(user)
        say = lambda m: _job_update(jid, message=m)  # noqa: E731
        if not proj["clips"]:
            raise ValueError("Pirmiausia įkelkite video ar nuotraukų")
        left = _user_info(user["username"])["minutes_left"]
        if client is not None and proj["settings"]["subtitles"] and left is not None and left <= 0:
            client = None  # minutės baigėsi – titrai be AI atpažinimo
        vo_path, vo_key = None, None
        vo = dict(proj["settings"].get("voiceover") or {})
        vo["voice"] = _voice_for(vo.get("voice"))
        if vo.get("on") and str(vo.get("text", "")).strip():  # 🎙 AI įgarsinimas
            google = str(vo.get("voice", "")).startswith("g:")
            if user["plan"] not in AI_PLANS:
                raise ValueError("AI įgarsinimas – Premium plane.")
            if google and not stock_key("gemini"):
                raise ValueError("Google balsams reikia Google (Gemini) rakto – „Mano projektai“ → Google raktas.")
            if not google and client is None:
                raise ValueError("AI įgarsinimui reikia OpenAI rakto (Premium planas).")
            vo_key = hashlib.sha1((engine.TTS_VERSION + "|" + vo["text"] + "|" + vo.get("voice", "") + "|" +
                                   proj["settings"]["subtitle_language"]).encode()).hexdigest()[:12]
            vo_path = os.path.join(d, f"vo_{vo_key}.mp3")
            if not os.path.exists(vo_path):
                say("Kuriu AI įgarsinimą…")
                try:
                    _voice_quota(user, vo["text"].strip())
                except PermissionError as e:
                    raise ValueError(str(e))
                engine.tts(client, vo["text"].strip(), _voice_for(vo.get("voice")), vo_path,
                           proj["settings"]["subtitle_language"], gemini_key=stock_key("gemini"))
                accounts.add_usage(user["username"], "voice_chars", len(vo["text"].strip()))
        prep = None if kind == "prepare" else _load_prep(user, proj)  # „Atpažinti iš naujo“ – visada iš naujo
        if prep is not None and proj.get("prep_vo") != vo_key:
            prep = None  # įgarsinimas pasikeitė – titrai ir montažas pagal naują
        if prep is not None and client is not None and proj["settings"]["subtitles"] and not proj.get("prep_ai"):
            prep = None  # paruošta dar be AI (pvz. prieš įrašant raktą) – dabar atpažinsim kalbą
        if prep is None:
            prep = engine.prepare(proj["clips"], proj["settings"], d, client, say,
                                  lambda p: _job_update(jid, progress=round(p * (1 if kind == "prepare" else 0.35),
                                                                            3)), vo_path=vo_path)
            proj["prep_vo"] = vo_key
            if prep["analysis"].get("subtitle_mode") in ("voice", "translated"):
                accounts.add_minutes_for(user["username"], prep["analysis"]["info"]["duration"] / 60)
            _save_prep(user, proj, prep)
            proj["prep_ai"] = client is not None
            _save(user, proj)
        if kind == "prepare":
            mode = prep["analysis"].get("subtitle_mode")
            _job_update(jid, status="done", progress=1.0, message="Paruošta",
                        result={"words": proj["words"], "mode": mode,
                                "note": "" if proj["words"] else
                                ("Kalbos neaptikta – patikrinkite, ar įraše girdisi balsas." if client is not None
                                 else "Automatinis atpažinimas neįjungtas – įrašykite titrų tekstą ranka.")})
            return
        if words is None and proj.get("line_texts") and proj.get("lines"):
            words = video_editor.apply_line_edits(
                prep["analysis"]["words"], [(a, b, t) for (a, b, _), t in zip(proj["lines"], proj["line_texts"])])
        base = 0.35
        say("Kuriu video…" if not quick else "Kuriu peržiūrą…")
        name = "preview.mp4" if quick else "reels.mp4"
        out = os.path.join(d, name)
        logo = os.path.join(DATA, "brand", re.sub(r"[^\w.@-]", "_", user["username"]) + "_logo.png")
        broll = [{"path": b["path"], "t": b["t"], "d": b["d"], "mode": b.get("mode", "full"),
                  "pos": b.get("pos", "auto")} for b in proj.get("broll", [])
                 if os.path.exists(b.get("path", ""))]
        if broll:
            say("Dedu intarpus…")
        extra = [] if quick or not proj["settings"].get("all_formats", True) else \
            engine.extra_formats(proj["settings"]["format"])
        share = (1 - base) / (1 + len(extra))  # pagrindinis + kiti formatai
        # tas pats planas (titrų žodžiai, animacijos, efektai) kaip peržiūroje, jei niekas nepasikeitė –
        # galutinis video tada sutampa su tuo, ką vartotojas matė ir girdėjo
        sig = hashlib.sha1(json.dumps([proj["settings"], words, [(c["id"], c.get("trim"), c.get("sound"))
                                                                   for c in proj["clips"]],
                                       prep["src"], os.path.getmtime(prep["src"]), broll, vo_key],
                                      sort_keys=True, default=str).encode()).hexdigest()
        cache = proj.get("plan_cache") or {}
        plan = cache.get("plan") if cache.get("sig") == sig else None
        fin = engine.build(prep, proj["settings"], out, d, client, words=words, quick=quick, broll=broll,
                           progress=lambda p: _job_update(jid, progress=round(base + p * share, 3)),
                           logo=logo if os.path.exists(logo) else None, plan=plan)
        plan = json.loads(json.dumps(fin.get("plan"), default=float))
        result = {"file": name, "duration": fin.get("duration"), "width": fin.get("width"),
                  "height": fin.get("height"), "plan_reused": plan is not None and bool(cache.get("plan"))
                  and cache.get("sig") == sig}
        if not quick:
            say("Kuriu viršelį ir aprašymą…")
            try:
                engine.cover(prep["src"], os.path.join(d, "cover.jpg"), proj["settings"],
                             width=fin.get("width") or 1080, height=fin.get("height") or 1920)
                result["cover"] = "cover.jpg"
            except Exception:
                traceback.print_exc()
            result["caption"] = engine.caption(prep, proj["settings"], client)
            main = proj["settings"]["format"]
            result["formats"] = [{"fmt": main, "file": name, "cover": result.get("cover")}]
            for i, f in enumerate(extra):  # 📐 tas pats video kitais formatais
                say(f"Kuriu {f} formatą…")
                tag = f.replace(":", "x")
                lo = base + share * (1 + i)
                try:
                    src_f = engine.source_for_format(proj["clips"], proj["settings"], d, f, vo_path,
                                                     lambda p: _job_update(jid, progress=round(lo + p * share * 0.3, 3)))
                    st_f = dict(proj["settings"], format=f)
                    engine.build(dict(prep, src=src_f, format=f), st_f, os.path.join(d, f"reels_{tag}.mp4"), d,
                                 client, words=words, broll=broll, logo=logo if os.path.exists(logo) else None,
                                 plan=plan,
                                 progress=lambda p: _job_update(jid, progress=round(lo + share * (0.3 + p * 0.7), 3)))
                    w_, h_ = engine.FORMAT_SIZES.get(f, (1080, 1920))
                    entry = {"fmt": f, "file": f"reels_{tag}.mp4"}
                    try:
                        engine.cover(src_f, os.path.join(d, f"cover_{tag}.jpg"), st_f, width=w_, height=h_)
                        entry["cover"] = f"cover_{tag}.jpg"
                    except Exception:
                        traceback.print_exc()
                    result["formats"].append(entry)
                    if os.path.exists(src_f) and src_f != prep["src"]:
                        os.unlink(src_f)
                except Exception:
                    traceback.print_exc()  # papildomas formatas nepavyko – pagrindinis video vis tiek paruoštas
        proj = _load(user, pid)
        proj["outputs"][("preview" if quick else "final")] = dict(result, at=time.time())
        proj["plan_cache"] = {"sig": sig, "plan": plan}
        _save(user, proj)
        if jid in _cancelled:
            raise JobCancelled()
        _job_update(jid, status="done", progress=1.0, message="Paruošta ✅", result=result)
    except JobCancelled:
        _finish_cancelled(jid)
    except Exception as e:
        if jid in _cancelled:
            _finish_cancelled(jid)
            return
        traceback.print_exc()
        _job_update(jid, status="error", message=str(e)[:300] or type(e).__name__)


class RenderBody(BaseModel):
    quick: bool = False
    words: list | None = None     # pataisyti titrai [[žodis, nuo, iki], ...]
    settings: dict | None = None


class LinesBody(BaseModel):
    lines: list[str]


@app.put("/api/projects/{pid}/lines")
def update_lines(pid: str, body: LinesBody, user=Depends(current_user)):
    """Pataisyti titrų sakiniai (tuščias – sakinys pašalinamas)."""
    proj = _load(user, pid)
    if not proj.get("lines"):
        raise HTTPException(400, "Pirmiausia paruoškite titrus")
    texts = [str(t)[:300] for t in body.lines][:len(proj["lines"])]
    texts += [t for _, _, t in proj["lines"][len(texts):]]
    proj["line_texts"] = None if texts == [t for _, _, t in proj["lines"]] else texts
    _save(user, proj)
    return _public(proj)


# ---------- stilių peržiūros (plytelės) ----------
def _base_frame(user, proj):
    """Pirmo įrašo kadras – pagrindas plytelėms; be įrašų – pavyzdinis kadras."""
    for c in proj["clips"]:
        thumb = c["path"] + ".base.jpg"
        if not os.path.exists(thumb):
            reels_studio.grab_frame(c["path"], thumb, at=0 if c.get("image") else min(1.0, c["duration"] / 2))
        return thumb, c["id"]
    sample = os.path.join(DATA, "sample_frame.jpg")
    if not os.path.exists(sample):
        os.makedirs(DATA, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "gradients=s=360x640:c0=0xE8A060:c1=0x2F6F7F:c2=0xF4D9B0:n=3:x0=0:y0=0:x1=360:y1=640:d=1",
                        "-vf", "drawbox=x=110:y=260:w=140:h=200:color=0x3A2A20:t=fill,"
                               "drawbox=x=150:y=200:w=60:h=60:color=0xF1C9A0:t=fill",
                        "-frames:v", "1", sample], check=True)
    return sample, "sample"


_tile_lock = threading.Lock()


@app.get("/api/projects/{pid}/tile/{kind}")
def tile(pid: str, kind: str, name: str = "", user=Depends(current_user)):
    """Plytelė: kind = template | look | color | effect | live (dabartiniai nustatymai su kabliuku ir titrais)."""
    proj = _load(user, pid)
    st_ = proj["settings"]
    base, bid = _base_frame(user, proj)
    if kind == "template":
        if name not in reels_studio.TEMPLATES:
            raise HTTPException(404, "Nėra tokio šablono")
        t = reels_studio.TEMPLATES[name]
        args = ("style", name, t["accent"], t["color"], (), "Kabliukas", None)
    elif kind == "look":
        if name not in video_editor.SUBTITLE_LOOKS:
            raise HTTPException(404, "Nėra tokio stiliaus")
        args = ("style", st_["template"], st_["accent"], st_["color"], (), "", name)
    elif kind == "color":
        if name not in reels_studio.COLOR_FILTERS:
            raise HTTPException(404, "Nėra tokio filtro")
        args = ("thumb", name, (), st_["accent"])
    elif kind == "effect":
        if name not in reels_studio.EFFECTS:
            raise HTTPException(404, "Nėra tokio efekto")
        args = ("thumb", st_["color"], (name,), st_["accent"])
    elif kind == "live":
        args = ("style", st_["template"], st_["accent"], st_["color"], tuple(st_["effects"]),
                st_["hook"] or "", st_["look"], st_["subs_pos"], st_["hook_pos"], st_["subs_size"], st_["text_size"])
    else:
        raise HTTPException(404, "Nėra tokios plytelės")
    key = hashlib.sha1(json.dumps([bid, args], ensure_ascii=False).encode()).hexdigest()[:16]
    d = os.path.join(_pdir(user, pid), "tiles")
    out = os.path.join(d, key + ".jpg")
    if not os.path.exists(out):
        os.makedirs(d, exist_ok=True)
        with _tile_lock:
            if args[0] == "style":
                extra = {}
                if kind == "live":
                    extra = dict(subs_ypos=reels_studio.SUBTITLE_POSITIONS.get(args[7], 0.72),
                                 hook_ypos=reels_studio.HOOK_POSITIONS.get(args[8], 0.2),
                                 subs_size=args[9] / 100, text_size=args[10] / 100, width=360, height=640)
                reels_studio.style_preview(base, out, args[1], args[2], args[3], args[4], args[5], args[6], **extra)
            else:
                reels_studio.thumbnail(base, out, args[1], args[2], accent=args[3])
    return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.post("/api/projects/{pid}/prepare")
def prepare(pid: str, user=Depends(current_user)):
    return _start(user, pid, "prepare", False, None)


@app.post("/api/projects/{pid}/render")
def render(pid: str, body: RenderBody, user=Depends(current_user)):
    if body.settings:
        update_settings(pid, SettingsBody(settings=body.settings), user)
    words = [(str(w), float(a), float(b)) for w, a, b in body.words] if body.words else None
    return _start(user, pid, "render", body.quick, words)


def _start(user, pid, kind, quick, words, runner=None):
    _load(user, pid)
    with _jobs_lock:  # ankstesnis to paties projekto darbas nebereikalingas – stabdomas (kad nesikauptų eilė)
        for j in _jobs.values():
            if j["user"] == user["username"] and j["project"] == pid and j["kind"] in ("render", "prepare", "auto") \
                    and j["status"] in ("queued", "running"):
                _cancelled.add(j["id"])
                if j["status"] == "queued":
                    j.update(status="cancelled", message="Sustabdyta")
        busy = [j for j in _jobs.values() if j["user"] == user["username"] and j["status"] in ("queued", "running")
                and j["id"] not in _cancelled]
        if len(busy) >= 2:
            raise HTTPException(429, "Palaukite, kol baigsis ankstesnis video (arba sustabdykite jį)")
        jid = uuid.uuid4().hex[:12]
        _jobs[jid] = {"id": jid, "user": user["username"], "project": pid, "kind": kind, "status": "queued",
                      "progress": 0.0, "message": "Eilėje…", "created": time.time(), "result": None}

    def run():
        if jid in _cancelled:
            return
        _job_update(jid, status="running", message="Pradedu…")
        (runner or _run_job)(jid, user, pid, kind, quick, words)
    _pool.submit(run)
    return _jobs[jid]


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: str, user=Depends(current_user)):
    """■ Sustabdyti darbą (eilėje – iškart; vykstantį – per akimirką, nutraukiant ffmpeg)."""
    with _jobs_lock:
        j = _jobs.get(jid)
        if not j or j["user"] != user["username"]:
            raise HTTPException(404, "Darbas nerastas")
        if j["status"] in ("queued", "running"):
            _cancelled.add(jid)
            j.update(status="cancelled" if j["status"] == "queued" else "running", message="Stabdoma…")
            if j["status"] == "cancelled":
                j["message"] = "Sustabdyta"
        return dict(j)


@app.get("/api/jobs/{jid}")
def job(jid: str, user=Depends(current_user)):
    j = _jobs.get(jid)
    if not j or j["user"] != user["username"]:
        raise HTTPException(404, "Darbas nerastas")
    return j


def _zip_formats(user, pid):
    """Visi formatai ir viršeliai viename ZIP (video jau suspausti – laikomi be papildomo glaudinimo)."""
    import zipfile
    proj = _load(user, pid)
    fin = (proj.get("outputs") or {}).get("final") or {}
    d = _pdir(user, pid)
    fname = re.sub(r"[^\w-]+", "_", proj["title"]).strip("_")[:40] or "reels"
    zpath = os.path.join(d, "visi_formatai.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        for f in fin.get("formats") or [{"fmt": proj["settings"]["format"], "file": "reels.mp4", "cover": fin.get("cover")}]:
            tag = f["fmt"].replace(":", "x")
            for key, ext in (("file", "mp4"), ("cover", "jpg")):
                if f.get(key) and os.path.exists(os.path.join(d, f[key])):
                    z.write(os.path.join(d, f[key]), f"{fname}_{tag}{'_virselis' if key == 'cover' else ''}.{ext}")
        cap = fin.get("caption") or {}
        if cap.get("caption"):
            z.writestr(f"{fname}_aprasymas.txt", cap["caption"] + "\n\n" + " ".join(cap.get("hashtags") or []))
    return FileResponse(zpath, filename=f"{fname}_visi_formatai.zip", media_type="application/zip")


@app.get("/api/projects/{pid}/files/{name}")
def download(pid: str, name: str, download: bool = False, user=Depends(current_user)):
    if name == "visi_formatai.zip":
        return _zip_formats(user, pid)
    if not re.fullmatch(r"(preview\.mp4|fxprev_\w+\.mp4|reels(_\d+x\d+)?\.mp4|cover(_\d+x\d+)?\.jpg)", name):
        raise HTTPException(404, "Failas nerastas")
    path = os.path.join(_pdir(user, pid), name)
    if not os.path.exists(path):
        raise HTTPException(404, "Failas dar nesukurtas")
    proj = _load(user, pid)
    fname = re.sub(r"[^\w-]+", "_", proj["title"]).strip("_")[:40] or "reels"
    m = re.search(r"_(\d+x\d+)\.", name)
    tag = "_" + m.group(1) if m else ""
    kind = "_virselis" if name.startswith("cover") else ""
    return FileResponse(path, filename=f"{fname}{tag}{kind}{os.path.splitext(name)[1]}" if download else None,
                        media_type="image/jpeg" if name.endswith(".jpg") else "video/mp4")


@app.get("/api/projects/{pid}/clips/{cid}/thumb")
def clip_thumb(pid: str, cid: str, user=Depends(current_user)):
    proj = _load(user, pid)
    c = next((c for c in proj["clips"] if c["id"] == cid), None)
    if not c:
        raise HTTPException(404, "Įrašas nerastas")
    thumb = c["path"] + ".thumb.jpg"
    if not os.path.exists(thumb):
        reels_studio.grab_frame(c["path"], thumb, at=0 if c.get("image") else min(1.0, c["duration"] / 2))
    return FileResponse(thumb, media_type="image/jpeg")


@app.get("/api/music/{name:path}")
def music_sample(name: str):
    lib = reels_studio.music_library()
    if name not in lib:
        raise HTTPException(404, "Muzika nerasta")
    return FileResponse(lib[name]["path"], media_type="audio/mpeg")


_ = video_editor  # (naudojama engine; importas – kad klaida išryškėtų paleidžiant)


# =====================================================================================================
# 💼 Verslas: el. laiškai (Brevo), slaptažodžio atkūrimas, Stripe prenumeratos
# =====================================================================================================
for _kind in ("brevo", "stripe", "stripe_whsec"):
    def _mk(kind):
        def status(user=Depends(admin_user)):
            return _key_status(kind)

        def save(body: KeyBody, user=Depends(admin_user)):
            return _key_save(kind, body.key)
        app.get(f"/api/admin/{kind}")(status)
        app.post(f"/api/admin/{kind}")(save)
    _mk(_kind)


def _origin(request):
    """Svetainės adresas nuorodoms laiškuose (pagal užklausą – veikia ir su sslip.io, ir su domenu)."""
    o = request.headers.get("origin")
    if o:
        return o.rstrip("/")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost"
    proto = request.headers.get("x-forwarded-proto") or ("https" if "sslip.io" in host or "." in host else "http")
    return f"{proto}://{host}"


def send_mail(to, subject, html_body):
    """El. laiškas per Brevo. Nepavykus – RuntimeError."""
    import urllib.request
    st_ = app_settings()
    key = stock_key("brevo")
    if not key or not st_.get("mail_from"):
        raise RuntimeError("El. laiškų siuntimas neįjungtas")
    body = {"sender": {"email": st_["mail_from"], "name": st_.get("mail_name") or "Reels montavimo studija"},
            "to": [{"email": to}], "subject": subject,
            "htmlContent": f"<div style='font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#1b2333'>"
                           f"{html_body}<p style='color:#888;font-size:12px;margin-top:24px'>Reels montavimo studija</p></div>"}
    req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=json.dumps(body).encode(),
                                 headers={"api-key": key, "Content-Type": "application/json",
                                          "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("message", "")
        except Exception:
            pass
        low = detail.lower()
        if "sender" in low:
            hint = (f"Siuntėjas {st_['mail_from']} nepatvirtintas Brevo. Brevo: Settings → Senders, Domains → "
                    "Senders → Add a sender, tada patvirtinkite nuorodą el. laiške.")
        elif "ip" in low and ("unrecogni" in low or "authori" in low):
            hint = "Brevo blokuoja serverio IP – Security → Authorized IPs pridėkite 2.31.169.169."
        elif "not activated" in low or "activate" in low:
            hint = "Brevo paskyroje dar neaktyvuoti transakciniai laiškai (Transactional) – aktyvuokite arba parašykite Brevo pagalbai."
        elif getattr(e, "code", None) in (401, 403):
            hint = "Brevo nepriima rakto – įklijuokite raktą iš naujo („Transactional email“ teisė – „All“)."
        else:
            hint = "Laiško išsiųsti nepavyko."
        raise RuntimeError(hint + (f" (Brevo: {detail})" if detail else f" ({e})"))


def _mail_bg(to, subject, html_body):
    def run():
        try:
            send_mail(to, subject, html_body)
        except Exception as e:
            print("Laiškas neišsiųstas:", e, file=sys.stderr)
    threading.Thread(target=run, daemon=True).start()


def _esc(x):
    import html as _h
    return _h.escape(str(x or ""))


# ---------- 🔑 Slaptažodžio atkūrimas ----------
_RESETS = os.path.join(DATA, "password_resets.json")


def _resets():
    try:
        with open(_RESETS, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if v["exp"] > time.time()}
    except (OSError, ValueError):
        return {}


def _save_resets(d):
    os.makedirs(DATA, exist_ok=True)
    with open(_RESETS, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.chmod(_RESETS, 0o600)


class ForgotBody(BaseModel):
    email: str


@app.post("/api/password/forgot")
def password_forgot(body: ForgotBody, request: Request):
    """Siunčia nuorodą naujam slaptažodžiui (galioja 1 val.). Atsakymas visada tas pats – neatskleidžiama,
    ar toks el. paštas užregistruotas."""
    st_ = app_settings()
    if not st_["mail"]:
        raise HTTPException(503, "Slaptažodžio atkūrimas el. paštu dar neįjungtas – kreipkitės į studiją"
                                 + (f": {st_['contact']}" if st_.get("contact") else "."))
    email = body.email.strip().lower()
    managed = accounts.managed_users()
    name = email if email in managed else next((n for n, c in managed.items() if c.get("email") == email), None)
    if name and managed[name].get("active", True) is not False:
        token = _secrets.token_urlsafe(32)
        d = _resets()
        d[hashlib.sha256(token.encode()).hexdigest()] = {"user": name, "exp": time.time() + 3600}
        _save_resets(d)
        link = f"{_origin(request)}/#/reset/{token}"
        _mail_bg(managed[name].get("email") or email, "Naujas slaptažodis – Reels montavimo studija",
                 f"<p>Sveiki, {_esc(managed[name].get('name') or name)},</p><p>gavome prašymą pakeisti slaptažodį. "
                 f"Spauskite nuorodą (galioja 1 valandą):</p><p><a href='{link}' style='background:#E39B2E;color:#1c1004;"
                 f"padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold'>Sukurti naują slaptažodį</a>"
                 f"</p><p>Jei to neprašėte – tiesiog ignoruokite šį laišką.</p>")
    time.sleep(0.5)
    return {"ok": True}


class ResetBody(BaseModel):
    token: str
    password: str


@app.post("/api/password/reset")
def password_reset(body: ResetBody):
    if len(body.password) < 8:
        raise HTTPException(400, "Slaptažodis – bent 8 simboliai.")
    d = _resets()
    h = hashlib.sha256(body.token.encode()).hexdigest()
    rec = d.pop(h, None)
    if not rec:
        raise HTTPException(400, "Nuoroda nebegalioja – paprašykite naujos.")
    managed = accounts.managed_users()
    if rec["user"] not in managed:
        raise HTTPException(400, "Paskyra nerasta.")
    managed[rec["user"]]["password_hash"] = accounts.hash_password(body.password)
    managed[rec["user"]].pop("password", None)
    accounts.save_managed_users(managed)
    _save_resets(d)
    return {"token": make_token(rec["user"]), "user": _user_info(rec["user"])}


@app.post("/api/admin/test_mail")
def admin_test_mail(user=Depends(admin_user)):
    to = app_settings().get("biz_email") or app_settings().get("mail_from")
    try:
        send_mail(to, "Bandomasis laiškas – Reels montavimo studija", "<p>El. laiškai veikia ✅</p>")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "to": to}


# ---------- 💳 Stripe prenumeratos ----------
def _stripe(path, data=None, method="POST"):
    import urllib.parse
    import urllib.request
    key = stock_key("stripe")
    if not key:
        raise HTTPException(400, "Mokėjimai neįjungti")
    req = urllib.request.Request("https://api.stripe.com/v1" + path, method=method,
                                 data=urllib.parse.urlencode(data or {}).encode() if method == "POST" else None,
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        detail = getattr(e, "read", lambda: b"")()[:300].decode(errors="ignore")
        print("Stripe klaida:", e, detail, file=sys.stderr)
        raise HTTPException(502, "Mokėjimų sistema šiuo metu nepasiekiama – pabandykite vėliau.")


@app.post("/api/billing/checkout")
def billing_checkout(request: Request, user=Depends(current_user)):
    st_ = app_settings()
    if not st_["billing"]:
        raise HTTPException(400, "Mokėjimai dar neįjungti – kreipkitės į studiją.")
    cfg = accounts.managed_users().get(user["username"])
    if not cfg:
        raise HTTPException(400, "Šiai paskyrai apmokėjimas internetu negalimas – kreipkitės į studiją.")
    o = _origin(request)
    data = {"mode": "subscription", "line_items[0][price]": st_["stripe_price"], "line_items[0][quantity]": "1",
            "success_url": o + "/#/?paid=1", "cancel_url": o + "/#/", "client_reference_id": user["username"],
            "metadata[username]": user["username"], "subscription_data[metadata][username]": user["username"],
            "allow_promotion_codes": "true", "locale": "lt"}
    if cfg.get("stripe_customer"):
        data["customer"] = cfg["stripe_customer"]
    elif cfg.get("email"):
        data["customer_email"] = cfg["email"]
    return {"url": _stripe("/checkout/sessions", data)["url"]}


@app.post("/api/billing/portal")
def billing_portal(request: Request, user=Depends(current_user)):
    cfg = accounts.managed_users().get(user["username"]) or {}
    if not cfg.get("stripe_customer"):
        raise HTTPException(400, "Prenumeratos nėra.")
    return {"url": _stripe("/billing_portal/sessions", {"customer": cfg["stripe_customer"],
                                                        "return_url": _origin(request) + "/#/"})["url"]}


def _stripe_verify(payload, header, secret, tolerance=300):
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    sigs = [v for k, v in (p.split("=", 1) for p in (header or "").split(",") if "=" in p) if k == "v1"]
    t = parts.get("t")
    if not t or not sigs or abs(time.time() - int(t)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s_) for s_ in sigs)


def _set_plan(username, plan, **extra):
    managed = accounts.managed_users()
    if username not in managed:
        return
    managed[username]["plan"] = plan
    if plan == "premium":
        managed[username].pop("trial_until", None)
    managed[username].update({k: v for k, v in extra.items() if v is not None})
    accounts.save_managed_users(managed)


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    """Stripe praneša apie apmokėjimą / prenumeratos pabaigą → planas keičiamas automatiškai."""
    payload = await request.body()
    secret = stock_key("stripe_whsec")
    if not secret or not _stripe_verify(payload, request.headers.get("stripe-signature"), secret):
        raise HTTPException(400, "Neteisingas parašas")
    ev = json.loads(payload)
    obj = (ev.get("data") or {}).get("object") or {}
    kind = ev.get("type", "")
    if kind == "checkout.session.completed":
        name = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("username")
        if name:
            _set_plan(name, "premium", stripe_customer=obj.get("customer"), stripe_subscription=obj.get("subscription"),
                      paid_since=time.time())
            cfg = accounts.managed_users().get(name) or {}
            if cfg.get("email") and app_settings()["mail"]:
                _mail_bg(cfg["email"], "Premium planas įjungtas ⭐",
                         f"<p>Sveiki, {_esc(cfg.get('name') or name)},</p><p>ačiū už apmokėjimą! Jūsų studijoje "
                         "įjungtas <b>Premium</b> planas: titrai iš kalbos, natūralūs lietuviški AI balsai ir AI kadrai.</p>")
    elif kind in ("customer.subscription.deleted", "customer.subscription.updated"):
        if kind == "customer.subscription.deleted" or obj.get("status") in ("canceled", "unpaid", "incomplete_expired"):
            name = (obj.get("metadata") or {}).get("username")
            if not name:
                name = next((n for n, c in accounts.managed_users().items()
                             if c.get("stripe_subscription") == obj.get("id")), None)
            if name:
                _set_plan(name, "basic", stripe_subscription="")
    return {"received": True}


# ---------- 💬 AI režisierius: pataisymai paprastais žodžiais ----------
DIRECTOR_SETTINGS = ("look", "template", "accent", "color", "music", "music_volume", "speed", "transition", "hook",
                     "cta", "handle", "subs_pos", "subs_size", "length", "progress_bar", "subtitles", "key_words")


def _director_tools():
    s = lambda d, **p: {"type": "function", "function": {"name": d[0], "description": d[1],  # noqa: E731
                                                          "parameters": {"type": "object", "properties": p,
                                                                         "required": d[2] if len(d) > 2 else []}}}
    st, num, intg = {"type": "string"}, {"type": "number"}, {"type": "integer"}
    return [
        s(("update_style", "Change the look of the whole video. Only pass fields to change. Values must come from "
                           "the options list."), look=st, template=st, accent=st, color=st, music=st,
          music_volume=intg, speed=num, transition=st, hook=st, cta=st, handle=st, subs_pos=st, subs_size=intg,
          length=st, progress_bar=st, subtitles={"type": "boolean"}, key_words={"type": "boolean"},
          effects_add={"type": "array", "items": st}, effects_remove={"type": "array", "items": st}),
        s(("set_voiceover", "Set AI voiceover text and/or voice (whole video). on=false turns it off."),
          text=st, voice=st, on={"type": "boolean"}),
        s(("replace_scene", "Replace the visual of one scene with a different free stock video found by an English "
                            "search query (1-3 concrete visual words).", ["clip_id", "query"]), clip_id=st, query=st),
        s(("remove_scene", "Remove a scene (clip) from the video.", ["clip_id"]), clip_id=st),
        s(("move_scene", "Move a scene to a new position (0 = first).", ["clip_id", "position"]),
          clip_id=st, position=intg),
        s(("trim_scene", "Keep only part of a scene (seconds within the clip).", ["clip_id", "start", "end"]),
          clip_id=st, start=num, end=num),
        s(("scene_music", "Give one scene its own music track from the library, or track=null to remove.",
           ["clip_id"]), clip_id=st, track={"type": ["string", "null"]}, volume=intg),
        s(("edit_subtitle", "Change the text of one subtitle line (index from the list).", ["index", "text"]),
          index=intg, text=st),
        s(("no_change", "Use ONLY when the request needs no change (a question) or is impossible. reason – short "
                        "explanation in Lithuanian.", ["reason"]), reason=st),
        s(("ai_scene", "Create a NEW AI-generated shot (Google, high quality) for a scene. Use when the user asks for "
                       "AI/generated/exact visuals, or when replace_scene reports no high-quality stock video. "
                       "prompt – one vivid English shot description (subject, action, setting, light, camera).",
           ["clip_id", "prompt"]), clip_id=st, prompt=st),
    ]


def _director_state(proj):
    s_ = proj["settings"]
    clips = []
    for i, c in enumerate(proj["clips"]):
        used = (c["trim"][1] - c["trim"][0]) if c.get("trim") else (None if c.get("image") else c["duration"])
        clips.append({"clip_id": c["id"], "position": i, "name": c.get("name"), "photo": bool(c.get("image")),
                      "seconds": round(used, 1) if used else None, "full_seconds": round(c["duration"], 1),
                      "scene_text": c.get("scene"), "stock_query": c.get("query"),
                      "own_sound": (c.get("sound") or {}).get("track") or (c.get("sound") or {}).get("kind")})
    subs = None
    if proj.get("lines"):
        texts = proj.get("line_texts") or [t for _, _, t in proj["lines"]]
        subs = [[i, round(a, 1), t] for i, ((a, _b, _t), t) in enumerate(zip(proj["lines"], texts))]
    return {"settings": {k: s_.get(k) for k in DIRECTOR_SETTINGS + ("effects",)},
            "voiceover": s_.get("voiceover"), "scenes": clips, "subtitles": subs}


def _director_options():
    o = engine.options()
    return {"looks": {k: v["title"] for k, v in video_editor.SUBTITLE_LOOKS.items()},
            "templates": list(o["templates"]), "accents": list(reels_studio.ACCENTS), "colors": o["colors"],
            "music": list(o["music"]), "transitions": o["transitions"], "effects": list(reels_studio.EFFECTS),
            "subs_pos": list(reels_studio.SUBTITLE_POSITIONS), "length": list(reels_studio.LENGTHS),
            "progress_bar": ["Viršuje", "Apačioje", "Nėra"],
            "voices": {**engine.GEMINI_VOICES, **engine.VOICES}}


DIRECTOR_AI_MAX = 3  # daugiausia AI kadrų vienai AI režisieriaus žinutei


def _director_queue_ai(user, clip, prompt, queue):
    """AI kadras scenai – įrašomas į eilę (sukuriamas fone po atsakymo), jei leidžia limitai ir raktas."""
    if any(q["clip_id"] == clip["id"] for q in queue):
        return "ok, AI shot already queued for this scene"
    if not stock_key("gemini"):
        return "error: no high-quality stock video found and AI shots are not available (no Google key)"
    lft = accounts.left(user["username"], "ai_clips")
    if lft is not None and lft - len(queue) < 1:
        return "error: no high-quality stock video found and the monthly AI shot limit is used up"
    if len(queue) >= DIRECTOR_AI_MAX:
        return f"error: at most {DIRECTOR_AI_MAX} AI shots per message – ask the user to continue in the next message"
    queue.append({"clip_id": clip["id"], "prompt": prompt, "name": clip.get("name")})
    return "ok, a high-quality AI shot will be generated for this scene (1-3 min, uses 1 AI shot)"


def _run_director_ai(jid, user, pid, queue):
    """AI kadrai po AI režisieriaus atsakymo – vienas po kito (kiekvienas skaičiuojamas į AI kadrų limitą)."""
    done = 0
    for i, q in enumerate(queue):
        _job_update(jid, message=f"Kuriamas AI kadras {i + 1}/{len(queue)}: „{q['name']}“…",
                    progress=round(i / len(queue), 2))
        sub = uuid.uuid4().hex[:12]
        with _jobs_lock:
            _jobs[sub] = {"id": sub, "user": user["username"], "project": pid, "kind": "veo_part", "status": "running",
                          "progress": 0.0, "message": "", "created": time.time(), "result": None}
        _run_veo(sub, user, pid, VeoBody(prompt=q["prompt"], replace=q["clip_id"]))
        if _jobs[sub]["status"] != "done":
            msg = _jobs[sub].get("message") or "nepavyko"
            _job_update(jid, status="error" if not done else "done", progress=1.0,
                        message=(f"Sukurta {done} AI kadr. Kitas nepavyko: {msg}" if done else msg))
            return
        done += 1
    _job_update(jid, status="done", progress=1.0, message=f"Sukurta AI kadrų: {done} ✅")


def _director_exec(user, pid, name, a, proposals):
    """Vienas AI režisieriaus veiksmas. Grąžina trumpą rezultatą (tekstas AI'ui)."""
    proj = _load(user, pid)
    clip = next((c for c in proj["clips"] if c["id"] == a.get("clip_id")), None)
    need_clip = name in ("replace_scene", "remove_scene", "move_scene", "trim_scene", "scene_music", "ai_scene")
    if need_clip and clip is None:
        return "error: no such clip_id"
    if name == "update_style":
        patch = {k: a[k] for k in DIRECTOR_SETTINGS if k in a and a[k] is not None}
        if "template" in patch and patch["template"] in reels_studio.TEMPLATES:
            t = reels_studio.TEMPLATES[patch["template"]]
            patch.setdefault("accent", t["accent"])
            patch.setdefault("color", t["color"])
            if t.get("look"):
                patch.setdefault("look", t["look"])
            if t.get("effects"):
                a["effects_add"] = list(a.get("effects_add") or []) + t["effects"]
        if a.get("effects_add") or a.get("effects_remove"):
            eff = [e for e in proj["settings"].get("effects", []) if e not in (a.get("effects_remove") or [])]
            eff += [e for e in (a.get("effects_add") or []) if e in reels_studio.EFFECTS and e not in eff]
            patch["effects"] = eff
        if not patch:
            return "nothing changed"
        update_settings(pid, SettingsBody(settings=patch), user)
        new = _load(user, pid)["settings"]
        bad = [k for k in patch if k != "effects" and new.get(k) != patch[k]]
        return "ok" + (f"; invalid values ignored for: {bad}" if bad else "")
    if name == "set_voiceover":
        vo = dict(proj["settings"].get("voiceover") or {})
        if a.get("text") is not None:
            vo["text"] = str(a["text"])[:4000]
            vo["on"] = True
        if a.get("voice"):
            if a["voice"] not in engine.VOICES and a["voice"] not in engine.GEMINI_VOICES:
                return "error: unknown voice"
            vo["voice"] = a["voice"]
        if a.get("on") is not None:
            vo["on"] = bool(a["on"])
        if vo.get("on") and user["plan"] not in AI_PLANS:
            return "error: AI voiceover needs Premium"
        update_settings(pid, SettingsBody(settings={"voiceover": vo}), user)
        return "ok"
    if name == "replace_scene":
        if clip.get("image"):
            return "error: this scene is the user's photo – do not replace own material"
        if not clip.get("auto"):
            return "error: this is the user's own video – suggest it instead of replacing"
        provider = stock_provider()
        if not provider:
            return "error: stock video key missing"
        want = (clip["trim"][1] - clip["trim"][0]) if clip.get("trim") else clip["duration"]
        best = _pick_stock(str(a["query"])[:60], proj["settings"]["format"], provider, want,
                           set(_stock_used(user)), openai_client(user), clip.get("scene") or "", min_score=8)
        if not best:  # kokybiško nemokamo kadro nėra – AI sukurs naują
            return _director_queue_ai(user, clip, clip.get("visual") or a["query"], proposals)
        src, _ = stock_download(user, pid, provider, best["id"], proj["settings"]["format"])
        path = os.path.join(_pdir(user, pid), "clips", clip["id"] + "_" + uuid.uuid4().hex[:4] + ".mp4")
        if engine._ffmpeg(["-i", src, "-an", "-c:v", "copy", path]).returncode != 0:
            shutil.copy(src, path)
        new = engine.add_clip(path, f"🎞 {a['query']}")
        new.update(id=clip["id"], auto=True, scene=clip.get("scene"), visual=clip.get("visual"), query=a["query"])
        if want < new["duration"] - 0.05:
            new["trim"] = [0.0, round(want, 3)]
        if clip.get("sound"):
            new["sound"] = clip["sound"]
        if clip["path"].startswith(_pdir(user, pid)) and os.path.exists(clip["path"]):
            os.unlink(clip["path"])
        _stock_used_add(user, [(provider, best["id"])])
        proj["clips"] = [new if c["id"] == clip["id"] else c for c in proj["clips"]]
        proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
        _save(user, proj)
        return f"ok, new clip {round(new['duration'], 1)} s"
    if name == "remove_scene":
        if len(proj["clips"]) <= 1:
            return "error: cannot remove the last scene"
        delete_clip(pid, clip["id"], user)
        return "ok"
    if name == "move_scene":
        order = [c["id"] for c in proj["clips"] if c["id"] != clip["id"]]
        order.insert(max(0, min(len(order), int(a["position"]))), clip["id"])
        proj["clips"] = [next(c for c in proj["clips"] if c["id"] == i) for i in order]
        proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
        _save(user, proj)
        return "ok"
    if name == "trim_scene":
        if clip.get("image"):
            return "error: photos cannot be trimmed"
        trim_clip(pid, clip["id"], TrimBody(start=float(a["start"]), end=float(a["end"])), user)
        return "ok"
    if name == "scene_music":
        if a.get("track"):
            clip_sound(pid, clip["id"], SoundBody(kind="music", track=a["track"], volume=int(a.get("volume") or 60),
                                                  orig=(clip.get("sound") or {}).get("orig", 100)), user)
        else:
            clip_sound(pid, clip["id"], SoundBody(kind="none"), user)
        return "ok"
    if name == "edit_subtitle":
        if not proj.get("lines"):
            return "error: subtitles are not prepared yet – they will be after the next preview"
        texts = proj.get("line_texts") or [t for _, _, t in proj["lines"]]
        i = int(a["index"])
        if not 0 <= i < len(texts):
            return "error: bad index"
        texts[i] = str(a["text"])[:300]
        update_lines(pid, LinesBody(lines=texts), user)
        return "ok"
    if name == "no_change":
        return "ok, nothing changed"
    if name == "ai_scene":
        if not clip.get("auto") and not clip.get("ai_scene"):
            return "error: this is the user's own video/photo – do not replace own material"
        return _director_queue_ai(user, clip, str(a["prompt"])[:400], proposals)
    return "error: unknown tool"


DIRECTOR_MODELS = ("gpt-4.1", "gpt-4.1-mini", "gpt-4o-mini")  # patikimiausias pirmas – režisierius turi tikrai atlikti


def _director_describe(name, a):
    """Žmogui suprantamas atlikto veiksmo aprašymas (rodomas po atsakymu – matosi, kas tikrai padaryta)."""
    if name == "update_style":
        lab = {"look": "titrų stilius", "template": "šablonas", "accent": "akcento spalva", "color": "spalvos",
               "music": "muzika", "music_volume": "muzikos garsumas", "speed": "greitis", "transition": "perėjimai",
               "hook": "užrašas pradžioje", "cta": "užrašas pabaigoje", "handle": "paskyros vardas",
               "subs_pos": "titrų vieta", "subs_size": "titrų dydis", "length": "trukmė", "progress_bar": "juostelė",
               "subtitles": "titrai", "key_words": "raktiniai žodžiai"}
        parts = [f"{lab[k]}: „{a[k]}“" if isinstance(a[k], str) else f"{lab[k]}: {a[k]}"
                 for k in lab if k in a and a[k] is not None]
        if a.get("effects_add"):
            parts.append("efektai + " + ", ".join(a["effects_add"]))
        if a.get("effects_remove"):
            parts.append("efektai − " + ", ".join(a["effects_remove"]))
        return "🎨 " + "; ".join(parts) if parts else ""
    return {"set_voiceover": "🎙 įgarsinimas" + (f": „{str(a.get('text', ''))[:80]}…“" if a.get("text") else " pakeistas"),
            "replace_scene": f"🎞 scenos vaizdas pakeistas („{a.get('query', '')}“)",
            "remove_scene": "🗑 scena pašalinta", "move_scene": "↕ scena perkelta", "trim_scene": "✂ scena apkarpyta",
            "scene_music": "🎵 scenos muzika" + (f": {a.get('track')}" if a.get("track") else " pašalinta"),
            "edit_subtitle": f"💬 titras pataisytas: „{str(a.get('text', ''))[:60]}“"}.get(name, "")


class DirectorBody(BaseModel):
    message: str


@app.get("/api/projects/{pid}/director")
def director_history(pid: str, user=Depends(current_user)):
    return {"messages": _load(user, pid).get("director", [])[-40:],
            "left": accounts.left(user["username"], "director")}


@app.post("/api/projects/{pid}/director")
def director(pid: str, body: DirectorBody, user=Depends(current_user)):
    """💬 AI režisierius: klientas paprastais žodžiais sako, ką pakeisti – AI pats atlieka pakeitimus."""
    msg = body.message.strip()[:1500]
    if not msg:
        raise HTTPException(400, "Parašykite, ką pakeisti.")
    client = openai_client(user)
    if client is None:
        raise HTTPException(400, "AI režisierius – Premium funkcija.")
    lft = accounts.left(user["username"], "director")
    if lft is not None and lft < 1:
        raise HTTPException(400, "Šio mėnesio AI režisieriaus žinučių limitas išnaudotas.")
    proj = _load(user, pid)
    if not proj["clips"]:
        raise HTTPException(400, "Pirmiausia sukurkite video arba įkelkite medžiagą.")
    history = proj.get("director", [])[-10:]
    lang = video_editor.LANGUAGES.get(proj["settings"]["subtitle_language"], "Lithuanian")
    system = (
        "You are the AI video director inside a Lithuanian Reels editing studio. The user tells you in plain words "
        "what to change in their short video; you make the changes with the tools, then reply briefly (1-3 short "
        f"sentences, in Lithuanian, friendly) what you changed. Use only values from OPTIONS. Scenes are clips in "
        "order. For better visuals use replace_scene (it accepts only high-quality free stock and, if none exists, "
        "automatically creates an AI shot); use ai_scene directly when the user asks for AI/generated/exact visuals. To shorten the video, set 'length' and/or shorten the voiceover text and "
        "remove or trim scenes. Never invent clip ids. If something cannot be done, say so and suggest how. "
        "On-screen texts: 'hook' is the big text at the START, 'cta' is the call-to-action text shown on screen at "
        "the END (e.g. 'Parašykite mums žinutę!', 'Registruokitės: www…'). When the user asks to add an invitation, "
        "call to action, website or text at the end – set 'cta' (keep it short, max ~6 words); if the voiceover is "
        "on, also add the invitation as the last sentence of the voiceover text. You MUST call tools to change "
        "anything – never claim a change you did not make with a tool. "
        f"Voiceover text must be in {lang} with perfect grammar.\nOPTIONS: "
        + json.dumps(_director_options(), ensure_ascii=False))
    messages = [{"role": "system", "content": system}]
    for h in history:
        messages.append({"role": h["role"], "content": h["text"]})
    messages.append({"role": "user", "content": "PROJECT: " + json.dumps(_director_state(proj), ensure_ascii=False)
                     + "\n\nREQUEST: " + msg})
    tools, actions, proposals, reply = _director_tools(), [], [], ""
    model = None
    descr = []
    for step in range(8):
        r, err = None, None
        for m in ([model] if model else DIRECTOR_MODELS):
            try:
                r = client.chat.completions.create(model=m, temperature=0.2, messages=messages, tools=tools,
                                                   tool_choice="required" if step == 0 else "auto")
                model = m
                break
            except Exception as e:
                err = e
        if r is None:
            raise HTTPException(502, f"AI neatsakė: {err}")
        m_ = r.choices[0].message
        calls = getattr(m_, "tool_calls", None) or []
        if not calls:
            reply = (m_.content or "").strip()
            break
        messages.append({"role": "assistant", "content": m_.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                        for c in calls]})
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except ValueError:
                args = {}
            try:
                res = _director_exec(user, pid, c.function.name, args, proposals)
            except HTTPException as e:
                res = "error: " + str(e.detail)
            except Exception as e:
                traceback.print_exc()
                res = "error: " + str(e)[:200]
            if res.startswith("ok") and c.function.name != "no_change":
                actions.append(c.function.name)
                d_ = _director_describe(c.function.name, args)
                if d_:
                    descr.append(d_)
            messages.append({"role": "tool", "tool_call_id": c.id, "content": res})
    accounts.add_usage(user["username"], "director", 1)
    proj = _load(user, pid)
    reply = reply or ("Atlikta." if actions else "Nieko nepakeičiau – patikslinkite, ką norite pakeisti.")
    if not actions and re.search(r"(pridėjau|pakeičiau|pakeista|pridėta|atlikta|sutrumpinau|nustačiau)", reply, re.I):
        reply += "\n\n⚠ Pakeitimų iš tikrųjų nepadariau – pabandykite parašyti konkrečiau."
    proj["director"] = (proj.get("director", []) + [{"role": "user", "text": msg},
                                                     {"role": "assistant", "text": reply, "done": descr}])[-40:]
    _save(user, proj)
    ai_job = None
    if proposals:  # AI kadrai – fone, vienas po kito
        with _jobs_lock:
            jid = uuid.uuid4().hex[:12]
            _jobs[jid] = {"id": jid, "user": user["username"], "project": pid, "kind": "veo", "status": "running",
                          "progress": 0.0, "message": "Ruošiu AI kadrus…", "created": time.time(), "result": None}
        threading.Thread(target=_run_director_ai, args=(jid, user, pid, list(proposals)), daemon=True).start()
        ai_job = _jobs[jid]
        descr.append(f"✨ kuriama AI kadrų: {len(proposals)} (1–3 min. kiekvienas)")
    return {"reply": reply, "actions": actions, "done": descr, "proposals": [], "ai_job": ai_job,
            "project": _public(proj),
            "preview": bool(actions), "left": accounts.left(user["username"], "director")}



# ---------- 🪄 Automatinis montažas ----------
import automontage  # noqa: E402

AUTO_SETTINGS = {"remove_silence": True, "punch": True, "key_words": True, "jcut": True, "ducking": True}


def _run_auto(jid, user, pid, kind, quick, words):
    """Automatinis montažas taikomas redaguojamai kopijai: pradinė versija išsaugoma (galima grįžti), klipų
    eilė nekeičiama; po to iškart sukuriama peržiūra."""
    try:
        proj = _load(user, pid)
        if not proj["clips"]:
            raise ValueError("Pirmiausia įkelkite video ar nuotraukų")
        _job_update(jid, message="Analizuoju kalbą, veiksmą ir muziką…", progress=0.02)
        if not proj.get("original"):
            proj["original"] = {"clips": json.loads(json.dumps(proj["clips"])),
                                "settings": json.loads(json.dumps(proj["settings"])), "at": time.time()}
        lib = reels_studio.music_library()
        music = proj["settings"].get("music")
        cuts, beat = automontage.plan(proj["clips"], lib[music]["path"] if music in lib else None)
        by_id = {c["id"]: c for c in proj["clips"]}
        notes = []
        for cut in cuts:
            c = by_id.get(cut["id"])
            if not c:
                continue
            a, b = cut["trim"]
            c["trim"] = None if a <= 0.01 and b >= c["duration"] - 0.01 else [a, b]
            notes.append(f"„{c.get('name', '')}“: {cut['why']} ({b - a:.1f} s)")
        proj["settings"] = engine.settings_with_defaults(dict(proj["settings"], **AUTO_SETTINGS))
        if proj["settings"].get("music"):
            notes.append("Muzika kalbant automatiškai patyla" + (f"; taktas ≈ {60 / beat:.0f} BPM" if beat else ""))
        notes.append("Svarbiausi žodžiai paryškinami priartinimu, kito kadro garsas prasideda truputį anksčiau")
        proj["auto_notes"] = notes
        proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
        _save(user, proj)
        _job_update(jid, message="Kuriu sumontuotą peržiūrą…", progress=0.1)
        _run_job(jid, user, pid, "render", True, None)
    except Exception as e:
        traceback.print_exc()
        _job_update(jid, status="error", message=str(e)[:300])


@app.post("/api/projects/{pid}/auto_edit")
def auto_edit(pid: str, user=Depends(current_user)):
    return _start(user, pid, "auto", True, None, runner=_run_auto)


@app.post("/api/projects/{pid}/auto_edit/revert")
def auto_edit_revert(pid: str, user=Depends(current_user)):
    """↩ Grįžti prie pradinės versijos (prieš automatinį montažą): klipų kirpimai, eilė ir nustatymai."""
    proj = _load(user, pid)
    orig = proj.get("original")
    if not orig:
        raise HTTPException(400, "Pradinės versijos nėra – automatinis montažas dar nedarytas")
    now = {c["id"]: c for c in proj["clips"]}
    clips = [dict(now[c["id"]], trim=c.get("trim"), sound=c.get("sound")) for c in orig["clips"] if c["id"] in now]
    clips += [c for c in proj["clips"] if c["id"] not in {x["id"] for x in orig["clips"]}]  # vėliau įkelti
    proj["clips"], proj["settings"] = clips, engine.settings_with_defaults(orig["settings"])
    for k in ("original", "auto_notes", "plan_cache"):
        proj.pop(k, None)
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


class FxPreviewBody(BaseModel):
    kind: str
    t: float


def _run_fx_preview(jid, user, pid, kind, t, _words):
    """👁 Trumpa efekto peržiūra: peržiūros video atkarpa nuo pasirinktos vietos su vienu efektu."""
    try:
        import fxpack
        d = _pdir(user, pid)
        src = os.path.join(d, "preview.mp4")
        if not os.path.exists(src):
            raise ValueError("Pirmiausia sukurkite peržiūrą – efektas rodomas ant jos")
        proj = _load(user, pid)
        dur = video_editor.probe(src)["duration"]
        length = fxpack.LEN.get(kind, 2.5) + 0.5
        t0 = max(0.0, min(float(t), dur - 1.0))
        seg = os.path.join(d, f"fxseg_{jid}.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t0:.3f}", "-i", src, "-t", f"{length:.3f}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", seg], check=True)
        words = [tuple(w) for w in ((proj.get("plan_cache") or {}).get("plan") or {}).get("words") or []]
        speed = float(proj["settings"].get("speed") or 1.0)
        g = engine.timeline_item({"kind": kind, "t": t0}, words, speed)
        g["t"] = 0.05
        _job_update(jid, message="Kuriu efekto peržiūrą…", progress=0.3)
        out = os.path.join(d, f"fxprev_{kind}.mp4")
        reels_studio.finish(seg, out, anims={"gfx": [g]}, color="Natūralios", effects=(), progress_bar="Ne",
                            preview=True, accent=proj["settings"].get("accent") or "Auksas")
        os.unlink(seg)
        _job_update(jid, status="done", progress=1.0, message="Paruošta",
                    result={"file": os.path.basename(out), "kind": kind, "t": round(t0, 2), "text": g.get("text")})
    except Exception as e:
        traceback.print_exc()
        _job_update(jid, status="error", message=str(e)[:300])


@app.post("/api/projects/{pid}/fx_preview")
def fx_preview(pid: str, body: FxPreviewBody, user=Depends(current_user)):
    import fxpack
    if body.kind not in fxpack.TIMELINE_KINDS:
        raise HTTPException(400, "Šio efekto negalima dėti į laiko juostą")
    jid = uuid.uuid4().hex[:12]
    _load(user, pid)
    with _jobs_lock:
        _jobs[jid] = {"id": jid, "user": user["username"], "project": pid, "kind": "fxprev", "status": "running",
                      "progress": 0.0, "message": "Ruošiu efekto peržiūrą…", "created": time.time(), "result": None}
    _pool.submit(_run_fx_preview, jid, user, pid, body.kind, body.t, None)
    return _jobs[jid]
