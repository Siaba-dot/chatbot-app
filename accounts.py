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

    [pricing]                          # planų lentelė prisijungimo puslapyje (neprivaloma)
    basic = "9 €/mėn."
    premium = "19 €/mėn."
    premium_minutes = 60
    note = "7 dienos nemokamai · mokant už metus – 2 mėnesiai dovanų"
    show = true                        # false – lentelės nerodyti

Jei [users] neaprašyta – programa atvira visiems, kaip anksčiau.
Kliento išjungimas: ištrinkite jo bloką arba įrašykite active = false.
"""
import datetime
import hmac
import html
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
    if pricing().get("show", True) is not False:
        st.markdown(plans_html(), unsafe_allow_html=True)
    st.stop()


def pricing():
    try:
        return dict(st.secrets.get("pricing") or {})
    except Exception:
        return {}


def _contact_link(subject):
    c = (contact() or "").strip()
    if not c:
        return ""
    if "@" in c and " " not in c:
        href = f"mailto:{c}?subject={subject.replace(' ', '%20')}"
    elif c.startswith(("http://", "https://")):
        href = c
    elif c.replace("+", "").replace(" ", "").isdigit():
        href = "tel:" + c.replace(" ", "")
    else:
        return f'<div class="pl-contact">{html.escape(c)}</div>'
    return f'<a class="pl-btn" href="{html.escape(href)}" target="_blank">Susisiekti</a>'


BASIC_FEATURES = [
    "Automatinis montažas: pauzių kirpimas, 9:16, keli įrašai",
    "Triukšmo valymas ir vienodas garsumas",
    "3 prabangūs šablonai, kabliukas, kvietimas veikti",
    "11 filtrų ir 7 efektai su peržiūra",
    "Muzikos biblioteka be autorių teisių",
    "Viršelis ir titrai iš įvesto teksto",
]
PREMIUM_FEATURES = [
    "Viskas, kas Pagrindiniame plane",
    "Automatiniai titrai iš kalbos",
    "Titrų vertimas (EN, RU, PL, DE…)",
    "Aprašymas, grotažymės ir kabliukų idėjos",
]


def plans_html():
    """Planų palyginimo lentelė (kainos – iš Secrets [pricing])."""
    pr = pricing()
    basic = html.escape(str(pr.get("basic", "9 €/mėn.")))
    premium = html.escape(str(pr.get("premium", "19 €/mėn.")))
    minutes = pr.get("premium_minutes", DEFAULT_MINUTES)
    note = html.escape(str(pr.get("note", "7 dienos nemokamai · mokant už metus – 2 mėnesiai dovanų")))
    prem = PREMIUM_FEATURES + [f"{minutes} min. balso atpažinimo per mėnesį"]

    def card(name, price, feats, cls, subject):
        items = "".join(f"<li>{html.escape(f)}</li>" for f in feats)
        badge = '<span class="pl-badge">Populiariausias</span>' if cls == "pl-prem" else ""
        return (f'<div class="pl-card {cls}">{badge}<div class="pl-name">{name}</div>'
                f'<div class="pl-price">{price}</div><ul>{items}</ul>{_contact_link(subject)}</div>')

    return f"""
<style>
.pl-wrap {{ margin: 2.2rem 0 .5rem; }}
.pl-title {{ text-align: center; font-family: 'Playfair Display', Georgia, serif; font-size: 1.7rem; color: #F4EEDF; }}
.pl-note {{ text-align: center; color: #B8AF9C; font-size: .9rem; margin: .3rem 0 1.2rem; }}
.pl-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }}
.pl-card {{ display: flex; flex-direction: column; position: relative; border: 1px solid rgba(212,175,55,.22); border-radius: 16px; padding: 1.3rem 1.2rem;
  background: linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.01)); }}
.pl-prem {{ border-color: rgba(212,175,55,.75); box-shadow: 0 10px 40px rgba(212,175,55,.12);
  background: linear-gradient(180deg, rgba(212,175,55,.12), rgba(212,175,55,.02)); }}
.pl-badge {{ position: absolute; top: -.7rem; right: 1rem; background: linear-gradient(100deg, #B8912E, #F3DE9C, #D4AF37);
  color: #0B0B0C; font-size: .68rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  padding: .2rem .6rem; border-radius: 999px; }}
.pl-name {{ letter-spacing: .3em; text-transform: uppercase; font-size: .75rem; color: #D4AF37; font-weight: 600; }}
.pl-price {{ font-family: 'Playfair Display', Georgia, serif; font-size: 2rem; color: #F3DE9C; margin: .3rem 0 .7rem; }}
.pl-card ul {{ list-style: none; padding: 0; margin: 0 0 1rem; flex: 1; }}
.pl-card li {{ color: #E4DCC8; font-size: .9rem; padding: .28rem 0 .28rem 1.4rem; position: relative; }}
.pl-card li::before {{ content: "✦"; position: absolute; left: 0; color: #D4AF37; font-size: .8rem; top: .35rem; }}
.pl-btn {{ display: block; text-align: center; padding: .55rem; border-radius: 10px; text-decoration: none !important;
  border: 1px solid rgba(212,175,55,.5); color: #F3DE9C !important; font-weight: 500; }}
.pl-prem .pl-btn {{ background: linear-gradient(100deg, #B8912E, #F3DE9C 45%, #D4AF37 70%, #B8912E); color: #0B0B0C !important;
  border: 0; font-weight: 600; }}
.pl-contact {{ text-align: center; color: #B8AF9C; font-size: .85rem; }}
</style>
<div class="pl-wrap">
  <div class="pl-title">Planai</div>
  <div class="pl-note">{note}</div>
  <div class="pl-grid">
    {card("Pagrindinis", basic, BASIC_FEATURES, "pl-basic", "Reels studija - Pagrindinis planas")}
    {card("Premium", premium, prem, "pl-prem", "Reels studija - Premium planas")}
  </div>
</div>
"""


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
