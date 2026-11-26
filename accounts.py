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


def users():
    """Visi klientai iš Secrets: {vardas: {password, plan, minutes, name, active}}."""
    return _secrets_users()


def check_password(username, password):
    """Grąžina kliento vardą, jei slaptažodis teisingas (naudoja ir API serveris)."""
    return _check(username, password)


def _secrets_users():
    """Visi klientai: iš Secrets (secrets.toml) ir pridėti per administravimą (DATA_DIR/users.json).
    Tas pats vardas Secrets'uose turi pirmenybę."""
    try:
        users = st.secrets.get("users") or {}
    except Exception:  # Secrets failo nėra
        users = {}
    out = {str(k): dict(v, source="managed") for k, v in managed_users().items()}
    out.update({str(k): dict(dict(v), source="secrets") for k, v in users.items()})
    return out


# ---------- Klientai, valdomi per naršyklę (administravimas) ----------
def _users_file():
    return os.path.join(DATA_DIR, "users.json")


def managed_users():
    try:
        with open(_users_file(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_managed_users(users):
    with _lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = _users_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _users_file())


def hash_password(password):
    """Slaptažodis saugomas tik kaip PBKDF2 maiša (ne atviru tekstu)."""
    import hashlib
    import secrets as _s
    salt = _s.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"pbkdf2${salt}${digest}"


def _password_ok(cfg, password):
    stored = str(cfg.get("password_hash") or "")
    if stored.startswith("pbkdf2$"):
        import hashlib
        _, salt, digest = stored.split("$", 2)
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
        return hmac.compare_digest(test, digest)
    return hmac.compare_digest(str(cfg.get("password", "")).encode(), password.encode())


# ---------- AI išlaidų ribos (per mėnesį) ----------
# ai_clips – AI video kadrai (Google), voice_chars – AI įgarsinimo simboliai. None – be ribos (administratorius).
# auto_videos – automatiškai iš scenarijaus sudėti video (ir „Kiti vaizdai“)
# director – 💬 AI režisieriaus žinutės
DEFAULT_LIMITS = {"basic": {"ai_clips": 0, "voice_chars": 0, "auto_videos": 10, "director": 0},
                  "premium": {"ai_clips": 10, "voice_chars": 20000, "auto_videos": 60, "director": 300},
                  "trial": {"ai_clips": 2, "voice_chars": 3000, "auto_videos": 5, "director": 30}}   # 🎁 Premium bandymas (mažesnės ribos)


def in_trial(cfg):
    """Ar klientas dabar naudojasi nemokamu Premium bandymu (pagrindinis planas + galiojantis trial_until)."""
    import time as _t
    return (str((cfg or {}).get("plan", "basic")).lower() == "basic"
            and float((cfg or {}).get("trial_until") or 0) > _t.time())


def effective_plan(cfg):
    """Planas, pagal kurį veikia funkcijos: bandymo metu – premium."""
    plan = str((cfg or {}).get("plan", "basic")).lower()
    plan = plan if plan in ("basic", "premium", "admin") else "basic"
    return "premium" if in_trial(cfg) else plan


def limits_for(username):
    cfg = _secrets_users().get(username) or {}
    plan = effective_plan(cfg)
    if plan == "admin":
        return {"ai_clips": None, "voice_chars": None, "auto_videos": None, "director": None}
    base = dict(DEFAULT_LIMITS["trial" if in_trial(cfg) else plan])
    for k in base:
        if cfg.get(k) is not None:
            base[k] = int(cfg[k])
    return base


def used(username, kind, month=None):
    """Panaudota šį mėnesį: kind – "minutes" | "ai_clips" | "voice_chars"."""
    data = _load()
    if kind == "minutes":
        return float(data.get(month or _month(), {}).get(username, 0.0))
    return float(data.get(f"{month or _month()}:{kind}", {}).get(username, 0))


def add_usage(username, kind, amount):
    if not username or amount <= 0:
        return
    if kind == "minutes":
        return add_minutes_for(username, amount)
    with _lock:
        data = _load()
        m = data.setdefault(f"{_month()}:{kind}", {})
        m[username] = round(m.get(username, 0) + amount, 2)
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = _usage_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _usage_file())


