"""✨ 3D akcentai: pasiūlymai pagal turinį (momentai, vietos), piešimas, peržiūra ir galutinis video."""
import os
import subprocess
import tempfile

import numpy as np
import pytest
from PIL import Image, ImageDraw

import accents
import engine
from conftest import new_project, upload, wait_job

WORDS = [("Šiandien", 0.0, 0.3), ("nuolaida", 0.3, 0.55), ("-30%!", 0.6, 1.1), ("Štai", 3.0, 3.3),
         ("mūsų", 3.35, 3.6), ("naujiena", 3.65, 4.3), ("Rezultatas", 5.2, 5.9), ("nuostabus.", 6.0, 6.6)]


def _grab(t):
    """Kadras: tamsus fonas su ryškia „preke“ dešinėje (x≈0.72, y≈0.4)."""
    im = Image.new("RGB", (270, 480), (30, 40, 55))
    ImageDraw.Draw(im).rectangle((165, 160, 225, 230), fill=(240, 200, 90))
    return im


def test_suggestions_follow_content_moments():
    prep = {"analysis": {"words": WORDS, "info": {"duration": 8.0}}, "spans": [[0.0, 5.5], [5.5, 8.0]]}
    st = {"speed": 1.0, "subs_pos": "Žemiau", "accent": "Auksas"}
    sugs = accents.suggest(prep, st, "p1", _grab)
    cats = {}
    for s in sugs:  # kiekvienos grupės pirmasis pasiūlymas
        cats.setdefault(s["cat"], s)
    assert set(cats) == {"word", "detail", "reveal"}, sugs
    w = cats["word"]
    assert w["text"] == "-30%" and abs(w["t"] - (0.6 - 0.08)) < 0.02          # iškyla, kai ištariamas
    d = cats["detail"]
    hit = d["t"] + accents.HIT_AT[d["kind"]] * d["dur"]
    assert abs(hit - 3.0) < 0.05                                               # pasiekia detalę, kai ji rodoma
    assert abs(d["x"] - 0.72) < 0.12 and abs(d["y"] - 0.4) < 0.12               # šalia ryškios detalės
    r = cats["reveal"]
    assert abs(r["t"] + accents.CUT_AT[r["kind"]] * r["dur"] - 5.5) < 0.02     # tiksliai kadro pasikeitimo metu
    assert "rezultat" in r["why"].lower()
    for a, b in zip(sugs, sugs[1:]):                                            # nepersidengia
        assert a["t"] + a["dur"] <= b["t"] + 1e-6
    # kitam projektui – kitokie variantai (savitas judesys)
    kinds = {tuple(s["kind"] for s in accents.suggest(prep, st, f"p{i}", _grab)) for i in range(6)}
    assert len(kinds) >= 2


def test_saliency_avoids_faces_and_subtitles():
    im = Image.new("RGB", (270, 480), (30, 40, 55))
    ImageDraw.Draw(im).rectangle((100, 330, 170, 360), fill=(255, 255, 255))   # „titrai“ y≈0.72
    ImageDraw.Draw(im).rectangle((40, 60, 110, 130), fill=(250, 220, 200))     # „veidas“
    ImageDraw.Draw(im).rectangle((180, 200, 230, 250), fill=(200, 160, 60))    # detalė
    x, y, score = accents.saliency_target(im, [(40 / 270, 60 / 480, 110 / 270, 130 / 480)], 0.72)
    assert abs(x - 205 / 270) < 0.12 and abs(y - 225 / 480) < 0.12


@pytest.mark.parametrize("kind", list(accents.KINDS))
def test_every_accent_renders_and_changes_frame(kind):
    d = tempfile.mkdtemp()
    src = os.path.join(d, "ab.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x2a3f55:s=270x480:d=1.5,"
                    "drawbox=x=150:y=180:w=80:h=110:color=0xe8c070:t=fill", "-f", "lavfi", "-i",
                    "color=c=0xd8a68a:s=270x480:d=1.5", "-filter_complex", "[0][1]concat=n=2:v=1[v]", "-map", "[v]",
                    "-pix_fmt", "yuv420p", src], check=True)
    dur = accents.LEN[kind]
    t = 1.5 - accents.CUT_AT.get(kind, 0.3) * dur if kind in accents.CUT_AT else 0.1
    it = {"kind": kind, "x": 0.7, "y": 0.45, "size": 1.2, "color": "#3AA0FF", "text": "Naujiena", "dir": "left"}
    out = accents.render(src, t, it, os.path.join(d, "o.mp4"), 270, 480, 15, dur)
    mid = (accents.CUT_AT.get(kind, 0.4) + 0.15) * dur
    a = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{mid:.2f}", "-i", out, "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "gray", "-"], capture_output=True).stdout
    b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t + mid:.2f}", "-i", src, "-frames:v", "1", "-f",
                        "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    changed = (np.abs(np.frombuffer(a, np.uint8).astype(int) - np.frombuffer(b, np.uint8).astype(int)) > 25).mean()
    assert changed > 0.005, f"{kind}: akcentas nematomas ({changed:.4f})"


