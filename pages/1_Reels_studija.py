import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import streamlit as st
import streamlit.components.v1 as components

# Kad puslapis veiktų ir paleistas kaip atskira programa (pagrindinis failas – šis puslapis)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import accounts
import clips_ui
import animations
import reels_studio
import video_editor

P = "reels_"  # šio puslapio būsenos raktų priešdėlis
# Langelių tinklelis su skirtukais (šablonai, filtrai, efektai, titrai, perėjimai) – components/tiles/index.html
tile_grid = components.declare_component(
    "tile_grid", path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "components", "tiles"))
# Muzikos takelis: muzikos blokai pasirinktose video vietose (components/musictrack/index.html)
music_track = components.declare_component(
    "music_track", path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "components",
                                     "musictrack"))

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
st.set_page_config(page_title="Gintaro Reels studija", page_icon=os.path.join(ASSETS, "gintaras_icon.png"),
                   layout="wide", initial_sidebar_state="auto")
with open(os.path.join(ASSETS, "gintaras.svg"), encoding="utf-8") as _f:
    LOGO = " ".join(_f.read().split())

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,700;1,400&family=Inter:wght@400;500;600&display=swap');
:root { --gold: #E39B2E; --gold-2: #FFD58A; --gold-3: #8A4310; --ink: #061226; --line: rgba(227,155,46,.22); }
.stApp {
  background:
    radial-gradient(900px 420px at 50% -120px, rgba(227,155,46,.18), transparent 70%),
    radial-gradient(1000px 700px at 110% 20%, rgba(28,72,140,.35), transparent 70%),
    radial-gradient(900px 600px at -15% 85%, rgba(18,52,108,.40), transparent 70%),
    linear-gradient(180deg, #071630 0%, #061226 55%, #040C1B 100%);
  background-attachment: fixed;
}
.stApp, .stApp p, .stApp label, .stApp li { font-family: 'Inter', system-ui, sans-serif; }
#MainMenu, footer { visibility: hidden; }
.lux-hero { text-align: center; padding: 1.2rem 0 1.6rem; }
.lux-kicker { letter-spacing: .42em; font-size: .72rem; color: var(--gold); text-transform: uppercase;
  font-weight: 600; }
.lux-title { font-family: 'Playfair Display', Georgia, serif; font-weight: 700; font-size: clamp(2.1rem, 7vw, 3.3rem);
  line-height: 1.08; margin: .5rem 0 .6rem;
  background: linear-gradient(100deg, #8A4310 0%, #FFD58A 35%, #E39B2E 55%, #FFEBC2 70%, #B85F12 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.lux-sub { color: #C9D3E2; font-size: 1rem; max-width: 34rem; margin: 0 auto; }
.lux-rule { width: 84px; height: 1px; margin: 1.2rem auto 0;
  background: linear-gradient(90deg, transparent, var(--gold), transparent); }
.lux-step { display: flex; align-items: baseline; gap: .8rem; margin: .2rem 0 .6rem; }
.lux-step .n { font-family: 'Playfair Display', serif; font-style: italic; color: var(--gold); font-size: 1.5rem; }
.lux-step .t { font-family: 'Playfair Display', serif; font-size: 1.35rem; color: #F7ECDA; font-weight: 500; }
.lux-step .d { color: #A9B9D0; font-size: .85rem; margin-left: auto; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--line) !important;
  background: linear-gradient(180deg, rgba(20,48,92,.35), rgba(8,22,46,.25)); border-radius: 14px;
  backdrop-filter: blur(2px); }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], .stFormSubmitButton > button,
button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(100deg, #B85F12, #FFD58A 45%, #E39B2E 70%, #B85F12);
  color: #061226; border: 0; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  box-shadow: 0 8px 30px rgba(227,155,46,.18); }
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover { filter: brightness(1.07); color: #061226; }
.stButton > button[kind="secondary"], .stDownloadButton > button[kind="secondary"],
button[data-testid="stBaseButton-secondary"] {
  border-color: rgba(227,155,46,.45); background: rgba(14,34,66,.55); }
button[data-testid="stBaseButton-secondary"]:hover { border-color: #E39B2E; color: #FFD58A; }
/* prislopintas tekstas – šviesesnis, kad gerai matytųsi ant mėlyno fono */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #B4C3D8 !important; }
[data-testid="stMetricValue"] { font-family: 'Playfair Display', serif; color: var(--gold-2); }
.lux-caption { white-space: pre-wrap; border-left: 2px solid var(--gold); padding: .2rem 0 .2rem 1rem;
  color: #F3E7D3; }
.lux-tags { color: var(--gold-2); font-size: .92rem; margin-top: .6rem; }
.lux-premium { border: 1px solid var(--line); border-radius: 12px; padding: .7rem .9rem; margin: .3rem 0 .6rem;
  background: linear-gradient(100deg, rgba(227,155,46,.10), rgba(227,155,46,.02)); color: #EEDFC4; font-size: .92rem; }
.lux-foot { text-align: center; color: #4F6688; font-size: .75rem; letter-spacing: .3em; margin-top: 2rem; }
[class*="st-key-reels_fgrid"] button, [class*="st-key-reels_egrid"] button {
  min-height: 1.9rem; padding: .15rem .3rem; border-radius: 8px; }
[class*="st-key-reels_tile"] button *, [class*="st-key-reels_tsel"] button * {
  font-size: .74rem !important; line-height: 1.15; letter-spacing: 0; text-transform: none; }
[class*="st-key-reels_tsel"] button, [class*="st-key-reels_tsel"] button * { color: #061226 !important; }
[class*="st-key-reels_tile"] img, [class*="st-key-reels_tsel"] img {
  border-radius: 10px 10px 0 0; transition: transform .15s; }
[class*="st-key-reels_tile"] img { opacity: .82; }
[class*="st-key-reels_tsel"] img { outline: 2px solid var(--gold); outline-offset: -2px; }
/* Šoninis nustatymų skydelis */
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0B1E3E, #061226);
  border-right: 1px solid var(--line); }
@media (min-width: 900px) { section[data-testid="stSidebar"] { width: 430px !important; } }
section[data-testid="stSidebar"] [data-testid="stExpander"] details { border-color: var(--line); border-radius: 12px; }
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p { font-family: 'Playfair Display', serif;
  font-size: 1.08rem; color: #F7ECDA; }
.lux-side-title { font-family: 'Playfair Display', serif; font-size: 1.5rem; color: var(--gold-2); margin: .2rem 0 .6rem; }
.block-container { max-width: 1100px; padding-top: 2.2rem; }
.lux-hint { color: #8EA2BF; font-size: .85rem; text-align: center; margin: -.4rem 0 .8rem; }
[class*="st-key-reels_actions"] button { padding-left: .3rem; padding-right: .3rem; }
[class*="st-key-reels_actions"] button p { font-size: .9rem; white-space: nowrap; }
[class*="st-key-reels_view"] video, [class*="st-key-reels_view"] img { max-height: 56vh; object-fit: contain; }
[class*="st-key-reels_view"] [data-testid="stImage"], [class*="st-key-reels_view"] [data-testid="stVideo"] {
  display: flex; justify-content: center; }
.lux-story { text-align: center; max-width: 46rem; margin: -.3rem auto .5rem; font-family: 'Playfair Display', serif;
  font-style: italic; color: #DCCFB8; font-size: .98rem; line-height: 1.5; }
.lux-story span { display: block; font-style: normal; margin-top: .15rem;
  background: linear-gradient(100deg, #B85F12, #FFD58A 45%, #E39B2E 70%, #B85F12);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.lux-empty { border: 1px dashed var(--line); border-radius: 14px; padding: 2.4rem 1rem; text-align: center;
  color: #8EA2BF; }
/* Baltijos gintaras: logotipas ir lietuviškas ornamentas */
.lux-logo { display: flex; justify-content: center; margin: .9rem 0 .2rem; }
.lux-logo svg { width: 74px; height: 74px; filter: drop-shadow(0 6px 22px rgba(227,155,46,.35)); }
.lux-orn { width: 230px; height: 14px; margin: .7rem auto 0; opacity: .8;
  background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='14'><g fill='none' stroke='%23E8A846' stroke-width='1'><path d='M1 7 L7 1 L13 7 L7 13 Z'/></g><circle cx='7' cy='7' r='1.5' fill='%23E8A846'/><path d='M17 7 L21 3 L25 7 L21 11 Z' fill='%23E8A846' fill-opacity='.55'/></svg>") repeat-x center;
  -webkit-mask: linear-gradient(90deg, transparent, #000 25%, #000 75%, transparent);
          mask: linear-gradient(90deg, transparent, #000 25%, #000 75%, transparent); }
.lux-side-logo { display: flex; align-items: center; gap: .6rem; }
.lux-side-logo svg { width: 38px; height: 38px; filter: drop-shadow(0 3px 10px rgba(227,155,46,.35)); }
.st-steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: .45rem; max-width: 52rem;
            margin: .2rem auto .45rem; }
.st-step { border: 1px solid rgba(227,155,46,.22); border-radius: 14px; padding: .5rem .55rem;
           background: rgba(14,34,66,.45); display: flex; flex-direction: column; gap: .1rem; }
.st-step .n { width: 1.55rem; height: 1.55rem; border-radius: 50%; display: inline-flex; align-items: center;
              justify-content: center; font-weight: 700; font-size: .85rem; color: #B4C3D8;
              border: 1px solid rgba(180,195,216,.35); }
.st-step .t { font-family: 'Playfair Display', serif; font-weight: 700; color: #F3E7D3; font-size: 1rem; }
.st-step .d { font-size: .74rem; color: #9FB0C8; line-height: 1.25; }
.st-step.on { border-color: #E39B2E; box-shadow: 0 0 16px rgba(227,155,46,.25); background: rgba(227,155,46,.10); }
.st-step.on .n { background: linear-gradient(135deg, #FFD58A, #E39B2E); color: #061226; border: 0; }
.st-step.done .n { background: rgba(227,155,46,.25); color: #FFD58A; border: 0; }
.st-gift { max-width: 52rem; margin: 0 auto .8rem; text-align: center; font-size: .86rem; color: #D9C9A8;
           padding: .45rem .8rem; border-radius: 999px; border: 1px dashed rgba(227,155,46,.4); }
.st-gift.on { border-style: solid; background: rgba(227,155,46,.14); color: #FFE7B0; }
.lux-howto { font-size: .88rem; color: #D6DFEC; background: rgba(14,34,66,.55); border: 1px solid rgba(227,155,46,.3);
             border-radius: 12px; padding: .6rem .85rem; margin-bottom: .6rem; }
.lux-howto ul { margin: .3rem 0 0 1.1rem; padding: 0; }
.lux-howto li { margin: .15rem 0; }
.lux-howto code { color: #FFD58A; background: rgba(227,155,46,.12); padding: 0 .25rem; border-radius: 4px; }
.lux-howto .k { color: #FFD58A; font-weight: 800; }
.lux-done { font-size: 1rem; color: #FFE7B0; margin-bottom: .5rem; }
@media (max-width: 640px) {
  .st-steps { grid-template-columns: repeat(2, 1fr); }
  .st-step .d { display: none; }
  .st-step { flex-direction: row; align-items: center; gap: .45rem; padding: .4rem .5rem; }
}
.lux-settings-hint { display: block; text-align: center; margin: .2rem auto .9rem; padding: .55rem .9rem;
  border: 1px solid rgba(227,155,46,.45); border-radius: 999px; max-width: 34rem; color: #FFD58A; font-size: .9rem;
  background: linear-gradient(100deg, rgba(227,155,46,.14), rgba(227,155,46,.04)); }
@media (min-width: 900px) { .lux-settings-hint { display: none; } }
.lux-foot .orn { display: block; margin: 0 auto .5rem; }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="lux-hero" style="padding:.2rem 0 .9rem">
  <div class="lux-logo">{LOGO}</div>
  <div class="lux-kicker">Lietuviška studija · Baltijos gintaro dvasia</div>
  <div class="lux-title" style="font-size:clamp(1.8rem,5vw,2.6rem)">Reels montavimo studija</div>
  <div class="lux-orn"></div>
</div>
""", unsafe_allow_html=True)


user = accounts.require_login()
plan = user["plan"]

# Gintaro istorija prisijungus: trumpai (kad peržiūra liktų arti), visa – išskleidžiama
st.markdown('<div class="lux-story">Gintaras milijonus metų saugo sustabdytą akimirką – mes darome tą patį su '
            'jūsų video. <span>Jūsų akimirkos – kaip gintaras: išsaugotos gražiausios.</span></div>',
            unsafe_allow_html=True)
_, _mid, _ = st.columns([1, 3, 1])
with _mid.expander("✦  Gintaro istorija"):
    st.markdown(accounts.STORY_FULL)


def step(n, title, desc=""):
    st.markdown(f'<div class="lux-step"><span class="n">{n}</span><span class="t">{title}</span>'
                f'<span class="d">{desc}</span></div>', unsafe_allow_html=True)


# ---------- 💡 Ką filmuoti? – idėjos ir sufleris ----------
def gen_ideas():
    ss = st.session_state
    niche = (ss.get(P + "niche") or "").strip()
    ss.pop(P + "ideas_err", None)
    if not niche:
        ss[P + "ideas_err"] = "Įrašykite savo sritį, pvz. „kirpykla“, „kavinė“, „buhalterė“."
        return
    ideas, cl = [], clips_ui.openai_client()
    if cl is not None:
        try:
            ideas = reels_studio.ai_ideas(cl, niche)
        except Exception as e:
            ss[P + "ideas_err"] = f"AI idėjų nepavyko gauti ({e}) – rodomos studijos idėjos."
    ss[P + "ideas_ai"] = bool(ideas)
    ss[P + "ideas"] = ideas or reels_studio.template_ideas(niche)
    ss.pop(P + "idea_used", None)


def use_idea(i):
    ss = st.session_state
    it = ss[P + "ideas"][i]
    ss[P + "script"] = (it["hook"].rstrip(".") + ". " + it["script"]).strip()
    ss[P + "hook"] = it["hook"]
    if it.get("cta"):
        ss[P + "cta"] = it["cta"]
    ss[P + "subtitle_text_in"] = ss[P + "script"]  # be AI rakto – titrai iš to paties teksto
    ss[P + "source"] = "🎥 Filmuoti dabar"
    ss[P + "idea_used"] = i


def ideas_ui():
    ss = st.session_state
    with st.expander("💡 Ką filmuoti? – idėjos su paruoštu tekstu ir sufleriu",
                     expanded=not ss.get(P + "clips") or bool(ss.get(P + "ideas"))):
        st.caption("Nežinote, ką pasakyti? Įrašykite savo sritį – gausite 5 Reels idėjas su paruoštu tekstu. "
                   "Pasirinkus idėją, filmuojant tekstas slinks ekrane kaip sufleris – nieko nereikia mokytis.")
        c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
        c1.text_input("Jūsų sritis", key=P + "niche", placeholder="Pvz.: kirpykla, kavinė, nagų salonas, buhalterė")
        c2.button("✨ Sugalvok 5 idėjas", on_click=gen_ideas, type="primary", width="stretch", key=P + "ideas_btn")
        if ss.get(P + "ideas_err"):
            st.warning(ss[P + "ideas_err"])
        ideas = ss.get(P + "ideas") or []
        if ideas and not ss.get(P + "ideas_ai"):
            st.caption("Studijos idėjų šablonai. Su OpenAI raktu idėjas ir tekstą jūsų sričiai sukurs AI.")
        for i, it in enumerate(ideas):
            used = ss.get(P + "idea_used") == i
            with st.container(border=True):
                st.markdown(f"**{i + 1}. {html.escape(it['title'])}**" + ("  ✅" if used else ""))
                st.markdown(f"🎣 **Kabliukas:** {html.escape(it['hook'])}  \n"
                            f"🗣 {html.escape(it['script'])}  \n"
                            + (f"📣 **Kvietimas:** {html.escape(it['cta'])}" if it.get("cta") else ""))
                if it.get("shot"):
                    st.caption("🎥 " + it["shot"])
                st.button("✅ Pasirinkta – filmuokite žemiau" if used else "🎬 Filmuoti su šiuo tekstu",
                          key=f"{P}idea{i}", on_click=use_idea, args=(i,), width="stretch",
                          type="secondary" if used else "primary")
        if ss.get(P + "script"):
            st.text_area("📜 Sufleris – tekstas, kuris slinks filmuojant (galite pataisyti)", key=P + "script",
                         height=110)


def apply_template():
    t = reels_studio.TEMPLATES[st.session_state[P + "template"]]
    st.session_state[P + "accent"] = t["accent"]
    st.session_state[P + "color"] = t["color"]


def pick_template(name):
    st.session_state[P + "template"] = name
    apply_template()


def pick_transition(name):
    st.session_state[P + "transition"] = name


@st.cache_data(max_entries=60, show_spinner=False)
def transition_tile(fa, fb, name):
    with tempfile.TemporaryDirectory() as tmp:
        a, b = os.path.join(tmp, "a.jpg"), os.path.join(tmp, "b.jpg")
        for path, data in ((a, fa), (b, fb)):
            with open(path, "wb") as f:
                f.write(data)
        out = reels_studio.transition_preview(a, b, os.path.join(tmp, "x.jpg"), name)
        with open(out, "rb") as f:
            return f.read()


@st.cache_data(max_entries=800, show_spinner=False)
def square(img, cy=0.5, frac=1.0, size=144):
    """Kvadratinė miniatiūra langeliui (data URI): iškerpama aplink aukštį cy (0–1), frac – kvadrato dalis pločio."""
    import base64
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(img)).convert("RGB")
    w, h = im.size
    side = max(8, min(h, round(min(w, h) * frac)))
    top = round(min(max(cy * h - side / 2, 0), h - side))
    left = (w - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def tiles(key, items, selected, tabs=None, size=64):
    """Langelių tinklelis. items: {id: {label, img, sig, group | multi, help}}. Grąžina nieko – paspaudimą
    apdoroja tile_click() kitame perpiešime."""
    ver = hash(tuple(it.get("img", "")[-64:] for it in items.values()))
    tile_grid(items=items, selected=list(selected), tabs=tabs or [], size=size, ver=ver, key=key, default=None)


def tile_click(key):
    """Naujas langelio paspaudimas (id) arba None. Skaitoma PRIEŠ piešiant – kad pasirinkimas būtų iškart."""
    v = st.session_state.get(key)
    if v and v.get("t") != st.session_state.get(key + "_t"):
        st.session_state[key + "_t"] = v["t"]
        return v.get("pick")
    return None


SPEEDS = [1.0, 1.05, 1.1, 1.15, 1.25, 1.5, 1.75, 2.0]
PROGRESS = ["Viršuje", "Apačioje", "Nėra"]


# ---------- ✨ Dirbtinis intelektas ----------
def ai_words():
    """Paruoštos kalbos žodžiai (montažo laiku) – AI kontekstui."""
    pr = st.session_state.get(P + "prep")
    return list(pr["analysis"]["words"]) if pr else []


def set_hook(text):
    st.session_state[P + "hook"] = text


def run_ai_hooks(client, words, text):
    st.session_state.pop(P + "ai_hooks_err", None)
    try:
        st.session_state[P + "hook_ideas"] = reels_studio.ai_hooks(client, words, text=text)
    except Exception as e:
        st.session_state[P + "ai_hooks_err"] = str(e)


AI_LABELS = {"template": "Šablonas", "accent": "Akcentas", "color": "Filtras", "effects": "Efektai",
             "look": "Titrų stilius", "hook": "Kabliukas", "cta": "Kvietimas", "link": "Nuoroda",
             "hook_pos": "Kabliuko vieta", "subs_pos": "Titrų vieta", "text_size": "Kabliuko dydis",
             "subs_size": "Titrų dydis", "key_words": "Svarbiausi žodžiai", "punch": "Akcentų priartėjimas",
             "end_card": "Pabaigos kortelė", "yt_end": "YouTube pabaigos ekranas",
             "moment_at": "Gintaro akimirka (s)", "transition": "Perėjimas", "music_choice": "Muzika",
             "music_volume": "Muzikos garsumas", "length": "Ilgiausia trukmė", "speed": "Greitis",
             "progress": "Progreso juostelė", "bubbles": "Debesėliai", "an_stickers": "Animuoti lipdukai",
             "an_marks": "Ranka piešti žymėjimai", "an_cards": "Iššokančios kortelės", "an_intro": "Įžanga",
             "an_outro": "Pabaiga"}


def ai_options():
    """Ką AI režisierius gali keisti ir kokios reikšmės leistinos."""
    looks = {k: L["title"] for k, L in video_editor.SUBTITLE_LOOKS.items()}
    return {
        "template": {n: f"accent {t['accent']}, filter {t['color']}" for n, t in reels_studio.TEMPLATES.items()},
        "accent": list(reels_studio.ACCENTS), "color": list(reels_studio.COLOR_FILTERS),
        "effects": reels_studio.EFFECTS, "look": looks, "hook": "short text", "cta": "short text",
        "link": "url", "hook_pos": list(reels_studio.HOOK_POSITIONS),
        "subs_pos": list(reels_studio.SUBTITLE_POSITIONS), "text_size": "60-150 (%)", "subs_size": "60-150 (%)",
        "key_words": "bool", "punch": "bool", "end_card": "bool (end card with link and QR)",
        "bubbles": "bool (comic speech bubbles ?, !, WOW at emotional moments)",
        "an_stickers": "bool (animated stickers: hearts, stars, confetti, fire)",
        "an_marks": "bool (hand-drawn circle / arrow / underline at key moments)",
        "an_cards": "bool (pop-up cards when the speaker lists points)", "an_intro": "bool (animated logo intro)",
        "an_outro": "bool (animated thank-you outro)",
        "yt_end": "bool (16:9 YouTube end screen)", "moment_at": "0.5-60 seconds",
        "transition": list(video_editor.TRANSITIONS),
        "music_choice": ["Be muzikos"] + list(reels_studio.music_library()), "music_volume": "0-100 (%)",
        "length": list(reels_studio.LENGTHS), "speed": SPEEDS, "progress": PROGRESS}


def ai_current():
    ss = st.session_state
    return {k: ss.get(P + k) for k in AI_LABELS if P + k in ss}


def _ai_value(key, v, opts):
    """Patikrina AI pasiūlytą reikšmę; netinkama – None."""
    o = opts[key]
    if key == "effects":
        return [e for e in (v if isinstance(v, list) else []) if e in reels_studio.EFFECTS]
    if key == "look":
        return v if v in o else next((k for k, t in o.items() if t == v), None)
    if isinstance(o, (list, dict)):
        if key == "speed":
            try:
                return min(SPEEDS, key=lambda x: abs(x - float(v)))
            except (TypeError, ValueError):
                return None
        return v if v in o else None
    if o.startswith("bool"):
        return bool(v) if isinstance(v, bool) else None
    if key in ("text_size", "subs_size", "music_volume"):
        try:
            lo, hi = (0, 100) if key == "music_volume" else (60, 150)
            v = max(lo, min(hi, int(round(float(v)))))
            return v if key == "music_volume" else v // 5 * 5
        except (TypeError, ValueError):
            return None
    if key == "moment_at":
        try:
            return round(max(0.5, min(60.0, float(v))), 1)
        except (TypeError, ValueError):
            return None
    return str(v).strip()[:120] if isinstance(v, str) else None


def apply_ai_changes(changes):
    """Pritaiko pakeitimus (su atšaukimu). Grąžina [(pavadinimas, reikšmė)]."""
    ss, opts = st.session_state, ai_options()
    clean = {}
    for k, v in changes.items():
        if k in opts:
            val = _ai_value(k, v, opts)
            if val is not None and ss.get(P + k) != val:
                clean[k] = val
    if "template" in clean:  # šablonas atneša savo akcentą ir filtrą, jei AI jų nenurodė
        t = reels_studio.TEMPLATES[clean["template"]]
        clean.setdefault("accent", t["accent"])
        clean.setdefault("color", t["color"])
    if "moment_at" in clean:  # akimirkai reikia efekto
        fx = list(clean.get("effects", ss.get(P + "effects", [])))
        if "Gintaro akimirka" not in fx:
            clean["effects"] = fx + ["Gintaro akimirka"]
    if "music_choice" in clean:  # nauja muzika – muzikos takelis iš naujo
        ss.pop(P + "mblocks", None)
    undo = {k: ss.get(P + k, "__none__") for k in clean}
    for k, v in clean.items():
        ss[P + k] = v
    ss[P + "ai_undo"] = undo
    return [(AI_LABELS.get(k, k), v) for k, v in clean.items()]


AUTOPILOT_REQUEST = ("Sukurk patraukliausią, profesionalų Reels šiam turiniui: parink jam tinkantį šabloną, filtrą, "
                     "1–3 efektus, titrų stilių, muziką ir tempą; įjunk svarbiausius žodžius, akcentų priartėjimą ir "
                     "debesėlius; jei nėra kabliuko – sugalvok trumpą intriguojantį kabliuką, jei nėra kvietimo veikti – "
                     "sugalvok trumpą kvietimą.")


def autopilot_plan(client, words):
    """✨ Autopilotas: ką nustatyti. Su AI – parenka AI pagal turinį; be jo – patikrintas studijos derinys."""
    ss = st.session_state
    library = reels_studio.music_library()
    ch = {"key_words": True, "punch": True, "bubbles": True, "look": "mixed", "an_stickers": True, "an_marks": True,
          "an_cards": True, "an_intro": True, "an_outro": True,
          "effects": sorted(set(ss.get(P + "effects", [])) | {"Švytėjimas", "Auksinės dulkės"})}
    if (ss.get(P + "link") or "").strip():
        ch["end_card"] = True
    if library and ss.get(P + "music_choice") in (None, "Be muzikos"):
        ch["music_choice"] = next(iter(library))
    summary = ("parinktas patikrintas studijos derinys: mišrūs titrai, švytėjimas, auksinės dulkės, debesėliai, "
               "svarbiausi žodžiai su priartėjimu.")
    if client is not None:
        try:
            res = reels_studio.ai_direct(client, AUTOPILOT_REQUEST, ai_current(), ai_options(), words,
                                         float(ss.get(P + "speed", 1.0)))
            ch.update(res["changes"])
            ch.update({"key_words": True, "bubbles": True})
            summary = res["summary"] or summary
        except Exception:
            pass
        if not (ss.get(P + "hook") or "").strip() and not ch.get("hook") and words:
            try:
                ideas = reels_studio.ai_hooks(client, words)
                if ideas:
                    ch["hook"] = ideas[0]
                    ss[P + "hook_ideas"] = ideas
            except Exception:
                pass
    if not (ss.get(P + "hook") or "").strip() and not ch.get("hook") and words:
        # be AI – pirmas sakinys (iki 7 žodžių) tampa kabliuku
        first = []
        for w, _, _ in words:
            first.append(video_editor.plain(w))
            if len(first) >= 7 or re.search(r"[.!?…]$", first[-1]):
                break
        ch["hook"] = " ".join(first).rstrip(",;:")
    return ch, summary


def run_ai_director(client, words, preset=None):
    ss = st.session_state
    req = (preset or ss.get(P + "ai_req") or "").strip()
    ss.pop(P + "ai_result", None)
    if not req:
        return
    try:
        speed_now = float(ss.get(P + "speed", 1.0))
        if preset == "moment" and words:
            t, word, why = reels_studio.ai_moment(client, words, speed_now)
            res = {"changes": {"moment_at": t}, "summary": f"Akimirka – ties žodžiu „{word}“: {why}".strip()}
        else:
            res = reels_studio.ai_direct(client, req, ai_current(), ai_options(), words, speed_now)
        done = apply_ai_changes(res["changes"])
        ss[P + "ai_result"] = {"summary": res["summary"], "done": done}
        if done:
            ss[P + "auto_preview"] = True
    except Exception as e:
        ss[P + "ai_result"] = {"error": str(e)}


def undo_ai():
    ss = st.session_state
    for k, v in (ss.pop(P + "ai_undo", None) or {}).items():
        if v == "__none__":
            ss.pop(P + k, None)
        else:
            ss[P + k] = v
    ss[P + "ai_result"] = {"summary": "↶ Pakeitimai atšaukti.", "done": []}


def anim_spec(words):
    """Animacijų planas build'ui: AI (Premium, įsimenama) arba pagal žodžius. None – visos išjungtos."""
    if not (an_stickers or an_marks or an_cards or an_intro or an_outro):
        return None
    words = list(words or [])
    plan = None
    if words and (an_stickers or an_marks or an_cards):
        if client is not None:
            cache = st.session_state.setdefault(P + "ai_anims", {})
            k = hash(tuple((w, round(a, 2)) for w, a, _ in words))
            if k not in cache:
                try:
                    cache[k] = animations.ai_plan(client, words, reels_studio._ai_json)
                except Exception:
                    cache[k] = None
            plan = cache[k]
        if not plan or not any(plan.values()):
            plan = animations.auto_plan(words)
    plan = plan or {}
    return {"plan": {"stickers": plan.get("stickers", []) if an_stickers else [],
                     "marks": plan.get("marks", []) if an_marks else [],
                     "cards": plan.get("cards", []) if an_cards else []},
            "intro": an_intro, "outro": an_outro, "handle": handle}


def bubble_list(words):
    """Debesėlių vietos: AI (Premium, įsimenama) arba pagal skyrybą. None – išjungta."""
    words = list(words or [])
    if not bubbles_on or not words:
        return None
    if client is not None:
        cache = st.session_state.setdefault(P + "ai_bubbles", {})
        k = hash(tuple((w, round(a, 2)) for w, a, _ in words))
        if k not in cache:
            try:
                cache[k] = reels_studio.ai_bubbles(client, words)
            except Exception:
                cache[k] = None
        if cache[k]:
            return cache[k]
    return reels_studio.auto_bubbles(words)


def marked(words):
    """Svarbiausi žodžiai: naudotojo *žymės*, AI parinkti (Premium) arba taisyklė."""
    words = list(words)
    if not words or any(video_editor.is_key(w) for w, _, _ in words):
        return words
    if client is not None:
        cache = st.session_state.setdefault(P + "ai_keys", {})
        k = hash(tuple((w, round(a, 2)) for w, a, _ in words))
        if k not in cache:
            try:
                cache[k] = reels_studio.ai_key_word_indices(client, words)
            except Exception:
                cache[k] = None
        if cache[k]:
            return reels_studio.mark_indices(words, cache[k])
    return video_editor.mark_key_words(words)  # be AI – pagal taisyklę


def pick_look(name):
    st.session_state[P + "look"] = name


@st.cache_data(max_entries=200, show_spinner=False)
def style_tile(base, template, accent, color, hook, look, effects=(), subs_y=0.72, hook_y=0.2, subs_size=1.0,
               text_size=1.0):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "b.jpg")
        with open(src, "wb") as f:
            f.write(base)
        out = reels_studio.style_preview(src, os.path.join(tmp, "s.jpg"), template, accent, color, effects,
                                         hook, look, subs_ypos=subs_y, hook_ypos=hook_y, subs_size=subs_size,
                                         text_size=text_size)
        with open(out, "rb") as f:
            return f.read()


def pick_color(name):
    st.session_state[P + "color"] = name


def toggle_effect(name):
    fx = st.session_state.setdefault(P + "effects", [])
    if name in fx:
        fx.remove(name)
    else:
        fx.append(name)


@st.cache_data(max_entries=16, show_spinner=False)
def base_frame(path, at):
    """Kadras iš video – pagrindas filtrų ir efektų miniatiūroms."""
    with tempfile.TemporaryDirectory() as tmp:
        out = reels_studio.grab_frame(path, os.path.join(tmp, "base.jpg"), at)
        with open(out, "rb") as f:
            return f.read()


@st.cache_data(show_spinner=False)
def sample_frame():
    """Pavyzdinis kadras, kol neįkeltas video: šiltas dangus, jūra ir smėlis."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "sample.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "gradients=s=360x640:c0=0xE8A060:c1=0x2F6F7F:c2=0xF4D9B0:n=3:x0=0:y0=0:x1=360:y1=640:d=1",
                        "-vf", "drawbox=x=110:y=260:w=140:h=200:color=0x3A2A20:t=fill,"
                               "drawbox=x=150:y=200:w=60:h=60:color=0xF1C9A0:t=fill",
                        "-frames:v", "1", out], check=True)
        with open(out, "rb") as f:
            return f.read()


@st.cache_data(max_entries=400, show_spinner=False)
def thumb(base, color, effects, accent="Aukso gradientas"):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "b.jpg")
        with open(src, "wb") as f:
            f.write(base)
        out = reels_studio.thumbnail(src, os.path.join(tmp, "t.jpg"), color, effects, accent=accent)
        with open(out, "rb") as f:
            return f.read()


st.session_state.setdefault(P + "format", list(reels_studio.STUDIO_FORMATS)[0])
fmt, cover_size = reels_studio.STUDIO_FORMATS[st.session_state[P + "format"]]
st.session_state.setdefault(P + "subs_size", 100)
st.session_state.setdefault(P + "text_size", 100)
subs_size = st.session_state[P + "subs_size"] / 100
text_size = st.session_state[P + "text_size"] / 100
st.session_state.setdefault(P + "subs_pos", "Žemiau")
st.session_state.setdefault(P + "hook_pos", "Aukščiau")
subs_y = reels_studio.SUBTITLE_POSITIONS[st.session_state[P + "subs_pos"]]
hook_y = reels_studio.HOOK_POSITIONS[st.session_state[P + "hook_pos"]]
# ---------- Prekės ženklo rinkinys: išsaugoti numatytieji nustatymai ----------
BRAND_DIR = os.path.join(accounts.DATA_DIR, "brand")
BRAND_KEYS = ("template", "accent", "color", "handle", "cta", "brand_color", "logo_on", "logo_pos", "logo_size",
              "logo_opacity", "link", "end_card", "yt_end", "niche")


def brand_file():
    return os.path.join(BRAND_DIR, re.sub(r"[^\w.-]", "_", user.get("username") or "studija"))


if P + "brand_loaded" not in st.session_state:
    st.session_state[P + "brand_loaded"] = True
    try:
        with open(brand_file() + ".json", encoding="utf-8") as f:
            saved_brand = json.load(f)
    except Exception:
        saved_brand = {}
    for k, v in saved_brand.items():
        if k in BRAND_KEYS:
            st.session_state.setdefault(P + k, v)
    if os.path.exists(brand_file() + "_logo.png"):
        st.session_state.setdefault(P + "logo_path", brand_file() + "_logo.png")
    if st.session_state.get(P + "template") not in reels_studio.TEMPLATES:
        st.session_state.pop(P + "template", None)


def save_brand():
    os.makedirs(BRAND_DIR, exist_ok=True)
    data = {k: st.session_state[P + k] for k in BRAND_KEYS if P + k in st.session_state}
    lp = st.session_state.get(P + "logo_path")
    if lp and os.path.exists(lp) and os.path.abspath(lp) != os.path.abspath(brand_file() + "_logo.png"):
        shutil.copy(lp, brand_file() + "_logo.png")
    with open(brand_file() + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    st.session_state[P + "brand_saved"] = True


def use_brand_color():
    st.session_state[P + "accent"] = st.session_state[P + "brand_color"].upper()


st.session_state.setdefault(P + "template", "Baltijos gintaras")
if P + "accent" not in st.session_state:
    apply_template()

top = st.container()  # peržiūra, mygtukai ir rezultatas – viršuje (užpildoma puslapio gale)
st.markdown('<div class="lux-settings-hint">⚙️ <b>Nustatymai</b> – filtrai, efektai, titrai, kalbos atpažinimas, '
            'muzika: paspauskite <b>»</b> viršuje kairėje</div>', unsafe_allow_html=True)

# ---------- I. Medžiaga ----------
with st.container(border=True):
    step("I", "Medžiaga", "video, nuotraukos arba filmavimas")
    ideas_ui()
    clips, image_duration = clips_ui.clip_picker(P, trim=True)
    st.session_state.setdefault(P + "transition", "Be perėjimo")
    pick = tile_click(P + "x_tiles")
    if pick and pick[2:] in video_editor.TRANSITIONS:
        pick_transition(pick[2:])
    transition = st.session_state[P + "transition"]
    if len(clips) >= 2:
        st.markdown("**Perėjimai tarp įrašų** · <small>✦ – firminiai studijos</small>", unsafe_allow_html=True)
        try:
            fa = base_frame(clips[0]["path"], 0.0 if clips[0].get("image") else min(1.0, clips[0]["duration"] / 2))
            fb = base_frame(clips[1]["path"], 0.0 if clips[1].get("image") else min(1.0, clips[1]["duration"] / 2))
        except Exception:
            fa = fb = None
        xitems = {}
        for name in video_editor.TRANSITIONS:
            xitems["x:" + name] = {"label": name, "group": "x", "sig": name in reels_studio.SIGNATURE_TRANSITIONS,
                                   "img": square(transition_tile(fa, fb, name)) if fa and fb else ""}
        tiles(P + "x_tiles", xitems, ["x:" + transition], size=64)

states = {c["audio"] for c in clips}
# Įgarsinimas (atskiras balso įrašas) – titrams ir garsui naudojamas jis
has_vo = st.session_state.get(P + "vo_file") is not None
speech = "speech" in states or has_vo

if st.session_state.get(P + "autopilot") == "apply":  # ✨ Autopilotas: nustatymai pritaikomi PRIEŠ piešiant valdiklius
    _done = apply_ai_changes(st.session_state.pop(P + "autopilot_changes", {}))
    st.session_state[P + "auto_formats"] = True
    st.session_state[P + "ai_result"] = {"summary": "✨ Autopilotas: " + st.session_state.pop(P + "autopilot_summary", ""),
                                         "done": _done}
    st.session_state[P + "autopilot"] = "create"

pick = tile_click(P + "style_tiles")  # Stiliaus langelių paspaudimas
if pick:
    kind, name = pick.split(":", 1)
    if kind == "t" and name in reels_studio.TEMPLATES:
        pick_template(name)
    elif kind == "c" and name in reels_studio.COLOR_FILTERS:
        pick_color(name)
    elif kind == "e" and name in reels_studio.EFFECTS:
        toggle_effect(name)
pick = tile_click(P + "look_tiles")
if pick and pick[2:] in video_editor.SUBTITLE_LOOKS:
    pick_look(pick[2:])

template = st.session_state[P + "template"]
accent = st.session_state[P + "accent"]
st.session_state.setdefault(P + "effects", [])
base = None
if clips:
    c0 = clips[0]
    try:
        base = base_frame(c0["path"], 0.0 if c0.get("image") else min(1.0, c0["duration"] / 2))
    except Exception:
        base = None
if base is None:
    base = sample_frame()

sb = st.sidebar
sb.markdown(f'<div class="lux-side-logo">{LOGO}<div class="lux-side-title" style="margin:0">Nustatymai</div></div>',
            unsafe_allow_html=True)
sb.selectbox("Formatas", list(reels_studio.STUDIO_FORMATS), key=P + "format",
             help="9:16 – Reels, TikTok, Shorts; 16:9 – YouTube; 1:1 ir 4:5 – Instagram įrašai. "
                  "Kitokios orientacijos vaizdas dedamas per vidurį su sulietu fonu.")
st.session_state.setdefault(P + "auto_formats", True)
sb.toggle("📐 Kartu sukurti visus 3 formatus", key=P + "auto_formats",
          help="Paspaudus „Kurti“ gausite iš karto 3 video: Reels / TikTok (9:16), YouTube (16:9) ir Instagram "
               "įrašui (4:5) – su viršeliais ir ZIP paketu. Kūrimas trunka ilgiau.")

# ---------- II. Stilius ----------
with sb.expander("🎨  Stilius – šablonas, filtrai, efektai", expanded=True):
    sample_hook = st.session_state.get(P + "hook") or "Jūsų antraštė čia"
    color = st.session_state[P + "color"]
    effects = st.session_state[P + "effects"]
    items = {}
    for name, t in reels_studio.TEMPLATES.items():
        img = style_tile(base, name, t["accent"], t["color"], sample_hook, None, hook_y=hook_y, text_size=text_size)
        items["t:" + name] = {"label": name, "img": square(img, hook_y, 1.0), "group": "t",
                              "help": f"Šablonas: {name}"}
    for name in reels_studio.COLOR_FILTERS:
        items["c:" + name] = {"label": name, "img": square(thumb(base, name, ())), "group": "c",
                              "sig": name in reels_studio.SIGNATURE_FILTERS,
                              "help": "Firminis studijos filtras" if name in reels_studio.SIGNATURE_FILTERS else name}
    for name, desc in reels_studio.EFFECTS.items():
        if name in reels_studio.TEXT_EFFECTS:
            img = square(style_tile(base, template, accent, color, sample_hook, None, (name,), hook_y=hook_y),
                         hook_y, 1.0)
        else:
            img = square(thumb(base, color, (name,), accent))
        items["e:" + name] = {"label": name, "img": img, "multi": True, "help": desc,
                              "sig": name in reels_studio.SIGNATURE_EFFECTS}
    signature = ["c:" + n for n in reels_studio.SIGNATURE_FILTERS] + ["e:" + n for n in reels_studio.SIGNATURE_EFFECTS]
    tiles(P + "style_tiles", items,
          ["t:" + template, "c:" + color] + ["e:" + e for e in effects],
          # pirmiausia – pagrindiniai skirtukai (telefone matomi iškart), po jų – šablonų kategorijos
          tabs=[{"name": "Šablonai", "items": ["t:" + n for n in reels_studio.TEMPLATES]},
                {"name": "Filtrai", "items": ["c:" + n for n in reels_studio.COLOR_FILTERS]},
                {"name": "Efektai", "items": ["e:" + n for n in reels_studio.EFFECTS], "multi": True},
                {"name": "✦ Firminiai", "items": signature}]
          + [{"name": cat, "items": ["t:" + n for n, t in reels_studio.TEMPLATES.items() if t.get("cat") == cat],
              "sub": True} for cat in reels_studio.TEMPLATE_CATEGORIES if cat != "Prabanga"])
    st.caption(f"Šablonas: **{template}** · filtras: **{color}**"
               + (" · efektai: " + ", ".join(effects) if effects else " · efektų galima rinktis kelis")
               + ("" if clips else " · įkėlus video matysite savo kadrą"))
    accent_opts = list(reels_studio.ACCENTS)
    for extra in (st.session_state.get(P + "accent"), (st.session_state.get(P + "brand_color") or "").upper()):
        if extra and extra.startswith("#") and extra not in accent_opts:
            accent_opts.append(extra)
    st.selectbox("Akcento spalva", accent_opts, key=P + "accent",
                 format_func=lambda a: f"💎 Prekės ženklo spalva {a}" if a.startswith("#") else a,
                 help="Gradientai – metalinis auksas ar sidabras kabliukui, kvietimui ir paryškintam titrų žodžiui. "
                      "Savo spalvą nustatysite skiltyje „Prekės ženklas“.")
    accent = st.session_state[P + "accent"]

    if "Gintaro akimirka" in effects:
        st.session_state.setdefault(P + "moment_at", 3.0)
        st.slider("✦ Gintaro akimirka – kurioje sekundėje nušvinta", 0.5, 60.0, step=0.1, key=P + "moment_at",
                  format="%.1f s", help=f"Šioje vietoje {reels_studio.MOMENT_LEN:.1f} s kadras švelniai nušvinta gintaro "
                  "šviesa ir truputį priartėja – video ir kalba nesustoja. Vieta skaičiuojama galutiniame "
                  "video (jei per toli – priartinama prie pabaigos).")

# ---------- III. Tekstai ----------
with sb.expander("✍️  Tekstai ir titrai"):
    hook = st.text_input("Kabliukas – pirmų sekundžių antraštė", key=P + "hook",
                         placeholder="Pvz.: Kaip atrodyti brangiai be didelio biudžeto",
                         help="Trumpa intriguojanti frazė (iki ~8 žodžių) – sustabdo slinkimą.")
    c1, c2 = st.columns(2)
    hook_duration = c1.slider("Kabliuko trukmė (s)", 1.5, 6.0, 3.0, 0.5)
    handle = c2.text_input("Paskyra", placeholder="@jusu.paskyra", key=P + "handle")
    cta = st.text_input("Kvietimas veikti pabaigoje", placeholder="Pvz.: Išsaugok vėlesniam", key=P + "cta")
    link = st.text_input("🔗 Nuoroda – svetainė, parduotuvė, registracija", key=P + "link",
                         placeholder="manosvetaine.lt",
                         help="Rodoma pabaigos kortelėje (su QR kodu) ir pridedama prie aprašymo.").strip()
    for k in ("end_card", "yt_end"):
        st.session_state.setdefault(P + k, False)
    end_on = st.toggle("✦ Pabaigos kortelė su nuoroda ir QR", key=P + "end_card",
                       help=f"Video pabaigoje – gintarinė kortelė ({reels_studio.END_CARD_LEN:.1f} s): kvietimas, "
                            "nuoroda, QR kodas ir paskyra. Kvietimas veikti tada rodomas joje.")
    yt_on = st.toggle("▶ YouTube pabaigos ekranas (16:9)", key=P + "yt_end", disabled=not end_on,
                      help=f"Tik 16:9 video: kortelė {reels_studio.YT_END_LEN:.0f} s su auksinėmis vietomis, ant kurių "
                           "YouTube Studio uždėsite paspaudžiamus elementus „Video“ ir „Prenumeruoti“.")
    c1, c2 = st.columns(2)
    c1.select_slider("Kabliuko vieta", list(reels_studio.HOOK_POSITIONS), key=P + "hook_pos",
                     help="Jei kabliukas uždengia veidą ar galvą – nuleiskite žemiau arba pakelkite.")
    c2.select_slider("Titrų vieta", list(reels_studio.SUBTITLE_POSITIONS), key=P + "subs_pos",
                     help="„Apačioje“ titrus gali dalinai uždengti Instagram aprašymas ir mygtukai.")
    c1, c2 = st.columns(2)
    c1.slider("Kabliuko dydis", 60, 150, step=5, format="%d%%", key=P + "text_size",
              help="Kabliuko ir kvietimo veikti teksto dydis.")
    c2.slider("Titrų dydis", 60, 150, step=5, format="%d%%", key=P + "subs_size")

    subtitles = st.toggle("Animuoti titrai", value=True,
                          help="Sakomas žodis paryškinamas akcento spalva.")
    st.session_state.setdefault(P + "look", "modern")
    look = st.session_state[P + "look"]
    if subtitles:
        st.markdown("**Titrų stilius**", unsafe_allow_html=True)
        litems = {}
        for key, L in video_editor.SUBTITLE_LOOKS.items():
            img = style_tile(base, template, accent, color, "", key, subs_y=0.5, subs_size=1.5)  # tikras pavyzdys
            litems["l:" + key] = {"label": L["title"], "img": square(img, 0.5, 0.85), "group": "l"}
        tiles(P + "look_tiles", litems, ["l:" + look], size=64)
        for k in ("key_words", "punch"):
            st.session_state.setdefault(P + k, True)
        key_words = st.toggle("✦ Svarbiausi žodžiai – didesni ir auksiniai", key=P + "key_words",
                              help="Studija pati parenka svarbiausius žodžius (skaičius, prasminius žodžius; Premium – "
                                   "dirbtinis intelektas) ir juos išryškina. Titrų taisyme žodį galite pažymėti ir patys: *žodis*.")
        punch = st.toggle("✦ Akcentų priartėjimas", key=P + "punch", disabled=not key_words,
                          help="Ties svarbiausiais žodžiais kadras trumpam „įšoka“ arčiau – kaip profesionalų montaže.")
        st.session_state.setdefault(P + "bubbles", False)
        bubbles_on = st.toggle("✦ Debesėliai (?, !, WOW)", key=P + "bubbles",
                               help="Komiksų debesėliai iššoka tam tikrose vietose: klausimui – „?“, nuostabai – "
                                    "„WOW!“, abejonei – „Hmm…“, patarimui – „IDĖJA!“, meilei – širdelė. Premium – vietas "
                                    "parenka dirbtinis intelektas pagal tai, ką sakote; be jo – pagal ? ir ! tekste.")
    else:
        key_words = punch = bubbles_on = False

    # Balso atpažinimas (OpenAI Whisper)
    speech_minutes = sum(clips_ui.clip_length(c, image_duration) for c in clips if not c.get("image")) / 60
    if plan == "open":  # prisijungimas išjungtas – raktas iš Secrets arba įvedamas čia
        has_secret = bool(clips_ui.configured_key())
        if not has_secret:
            with st.expander("🎙️ Balso atpažinimas – įveskite OpenAI raktą",
                             expanded=not st.session_state.get("openai_key")):
                st.text_input("OpenAI API raktas", type="password", key="openai_key", placeholder="sk-…",
                              help="Raktas naudojamas tik šioje naršyklės sesijoje ir niekur nesaugomas. "
                                   "Kad nereikėtų įvesti kaskart – įrašykite jį Streamlit Cloud: "
                                   "⋮ → Settings → Secrets: OPENAI_API_KEY = \"sk-…\"")
                st.caption("Raktą gausite platform.openai.com → API keys. Minutė atpažinimo kainuoja ~0,006 $.")
        client = clips_ui.openai_client()
        typed = st.session_state.get("openai_key", "").strip()
        if client is not None and not has_secret and st.session_state.get(P + "checked_key") != typed:
            try:
                client.models.list()
                st.session_state[P + "key_ok"] = True
            except Exception as e:
                auth = "401" in str(e) or "api key" in str(e).lower() or type(e).__name__ == "AuthenticationError"
                # Tik tikrai neteisingas raktas atmetamas; ryšio sutrikimai – ne rakto kaltė.
                st.session_state[P + "key_ok"] = "neteisingas raktas – patikrinkite, ar nukopijavote visą." \
                    if auth else True
            st.session_state[P + "checked_key"] = typed
        key_ok = has_secret or st.session_state.get(P + "key_ok") is True
        if client is not None and not key_ok:
            st.error(f"OpenAI raktas netinka: {st.session_state.get(P + 'key_ok')}")
            client = None
        elif client is not None:
            st.success("🎙️ Balso atpažinimas įjungtas – titrai bus sukurti automatiškai iš kalbos.")
    elif plan == "basic":
        client = None
        st.markdown(
            '<div class="lux-premium">🔒 <b>Premium</b> – automatiniai titrai iš kalbos, titrų vertimas, '
            'aprašymas ir grotažymės.' + (f' Norite Premium? Susisiekite: {html.escape(accounts.contact())}'
                                          if accounts.contact() else '') + '</div>', unsafe_allow_html=True)
    else:  # premium / admin – savininko raktas iš Secrets
        client = clips_ui.openai_client()
        left = accounts.remaining_minutes()
        if client is None:
            st.warning("Balso atpažinimas laikinai neveikia – administratorius dar neįrašė OpenAI rakto.")
        elif left is not None and left < max(0.05, speech_minutes):
            client = None
            st.warning(f"Šio mėnesio balso atpažinimo minutės baigėsi (liko {left:.1f} min., "
                       f"šiam video reikia {speech_minutes:.1f} min.). Titrus galite įrašyti tekstu.")
        else:
            st.success("🎙️ Premium: titrai bus sukurti automatiškai iš kalbos."
                       + (f" Liko {left:.0f} min. šį mėnesį." if left is not None else ""))

    subtitle_text, subtitle_language = "", "lt"
    if subtitles and clips:
        if client:
            choice = st.selectbox("Titrų kalba", ["Lietuvių", "Kaip kalbama video (be vertimo)", "English",
                                                  "Русский", "Polski", "Deutsch"],
                                  help="Jei video kalbama kita kalba, titrai bus išversti.")
            subtitle_language = {"Lietuvių": "lt", "English": "en", "Русский": "ru", "Polski": "pl",
                                 "Deutsch": "de"}.get(choice)
            if not speech:
                subtitle_text = st.text_area(
                    "Titrų tekstas (jei video be balso)",
                    placeholder="Balso neaptikta. Jei balsas yra – palikite tuščią, programa vis tiek bandys "
                                "atpažinti. Jei ne – įrašykite tekstą.")
        else:
            subtitle_text = st.text_area("Titrų tekstas", placeholder="Tekstas bus tolygiai išdėliotas per video.",
                                         key=P + "subtitle_text_in",
                                         help="Įrašykite tekstą – programa suskaidys jį į frazes ir išdėlios "
                                              "per video.")

    # ✨ AI kabliukai iš kalbos (Premium)
    if client is not None and (ai_words() or subtitle_text.strip()):
        st.button("✨ AI: pasiūlyk kabliukų", key=P + "ai_hooks_btn", width="stretch",
                  on_click=run_ai_hooks, args=(client, ai_words(), subtitle_text),
                  help="Dirbtinis intelektas perskaito, ką sakote video, ir pasiūlo kabliukų pirmoms sekundėms.")
        if st.session_state.get(P + "ai_hooks_err"):
            st.error(st.session_state[P + "ai_hooks_err"])
        ideas = st.session_state.get(P + "hook_ideas") or []
        if ideas:
            st.caption("Paspauskite – kabliukas bus įrašytas:")
            for i, h in enumerate(ideas):
                st.button(f"„{h}“", key=f"{P}hook_idea{i}", width="stretch", on_click=set_hook, args=(h,))

# ---------- IV. Garsas ----------
with sb.expander("🎬  Animacijos"):
    st.caption("Animacijos dedamos ten, kur jos tinka pagal tai, ką sakote" +
               (" – vietas parenka dirbtinis intelektas." if client is not None else
                " (pagal žodžius: „patinka“ – širdelės, „super“ – žvaigždutės, „pirma, antra…“ – kortelės)."))
    for k in ("an_stickers", "an_marks", "an_cards", "an_intro", "an_outro"):
        st.session_state.setdefault(P + k, False)
    an_stickers = st.toggle("✨ Animuoti lipdukai", key=P + "an_stickers",
                            help="Kylančios širdelės, žvaigždučių sprogimas, krentantys konfeti, liepsnelės.")
    an_marks = st.toggle("✏️ Ranka piešti žymėjimai", key=P + "an_marks",
                         help="Apskritimas, rodyklė ir pabraukimas „nusipiešia“ ties svarbiausiais žodžiais.")
    an_cards = st.toggle("🃏 Iššokančios kortelės", key=P + "an_cards",
                         help="Kai vardijate („pirma…, antra…“ ar patarimus), kortelės su tekstu išslysta po vieną.")
    c1, c2 = st.columns(2)
    an_intro = c1.toggle("🎬 Įžanga", key=P + "an_intro", help="Logotipas ir jūsų paskyra įskrenda pradžioje (1,3 s).")
    an_outro = c2.toggle("🙏 Pabaiga", key=P + "an_outro",
                         help="Paskutinės 1,8 s – „AČIŪ!“, logotipas ir paskyra (jei nėra pabaigos kortelės).")

with sb.expander("💎  Prekės ženklas"):
    st.caption("Jūsų logotipas ir spalva ant kiekvieno video. Išsaugokite – kitą kartą šablonas, spalvos, "
               "paskyra, kvietimas ir logotipas bus nustatyti automatiškai.")
    logo_up = st.file_uploader("Logotipas (geriausia PNG su permatomu fonu)", type=["png", "jpg", "jpeg", "webp"],
                               key=P + "logo_up")
    if logo_up is not None and st.session_state.get(P + "logo_id") != logo_up.file_id:
        from PIL import Image
        bdir = st.session_state.setdefault(P + "brand_tmp", tempfile.mkdtemp(prefix="brand_"))
        lp = os.path.join(bdir, f"logo_{logo_up.file_id}.png")
        try:
            with Image.open(logo_up) as im:
                im.convert("RGBA").save(lp)
            st.session_state[P + "logo_path"] = lp
            st.session_state[P + "logo_id"] = logo_up.file_id
            st.session_state[P + "logo_on"] = True
        except Exception:
            st.error("Logotipo nepavyko atidaryti – įkelkite PNG ar JPG.")
    logo_path = st.session_state.get(P + "logo_path")
    if logo_path and not os.path.exists(logo_path):
        logo_path = None
    if logo_path:
        c1, c2 = st.columns([1, 2])
        c1.image(logo_path, width="stretch")
        for k, v in (("logo_on", True), ("logo_pos", reels_studio.LOGO_POSITIONS[0]), ("logo_size", 16),
                     ("logo_opacity", 85)):
            st.session_state.setdefault(P + k, v)
        c2.toggle("Rodyti logotipą", key=P + "logo_on")
        st.selectbox("Logotipo vieta", reels_studio.LOGO_POSITIONS, key=P + "logo_pos")
        c1, c2 = st.columns(2)
        c1.slider("Dydis", 8, 30, format="%d%%", key=P + "logo_size", help="Kadro pločio dalis")
        c2.slider("Matomumas", 30, 100, step=5, format="%d%%", key=P + "logo_opacity")
    st.session_state.setdefault(P + "brand_color", "#E39B2E")
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    c1.color_picker("Spalva", key=P + "brand_color", help="Jūsų prekės ženklo spalva – kabliukui, kvietimui, "
                                                          "paryškintiems žodžiams ir progreso juostai.")
    c2.button("Naudoti kaip akcentą", on_click=use_brand_color, width="stretch", key=P + "use_brand_color",
              disabled=st.session_state.get(P + "accent") == st.session_state[P + "brand_color"].upper())
    st.button("💾  Išsaugoti mano prekės ženklą", on_click=save_brand, type="primary", width="stretch",
              key=P + "save_brand", help="Išsaugomi: šablonas, akcentas, filtras, paskyra, kvietimas, spalva ir "
                                         "logotipas. Pastaba: atnaujinus programą serveryje, išsaugojimas gali "
                                         "išsitrinti – tada tiesiog išsaugokite iš naujo.")
    if st.session_state.pop(P + "brand_saved", False):
        st.success("Išsaugota – kitą kartą prisijungus viskas bus nustatyta.")
logo = ({"path": logo_path, "pos": st.session_state.get(P + "logo_pos", reels_studio.LOGO_POSITIONS[0]),
         "size": st.session_state.get(P + "logo_size", 16) / 100,
         "opacity": st.session_state.get(P + "logo_opacity", 85) / 100}
        if logo_path and st.session_state.get(P + "logo_on", True) else None)
end_card = ({"link": link, "handle": handle, "youtube": yt_on, "qr": True,
             "logo": logo["path"] if logo else None} if end_on else None)

with sb.expander("🎵  Garsas ir muzika", expanded=has_vo):
    st.markdown("**🎙️ Įgarsinimas – jūsų balsas**")
    vo_file = st.file_uploader("Balso įrašas (garso arba video failas)", key=P + "vo_file",
                               help="Jūsų kalba skambės visu garsumu (sustiprinta ir išvalyta), titrai bus sukurti "
                                    "iš jos, o muzika patyli, kai kalbate. Iš video failo paimamas tik garsas.")
    vo_path, clip_gain = None, 1.0
    if vo_file is not None:
        _work = st.session_state.setdefault(P + "work", tempfile.mkdtemp(prefix="reels_"))
        os.makedirs(_work, exist_ok=True)
        vo_path = os.path.join(_work, f"vo_{vo_file.file_id}" + (os.path.splitext(vo_file.name)[1] or ".m4a"))
        if not os.path.exists(vo_path):
            with open(vo_path, "wb") as f:
                vo_file.seek(0)
                shutil.copyfileobj(vo_file, f, 1 << 20)
        vo_dur = reels_studio.media_duration(vo_path)
        gain_label = st.radio("Video klipų garsas", ["Išjungti", "Patylinti", "Palikti"], horizontal=True,
                              key=P + "clip_audio", help="Ką daryti su pačių video įrašų garsu, kai yra įgarsinimas.")
        clip_gain = {"Išjungti": 0.0, "Patylinti": 0.15, "Palikti": 1.0}[gain_label]
        st.caption(f"🎙️ Įgarsinimas: {vo_dur:.1f} s. Jei jis ilgesnis už video – paskutinis kadras bus "
                   f"prailgintas. Pauzės video neiškerpamos (vaizdas lieka toks, kokį sudėjote).")
    st.markdown("**🎵 Foninė muzika**")
    library = reels_studio.music_library()
    options = ["Be muzikos"] + list(library) + ["📁 Įkelti savo muziką"]
    if st.session_state.get(P + "music_choice") not in options:
        st.session_state[P + "music_choice"] = options[1] if library else options[0]
    music_choice = st.selectbox("Foninė muzika", options, key=P + "music_choice",
                                help="Studijos muzika sukurta specialiai – be autorių teisių apribojimų. "
                                     "Muzika kartojama per visą video ir švelniai užgęsta pabaigoje.")
    music_file = None
    if music_choice in library:
        st.caption(library[music_choice]["desc"])
        st.audio(library[music_choice]["path"])
    elif music_choice.startswith("📁"):
        music_file = st.file_uploader("Jūsų muzika (MP3, M4A, WAV)", key=P + "music")
        st.caption("Instagram gali nutildyti video su autorių teisių saugoma muzika – "
                   "populiarią dainą geriau pridėti pačiame Instagram.")
    if st.session_state.get(P + "mblocks") is not None:
        st.caption("🎵 Muzika sudėliota **muzikos takelyje** (žemiau, pagrindiniame lange) – ten pasirinkite, "
                   "kokia muzika kurioje vietoje.")
    has_music = music_choice in library or music_file is not None or bool(st.session_state.get(P + "mblocks"))
    c1, c2 = st.columns(2)
    st.session_state.setdefault(P + "music_volume", 22)
    music_volume = c1.slider("Muzikos garsumas", 0, 100, step=1, format="%d%%", disabled=not has_music,
                             key=P + "music_volume") / 100
    ducking = c2.toggle("Muzika patyli, kai kalbama", value=True, disabled=not has_music)
    c1, c2 = st.columns(2)
    remove_silence = c1.toggle("Iškirpti pauzes", value=True)
    denoise = c2.toggle("Išvalyti foninį triukšmą", value=True)

# ---------- V. Tempas ----------
with sb.expander("⏱  Tempas, trukmė, viršelis"):
    c1, c2 = st.columns(2)
    for k, v in (("length", "90 s"), ("speed", 1.0), ("progress", "Viršuje")):
        st.session_state.setdefault(P + k, v)
    length = c1.select_slider("Ilgiausia trukmė", list(reels_studio.LENGTHS), key=P + "length")
    speed = c2.select_slider("Greitis", SPEEDS, format_func=lambda x: f"{x:g}×", key=P + "speed")
    c1, c2 = st.columns(2)
    progress_bar = c1.radio("Progreso juostelė", PROGRESS, horizontal=True, key=P + "progress")
    total = float(sum(clips_ui.clip_length(c, image_duration) for c in clips))
    cover_at = c2.slider("Viršelio kadras (s)", 0.0, max(0.1, round(total, 1)), min(1.0, round(total, 1)), 0.1,
                         disabled=not clips)
    topic = st.text_input("Tema / produktas (aprašymui)", placeholder="Pvz.: rudens stiliaus patarimai",
                          disabled=client is None,
                          help="Padeda dirbtiniam intelektui parašyti aprašymą ir grotažymes."
                          if client else "Aprašymas ir grotažymės – Premium plane." if plan == "basic"
                          else "Aprašymui reikia OpenAI rakto.")


def source_for_cover():
    """Kuris įrašas ir kuri jo vieta atitinka viršelio kadrą (atsižvelgiant į apkarpymą)."""
    t = 0.0
    for c in clips:
        segs = clips_ui.clip_segments(c) or [(0.0, image_duration if c.get("image") else c["duration"])]
        for a, b in segs:
            if cover_at < t + (b - a):
                return c["path"], 0.0 if c.get("image") else a + (cover_at - t)
            t += b - a
    return clips[-1]["path"], 0.0


def other_format(fmt_name, tmp, progress):
    """Tas pats Reels kitu formatu: medžiaga sujungiama iš naujo pasirinktu formatu, o analizė (iškirptos pauzės,
    titrai, kalbos atpažinimas) panaudojama ta pati – nieko neperskaičiuojama ir minutės neskaičiuojamos."""
    f, size = reels_studio.STUDIO_FORMATS[fmt_name]
    src = os.path.join(tmp, "joined.mkv")
    src, _ = video_editor.concat_clips([c["path"] for c in clips], src, f, progress=lambda p: progress(p * 0.3),
                                       image_duration=image_duration,
                                       segments=[clips_ui.clip_segments(c) for c in clips], transition=transition)
    out = os.path.join(tmp, "reels.mp4")
    build(dict(prep, src=src), words, tmp, out, False, lambda p: progress(0.3 + p * 0.65), fmt=f)
    cover = os.path.join(tmp, "cover.jpg")
    reels_studio.make_cover(src, cover, min(cover_at, prep["analysis"]["info"]["duration"] - 0.1), hook, accent,
                            template, handle, size[0], size[1], color=color, effects=effects, text_size=text_size)
    if logo:
        reels_studio.stamp_logo(cover, logo)
    return out, cover


def link_url(link):
    link = (link or "").strip()
    return link if not link or re.match(r"^[a-z]+://", link, re.I) else "https://" + link


def link_help(result):
    """Kaip padaryti nuorodą paspaudžiamą: video faile ji nepaspaudžiama, todėl dedama platformose."""
    full = link_url(result.get("link"))
    if not full:
        return
    st.markdown("**🔗 Nuoroda** – nukopijuokite ir įdėkite platformoje:")
    st.code(full, language=None)
    with st.expander("📌 Kaip padaryti nuorodą paspaudžiamą"):
        st.markdown(
            "Video faile nuoroda **nepaspaudžiama** – paspaudžiamą ją padaro pati platforma:\n\n"
            "- **Instagram istorija** – įkelkite video į istoriją → lipdukų mygtukas → **„Nuoroda“** → "
            "įklijuokite nuorodą.\n"
            "- **Instagram / TikTok Reels** – nuorodą įdėkite į **profilio aprašymą** (Redaguoti profilį → "
            "Nuorodos); aprašyme parašykite „Nuoroda profilyje 👆“.\n"
            "- **Facebook** – įklijuokite nuorodą į įrašo aprašymą – ji bus paspaudžiama.\n"
            "- **YouTube** – nuorodą įdėkite į video aprašymą (įprastuose video ji paspaudžiama; Shorts – ne).\n"
            "- **QR kodas** pabaigos kortelėje – žiūrovai nuskenuoja telefonu, kai video rodomas kitame ekrane.")
        if result.get("yt_end"):
            st.markdown(
                "**YouTube pabaigos ekranas (16:9 video):** YouTube Studio → jūsų video → **Redaguoti** → "
                "**Pabaigos ekranas** (End screen) → pridėkite **„Video“** (pvz. „Naujausias įkėlimas“ arba "
                "„Tinkamiausias žiūrovui“) ir **„Prenumeruoti“** → nutempkite juos ant auksinio stačiakampio ir "
                "apskritimo → **Išsaugoti**. Elementai rodomi paskutines sekundes, video turi būti bent 25 s.")


def ai_director_ui():
    """✨ AI režisierius – Reels patobulinimas pagal žodinį prašymą."""
    box = st.container(key=P + "ai_box")
    res = st.session_state.get(P + "ai_result")
    if res and client is None and not res.get("error"):  # pvz. Autopilotas be AI rakto – kas parinkta
        lines = [f"- **{k}:** {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in res["done"]]
        box.info((res.get("summary") or "") + ("\n\n" + "\n".join(lines) if lines else ""))
        if res["done"] and st.session_state.get(P + "ai_undo"):
            box.button("↶ Atšaukti Autopiloto pakeitimus", key=P + "ai_undo_btn0", on_click=undo_ai)
    if client is None:  # visada matoma – kad būtų aišku, kur ir kada AI veikia
        box.caption("✨ **AI režisierius** – patobulina Reels pagal jūsų prašymą, parenka debesėlius, kabliukus ir "
                    "svarbiausius žodžius: " + ("Premium plane." if plan == "basic" else
                                                "įveskite OpenAI raktą (⚙️ Nustatymai → Tekstai ir titrai)."))
        return
    if not clips:
        box.caption("✨ **AI režisierius** – įkelkite ar nufilmuokite video, ir galėsite parašyti, kaip jį "
                    "patobulinti (pvz. „padaryk prabangiau, su debesėliais“).")
        return
    words = ai_words()
    box.text_input("✨ AI režisierius – ką patobulinti?", key=P + "ai_req",
                   placeholder="Pvz.: padaryk prabangiau ir energingiau, iki 30 s, sustabdyk ties žodžiu „paslaptis“",
                   help="Parašykite savais žodžiais – AI pakeis šabloną, filtrus, efektus, titrus, kabliuką, "
                        "muziką, tempą ir parodys peržiūrą. Viską galima atšaukti.")
    row = box.container(horizontal=True, gap="small", wrap=True)
    row.button("✨ Pritaikyti", type="primary", key=P + "ai_go", on_click=run_ai_director, args=(client, words))
    presets = [("💎 Prabangiau", "Padaryk prabangiau ir elegantiškiau"),
               ("⚡ Energingiau", "Padaryk energingiau ir dinamiškiau, trumpesnį"),
               ("🌿 Ramiau", "Padaryk ramesnį, švelnesnį ir natūralesnį"),
               ("💬 Debesėliai", "Įjunk debesėlius ir svarbiausius žodžius su akcentų priartėjimu")]
    for i, (label, text) in enumerate(presets):
        row.button(label, key=f"{P}ai_p{i}", on_click=run_ai_director, args=(client, words, text))
    if words:
        row.button("✦ Akimirka svarbiausioje vietoje", key=P + "ai_moment", on_click=run_ai_director,
                   args=(client, words, "moment"),
                   help="AI suras svarbiausią kalbos vietą – ten kadras nušvis gintaro šviesa (Gintaro akimirka).")
    # ✨ Kabliukai – AI pasiūlo iškart, kai tik kalba atpažinta (vieną kartą kiekvienam paruoštam video)
    pr = st.session_state.get(P + "prep")
    if words and pr and st.session_state.get(P + "hook_ideas_for") != pr["n"]:
        st.session_state[P + "hook_ideas_for"] = pr["n"]
        with box, st.spinner("✨ AI ieško kabliukų…"):
            run_ai_hooks(client, words, "")
    ideas = st.session_state.get(P + "hook_ideas") or []
    if ideas:
        box.caption("✨ **AI siūlo kabliukus** – paspauskite, ir jis bus įrašytas pirmoms sekundėms:")
        hrow = box.container(horizontal=True, gap="small", wrap=True)
        for i, h in enumerate(ideas):
            hrow.button(f"„{h}“", key=f"{P}top_hook{i}", on_click=set_hook, args=(h,),
                        type="primary" if st.session_state.get(P + "hook") == h else "secondary")
    res = st.session_state.get(P + "ai_result")
    if res:
        if res.get("error"):
            box.error(res["error"])
        else:
            lines = [f"- **{k}:** {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in res["done"]]
            box.info((res.get("summary") or "") + ("\n\n" + "\n".join(lines) if lines else
                                                    ("" if res.get("summary", "").startswith("↶")
                                                     else "\n\nNieko keisti nereikėjo.")))
            if res["done"] and st.session_state.get(P + "ai_undo"):
                box.button("↶ Atšaukti AI pakeitimus", key=P + "ai_undo_btn", on_click=undo_ai)


AUTO_FORMATS = ("9:16 · Reels, TikTok, Shorts", "16:9 · YouTube", "4:5 · Instagram įrašas")


def make_formats(result, names, box):
    """Sukuria nurodytus papildomus formatus (tas pats montažas) ir įrašo juos į result["formats"]."""
    done = result.setdefault("formats", {})
    bar = st.progress(0.0)
    ok = True
    for i, name in enumerate(names):
        box.write(f"📐 {name}…")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                out, cover = other_format(name, tmp, lambda p: bar.progress(min(1.0, (i + p) / len(names))))
            except Exception as e:
                box.update(label=f"Nepavyko: {name}", state="error")
                st.error(str(e))
                ok = False
                break
            tag = reels_studio.STUDIO_FORMATS[name][0].replace(":", "x")
            vpath = os.path.join(work, f"{result['name']}_{tag}.mp4")
            cpath = os.path.join(work, f"{result['name']}_{tag}_virselis.jpg")
            shutil.copy(out, vpath)
            shutil.copy(cover, cpath)
            done[name] = {"video": vpath, "cover": cpath}
    if ok:
        box.update(label="Visi formatai paruošti", state="complete", expanded=False)
    bar.empty()
    return ok


def all_formats_ui(result):
    """✦ Visi formatai vienu paspaudimu – tas pats video 16:9 (YouTube), 1:1, 4:5 ir 9:16 su ZIP paketu."""
    st.markdown("**📐 Visi formatai** · <small>peržiūrėkite ir atsisiųskite kiekvieną atskirai arba visus ZIP paketu</small>", unsafe_allow_html=True)
    done = result.setdefault("formats", {})
    main_fmt = result.get("fmt_name", st.session_state[P + "format"])
    others = [n for n in reels_studio.STUDIO_FORMATS if n != main_fmt]
    # analizė tinka, jei medžiaga ir jos nustatymai nepakito (formatas – nesvarbu)
    same = bool(prep) and os.path.exists(prep["src"]) and prep["sig"][:3] + prep["sig"][4:] == signature[:3] + signature[4:]
    pick = st.multiselect("Kokių formatų dar reikia?", others, default=[n for n in others if n not in done],
                          key=P + "more_formats", label_visibility="collapsed",
                          placeholder="Pasirinkite formatus")
    todo = [n for n in pick if n not in done]
    if st.button(f"✨ Sukurti {len(todo)} formatus" if len(todo) != 1 else "✨ Sukurti formatą",
                 disabled=not todo or not same, width="stretch",
                 key=P + "formats_btn",
                 help="Tas pats montažas, titrai, muzika ir efektai – kiekvienam tinklui savo formatu. "
                      "Kalbos atpažinimas nekartojamas."):
        box = st.status("Kuriami formatai…", expanded=True)
        make_formats(result, todo, box)
    ready_f = {n: d for n, d in done.items() if os.path.exists(d["video"])}
    if not ready_f:
        st.caption("Pažymėkite formatus ir spauskite – gausite tą patį Reels YouTube, Instagram įrašui ar kvadratu."
                   if same else "Medžiaga pakeista – pirmiausia spauskite „Kurti“.")
        return
    tabs = st.tabs([n.split(" · ")[0] + " · " + n.split(" · ")[1].split(",")[0] for n in ready_f])
    for tab, (name, d) in zip(tabs, ready_f.items()):
        with tab:
            w = reels_studio.STUDIO_FORMATS[name][1]
            cols = st.columns([1, 1.2, 1]) if w[1] > w[0] else st.columns([0.1, 3, 0.1])
            cols[1].video(d["video"])
            b1, b2 = st.columns(2)
            with open(d["video"], "rb") as fv:
                b1.download_button("⬇  Video", fv.read(), file_name=os.path.basename(d["video"]), mime="video/mp4",
                                   width="stretch", key=P + "dl_" + name)
            with open(d["cover"], "rb") as fc:
                b2.download_button("⬇  Viršelis", fc.read(), file_name=os.path.basename(d["cover"]),
                                   mime="image/jpeg", width="stretch", key=P + "dlc_" + name)
    zpath = os.path.join(work, result["name"] + "_visi_formatai.zip")
    names = sorted(ready_f)
    if result.get("zip_names") != names or not os.path.exists(zpath):
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:  # video jau suspausti
            tag = reels_studio.STUDIO_FORMATS[main_fmt][0].replace(":", "x")
            z.writestr(f"{result['name']}_{tag}.mp4", result["video"])
            z.writestr(f"{result['name']}_{tag}_virselis.jpg", result["cover"])
            for d in ready_f.values():
                z.write(d["video"], os.path.basename(d["video"]))
                z.write(d["cover"], os.path.basename(d["cover"]))
        result["zip_names"] = names
    with open(zpath, "rb") as fz:
        st.download_button(f"📦  Atsisiųsti visus formatus (ZIP, {len(ready_f) + 1} video)", fz.read(),
                           file_name=os.path.basename(zpath), mime="application/zip", type="primary",
                           width="stretch", key=P + "dl_zip")


highlight = reels_studio._ass_color(reels_studio.accent_colors(accent)[0])[4:]  # BBGGRR
work = st.session_state.setdefault(P + "work", tempfile.mkdtemp(prefix="reels_"))
os.makedirs(work, exist_ok=True)
signature = (tuple((c["id"], tuple(clips_ui.clip_segments(c) or ())) for c in clips), image_duration, transition, fmt,
             remove_silence, subtitles, client is not None, subtitle_language, subtitle_text.strip(),
             vo_file.file_id if vo_file is not None else None)
prep = st.session_state.get(P + "prep")
ready = bool(prep) and prep["sig"] == signature and os.path.exists(prep["src"])


def prepare(say, progress):
    """Sujungia / apkarpo medžiagą, suranda pauzes ir paruošia titrus (be galutinio montažo)."""
    old = st.session_state.get(P + "prep")
    segments = [clips_ui.clip_segments(c) for c in clips]
    # Visada per sujungimą: medžiaga suvienodinama pagal pasirinktą formatą (standartinis dydis, sulietas fonas).
    say(f"Sujungiu {len(clips)} įrašus…" if len(clips) > 1 else "Ruošiu medžiagą…")
    src = os.path.join(work, f"joined_{datetime.datetime.now().strftime('%H%M%S%f')}.mkv")
    src, spans = video_editor.concat_clips([c["path"] for c in clips], src, fmt,
                                           progress=lambda p: progress(p * 0.5), image_duration=image_duration,
                                           segments=segments, transition=transition)
    protect = [sp for sp, c in zip(spans, clips) if c["audio"] != "speech"]
    analysis = video_editor.analyze(src, remove_silence=remove_silence and not vo_path,
                                    subtitles=subtitles and not vo_path, client=client,
                                    subtitle_language=subtitle_language, subtitle_text=subtitle_text,
                                    protect=protect, status=say)
    if analysis["subtitle_mode"] in ("voice", "translated"):
        accounts.add_minutes(analysis["info"]["duration"] / 60)
    if vo_path:  # titrai iš įgarsinimo (jo laiko skalė = galutinio video laikas)
        words_vo, mode = video_editor.analyze_voice(vo_path, subtitles, client, None, subtitle_language,
                                                    subtitle_text, status=say)
        analysis["words"], analysis["subtitle_mode"] = words_vo, mode
        if mode in ("voice", "translated"):
            accounts.add_minutes(reels_studio.media_duration(vo_path) / 60)
    if old and old["src"] != src and old["src"].startswith(work) and os.path.exists(old["src"]):
        os.unlink(old["src"])
    st.session_state.pop(P + "quick_video", None)
    n = (old or {}).get("n", 0) + 1
    st.session_state[P + "prep"] = {"sig": signature, "src": src, "analysis": analysis, "n": n,
                                    "lines": video_editor.edit_lines(analysis["words"])}
    return st.session_state[P + "prep"]


OWN_MUSIC = "📁 Jūsų muzika"


def music_block_paths(tmp):
    """Muzikos takelio blokai su failų keliais (None – takelis nenaudojamas, veikia įprasta muzika)."""
    blocks = st.session_state.get(P + "mblocks")
    if blocks is None:
        return None
    out = []
    for b in blocks:
        if b["name"] in library:
            path = library[b["name"]]["path"]
        elif b["name"] == OWN_MUSIC and music_file:
            path = os.path.join(tmp, "own" + (os.path.splitext(music_file.name)[1] or ".mp3"))
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(music_file.getvalue())
        else:
            continue
        out.append({"path": path, "start": float(b["start"]), "end": float(b["end"]), "vol": b.get("vol", 100)})
    return out


def music_path(tmp):
    if music_file:
        path = os.path.join(tmp, "music" + (os.path.splitext(music_file.name)[1] or ".mp3"))
        with open(path, "wb") as f:
            f.write(music_file.getvalue())
        return path
    return library[music_choice]["path"] if music_choice in library else None


def build(prep, words, tmp, out, quick, progress, fmt=fmt):
    """Montažas + Reels apdaila. quick – greita peržiūra (maža raiška, greitas kodavimas).
    fmt – kitas formatas (prep["src"] tada turi būti sujungtas tuo formatu)."""
    edited = os.path.join(tmp, "edited.mp4")
    words = prep["analysis"]["words"] if words is None else words
    # svarbiausi žodžiai: naudotojo *žymės* arba automatinis parinkimas; išjungus – žymės pašalinamos
    words = (marked(words) if key_words
             else [(video_editor.plain(w), a, b) for w, a, b in words])
    if vo_path:  # įgarsinimo titrai – galutinio video laiku; montaže jie dar bus pagreitinti kartu su vaizdu
        words = [(w, a * speed, b * speed) for w, a, b in words]
    res = video_editor.render_edit(
        prep["src"], edited, prep["analysis"], words, fmt=fmt, denoise=denoise and not quick,
        loudnorm=not quick, subtitle_style="modern", highlight=highlight, subtitle_look=look, ypos=subs_y,
        subtitle_size=subs_size,
        progress=lambda p: progress(p * 0.6), max_side=640 if quick else 1920,
        preset="ultrafast" if quick else "veryfast", crf=30 if quick else 20)
    fin = reels_studio.finish(
        edited, out, hook, hook_duration, cta, 2.5, handle, accent, template,
        None if music_block_paths(tmp) is not None else music_path(tmp), music_volume,
        ducking, reels_studio.LENGTHS[length], speed, color, progress_bar,
        progress=lambda p: progress(0.6 + p * 0.4), effects=effects, preview=quick,
        subs_words=words, subs_look=look, subs_ypos=subs_y,
        hook_ypos=hook_y, subs_size=subs_size, text_size=text_size, music_blocks=music_block_paths(tmp),
        voiceover=vo_path, clip_gain=clip_gain if vo_path else 1.0, punch=key_words and punch, logo=logo, end_card=end_card,
        bubbles=bubble_list(words), anims=anim_spec(words),
        moment_at=st.session_state.get(P + "moment_at", 3.0) if "Gintaro akimirka" in effects else None)
    return res, fin


# ---------- II. Titrų taisymas (po medžiaga) ----------
words = None
if clips and subtitles:
    with st.container(border=True):
        step("II", "Titrų taisymas", "pataisykite prieš kuriant")
        if not ready:
            st.caption("Paspauskite – studija iškirps pauzes ir parodys titrus, kuriuos galėsite pataisyti. "
                       "(Galite ir iškart spausti „Peržiūra“ ar „Kurti“ viršuje.)")
            if prep:
                st.info("Pakeitėte medžiagą, formatą ar titrų nustatymus – paruoškite iš naujo.")
            if st.button("🎙️  Paruošti titrus", width="stretch", key=P + "prepare"):
                box = st.status("Ruošiama…", expanded=True)
                pbar = st.progress(0.0)
                try:
                    prepare(box.write, lambda p: pbar.progress(min(1.0, p)))
                except Exception as e:
                    box.update(label="Nepavyko paruošti", state="error")
                    st.error(str(e))
                    st.stop()
                st.rerun()
        else:
            a = prep["analysis"]
            base_words = (marked(a["words"]) if key_words
                          else [(video_editor.plain(w), x, y) for w, x, y in a["words"]])
            lines = video_editor.edit_lines(base_words)
            if lines:
                import pandas as pd
                st.markdown(
                    '<div class="lux-howto"><b>✏️ Kaip taisyti titrus</b><ul>'
                    "<li><b>Neteisingai atpažintą žodį</b> – spustelėkite eilutę ir parašykite teisingai.</li>"
                    "<li><b>Nereikalingą eilutę</b> – ištrinkite visą jos tekstą (video ji nebus rodoma).</li>"
                    + ("<li><b>✦ Žodžiai tarp žvaigždučių</b>, pvz. <code>*svarbiausia*</code>, video bus "
                       "<span class='k'>DIDESNI ir auksiniai</span>, o kadras ties jais trumpam priartės. "
                       "Žvaigždučių video nesimatys. Norite paryškinti kitą žodį – apgaubkite jį "
                       "<code>*žvaigždutėmis*</code>; nenorite – ištrinkite jas. Išjungti visai: "
                       "⚙️ Nustatymai → Tekstai ir titrai → „Svarbiausi žodžiai“.</li>" if key_words else "")
                    + "<li>Pataisę spauskite <b>▶ Peržiūra</b> viršuje.</li></ul></div>",
                    unsafe_allow_html=True)
                df = pd.DataFrame([{"Nuo": round(x, 1), "Iki": round(y, 1), "Tekstas": t} for x, y, t in lines])
                edited = st.data_editor(
                    df, key=f"{P}lines_{prep['n']}_{int(key_words)}", hide_index=True, width="stretch", num_rows="fixed",
                    disabled=["Nuo", "Iki"],
                    column_config={"Nuo": st.column_config.NumberColumn("Nuo (s)", format="%.1f", width="small"),
                                   "Iki": st.column_config.NumberColumn("Iki (s)", format="%.1f", width="small"),
                                   "Tekstas": st.column_config.TextColumn("Tekstas", width="large")})
                new_lines = [(x, y, str(t) if t is not None else "")
                             for (x, y, _), t in zip(lines, edited["Tekstas"].tolist())]
                words = video_editor.apply_line_edits(base_words, new_lines)
                changed = sum(1 for (_, _, t0), (_, _, t1) in zip(lines, new_lines) if t0 != t1)
                if changed:
                    st.caption(f"✏️ Pataisyta eilučių: {changed} – spauskite „Peržiūra“ viršuje.")
            else:
                st.caption("Titrų nėra – kalbos neatpažinta ir teksto neįrašyta.")
            cut = a["info"]["duration"] - sum(y - x for x, y in a["keep"])
            st.caption(f"Medžiaga: {a['info']['duration']:.1f} s · iškirpta pauzių: {cut:.1f} s · "
                       f"kirpimų: {len(a['keep']) - 1}")

# ---------- III. Muzikos takelis ----------
@st.cache_data(max_entries=20, show_spinner=False)
def edited_filmstrip(src, keep, speed, final_dur, n=12, height=160):
    """Kadrų miniatiūros galutinio (iškirptų pauzių, pagreitinto) video laiko juostai."""
    out = []
    starts, acc = [], 0.0
    for a_, b_ in keep:
        starts.append(acc)
        acc += b_ - a_
    for i in range(n):
        te = min(acc - 0.05, (i + 0.5) * final_dur / n * speed)  # laikas iškirptame video
        k = max(j for j in range(len(keep)) if starts[j] <= te) if keep else 0
        ts = keep[k][0] + (te - starts[k]) if keep else te
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, ts):.2f}", "-i", src, "-frames:v", "1",
                            "-vf", f"scale=-2:{height}", "-q:v", "6", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
                           capture_output=True)
        if r.stdout:
            import base64
            out.append("data:image/jpeg;base64," + base64.b64encode(r.stdout).decode())
    return out


if clips:
    with st.container(border=True):
        step("III", "Muzikos takelis", "kokia muzika – kurioje vietoje")
        if not ready:
            st.caption("Muzikos takelis rodomas pagal jau paruoštą video (iškirptos pauzės, pritaikytas greitis), "
                       "kad muzika skambėtų tiksliai ten, kur ją padėsite.")
            if st.button("🎵  Paruošti muzikos takelį", width="stretch", key=P + "prepare_music"):
                box = st.status("Ruošiama…", expanded=True)
                pbar = st.progress(0.0)
                try:
                    prepare(box.write, lambda p: pbar.progress(min(1.0, p)))
                except Exception as e:
                    box.update(label="Nepavyko paruošti", state="error")
                    st.error(str(e))
                    st.stop()
                st.rerun()
        else:
            keep = tuple(tuple(x) for x in prep["analysis"]["keep"])
            final_dur = sum(b_ - a_ for a_, b_ in keep) / speed
            if vo_path:  # įgarsinimas gali prailginti video
                final_dur = max(final_dur, reels_studio.media_duration(vo_path) + 0.3)
            if reels_studio.LENGTHS[length]:
                final_dur = min(final_dur, reels_studio.LENGTHS[length])
            final_dur += reels_studio.end_card_len(end_card, *cover_size)  # pabaigos kortelė
            tracks = list(library) + ([OWN_MUSIC] if music_file else [])
            if P + "mblocks" not in st.session_state:  # pradžia – pasirinkta muzika per visą video
                st.session_state[P + "mblocks"] = ([{"name": music_choice, "start": 0.0, "end": round(final_dur, 2),
                                                     "vol": 100}] if music_choice in library else [])
            # Naujausia takelio reikšmė perskaitoma PRIEŠ jį piešiant – kitaip takelis būtų perpieštas pagal
            # pasenusį sąrašą ir ką tik pridėtas blokas „dingtų“.
            mval = st.session_state.get(f"{P}mtrack")
            if mval and mval.get("t") != st.session_state.get(P + "mblocks_t"):
                st.session_state[P + "mblocks"] = mval["blocks"]
                st.session_state[P + "mblocks_t"] = mval["t"]
            music_track(duration=round(final_dur, 2), blocks=st.session_state[P + "mblocks"], tracks=tracks,
                        thumbs=edited_filmstrip(prep["src"], keep, speed, round(final_dur, 2)),
                        key=f"{P}mtrack", default=None)
            mb = st.session_state[P + "mblocks"]
            st.caption((f"🎵 Muzikos blokų: {len(mb)} · " if mb else "🔇 Muzikos nėra · ")
                       + "garsumas ir „patyli kalbant“ – šoniniame skydelyje (Garsas). Pakeitę – spauskite „Peržiūra“.")
            if st.button("↺  Atstatyti takelį pagal pasirinktą muziką", key=P + "mreset"):
                st.session_state.pop(P + "mblocks", None)
                st.session_state[P + "mblocks_t"] = (st.session_state.get(f"{P}mtrack") or {}).get("t")
                st.rerun()

# ---------- Peržiūra ir rezultatas (viršuje) ----------
portrait = cover_size[1] > cover_size[0]
def steps_html():
    """Žingsnių juosta: kas dabar daroma ir ką gausite pabaigoje."""
    res = st.session_state.get(P + "result")
    seen = bool(st.session_state.get(P + "quick_video")) or bool(res)
    cur = 5 if res else 4 if seen else 2 if clips else 1
    steps = [("1", "Medžiaga", "įkelkite ar nufilmuokite video"),
             ("2", "Stilius", "» nustatymai: šablonas, filtrai, titrai, muzika"),
             ("3", "Peržiūra", "pažiūrėkite, ar viskas patinka"),
             ("4", "Kurti", "galutinis video pilna kokybe")]
    if cur == 2:
        cur_set = {2, 3}  # stilius neprivalomas – galima iškart peržiūrėti
    else:
        cur_set = {cur}
    items = "".join(
        f'<div class="st-step{" on" if int(n) in cur_set else " done" if int(n) < cur else ""}">'
        f'<span class="n">{"✓" if int(n) < cur and int(n) not in cur_set else n}</span>'
        f'<span class="t">{t}</span><span class="d">{d}</span></div>' for n, t, d in steps)
    gift = (f'<div class="st-gift{" on" if cur == 5 else ""}">🎁 <b>Pabaigoje gausite:</b> '
            "3 video formatai (Reels / TikTok 9:16 · YouTube 16:9 · Instagram 4:5) · viršelis · "
            "paruoštas aprašymas su grotažymėmis · viskas viename ZIP"
            "<br><small>Skubate? Įkėlę video spauskite <b>✨ Autopilotas</b> – studija padarys viską pati."
            "</small></div>")
    return f'<div class="st-steps">{items}</div>{gift}'


with top:
    st.markdown(steps_html(), unsafe_allow_html=True)
    with st.container(border=True):
        view = st.container(key=P + "view")
        autopilot_btn = st.button("✨ AUTOPILOTAS – padaryk viską už mane", type="primary", width="stretch",
                                  disabled=not clips, key=P + "autopilot_btn",
                                  help="Vienas paspaudimas: studija atpažins kalbą, parinks stilių, titrus, kabliuką, "
                                       "efektus, debesėlius ir muziką, sukurs 3 formatus su viršeliais ir aprašymu.")
        row = st.container(horizontal=True, gap="small", key=P + "actions")  # telefone – irgi vienoje eilutėje
        cover_btn = row.button("👁 Viršelis", width="stretch", disabled=not clips, key=P + "cover_btn",
                               help="Viršelio peržiūra")
        quick_btn = row.button("▶ Peržiūra", width="stretch", disabled=not clips, key=P + "quick_btn",
                               help="Greita peržiūra: visas video mažesne kokybe per kelias sekundes")
        create = row.button("✨ Kurti", type="primary", width="stretch", disabled=not clips, key=P + "create_btn",
                            help="Galutinis video pilna kokybe")
        quick_btn = quick_btn or bool(st.session_state.pop(P + "auto_preview", False) and clips)
        create = create or bool(st.session_state.pop(P + "autopilot", None) == "create" and clips)
        ai_director_ui()
        work_area = st.container()
        if autopilot_btn and clips:  # 1 etapas: paruošiam kalbą ir parenkam nustatymus, tada perkraunam
            with work_area:
                box = st.status("✨ Autopilotas dirba…", expanded=True)
                pbar = st.progress(0.0)
                try:
                    if not ready:
                        prep = prepare(box.write, lambda p: pbar.progress(min(1.0, p)))
                        ready = True
                    box.write("🎨 Renku stilių, titrus, kabliuką ir efektus…")
                    ch, summ = autopilot_plan(client, list(prep["analysis"]["words"]))
                    st.session_state[P + "autopilot_changes"] = ch
                    st.session_state[P + "autopilot_summary"] = summ
                    st.session_state[P + "autopilot"] = "apply"
                    st.session_state.pop(P + "mblocks", None)
                except Exception as e:
                    box.update(label="Autopilotui nepavyko", state="error")
                    st.error(str(e))
                    st.stop()
            st.rerun()

    def show(media, kind, caption=None):
        """Rodo vaizdą/video peržiūros lange tinkamu pločiu pagal formatą."""
        cols = view.columns([1, 1.15, 1]) if portrait else view.columns([1, 6, 1])
        if kind == "video":
            cols[1].video(media)
        else:
            cols[1].image(media, width="stretch")
        if caption:
            cols[1].caption(caption)

    if cover_btn and clips:
        with work_area, tempfile.TemporaryDirectory() as tmp, st.spinner("Kuriu viršelį…"):
            path, at = source_for_cover()
            out = os.path.join(tmp, "cover.jpg")
            try:
                reels_studio.make_cover(path, out, at, hook, accent, template, handle, cover_size[0] // 2,
                                        cover_size[1] // 2, color=color, effects=effects, text_size=text_size)
                if logo:
                    reels_studio.stamp_logo(out, logo)
                with open(out, "rb") as f:
                    st.session_state[P + "preview"] = f.read()
                st.session_state[P + "view"] = "cover"
            except Exception as e:
                st.error(str(e))

    if quick_btn and clips:
        with work_area, tempfile.TemporaryDirectory() as tmp:
            pbar = st.progress(0.0, text="Kuriama peržiūra…")
            try:
                if not ready:
                    prep = prepare(lambda m: pbar.progress(0.0, text=m), lambda p: pbar.progress(min(1.0, p) * 0.4,
                                                                                               text="Ruošiama…"))
                    ready = True
                out = os.path.join(tmp, "preview.mp4")
                build(prep, words, tmp, out, True,
                      lambda p: pbar.progress(0.4 + min(1.0, p) * 0.6, text="Kuriama peržiūra…"))
                with open(out, "rb") as f:
                    st.session_state[P + "quick_video"] = f.read()
                st.session_state[P + "view"] = "quick"
            except Exception as e:
                st.error(str(e))
            pbar.empty()

    if create and clips:
        st.session_state.pop(P + "preview", None)
        with work_area, tempfile.TemporaryDirectory() as tmp:
            status = st.status("Kuriama…", expanded=True)
            bar = st.progress(0.0)
            say = status.write
            try:
                if not ready:
                    prep = prepare(say, lambda p: bar.progress(min(1.0, p) * 0.3))
                final = os.path.join(tmp, "reels.mp4")
                say("Montuoju ir uždedu apdailą…")
                res, fin = build(prep, words, tmp, final, False, lambda p: bar.progress(0.3 + min(1.0, p) * 0.65))
                say("Kuriu viršelį…")
                # Viršelis iš paruoštos (jau suformatuotos) medžiagos – su tuo pačiu sulietu fonu kaip video.
                path, at = (prep["src"], min(cover_at, prep["analysis"]["info"]["duration"] - 0.1)) if prep \
                    else source_for_cover()
                cover = os.path.join(tmp, "cover.jpg")
                reels_studio.make_cover(path, cover, at, hook, accent, template, handle, cover_size[0],
                                        cover_size[1], color=color, effects=effects, text_size=text_size)
                if logo:
                    reels_studio.stamp_logo(cover, logo)
                caption = None
                if client:
                    say("Rašau aprašymą ir grotažymes…")
                    try:
                        caption = reels_studio.write_caption(client, res.get("text", ""), hook, topic,
                                                             subtitle_language or "lt")
                    except Exception as e:
                        say(f"AI aprašymo sukurti nepavyko ({e}) – paruošiu paprastą.")
                if not caption:  # be AI – paprastas aprašymas iš kabliuko, temos ir kalbos
                    caption = reels_studio.simple_caption(
                        res.get("text", ""), hook, topic, cta,
                        reels_studio.TEMPLATES.get(template, {}).get("cat", "Prabanga"), words or [])
            except Exception as e:
                status.update(label="Nepavyko sukurti", state="error")
                st.error(str(e))
                st.stop()
            bar.progress(1.0)
            bar.empty()
            status.update(label="Paruošta", state="complete", expanded=False)
            with open(final, "rb") as f:
                video = f.read()
            with open(cover, "rb") as f:
                cover_bytes = f.read()
            st.session_state[P + "result"] = {
                "video": video, "cover": cover_bytes, "caption": caption, "portrait": portrait,
                "before": res["original_duration"], "after": fin["duration"], "cuts": res["cuts"],
                "name": "reels_" + datetime.datetime.now().strftime("%Y%m%d_%H%M"),
                "fmt_name": st.session_state[P + "format"], "link": link,
                "yt_end": bool(end_on and yt_on)}
            st.session_state[P + "view"] = "result"
            if st.session_state.get(P + "auto_formats", True):  # iškart ir kiti formatai
                main = st.session_state[P + "format"]
                extra = [n for n in AUTO_FORMATS if n != main][:2]
                make_formats(st.session_state[P + "result"], extra,
                             st.status("Kuriu kitus formatus (16:9 YouTube, 4:5 Instagram)…", expanded=True))

    result = st.session_state.get(P + "result")
    mode = st.session_state.get(P + "view")
    if mode == "result" and result:
        if result.get("portrait", True):
            c0, cv, cc, c3 = view.columns([0.3, 1.2, 0.9, 0.3])
        else:
            c0, cv, cc, c3 = view.columns([0.05, 2.2, 1, 0.05])
        cv.video(result["video"])
        cc.image(result["cover"], caption="Viršelis", width="stretch")
        saved = result["before"] - result["after"]
        cc.metric("Trukmė", f"{result['after']:.1f} s", f"-{saved:.1f} s" if saved >= 0.1 else None,
                  delta_color="inverse")
    elif mode == "quick" and st.session_state.get(P + "quick_video"):
        show(st.session_state[P + "quick_video"], "video",
             "Greita peržiūra: mažesnė kokybė, garsas neapdorotas. Galutinis video – mygtukas „Kurti“.")
    elif mode == "cover" and st.session_state.get(P + "preview"):
        show(st.session_state[P + "preview"], "image", "Viršelio peržiūra")
    elif not clips:
        view.markdown('<div class="lux-empty">Įkelkite video ar nuotraukas žemiau – čia matysite peržiūrą '
                      'ir rezultatą.</div>', unsafe_allow_html=True)
    else:
        show(base, "image", "Spauskite „▶ Peržiūra“ – pamatysite visą video su titrais ir efektais.")

    if result and mode == "result":
        with st.container(border=True):
            nf = 1 + len([d for d in (result.get("formats") or {}).values() if os.path.exists(d["video"])])
            st.markdown(f'<div class="lux-done">🎁 <b>Jūsų Reels paruoštas!</b> Žemiau: video ({nf} '
                        f'format{"as" if nf == 1 else "ai"}), viršelis, aprašymas su grotažymėmis'
                        + (', nuoroda' if result.get("link") else '') + ' ir ZIP su viskuo.</div>',
                        unsafe_allow_html=True)
            d1, d2 = st.columns(2)
            d1.download_button("⬇  Atsisiųsti video", result["video"], file_name=result["name"] + ".mp4",
                               mime="video/mp4", type="primary", width="stretch")
            d2.download_button("⬇  Viršelis (JPG)", result["cover"], file_name=result["name"] + "_virselis.jpg",
                               mime="image/jpeg", width="stretch")
            cap = result.get("caption")
            if cap:
                st.markdown("**✍️ Aprašymas su grotažymėmis**")
                st.markdown(f'<div class="lux-caption">{html.escape(cap["caption"])}</div>'
                            f'<div class="lux-tags">{html.escape(" ".join(cap["hashtags"]))}</div>',
                            unsafe_allow_html=True)
                full_link = link_url(result.get("link"))
                st.code(cap["caption"] + (f"\n\n🔗 {full_link}" if full_link else "") + "\n\n"
                        + " ".join(cap["hashtags"]), language=None)
                if cap.get("hooks"):
                    st.markdown("**Kabliukų idėjos kitam kartui:** " + " · ".join(f"„{h}“" for h in cap["hooks"]))
                if cap.get("simple"):
                    st.caption("Paprastas aprašymas (be AI) – iš jūsų kabliuko, temos ir kalbos. "
                               + ("Su OpenAI raktu jį parašys dirbtinis intelektas." if plan != "basic"
                                  else "Premium plane jį parašo dirbtinis intelektas."))
                st.caption("📋 Nukopijuokite (mygtukas laukelio kampe) ir įklijuokite į Instagram / TikTok aprašymą.")
            link_help(result)
        with st.container(border=True):
            all_formats_ui(result)

if plan == "admin":
    with st.expander("👑 Administravimas – klientai ir naudojimas šį mėnesį"):
        st.dataframe(accounts.usage_table(), hide_index=True, width="stretch")
        st.caption("Klientai pridedami ir šalinami Streamlit Secrets (⋮ → Settings → Secrets). "
                   "Minučių apskaita išsivalo, kai programa perkraunama ar atnaujinama – "
                   "OpenAI svetainėje nustatykite ir išlaidų ribą.")

st.markdown('<div class="lux-foot"><span class="lux-orn orn"></span>SUKURTA LIETUVOJE · BALTIJOS GINTARAS</div>',
            unsafe_allow_html=True)
