"""🪄 Automatinis montažas – visas kelias: įkėlimas → montažas → efekto peržiūra → pritaikymas → peržiūra →
galutinis video (sutampa su peržiūra) → efekto pašalinimas → grįžimas prie pradinės versijos."""
import os
import subprocess
import tempfile

import numpy as np

import automontage
from conftest import new_project, upload, wait_job


def _speech_clip(path, pre=1.2, talk=2.5, post=2.3):
    """Kalbą primenantis įrašas: tyli pradžia, „kalba“ (harmonikos su ritmu), tyli pabaiga + vaizdas."""
    sr = 16000
    rng = np.random.default_rng(3)
    t = np.arange(int(talk * sr)) / sr
    voice = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in range(1, 10)) * 0.12
    voice *= 0.35 + 0.65 * np.abs(np.sin(2 * np.pi * 3 * t))
    noise = lambda d: rng.normal(0, 0.002, int(d * sr))  # noqa: E731 – tylus fonas (ne skaitmeninė tyla)
    x = np.concatenate([noise(pre), voice + noise(talk), noise(post)]).astype("<f4")
    wav = path + ".wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", wav],
                   input=x.tobytes(), check=True)
    dur = pre + talk + post
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=360x640:rate=25:duration={dur}",
                    "-i", wav, "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path], check=True)
    return path


def _frame(path, t, size=(90, 160)):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf",
                        f"scale={size[0]}:{size[1]},format=gray", "-f", "rawvideo", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).astype(np.int16)


def test_plan_speech_trim_and_action_window(media):
    d = tempfile.mkdtemp()
    sp = _speech_clip(os.path.join(d, "kalba.mp4"))
    clips = [{"id": "a", "path": sp, "duration": 6.0, "audio": "speech"},
             {"id": "b", "path": media["landscape"], "duration": 12.0, "audio": "none"}]
    cuts, beat = automontage.plan(clips)
    by = {c["id"]: c["trim"] for c in cuts}
    a0, a1 = by["a"]
    assert 0.8 <= a0 <= 1.2 and 3.6 <= a1 <= 4.3, by["a"]      # prie frazių ribų (tylos kraštai nukirpti)
    b0, b1 = by["b"]
    assert 2.0 <= b1 - b0 <= automontage.ACTION_LEN + 0.1     # be kalbos – veiksmo atkarpa
    assert beat is None


def test_music_beat_detects_tempo():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.wav")
    sr = 11025
    x = np.zeros(sr * 12)
    for k in range(int(12 / 0.5)):  # 120 BPM spragsėjimai
        a = int(k * 0.5 * sr)
        x[a:a + 400] += np.sin(2 * np.pi * 900 * np.arange(400) / sr) * np.exp(-np.arange(400) / 80)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f64le", "-ar", str(sr), "-ac", "1", "-i", "-", p],
                   input=x.astype("<f8").tobytes(), check=True)
    beat = automontage.music_beat(p)
    assert beat and abs(beat - 0.5) < 0.05


def test_auto_edit_full_path(client, make_user, media):
    _, h = make_user("basic")
    pid = new_project(client, h)
    d = tempfile.mkdtemp()
    upload(client, h, pid, _speech_clip(os.path.join(d, "kalba.mp4")), "kalba.mp4")
    upload(client, h, pid, media["landscape"], "vaizdas.mp4")
    client.put(f"/api/projects/{pid}/settings", json={"settings": {"all_formats": False, "subtitles": False}},
               headers=h)
    order = [c["id"] for c in client.get(f"/api/projects/{pid}", headers=h).json()["clips"]]

    # 🪄 automatinis montažas (pradinė versija išsaugoma, iškart sukuriama peržiūra)
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/auto_edit", headers=h).json(), timeout=400)
    assert st["status"] == "done", st
    p = client.get(f"/api/projects/{pid}", headers=h).json()
    assert p["has_original"] and p["auto_notes"]
    assert [c["id"] for c in p["clips"]] == order                       # eilė nepakeista
    assert all(c["trim"] for c in p["clips"])
    assert p["settings"]["jcut"] and p["settings"]["ducking"]
    assert "original" not in p and "plan_cache" not in p               # vidiniai duomenys neišduodami
    assert p["outputs"]["preview"]

    # 👁 efekto peržiūra prieš pritaikant
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/fx_preview", json={"kind": "shatter3d", "t": 0.5},
                                         headers=h).json(), timeout=300)
    assert st["status"] == "done", st
    assert client.get(f"/api/projects/{pid}/files/{st['result']['file']}", headers=h).status_code == 200
    assert client.post(f"/api/projects/{pid}/fx_preview", json={"kind": "chat", "t": 1}, headers=h).status_code == 400

    # 🎯 pritaikom du efektus laiko juostoje → peržiūra → galutinis video
    items = [{"id": "x1", "kind": "shatter3d", "t": 0.5}, {"id": "x2", "kind": "phone3d", "t": 3.5}]
    client.put(f"/api/projects/{pid}/settings", json={"settings": {"fx_items": items}}, headers=h)
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/render", json={"quick": True}, headers=h).json(),
                  timeout=400)
    assert st["status"] == "done", st
    prev_dur = st["result"]["duration"]
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/render", json={"quick": False}, headers=h).json(),
                  timeout=600)
    assert st["status"] == "done", st
    assert st["result"]["plan_reused"]                                   # tas pats planas kaip peržiūroje
    assert abs(st["result"]["duration"] - prev_dur) < 0.15
    prev_f = client.get(f"/api/projects/{pid}/files/preview.mp4", headers=h)
    fin_f = client.get(f"/api/projects/{pid}/files/reels.mp4", headers=h)
    assert prev_f.status_code == fin_f.status_code == 200
    a, b = os.path.join(d, "p.mp4"), os.path.join(d, "f.mp4")
    open(a, "wb").write(prev_f.content)
    open(b, "wb").write(fin_f.content)
    for t in (1.2, 4.2):  # efektų metu vaizdas peržiūroje ir galutiniame video – tas pats
        fa, fb = _frame(a, t), _frame(b, t)
        assert len(fa) and len(fb) and np.abs(fa - fb).mean() < 22, t

    # ✕ vieno efekto pašalinimas
    client.put(f"/api/projects/{pid}/settings", json={"settings": {"fx_items": items[:1]}}, headers=h)
    p = client.get(f"/api/projects/{pid}", headers=h).json()
    assert [i["id"] for i in p["settings"]["fx_items"]] == ["x1"]

    # ↩ grįžimas prie pradinės versijos
    r = client.post(f"/api/projects/{pid}/auto_edit/revert", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert not p["has_original"] and not p["settings"]["jcut"]
    assert all(not c.get("trim") for c in p["clips"]) and [c["id"] for c in p["clips"]] == order
    assert client.post(f"/api/projects/{pid}/auto_edit/revert", headers=h).status_code == 400