def left(username, kind):
    """Kiek liko šį mėnesį (None – be ribos)."""
    lim = limits_for(username).get(kind)
    return None if lim is None else max(0, lim - used(username, kind))


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
    plan = effective_plan(cfg)
    view = st.session_state.get("view_as") if plan == "admin" else None
    if view in ("basic", "premium"):  # administratorius žiūri, ką mato klientas (minutės neskaičiuojamos)
        return {"username": u, "name": cfg.get("name") or u, "plan": view, "minutes": None,
                "preview": True, "admin": True}
    return {"username": u, "name": cfg.get("name") or u, "plan": plan, "admin": plan == "admin",
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
    return key if _password_ok(cfg, password) else None


# Prekės ženklo istorija prisijungimo puslapyje (trumpa versija + visa išskleidžiama)
STORY_HTML = """
<style>
.st-story { text-align: center; margin: .2rem auto 1rem; max-width: 34rem; }
.st-story .q { font-family: 'Playfair Display', Georgia, serif; font-style: italic; font-size: 1.12rem;
  line-height: 1.55; color: #F3E7D3; }
.st-story .m { margin-top: .8rem; font-family: 'Playfair Display', Georgia, serif; font-size: 1.05rem;
  background: linear-gradient(100deg, #B85F12, #FFD58A 45%, #E39B2E 70%, #B85F12);
  -webkit-background-clip: text; background-clip: text; color: transparent; letter-spacing: .02em; }
</style>
<div class="st-story">
  <div class="q">Gintaras milijonus metų saugo sustabdytą akimirką.<br>Mes darome tą patį su jūsų video.</div>
  <div class="m">Jūsų akimirkos – kaip gintaras: išsaugotos gražiausios.</div>
</div>
"""

STORY_FULL = """
Senovėje Baltijos jūros dugne stovėjo gintaro rūmai. Juose gyveno jūrų deivė **Jūratė**. Ji pamilo paprastą
žvejį **Kastytį**, tačiau griaustinio dievas, supykęs dėl tos meilės, sudaužė jos rūmus. Nuo tada audros į
Lietuvos krantą išmeta gintaro gabalėlius – tos meilės nuolaužas.

Bet gintaras slepia dar vieną paslaptį. Prieš milijonus metų lašas sakų sustabdė akimirką – lapelį, oro
burbuliuką, saulės spindulį – ir išsaugojo ją amžinai. Todėl kiekvienas gintaro gabalėlis yra laiko
sustabdyta istorija.

Šiandien mūsų akimirkos gyvena trumpuose video. Jos greitai prabėga ekrane, nors kiekviena verta būti
išsaugota gražiai.

Taip gimė **Reels montavimo studija** – lietuviška studija su Baltijos gintaro dvasia. Ji iš jūsų video
išsaugo tai, kas vertingiausia: iškerpa tuščias pauzes, nušveičia garsą, suteikia vaizdui šiltą gintaro
šviesą ir paverčia kasdienį įrašą žibančia istorija.

Kaip jūra išneša gintarą į krantą, taip studija iškelia į šviesą geriausias jūsų akimirkas.

*Jūsų akimirkos – kaip gintaras: išsaugotos gražiausios.*
"""


def require_login():
    """Grąžina naudotoją arba parodo prisijungimo formą ir sustabdo puslapį."""
    u = current()
    if u:
        if u["plan"] != "open":
            with st.sidebar:
                st.markdown(f"**{u['name']}**  \n{PLANS[u['plan']]} planas")
                if u.get("admin"):
                    st.selectbox("👁 Žiūrėti kaip klientas", ["admin", "premium", "basic"], key="view_as",
                                 format_func=lambda p: {"admin": "Administratorius (aš)",
                                                        "premium": "Premium klientas",
                                                        "basic": "Pagrindinio plano klientas"}[p],
                                 help="Pamatykite studiją taip, kaip ją mato klientas. Jūsų minutės neskaičiuojamos.")
                if st.button("Atsijungti", key="logout"):
                    st.session_state.pop("account", None)
                    st.rerun()
        return u
    _, mid, _ = st.columns([1, 3, 1])
    with mid:
        st.markdown(STORY_HTML, unsafe_allow_html=True)
        with st.expander("✦  Gintaro istorija"):
            st.markdown(STORY_FULL)
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
.pl-title {{ text-align: center; font-family: 'Playfair Display', Georgia, serif; font-size: 1.7rem; color: #F7ECDA; }}
.pl-note {{ text-align: center; color: #C9D3E2; font-size: .9rem; margin: .3rem 0 1.2rem; }}
.pl-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }}
.pl-card {{ display: flex; flex-direction: column; position: relative; border: 1px solid rgba(227,155,46,.22); border-radius: 16px; padding: 1.3rem 1.2rem;
  background: linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.01)); }}
.pl-prem {{ border-color: rgba(227,155,46,.75); box-shadow: 0 10px 40px rgba(227,155,46,.12);
  background: linear-gradient(180deg, rgba(227,155,46,.12), rgba(227,155,46,.02)); }}
.pl-badge {{ position: absolute; top: -.7rem; right: 1rem; background: linear-gradient(100deg, #B85F12, #FFD58A, #E39B2E);
  color: #061226; font-size: .68rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  padding: .2rem .6rem; border-radius: 999px; }}
.pl-name {{ letter-spacing: .3em; text-transform: uppercase; font-size: .75rem; color: #E39B2E; font-weight: 600; }}
.pl-price {{ font-family: 'Playfair Display', Georgia, serif; font-size: 2rem; color: #FFD58A; margin: .3rem 0 .7rem; }}
.pl-card ul {{ list-style: none; padding: 0; margin: 0 0 1rem; flex: 1; }}
.pl-card li {{ color: #EADCC4; font-size: .9rem; padding: .28rem 0 .28rem 1.4rem; position: relative; }}
.pl-card li::before {{ content: "✦"; position: absolute; left: 0; color: #E39B2E; font-size: .8rem; top: .35rem; }}
.pl-btn {{ display: block; text-align: center; padding: .55rem; border-radius: 10px; text-decoration: none !important;
  border: 1px solid rgba(227,155,46,.5); color: #FFD58A !important; font-weight: 500; }}
.pl-prem .pl-btn {{ background: linear-gradient(100deg, #B85F12, #FFD58A 45%, #E39B2E 70%, #B85F12); color: #061226 !important;
  border: 0; font-weight: 600; }}
.pl-contact {{ text-align: center; color: #C9D3E2; font-size: .85rem; }}
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
    if not u or u["plan"] == "open" or u.get("preview") or minutes <= 0:
        return
    add_minutes_for(u["username"], minutes)


def add_minutes_for(username, minutes):
    """Užskaito minutes nurodytam naudotojui (naudoja ir API serveris)."""
    if not username or minutes <= 0:
        return
    with _lock:
        data = _load()
        m = data.setdefault(_month(), {})
        m[username] = round(m.get(username, 0.0) + minutes, 2)
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
