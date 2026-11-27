"""Bendras testų paruošimas: atskiras duomenų aplankas, bandomieji vartotojai ir video, išorinių paslaugų imitacijos.

Paleisti:  python -m pytest -q
Išorinės paslaugos (OpenAI, Google, Pixabay, Stripe, Brevo) niekada nekviečiamos – jos imituojamos.
"""
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = tempfile.mkdtemp(prefix="reels-test-data-")
os.environ["REELS_DATA_DIR"] = _DATA  # turi būti nustatyta prieš importuojant studijos modulius
os.environ["DATA_DIR"] = _DATA
for p in (ROOT, os.path.join(ROOT, "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

import accounts  # noqa: E402
import engine  # noqa: E402
import server as srv  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PASSWORD = secrets.token_urlsafe(12)  # kiekvienam paleidimui atsitiktinis (ne tikras slaptažodis)


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


@pytest.fixture(scope="session")
def media():
    """Maži bandomieji failai: statūs ir gulsčias video, nuotrauka, garsas."""
    d = tempfile.mkdtemp(prefix="reels-test-media-")
    m = {"portrait": os.path.join(d, "portrait.mp4"), "landscape": os.path.join(d, "landscape.mp4"),
         "silent": os.path.join(d, "silent.mp4"), "image": os.path.join(d, "photo.jpg"),
         "audio": os.path.join(d, "voice.mp3")}
    ff("-f", "lavfi", "-i", "testsrc2=size=360x640:rate=25:duration=4", "-f", "lavfi", "-i",
       "sine=frequency=300:duration=4", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
       m["portrait"])
    ff("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
       m["landscape"])
    ff("-f", "lavfi", "-i", "testsrc2=size=360x640:rate=25:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
       m["silent"])
    ff("-f", "lavfi", "-i", "testsrc=size=480x640", "-frames:v", "1", m["image"])
    ff("-f", "lavfi", "-i", "sine=frequency=500:duration=3", m["audio"])
    yield m
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def mocks(monkeypatch, media):
    """Išorinių paslaugų imitacijos. Grąžina žodyną, kur testai gali pakeisti elgesį (pvz. AI atsakymą)."""
    state = {"stock_downloads": [], "mails": [], "ai_client": None, "gemini": True}
    monkeypatch.setattr(srv, "_mail_bg", lambda to, subj, body: state["mails"].append((to, subj)))
    monkeypatch.setattr(srv, "stock_provider", lambda: "pixabay")
    keys = {"pixabay": "test", "gemini": "test", "stripe": "sk_test_x", "stripe_whsec": "whsec_test"}
    monkeypatch.setattr(srv, "stock_key", lambda p: keys.get(p) if (p != "gemini" or state["gemini"]) else None)

    def stock_search(q, fmt="9:16", page=1, per_page=18, provider=None):
        portrait = fmt != "16:9"
        return [{"provider": "pixabay", "id": page * 100 + i, "duration": 5 + i % 4, "image": f"https://x/{i}.jpg",
                 "width": 1080 if (portrait ^ (i % 5 == 0)) else 1920,
                 "height": 1920 if (portrait ^ (i % 5 == 0)) else 1080, "likes": 50 - i, "downloads": 900 - i}
                for i in range(20)]

    def stock_download(user, pid, provider, vid, fmt):
        state["stock_downloads"].append(vid)
        return media["portrait"], {}

    monkeypatch.setattr(srv, "stock_search", stock_search)
    monkeypatch.setattr(srv, "stock_download", stock_download)
    monkeypatch.setattr(engine, "tts", lambda client, text, voice, out, language="lt", gemini_key=None:
                        shutil.copy(media["audio"], out))
    monkeypatch.setattr(engine, "veo_generate", lambda key, prompt, aspect, out, status=None, **kw:
                        state.setdefault("veo", []).append((prompt, kw)) or shutil.copy(media["portrait"], out))
    monkeypatch.setattr(srv, "_veo_prompt_en", lambda client, prompt: prompt)
    monkeypatch.setattr(srv, "openai_client", lambda user: state["ai_client"]
                        if user["plan"] in srv.AI_PLANS else None)
    return state


@pytest.fixture()
def client(mocks):
    return TestClient(srv.app)


_n = [0]


@pytest.fixture()
def make_user(client):
    """Sukuria vartotoją (plan: basic | premium | admin) ir grąžina (vardas, antraštės)."""
    def make(plan="premium", **extra):
        _n[0] += 1
        name = f"user{_n[0]}_{int(time.time() * 1000) % 100000}@test.lt"
        users = accounts.managed_users()
        users[name] = dict({"plan": plan, "name": "Testas", "email": name,
                            "password_hash": accounts.hash_password(PASSWORD)}, **extra)
        accounts.save_managed_users(users)
        r = client.post("/api/login", json={"username": name, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return name, {"Authorization": "Bearer " + r.json()["token"]}
    return make


def wait_job(client, headers, job, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"/api/jobs/{job['id']}", headers=headers).json()
        if st["status"] in ("done", "error", "cancelled"):
            return st
        time.sleep(0.3)
    raise AssertionError("Darbas neužsibaigė per laiką")


def new_project(client, headers, title="Testas"):
    r = client.post("/api/projects", json={"title": title}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def upload(client, headers, pid, path, name=None):
    with open(path, "rb") as f:
        r = client.post(f"/api/projects/{pid}/clips", files={"file": (name or os.path.basename(path), f)},
                        headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def fake_ai(handler):
    """OpenAI kliento imitacija: handler(kwargs) -> message (content, tool_calls)."""
    NS = types.SimpleNamespace

    def create(**kw):
        return NS(choices=[NS(message=handler(kw))])
    return NS(chat=NS(completions=NS(create=create)))