def test_remap_positions_for_other_formats():
    items = [{"kind": "arrow3d", "t": 1, "x": 0.8, "y": 0.3}]
    yt = engine.remap_xy(items, "9:16", "16:9")[0]
    assert abs(yt["x"] - (0.5 + 0.3 * (9 / 16) / (16 / 9))) < 0.01 and yt["y"] == 0.3  # stačias kadras per vidurį
    ig = engine.remap_xy(items, "9:16", "4:5")[0]
    assert ig["x"] == 0.8 and ig["y"] < 0.3                                              # viršus / apačia apkarpyti
    assert engine.remap_xy(items, "9:16", "9:16")[0] == items[0]


def test_clean_item_limits_values():
    it = engine.clean_fx_item({"kind": "ring3d", "t": -2, "x": 5, "size": 9, "color": "red", "dir": "x", "dur": 0.1})
    assert it["t"] == 0 and it["x"] == 1 and it["size"] == 2.5 and it["dur"] == 0.4
    assert "color" not in it and "dir" not in it


def test_accents_full_path(client, make_user, media):
    """Peržiūra → pasiūlymai → vieno paspaudimo peržiūra su pakeistais parametrais → pritaikymas →
    peržiūra → galutinis video (efektai atrodo taip pat)."""
    _, h = make_user("basic")
    pid = new_project(client, h)
    upload(client, h, pid, media["portrait"])
    upload(client, h, pid, media["silent"])
    client.put(f"/api/projects/{pid}/settings", json={"settings": {
        "all_formats": False, "subtitle_text": "Štai mūsų naujiena -30%! Rezultatas nuostabus."}}, headers=h)
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/accents/suggest", headers=h).json(), 60)
    assert st["status"] == "error" and "peržiūrą" in st["message"]  # be peržiūros – aiškus paaiškinimas
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/render", json={"quick": True}, headers=h).json(), 400)
    assert st["status"] == "done", st
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/accents/suggest", headers=h).json(), 300)
    assert st["status"] == "done", st
    sugs = st["result"]["suggestions"]
    assert any(s["cat"] == "reveal" for s in sugs), sugs            # kadro pasikeitimas (2 klipai)
    it = dict(sugs[0], size=1.4, color="#22CC88")
    it.pop("why"), it.pop("variants"), it.pop("cat"), it.pop("id")
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/fx_preview",
                                         json={"kind": it["kind"], "t": it["t"], "item": it}, headers=h).json(), 300)
    assert st["status"] == "done", st
    assert st["result"]["item"]["color"] == "#22CC88" and st["result"]["item"]["size"] == 1.4
    assert client.get(f"/api/projects/{pid}/files/{st['result']['file']}", headers=h).status_code == 200
    items = [dict(it, id="a1")] + [dict({k: v for k, v in s.items() if k not in ("why", "variants", "cat")}, id=f"b{i}")
                                   for i, s in enumerate(sugs[1:])]
    client.put(f"/api/projects/{pid}/settings", json={"settings": {"fx_items": items}}, headers=h)
    saved = client.get(f"/api/projects/{pid}", headers=h).json()["settings"]["fx_items"]
    assert saved[0]["color"] == "#22CC88" or any(x["color"] == "#22CC88" for x in saved)
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/render", json={"quick": True}, headers=h).json(), 400)
    assert st["status"] == "done", st
    st2 = wait_job(client, h, client.post(f"/api/projects/{pid}/render", json={"quick": False}, headers=h).json(), 600)
    assert st2["status"] == "done", st2
    assert st2["result"]["plan_reused"] and abs(st2["result"]["duration"] - st["result"]["duration"]) < 0.15
    d = tempfile.mkdtemp()
    a, b = os.path.join(d, "p.mp4"), os.path.join(d, "f.mp4")
    open(a, "wb").write(client.get(f"/api/projects/{pid}/files/preview.mp4", headers=h).content)
    open(b, "wb").write(client.get(f"/api/projects/{pid}/files/reels.mp4", headers=h).content)
    for s_ in saved:
        tm = s_["t"] + 0.45 * s_.get("dur", 1.0)
        fa = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tm:.2f}", "-i", a, "-frames:v", "1", "-vf",
                             "scale=90:160,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        fb = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tm:.2f}", "-i", b, "-frames:v", "1", "-vf",
                             "scale=90:160,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        assert fa and fb
        diff = np.abs(np.frombuffer(fa, np.uint8).astype(int) - np.frombuffer(fb, np.uint8).astype(int)).mean()
        assert diff < 22, (s_["kind"], diff)
