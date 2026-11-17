"""Klientų prisijungimas ir planai (Pagrindinis / Premium) svetainei.

Klientai aprašomi Streamlit Secrets (⋮ → Settings → Secrets), pvz.:

    OPENAI_API_KEY = "sk-..."          # jūsų raktas – naudojamas tik Premium klientams
    contact = "info@jusu.lt"           # rodoma Pagrindinio plano klientams (kaip įsigyti Premium)

    [users.admin]
    password = "labai-slaptas"
    plan = "admin"                     # mato visų naudojimą, be limitų

    [users.salonas]
    password = "slaptazodis1"
    plan = "premium"                   # automatiniai titrai iš kalbos, vertimas, aprašymai
    minutes = 60                       # balso atpažinimo minučių per mėnesį
    name = "Grožio salonas Rūta"

    [users.kirpykla]
    password = "slaptazodis2"
    plan = "basic"                     # viskas, išskyrus balso atpažinimą ir aprašymus
    name = "Kirpykla"

Jei [users] neaprašyta – programa atvira visiems, kaip anksčiau.
Kliento išjungimas: ištrinkite jo bloką arba įrašykite active = false.
"""
import datetime
import hmac
import json
import os
import threading
import time

import streamlit as st

PLANS = {"basic": "Pagrindinis", "premium": "Premium", "admin": "Administratorius", "open": "Atvira prieiga"}
AI_PLANS = ("premium", "admin", "open")
DEFAULT_MINUTES = 60

DATA_DIR = os.environ.get("REELS_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
_lock = threading.Lock()


def _secrets_users():
    try:
        users = st.secrets.get("users")
    except Exception:  # Secrets failo nėra
        return {}
    if not users:
        return {}
    return {str(k): dict(v) for k, v in users.items()}


def enabled():
    """Ar įjungtas prisijungimas (Secrets aprašyta bent vienas klientas)."""
    return bool(_secrets_users())


def contact():
    try:
        return st.secrets.get("contact", "")
    except Exception:
        return ""


def current():
    """Prisijungęs naudotojas: {"username", "name", "plan", "minutes"}. Kai prisijungimas išjungtas – "open"."""
    if not enabled():
        return {"username": "", "name": "", "plan": "open", "minutes": None}
    u = st.session_state.get("account")
    if not u:
        return None
    cfg = _secrets_users().get(u)
    if not cfg or cfg.get("active", True) is False:  # klientas pašalintas – atjungiam
        st.session_state.pop("account", None)
        return None
    plan = str(cfg.get("plan", "basic")).lower()
    plan = plan if plan in ("basic", "premium", "admin") else "basic"
    return {"username": u, "name": cfg.get("name") or u, "plan": plan,
            "minutes": None if plan == "admin" else float(cfg.get("minutes", DEFAULT_MINUTES))}


def ai_allowed():
    """Ar galima naudoti balso atpažinimą ir aprašymus (OpenAI) šiam naudotojui."""
    u = current()
    return bool(u) and u["plan"] in AI_PLANS


def _check(username, password):
    """Grąžina kliento vardą (raktą Secrets), jei slaptažodis teisingas."""
    users = _secrets_users()
    name = username.strip()
    key = name if name in users else name.lower() if name.lower() in users else None
    cfg = users.get(key) if key else None
    if not cfg or cfg.get("active", True) is False:
        hmac.compare_digest(b"x", b"y")  # vienodas laikas, kad nesimatytų, ar vardas egzistuoja
        return None
    return key if hmac.compare_digest(str(cfg.get("password", "")).encode(), password.encode()) else None


def require_login():
    """Grąžina naudotoją arba parodo prisijungimo formą ir sustabdo puslapį."""
    u = current()
    if u:
        if u["plan"] != "open":
            with st.sidebar:
                st.markdown(f"**{u['name']}**  \n{PLANS[u['plan']]} planas")
                if st.button("Atsijungti", key="logout"):
                    st.session_state.pop("account", None)
                    st.rerun()
        return u
    _, mid, _ = st.columns([1, 3, 1])
    with mid:
        with st.form("login"):
            st.markdown("#### Prisijungimas")
            name = st.text_input("Prisijungimo vardas", autocomplete="username")
            pw = st.text_input("Slaptažodis", type="password", autocomplete="current-password")
            ok = st.form_submit_button("Prisijungti", type="primary", width="stretch")
        if ok:
            user = _check(name, pw)
            if user:
                st.session_state["account"] = user
                st.rerun()
            time.sleep(1.0)  # lėtina slaptažodžių spėliojimą
            st.error("Neteisingas vardas arba slaptažodis.")
        if contact():
            st.caption(f"Neturite prieigos? Susisiekite: {contact()}")
    st.stop()


# ---------- Balso atpažinimo minučių apskaita ----------

def _month():
    return datetime.date.today().strftime("%Y-%m")


def _usage_file():
    return os.path.join(DATA_DIR, "usage.json")


def _load():
    try:
        with open(_usage_file(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def used_minutes(username=None, month=None):
    u = username if username is not None else (current() or {}).get("username", "")
    return float(_load().get(month or _month(), {}).get(u, 0.0))


def remaining_minutes():
    """Kiek balso atpažinimo minučių liko šį mėnesį (None – be limito)."""
    u = current()
    if not u or u["minutes"] is None or u["plan"] == "open":
        return None
    return max(0.0, u["minutes"] - used_minutes(u["username"]))


def add_minutes(minutes):
    """Užskaito panaudotas balso atpažinimo minutes prisijungusiam naudotojui."""
    u = current()
    if not u or u["plan"] == "open" or minutes <= 0:
        return
    with _lock:
        data = _load()
        m = data.setdefault(_month(), {})
        m[u["username"]] = round(m.get(u["username"], 0.0) + minutes, 2)
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = _usage_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _usage_file())


def usage_table():
    """Administratoriui: visų klientų šio mėnesio naudojimas."""
    rows = []
    for name, cfg in _secrets_users().items():
        plan = str(cfg.get("plan", "basic")).lower()
        rows.append({"Klientas": cfg.get("name") or name, "Vardas": name,
                     "Planas": PLANS.get(plan, plan),
                     "Aktyvus": "taip" if cfg.get("active", True) is not False else "ne",
                     "Panaudota min.": round(used_minutes(name), 1),
                     "Limitas min.": "–" if plan != "premium" else float(cfg.get("minutes", DEFAULT_MINUTES))})
    return rows
