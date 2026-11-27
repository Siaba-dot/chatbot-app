"""Projektai ir kadrai: įkėlimas, karpymas, dalinimas, kadro garsas, savas garsas."""
import os

from conftest import new_project, upload


def test_upload_trim_split_delete(client, make_user, media):
    _, h = make_user("basic")
    pid = new_project(client, h)
    p = upload(client, h, pid, media["portrait"])
    cid = p["clips"][0]["id"]
    assert "path" not in p["clips"][0]  # vidiniai keliai nerodomi naršyklei
    r = client.put(f"/api/projects/{pid}/clips/{cid}/trim", json={"start": 0.5, "end": 3.0}, headers=h)
    assert r.status_code == 200 and r.json()["clips"][0]["trim"] == [0.5, 3.0]
    r = client.post(f"/api/projects/{pid}/clips/{cid}/split", json={"at": 1.5}, headers=h)
    assert r.status_code == 200 and len(r.json()["clips"]) == 2
    r = client.delete(f"/api/projects/{pid}/clips/{cid}", headers=h)
    assert r.status_code == 200 and len(r.json()["clips"]) == 1


def test_bad_upload_rejected(client, make_user, tmp_path):
    _, h = make_user("basic")
    pid = new_project(client, h)
    bad = tmp_path / "blogas.mp4"
    bad.write_bytes(b"not a video")
    with open(bad, "rb") as f:
        r = client.post(f"/api/projects/{pid}/clips", files={"file": ("blogas.mp4", f)}, headers=h)
    assert r.status_code == 400


def test_other_user_cannot_open_project(client, make_user):
    _, h1 = make_user("basic")
    _, h2 = make_user("basic")
    pid = new_project(client, h1)
    assert client.get(f"/api/projects/{pid}", headers=h2).status_code == 404


def test_clip_frame_and_preview(client, make_user, media):
    _, h = make_user("basic")
    pid = new_project(client, h)
    cid = upload(client, h, pid, media["portrait"])["clips"][0]["id"]
    r = client.get(f"/api/projects/{pid}/clips/{cid}/frame", params={"t": 1.2}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/projects/{pid}/clips/{cid}/strip", headers=h).status_code == 200


def test_clip_music_and_own_sound(client, make_user, media):
    _, h = make_user("basic")
    pid = new_project(client, h)
    cid = upload(client, h, pid, media["portrait"])["clips"][0]["id"]
    track = next(iter(client.get("/api/options").json()["music"]))
    r = client.put(f"/api/projects/{pid}/clips/{cid}/sound",
                   json={"kind": "music", "track": track, "volume": 50, "orig": 80}, headers=h)
    assert r.status_code == 200 and r.json()["clips"][0]["sound"]["track"] == track
    with open(media["audio"], "rb") as f:
        r = client.post(f"/api/projects/{pid}/clips/{cid}/sound_upload", files={"file": ("balsas.mp3", f)},
                        data={"voice": "true"}, headers=h)
    snd = r.json()["clips"][0]["sound"]
    assert r.status_code == 200 and snd["kind"] == "file" and snd["voice"] and "path" not in snd
    assert client.get(f"/api/projects/{pid}/voiceover/{snd['file']}", headers=h).status_code == 200


def test_ai_voice_for_clip_needs_premium(client, make_user, media):
    _, h = make_user("basic")
    pid = new_project(client, h)
    cid = upload(client, h, pid, media["portrait"])["clips"][0]["id"]
    r = client.put(f"/api/projects/{pid}/clips/{cid}/sound", json={"kind": "voice", "text": "Labas"}, headers=h)
    assert r.status_code == 400


def test_all_music_tracks_playable(client):
    import urllib.parse
    music = client.get("/api/options").json()["music"]
    assert len(music) >= 17
    for name in music:
        assert client.get("/api/music/" + urllib.parse.quote(name, safe="")).status_code == 200, name


def test_projects_list_and_rename(client, make_user):
    _, h = make_user("basic")
    pid = new_project(client, h, "Pirmas")
    r = client.put(f"/api/projects/{pid}/settings", json={"settings": {}, "title": "Pervadintas"}, headers=h)
    assert r.json()["title"] == "Pervadintas"
    assert any(p["id"] == pid for p in client.get("/api/projects", headers=h).json())
    assert os.path.isdir(os.path.join(os.environ["REELS_DATA_DIR"], "projects"))
