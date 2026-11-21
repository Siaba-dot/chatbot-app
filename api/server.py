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
        if c["path"].startswith(_pdir(user, pid)) and os.path.exists(c["path"]):
            os.unlink(c["path"])
    proj["clips"] = [c for c in proj["clips"] if c["id"] != cid]
    proj["prepared"], proj["words"], proj["lines"], proj["line_texts"] = False, None, None, None
    _save(user, proj)
    return _public(proj)


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
def _job_update(jid, **kw):
    with _jobs_lock:
        _jobs[jid].update(kw)


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
        prep = None if kind == "prepare" else _load_prep(user, proj)  # „Atpažinti iš naujo“ – visada iš naujo
        if prep is not None and client is not None and proj["settings"]["subtitles"] and not proj.get("prep_ai"):
            prep = None  # paruošta dar be AI (pvz. prieš įrašant raktą) – dabar atpažinsim kalbą
        if prep is None:
            prep = engine.prepare(proj["clips"], proj["settings"], d, client, say,
                                  lambda p: _job_update(jid, progress=round(p * (1 if kind == "prepare" else 0.35),
                                                                            3)))
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
        fin = engine.build(prep, proj["settings"], out, d, client, words=words, quick=quick,
                           progress=lambda p: _job_update(jid, progress=round(base + p * (1 - base), 3)),
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
        proj = _load(user, pid)
        proj["outputs"][("preview" if quick else "final")] = dict(result, at=time.time())
        _save(user, proj)
        _job_update(jid, status="done", progress=1.0, message="Paruošta ✅", result=result)
    except Exception as e:
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
    with _jobs_lock:
        busy = [j for j in _jobs.values() if j["user"] == user["username"] and j["status"] in ("queued", "running")]
        if len(busy) >= 2:
            raise HTTPException(429, "Palaukite, kol baigsis ankstesnis video")
        jid = uuid.uuid4().hex[:12]
        _jobs[jid] = {"id": jid, "user": user["username"], "project": pid, "kind": kind, "status": "queued",
                      "progress": 0.0, "message": "Eilėje…", "created": time.time(), "result": None}

    def run():
        _job_update(jid, status="running", message="Pradedu…")
        _run_job(jid, user, pid, kind, quick, words)
    _pool.submit(run)
    return _jobs[jid]


@app.get("/api/jobs/{jid}")
def job(jid: str, user=Depends(current_user)):
    j = _jobs.get(jid)
    if not j or j["user"] != user["username"]:
        raise HTTPException(404, "Darbas nerastas")
    return j


@app.get("/api/projects/{pid}/files/{name}")
def download(pid: str, name: str, download: bool = False, user=Depends(current_user)):
    if name not in ("preview.mp4", "reels.mp4", "cover.jpg"):
        raise HTTPException(404, "Failas nerastas")
    path = os.path.join(_pdir(user, pid), name)
    if not os.path.exists(path):
        raise HTTPException(404, "Failas dar nesukurtas")
    proj = _load(user, pid)
    fname = re.sub(r"[^\w-]+", "_", proj["title"]).strip("_")[:40] or "reels"
    return FileResponse(path, filename=f"{fname}{os.path.splitext(name)[1]}" if download else None,
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
