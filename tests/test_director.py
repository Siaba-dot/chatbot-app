"""💬 AI režisierius: privalo naudoti įrankius, tikrai pakeičia, rodo atliktus veiksmus, saugo limitus."""
import json
import types

from conftest import fake_ai, new_project, upload, wait_job

NS = types.SimpleNamespace


def calls(*items):
    return [NS(id=f"c{i}", function=NS(name=n, arguments=json.dumps(a))) for i, (n, a) in enumerate(items)]


def scripted(*steps):
    """AI imitacija: kiekvienas kvietimas grąžina kitą žingsnį; įrašo tool_choice."""
    seen = []

    def handler(kw):
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
                                   ("propose_ai_scene", {"clip_id": cid, "prompt": "Coffee close-up"}),
                                   ("remove_scene", {"clip_id": "nera"})),
                             "Pakeičiau stilių ir pirmą sceną.")
    mocks["ai_client"] = fake_ai(handler)
    r = client.post(f"/api/projects/{pid}/director", json={"message": "Padaryk kaip kino anonsą"}, headers=h).json()
    s = r["project"]["settings"]
    assert s["template"] == "Kino anonsas" and s["look"] == "trailer" and s["cta"] == "Parašykite mums!"
    assert "Kino juostos" in s["effects"]
    assert r["preview"] and r["proposals"] and len(r["done"]) == 2
    assert seen[0] == "required"  # pirmą kartą AI privalo kviesti įrankį
    assert r["project"]["clips"][0]["name"] == "🎞 coffee pour"


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
