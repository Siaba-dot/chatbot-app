"""Paskyros: registracija, prisijungimas, planai, nemokamas bandymas, limitai, Stripe."""
import hashlib
import hmac
import json
import time

import accounts
import server as srv
from conftest import PASSWORD


def register(client, email, **kw):
    body = dict({"name": "Kirpykla", "email": email, "password": "slaptazodis1", "consent": True}, **kw)
    return client.post("/api/register", json=body)


def test_register_gives_trial(client, mocks):
    r = register(client, "nauja@test.lt")
    assert r.status_code == 200, r.text
    u = r.json()["user"]
    assert u["plan"] == "premium" and u["trial_until"]
    assert u["limits"] == accounts.DEFAULT_LIMITS["trial"]


def test_register_requires_consent_and_unique_email(client):
    assert register(client, "be.sutikimo@test.lt", consent=False).status_code == 400
    assert register(client, "du@test.lt").status_code == 200
    assert register(client, "du@test.lt").status_code == 400


def test_register_honeypot_blocks_bots(client):
    assert register(client, "botas@test.lt", website="http://spam").status_code == 429


def test_trial_expires_to_basic(client):
    r = register(client, "baigesi@test.lt")
    tok = r.json()["token"]
    users = accounts.managed_users()
    users["baigesi@test.lt"]["trial_until"] = time.time() - 1
    accounts.save_managed_users(users)
    me = client.get("/api/me", headers={"Authorization": "Bearer " + tok}).json()
    assert me["plan"] == "basic" and me["trial_until"] is None
    assert me["limits"]["voice_chars"] == 0


def test_login_wrong_password(client, make_user):
    name, _ = make_user("basic")
    assert client.post("/api/login", json={"username": name, "password": "blogas"}).status_code in (400, 401)
    assert client.post("/api/login", json={"username": name, "password": PASSWORD}).status_code == 200


def test_basic_has_no_ai(client, make_user, mocks):
    _, h = make_user("basic")
    me = client.get("/api/me", headers=h).json()
    assert me["plan"] == "basic"
    assert me["limits"]["ai_clips"] == 0 and me["limits"]["director"] == 0


def test_admin_only_endpoints(client, make_user):
    _, h = make_user("basic")
    assert client.get("/api/admin/users", headers=h).status_code in (401, 403)
    _, ha = make_user("admin")
    assert client.get("/api/admin/users", headers=ha).status_code == 200


def _stripe_post(client, event, secret="whsec_test"):
    payload = json.dumps(event).encode()
    t = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return client.post("/api/billing/webhook", content=payload,
                       headers={"stripe-signature": f"t={t},v1={sig}", "content-type": "application/json"})


def test_stripe_webhook_switches_plan(client, make_user):
    name, h = make_user("basic", trial_until=time.time() + 999)
    r = _stripe_post(client, {"type": "checkout.session.completed",
                              "data": {"object": {"client_reference_id": name, "customer": "cus_1",
                                                  "subscription": "sub_1"}}})
    assert r.status_code == 200, r.text
    cfg = accounts.managed_users()[name]
    assert cfg["plan"] == "premium" and "trial_until" not in cfg
    _stripe_post(client, {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1"}}})
    assert accounts.managed_users()[name]["plan"] == "basic"


def test_stripe_webhook_rejects_bad_signature(client):
    r = _stripe_post(client, {"type": "checkout.session.completed", "data": {"object": {}}}, secret="wrong")
    assert r.status_code == 400


def test_public_settings_shape(client):
    s = client.get("/api/public/settings").json()
    for k in ("registration", "trial_days", "limits", "minutes", "billing", "mail"):
        assert k in s
    assert srv.app_settings()["trial_days"] == s["trial_days"]
