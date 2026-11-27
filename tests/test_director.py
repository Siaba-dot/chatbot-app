"""💬 AI režisierius: privalo naudoti įrankius, tikrai pakeičia, rodo atliktus veiksmus, saugo limitus."""
import json
import types

from conftest import fake_ai, new_project, upload, wait_job

NS = types.SimpleNamespace


def calls(*items):
    return [NS(id=f"c{i}", function=NS(name=n, arguments=json.dumps(a))) for i, (n, a) in enumerate(items)]


def scripted(*steps, vision_score=9):
    """AI imitacija: kiekvienas kvietimas grąžina kitą žingsnį; įrašo tool_choice.
    Vaizdų įvertinimo užklausos (su response_format) gauna įvertinimą vision_score."""
    seen = []

    def handler(kw):
        if kw.get("response_format"):  # AI peržiūri bibliotekos kadrus
            return NS(content=json.dumps({"best": 0, "ok": True, "score": vision_score}), tool_calls=None)
        seen.append(kw.get("tool_choice"))
        step = steps[min(len(seen) - 1, len(steps) - 1)]
        return NS(content=step if isinstance(step, str) else "", tool_calls=None if isinstance(step, str) else step)
    return handler, seen


def _project_with_auto_clip(client, h):
    pid = new_project(client, h)
    st = wait_job(client, h, client.post(f"/api/projects/{pid}/auto_video",
                                         json={"sector": "kavine", "text": "Labas rytas. Kava jau laukia jūsų čia."},
                                         headers=h).json())
    assert st["status"] == "done", st
    return pid, client.get(f"/api/projects/{pid}", headers=h).json()["clips"][0]["id"]


def test_director_changes_style_and_scene(client, make_user, mocks):
    _, h = make_user("premium")
    pid, cid = _project_with_auto_clip(client, h)
    handler, seen = scripted(calls(("update_style", {"template": "Kino anonsas", "cta": "Parašykite mums!"}),
                                   ("replace_scene", {"clip_id": cid, "query": "coffee pour"}),
                                   ("remove_scene", {"clip_id": "nera"})),
                             "Pakeičiau stilių ir pirmą sceną.")
    mocks["ai_client"] = fake_ai(handler)
    r = client.post(f"/api/projects/{pid}/director", json={"message": "Padaryk kaip kino anonsą"}, headers=h).json()
    s = r["project"]["settings"]
    assert s["template"] == "Kino anonsas" and s["look"] == "trailer" and s["cta"] == "Parašykite mums!"
    assert "Kino juostos" in s["effects"]
    assert r["preview"] and r["ai_job"] is None and len(r["done"]) == 2
    assert seen[0] == "required"  # pirmą kartą AI privalo kviesti įrankį
    assert r["project"]["clips"][0]["name"] == "🎞 coffee pour"


def test_director_low_quality_stock_becomes_ai_shot(client, make_user, mocks):
    """Kai bibliotekoje nėra kokybiško kadro (AI įvertinimas < 8), režisierius pats sukuria AI kadrą (geresnė kokybė)."""
    _, h = make_user("premium")
    pid, cid = _project_with_auto_clip(client, h)
    handler, _ = scripted(calls(("replace_scene", {"clip_id": cid, "query": "coffee pour"})), "Sukursiu AI kadrą.",
                          vision_score=5)
    mocks["ai_client"] = fake_ai(handler)
    r = client.post(f"/api/projects/{pid}/director", json={"message": "gražesnį vaizdą"}, headers=h).json()
    assert r["ai_job"], r
    assert wait_job(client, h, r["ai_job"])["status"] == "done"
    c = client.get(f"/api/projects/{pid}", headers=h).json()["clips"][0]
    assert c["id"] == cid and c.get("ai_scene")
    assert mocks["veo"][-1][1].get("hq") is True  # geresnės kokybės Google modelis


def test_director_ai_shot_respects_limit(client, make_user, mocks):
    _, h = make_user("premium", ai_clips=0)
    pid, cid = _project_with_auto_clip(client, h)
    handler, _ = scripted(calls(("ai_scene", {"clip_id": cid, "prompt": "Coffee close-up"})), "Limitas baigėsi.")
    mocks["ai_client"] = fake_ai(handler)
    r = client.post(f"/api/projects/{pid}/director", json={"message": "AI kadrą"}, headers=h).json()
    assert r["ai_job"] is None and not r["actions"]


def test_director_warns_when_claiming_without_action(client, make_user, mocks):
    _, h = make_user("premium")
    pid, _ = _project_with_auto_clip(client, h)
    handler, _ = scripted("Pridėjau kvietimą pabaigoje.")
    mocks["ai_client"] = fake_ai(handler)
    r = client.post(f"/api/projects/{pid}/director", json={"message": "Pridėk kvietimą"}, headers=h).json()
    assert not r["actions"] and "⚠" in r["reply"]


def test_director_never_replaces_own_video(client, make_user, mocks, media):
    _, h = make_user("premium")
    pid = new_project(client, h)
    cid = upload(client, h, pid, media["portrait"])["clips"][0]["id"]
    handler, _ = scripted(calls(("replace_scene", {"clip_id": cid, "query": "x"})), "Negaliu.")
    mocks["ai_client"] = fake_ai(handler)
    r = client.post(f"/api/projects/{pid}/director", json={"message": "pakeisk"}, headers=h).json()
    assert r["actions"] == [] and r["project"]["clips"][0]["id"] == cid


def test_director_premium_only(client, make_user):
    _, h = make_user("basic")
    pid = new_project(client, h)
    assert client.post(f"/api/projects/{pid}/director", json={"message": "x"}, headers=h).status_code == 400
