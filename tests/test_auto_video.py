"""Scenarijai pagal verslo sritį, automatinis video, vaizdų parinkimas, limitai, AI kadras scenai, aprašymas → planas."""
import json
import types

import pytest

import accounts
import scripts
import server as srv
from conftest import fake_ai, new_project, wait_job

NS = types.SimpleNamespace


@pytest.mark.parametrize("sector", list(scripts.SECTORS))
def test_templates_for_every_sector(sector):
    assert sector in scripts.TOPICS, f"sričiai {sector} trūksta temų"
    for goal in scripts.GOALS:
        vs = scripts.template_variants(sector, goal, "", 30)
        assert len(vs) == 3 and all(v["text"] and v["scenes"] for v in vs)
        assert len({v["title"] for v in vs}) == 3  # trys skirtingi variantai


def test_templates_use_different_topics():
    texts = " ".join(v["text"] for v in scripts.template_variants("grozis", "pristatymas", "", 30))
    assert sum(t in texts for t, _ in scripts.TOPICS["grozis"]) >= 2  # ne vien šukuosenos


def test_more_variants_avoid_previous():
    a = scripts.template_variants("kavine", "akcija", "", 30)
    b = scripts.template_variants("kavine", "akcija", "", 30, avoid=[v["title"] for v in a])
    assert not {v["title"] for v in a} & {v["title"] for v in b}


def test_pick_stock_prefers_shape_and_quality(mocks):
    for _ in range(5):
        v = srv._pick_stock("coffee", "9:16", "pixabay", 4, set())
        assert v["height"] > v["width"]  # Reels – statūs kadrai
    assert srv._pick_stock("coffee", "16:9", "pixabay", 4, set())["width"] > 1000


def test_auto_video_and_reshuffle_no_repeats(client, make_user, mocks):
    _, h = make_user("basic")
    pid = new_project(client, h)
    v = client.post(f"/api/projects/{pid}/scripts", json={"sector": "kavine", "goal": "akcija", "seconds": 15},
                    headers=h).json()["variants"][0]
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/auto_video",
                                         json={"sector": "kavine", "text": v["text"], "scenes": v["scenes"]},
                                         headers=h).json())
    assert st["status"] == "done", st
    first = list(mocks["stock_downloads"])
    p = client.get(f"/api/projects/{pid}", headers=h).json()
    assert p["clips"] and all(c["auto"] for c in p["clips"])
    assert p["settings"]["subtitle_text"] and p["settings"]["music"]
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/auto_video/reshuffle", headers=h).json())
    assert st["status"] == "done"
    second = mocks["stock_downloads"][len(first):]
    assert not set(first) & set(second)  # „Kiti vaizdai“ – nauji kadrai


def test_auto_video_limit(client, make_user, mocks):
    _, h = make_user("basic", auto_videos=1)
    pid = new_project(client, h)
    body = {"sector": "kita", "text": "Labas. Čia mūsų paslauga ir dar keli žodžiai."}
    assert wait_job(client, h, client.post(f"/api/projects/{pid}/auto_video", json=body, headers=h).json())[
        "status"] == "done"
    r = client.post(f"/api/projects/{pid}/auto_video", json=body, headers=h)
    assert r.status_code == 400 and "limitas" in r.json()["detail"]


def test_auto_video_voice_needs_premium(client, make_user, mocks):
    _, h = make_user("basic")
    pid = new_project(client, h)
    r = client.post(f"/api/projects/{pid}/auto_video", json={"sector": "kita", "text": "Labas.", "voice": "coral"},
                    headers=h)
    assert r.status_code == 400


def test_prompt_plan_and_ai_scene(client, make_user, mocks):
    plan = {"title": "Kavinės rytas", "sector": "kavine", "voice": "female",
            "text": "Labas rytas Kaune! Kava jau laukia. Ateikite savaitgalį.",
            "scenes": [{"text": "Labas rytas Kaune!", "query": "coffee", "visual": "Latte on a table"},
                       {"text": "Kava jau laukia. Ateikite savaitgalį.", "query": "croissant", "visual": "Croissants"}]}
    mocks["ai_client"] = fake_ai(lambda kw: NS(content=json.dumps(plan), tool_calls=None))
    _, hb = make_user("basic")
    assert client.post(f"/api/projects/{new_project(client, hb)}/prompt_plan",
                       json={"prompt": "Video kavinei apie pusryčius"}, headers=hb).status_code == 400
    _, h = make_user("premium")
    pid = new_project(client, h)
    r = client.post(f"/api/projects/{pid}/prompt_plan", json={"prompt": "Video kavinei apie pusryčius"}, headers=h)
    assert r.status_code == 200 and r.json()["sector"] == "kavine"
    p = r.json()
    mocks["ai_client"] = None  # vaizdai be AI peržiūros
    assert wait_job(client, h, client.post(f"/api/projects/{pid}/auto_video", json={
        "sector": p["sector"], "text": p["text"], "scenes": p["scenes"]}, headers=h).json())["status"] == "done"
    c = client.get(f"/api/projects/{pid}", headers=h).json()["clips"][0]
    assert c["visual"] == "Latte on a table"
    used = accounts.used(_name(h, client), "ai_clips")
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/broll/veo",
                                         json={"prompt": c["visual"], "replace": c["id"]}, headers=h).json())
    assert st["status"] == "done", st
    c2 = client.get(f"/api/projects/{pid}", headers=h).json()["clips"][0]
    assert c2["id"] == c["id"] and c2.get("ai_scene") and not c2.get("auto")
    assert accounts.used(_name(h, client), "ai_clips") == used + 1


def _name(h, client):
    return client.get("/api/me", headers=h).json()["username"]
