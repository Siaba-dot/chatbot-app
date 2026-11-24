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

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile  # noqa: E402
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
    plan = str(cfg.get("plan", "basic")).lower()
    plan = plan if plan in ("basic", "premium", "admin") else "basic"
    minutes = None if plan == "admin" else float(cfg.get("minutes", accounts.DEFAULT_MINUTES))
    left = None if minutes is None else max(0.0, minutes - accounts.used_minutes(username))
    return {"username": username, "name": cfg.get("name") or username, "plan": plan,
            "plan_title": accounts.PLANS[plan], "ai": plan in AI_PLANS and bool(clips_ui.configured_key()),
            "pexels": bool(stock_provider()), "stock": STOCK.get(stock_provider() or "", ""),
            "gemini": plan in AI_PLANS and bool(stock_key("gemini")),
            "veo": plan in AI_PLANS and bool(stock_key("gemini")),
            "minutes_left": left}


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
    env = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY", "gemini": "GEMINI_API_KEY"}[provider]
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
            "url": v.get("pageURL")}


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
                      "safesearch": "true"})
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


def _key_status(provider):
    k = stock_key(provider)
    return {"set": bool(k), "tail": k[-4:] if k else ""}


def _key_save(provider, key):
    key = key.strip()
    if key:  # patikrinam prieš išsaugant
        if provider == "gemini":
            _http_json("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                       {"x-goog-api-key": key}, "Google (Gemini)")
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
        engine.veo_generate(key, prompt, "16:9" if fmt == "16:9" else "9:16", path,
                            status=lambda m: _job_update(jid, message=m, progress=0.15))
        _job_update(jid, message="Dedu kadrą į projektą…", progress=0.9)  # sustabdžius – čia nutrūksta
        thumb = path + ".thumb.jpg"
        reels_studio.grab_frame(path, thumb, at=1.0)
        _library_add(user, path, body.prompt, fmt)  # 📚 kad būtų galima naudoti ir kituose Reels'uose
        proj = _load(user, pid)
        if body.as_clip:
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


@app.post("/api/projects/{pid}/voiceover_preview")
def voiceover_preview(pid: str, user=Depends(current_user)):
    """▶ Išklausyti tikrąjį įgarsinimą (tas pats failas bus naudojamas video – antrą kartą nemokama)."""
    proj = _load(user, pid)
    vo = proj["settings"].get("voiceover") or {}
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
            engine.tts(client, text, vo.get("voice", "coral"), path, proj["settings"]["subtitle_language"],
                       gemini_key=stock_key("gemini"))
        except RuntimeError as e:
            raise HTTPException(400, str(e))
    return {"file": f"vo_{key}.mp3", "text": text, "voice": vo.get("voice")}


@app.get("/api/projects/{pid}/voiceover/{name}")
def voiceover_file(pid: str, name: str, user=Depends(current_user)):
    if not re.fullmatch(r"vo_[a-f0-9]{12}\.mp3", name):
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


def _public(proj):
    """Projekto vaizdas naršyklei – be vidinių failų kelių."""
    p = dict(proj)
    p["clips"] = [{k: v for k, v in c.items() if k not in ("path",)} for c in proj.get("clips", [])]
    p["broll"] = [{k: v for k, v in b.items() if k not in ("path",)} for b in proj.get("broll", [])]
    p.setdefault("prepared", False)
    p.setdefault("words", None)
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
        vo = proj["settings"].get("voiceover") or {}
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
                engine.tts(client, vo["text"].strip(), vo.get("voice", "coral"), vo_path,
                           proj["settings"]["subtitle_language"], gemini_key=stock_key("gemini"))
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
        fin = engine.build(prep, proj["settings"], out, d, client, words=words, quick=quick, broll=broll,
                           progress=lambda p: _job_update(jid, progress=round(base + p * share, 3)),
                           logo=logo if os.path.exists(logo) else None)
        result = {"file": name, "duration": fin.get("duration"), "width": fin.get("width"),
                  "height": fin.get("height")}
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


def _start(user, pid, kind, quick, words):
    _load(user, pid)
    with _jobs_lock:  # ankstesnis to paties projekto darbas nebereikalingas – stabdomas (kad nesikauptų eilė)
        for j in _jobs.values():
            if j["user"] == user["username"] and j["project"] == pid and j["kind"] in ("render", "prepare") \
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
        _run_job(jid, user, pid, kind, quick, words)
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
    if not re.fullmatch(r"(preview\.mp4|reels(_\d+x\d+)?\.mp4|cover(_\d+x\d+)?\.jpg)", name):
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


@app.get("/api/music/{name}")
def music_sample(name: str):
    lib = reels_studio.music_library()
    if name not in lib:
        raise HTTPException(404, "Muzika nerasta")
    return FileResponse(lib[name]["path"], media_type="audio/mpeg")


_ = video_editor  # (naudojama engine; importas – kad klaida išryškėtų paleidžiant)
