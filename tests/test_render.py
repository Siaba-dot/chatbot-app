"""Video kūrimas ir titrai: visi titrų stiliai, telpa ekrane, efektai, formatai."""
import os
import subprocess
import tempfile

import numpy as np
import pytest

import engine
import video_editor as ve
from conftest import new_project, upload, wait_job

WORDS = [("Bendradarbiavimas", 0.0, 0.8), ("su", 0.8, 1.0), ("klientais", 1.0, 1.6), ("visada", 1.6, 2.0),
         ("džiugina.", 2.0, 2.8), ("Ateikite", 3.0, 3.4), ("pas", 3.4, 3.6), ("mus!", 3.6, 4.2)]


@pytest.mark.parametrize("look", list(ve.SUBTITLE_LOOKS))
def test_every_subtitle_look_renders_inside_frame(look):
    """Kiekvienas titrų stilius sukuriamas be klaidų, o tekstas neišlenda už kadro kraštų."""
    W, H = 540, 960
    d = tempfile.mkdtemp()
    ass = os.path.join(d, "s.ass")
    with open(ass, "w", encoding="utf-8") as f:
        f.write(ve.build_ass(WORDS, W, H, 0.6, look=look, size=1.2))
    for t in (0.7, 2.5, 4.0):
        out = os.path.join(d, f"f{t}.png")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x101010:s={W}x{H}:d=5",
                            "-vf", f"subtitles={ass}:fontsdir={ve.FONT_DIR}", "-ss", str(t), "-frames:v", "1", out],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        from PIL import Image
        img = np.asarray(Image.open(out).convert("L"), dtype=np.int16)
        edge = np.concatenate([img[:, :3].ravel(), img[:, -3:].ravel()])
        assert (edge > 120).sum() < 15, f"{look}: tekstas išlenda už krašto ties {t} s"


def test_build_video_with_effects_and_graphics(media):
    d = tempfile.mkdtemp()
    clips = [engine.add_clip(media["portrait"]), engine.add_clip(media["image"])]
    st = {"subtitle_text": "Turėjau vieną papūgą nimfą. Ji buvo geltona ir labai linksma.", "look": "wave",
          "effects": ["Lėtas priartėjimas", "Kino juostos"], "gfx_kinds": ["reel"], "cta": "Parašykite mums!",
          "subs_size": 120}
    prep = engine.prepare(clips, st, d)
    fin = engine.build(prep, st, os.path.join(d, "o.mp4"), d, quick=True)
    assert fin["duration"] > 4 and os.path.getsize(os.path.join(d, "o.mp4")) > 10000


def test_youtube_format_keeps_portrait_whole(media):
    """16:9 versijoje stati medžiaga nenukerpama (rodoma su sulietu fonu), net jei šalia ilgas gulsčias video."""
    d = tempfile.mkdtemp()
    clips = [engine.add_clip(media["silent"]), engine.add_clip(media["landscape"])]
    clips[1]["trim"] = [0.0, 2.0]
    src = engine.source_for_format(clips, {"format": "9:16"}, d, "16:9")
    out = os.path.join(d, "f.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", src, "-frames:v", "1", out], check=True)
    from PIL import Image
    img = np.asarray(Image.open(out).convert("RGB"), dtype=np.int16)
    h, w, _ = img.shape
    left = img[:, : w // 6].std()
    mid = img[:, w // 2 - 20: w // 2 + 20].std()
    assert left < mid, "šonuose turi būti sulietas fonas, ne ištemptas vaizdas"


def test_render_job_all_formats(client, make_user, media):
    _, h = make_user("basic")
    pid = new_project(client, h)
    upload(client, h, pid, media["portrait"])
    client.put(f"/api/projects/{pid}/settings", json={"settings": {"subtitle_text": "Labas, čia mūsų video."}},
               headers=h)
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/render", json={"quick": False}, headers=h).json(),
                  timeout=400)
    assert st["status"] == "done", st
    fmts = {f["fmt"] for f in st["result"]["formats"]}
    assert fmts == {"9:16", "16:9", "4:5"}
    assert client.get(f"/api/projects/{pid}/files/visi_formatai.zip", headers=h).status_code == 200
