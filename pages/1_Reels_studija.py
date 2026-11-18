import datetime
import html
import os
import subprocess
import sys
import tempfile

import streamlit as st
import streamlit.components.v1 as components

# Kad puslapis veiktų ir paleistas kaip atskira programa (pagrindinis failas – šis puslapis)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import accounts
import clips_ui
import reels_studio
import video_editor

P = "reels_"  # šio puslapio būsenos raktų priešdėlis
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
.lux-logo { display: flex; justify-content: center; margin-bottom: .2rem; }
.lux-logo svg { width: 74px; height: 74px; filter: drop-shadow(0 6px 22px rgba(227,155,46,.35)); }
.lux-orn { width: 230px; height: 14px; margin: .7rem auto 0; opacity: .8;
  background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='14'><g fill='none' stroke='%23E8A846' stroke-width='1'><path d='M1 7 L7 1 L13 7 L7 13 Z'/></g><circle cx='7' cy='7' r='1.5' fill='%23E8A846'/><path d='M17 7 L21 3 L25 7 L21 11 Z' fill='%23E8A846' fill-opacity='.55'/></svg>") repeat-x center;
  -webkit-mask: linear-gradient(90deg, transparent, #000 25%, #000 75%, transparent);
          mask: linear-gradient(90deg, transparent, #000 25%, #000 75%, transparent); }
.lux-side-logo { display: flex; align-items: center; gap: .6rem; }
.lux-side-logo svg { width: 38px; height: 38px; filter: drop-shadow(0 3px 10px rgba(227,155,46,.35)); }
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
st.session_state.setdefault(P + "template", "Baltijos gintaras")
if P + "accent" not in st.session_state:
    apply_template()

top = st.container()  # peržiūra, mygtukai ir rezultatas – viršuje (užpildoma puslapio gale)
st.markdown('<div class="lux-settings-hint">⚙️ <b>Nustatymai</b> – filtrai, efektai, titrai, kalbos atpažinimas, '
            'muzika: paspauskite <b>»</b> viršuje kairėje</div>', unsafe_allow_html=True)

# ---------- I. Medžiaga ----------
with st.container(border=True):
    step("I", "Medžiaga", "video, nuotraukos arba filmavimas")
    clips, image_duration = clips_ui.clip_picker(P, trim=True)
    if st.session_state.get(P + "transition") not in video_editor.TRANSITIONS:  # pvz. pašalintas „Lapo vertimas“
        st.session_state[P + "transition"] = "Be perėjimo"
    transition = st.session_state[P + "transition"]
    if len(clips) >= 2:
        st.markdown("**Perėjimai tarp įrašų** · <small>✦ – firminiai studijos</small>", unsafe_allow_html=True)
        try:
            fa = base_frame(clips[0]["path"], 0.0 if clips[0].get("image") else min(1.0, clips[0]["duration"] / 2))
            fb = base_frame(clips[1]["path"], 0.0 if clips[1].get("image") else min(1.0, clips[1]["duration"] / 2))
        except Exception:
            fa = fb = None
        grid = st.container(horizontal=True, wrap=True, gap="small", key=P + "xgrid")
        for i, name in enumerate(video_editor.TRANSITIONS):
            sel = name == transition
            tile = grid.container(width=96, gap=None, key=f"{P}{'tsel' if sel else 'tile'}_x{i}")
            if fa and fb:
                tile.image(transition_tile(fa, fb, name), width="stretch")
            mark = "✦ " if name in reels_studio.SIGNATURE_TRANSITIONS else ""
            tile.button(mark + name, key=f"{P}xbtn{i}", type="primary" if sel else "secondary", width="stretch",
                        on_click=pick_transition, args=(name,))

states = {c["audio"] for c in clips}
speech = "speech" in states

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

# ---------- II. Stilius ----------
with sb.expander("🎨  Stilius – šablonas, filtrai, efektai", expanded=True):
    sample_hook = st.session_state.get(P + "hook") or "Jūsų antraštė čia"
    st.markdown("**Šablonas** · <small>kabliuko ir kvietimo stilius</small>"
                + ("" if clips else " · <small>įkėlus video matysite savo kadrą</small>"), unsafe_allow_html=True)
    grid = st.container(horizontal=True, wrap=True, gap="small", key=P + "tgrid")
    for i, (name, t) in enumerate(reels_studio.TEMPLATES.items()):
        sel = name == template
        tile = grid.container(width=124, gap=None, key=f"{P}{'tsel' if sel else 'tile'}_t{i}")
        tile.image(style_tile(base, name, t["accent"], t["color"], sample_hook, None, hook_y=hook_y,
                              text_size=text_size), width="stretch")
        tile.button(name, key=f"{P}tbtn{i}", type="primary" if sel else "secondary", width="stretch",
                    on_click=pick_template, args=(name,))

    st.selectbox("Akcento spalva", list(reels_studio.ACCENTS), key=P + "accent",
                 help="Gradientai – metalinis auksas ar sidabras kabliukui, kvietimui ir paryškintam titrų žodžiui.")
    accent = st.session_state[P + "accent"]

    st.markdown("**Filtrai** · <small>✦ – firminiai studijos</small>", unsafe_allow_html=True)
    color = st.session_state[P + "color"]
    grid = st.container(horizontal=True, wrap=True, gap="small", key=P + "fgrid")
    for i, name in enumerate(reels_studio.COLOR_FILTERS):
        sel = name == color
        tile = grid.container(width=96, gap=None, key=f"{P}{'tsel' if sel else 'tile'}_f{i}")
        tile.image(thumb(base, name, ()), width="stretch")
        sig = name in reels_studio.SIGNATURE_FILTERS
        tile.button(("✦ " if sig else "") + name, key=f"{P}fbtn{i}", type="primary" if sel else "secondary",
                    width="stretch", on_click=pick_color, args=(name,),
                    help="Firminis studijos filtras" if sig else None)

    effects = st.session_state[P + "effects"]
    st.markdown("**Efektai** · <small>galima rinktis kelis</small>", unsafe_allow_html=True)
    grid = st.container(horizontal=True, wrap=True, gap="small", key=P + "egrid")
    for i, (name, desc) in enumerate(reels_studio.EFFECTS.items()):
        sel = name in effects
        tile = grid.container(width=96, gap=None, key=f"{P}{'tsel' if sel else 'tile'}_e{i}")
        img = (style_tile(base, template, accent, color, sample_hook, None, (name,), hook_y=hook_y)
               if name in reels_studio.TEXT_EFFECTS else thumb(base, color, (name,), accent))
        tile.image(img, width="stretch")
        mark = "✓ " if sel else "✦ " if name in reels_studio.SIGNATURE_EFFECTS else ""
        tile.button(mark + name, key=f"{P}ebtn{i}", type="primary" if sel else "secondary",
                    width="stretch", help=desc, on_click=toggle_effect, args=(name,))
    if effects:
        st.caption("Pasirinkta: " + " · ".join(effects))

# ---------- III. Tekstai ----------
with sb.expander("✍️  Tekstai ir titrai"):
    hook = st.text_input("Kabliukas – pirmų sekundžių antraštė", key=P + "hook",
                         placeholder="Pvz.: Kaip atrodyti brangiai be didelio biudžeto",
                         help="Trumpa intriguojanti frazė (iki ~8 žodžių) – sustabdo slinkimą.")
    c1, c2 = st.columns(2)
    hook_duration = c1.slider("Kabliuko trukmė (s)", 1.5, 6.0, 3.0, 0.5)
    handle = c2.text_input("Paskyra", placeholder="@jusu.paskyra")
    cta = st.text_input("Kvietimas veikti pabaigoje", placeholder="Pvz.: Išsaugok vėlesniam")
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
        grid = st.container(horizontal=True, wrap=True, gap="small", key=P + "lgrid")
        for i, (key, L) in enumerate(video_editor.SUBTITLE_LOOKS.items()):
            sel = key == look
            tile = grid.container(width=110, gap=None, key=f"{P}{'tsel' if sel else 'tile'}_l{i}")
            tile.image(style_tile(base, template, accent, color, "", key, subs_y=subs_y, subs_size=subs_size),
                       width="stretch")
            tile.button(L["title"], key=f"{P}lbtn{i}", type="primary" if sel else "secondary", width="stretch",
                        on_click=pick_look, args=(key,))

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
                                         help="Įrašykite tekstą – programa suskaidys jį į frazes ir išdėlios "
                                              "per video.")

# ---------- IV. Garsas ----------
with sb.expander("🎵  Garsas ir muzika"):
    library = reels_studio.music_library()
    options = ["Be muzikos"] + list(library) + ["📁 Įkelti savo muziką"]
    music_choice = st.selectbox("Foninė muzika", options, index=1 if library else 0, key=P + "music_choice",
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
    music_volume = c1.slider("Muzikos garsumas", 0, 100, 22, 1, format="%d%%", disabled=not has_music) / 100
    ducking = c2.toggle("Muzika patyli, kai kalbama", value=True, disabled=not has_music)
    c1, c2 = st.columns(2)
    remove_silence = c1.toggle("Iškirpti pauzes", value=True)
    denoise = c2.toggle("Išvalyti foninį triukšmą", value=True)

# ---------- V. Tempas ----------
with sb.expander("⏱  Tempas, trukmė, viršelis"):
    c1, c2 = st.columns(2)
    length = c1.select_slider("Ilgiausia trukmė", list(reels_studio.LENGTHS), value="90 s")
    speed = c2.select_slider("Greitis", [1.0, 1.05, 1.1, 1.15, 1.25, 1.5], value=1.0,
                             format_func=lambda x: f"{x:g}×")
    c1, c2 = st.columns(2)
    progress_bar = c1.radio("Progreso juostelė", ["Viršuje", "Apačioje", "Nėra"], horizontal=True)
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


highlight = reels_studio._ass_color(reels_studio.ACCENTS[accent][0])[4:]  # BBGGRR
work = st.session_state.setdefault(P + "work", tempfile.mkdtemp(prefix="reels_"))
os.makedirs(work, exist_ok=True)
signature = (tuple((c["id"], tuple(clips_ui.clip_segments(c) or ())) for c in clips), image_duration, transition, fmt,
             remove_silence, subtitles, client is not None, subtitle_language, subtitle_text.strip())
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
    analysis = video_editor.analyze(src, remove_silence=remove_silence, subtitles=subtitles, client=client,
                                    subtitle_language=subtitle_language, subtitle_text=subtitle_text,
                                    protect=protect, status=say)
    if analysis["subtitle_mode"] in ("voice", "translated"):
        accounts.add_minutes(analysis["info"]["duration"] / 60)
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


def build(prep, words, tmp, out, quick, progress):
    """Montažas + Reels apdaila. quick – greita peržiūra (maža raiška, greitas kodavimas)."""
    edited = os.path.join(tmp, "edited.mp4")
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
        subs_words=prep["analysis"]["words"] if words is None else words, subs_look=look, subs_ypos=subs_y,
        hook_ypos=hook_y, subs_size=subs_size, text_size=text_size, music_blocks=music_block_paths(tmp))
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
            lines = prep["lines"]
            if lines:
                import pandas as pd
                st.caption("Spustelėkite tekstą ir pataisykite; ištrintas tekstas – eilutė nerodoma.")
                df = pd.DataFrame([{"Nuo": round(x, 1), "Iki": round(y, 1), "Tekstas": t} for x, y, t in lines])
                edited = st.data_editor(
                    df, key=f"{P}lines_{prep['n']}", hide_index=True, width="stretch", num_rows="fixed",
                    disabled=["Nuo", "Iki"],
                    column_config={"Nuo": st.column_config.NumberColumn("Nuo (s)", format="%.1f", width="small"),
                                   "Iki": st.column_config.NumberColumn("Iki (s)", format="%.1f", width="small"),
                                   "Tekstas": st.column_config.TextColumn("Tekstas", width="large")})
                new_lines = [(x, y, str(t) if t is not None else "")
                             for (x, y, _), t in zip(lines, edited["Tekstas"].tolist())]
                words = video_editor.apply_line_edits(a["words"], new_lines)
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
            if reels_studio.LENGTHS[length]:
                final_dur = min(final_dur, reels_studio.LENGTHS[length])
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
with top:
    with st.container(border=True):
        view = st.container(key=P + "view")
        row = st.container(horizontal=True, gap="small", key=P + "actions")  # telefone – irgi vienoje eilutėje
        cover_btn = row.button("👁 Viršelis", width="stretch", disabled=not clips, key=P + "cover_btn",
                               help="Viršelio peržiūra")
        quick_btn = row.button("▶ Peržiūra", width="stretch", disabled=not clips, key=P + "quick_btn",
                               help="Greita peržiūra: visas video mažesne kokybe per kelias sekundes")
        create = row.button("✨ Kurti", type="primary", width="stretch", disabled=not clips, key=P + "create_btn",
                            help="Galutinis video pilna kokybe")
        work_area = st.container()

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
                caption = None
                if client:
                    say("Rašau aprašymą ir grotažymes…")
                    try:
                        caption = reels_studio.write_caption(client, res.get("text", ""), hook, topic,
                                                             subtitle_language or "lt")
                    except Exception as e:
                        say(f"Aprašymo sukurti nepavyko: {e}")
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
                "name": "reels_" + datetime.datetime.now().strftime("%Y%m%d_%H%M")}
            st.session_state[P + "view"] = "result"

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
            d1, d2 = st.columns(2)
            d1.download_button("⬇  Atsisiųsti video", result["video"], file_name=result["name"] + ".mp4",
                               mime="video/mp4", type="primary", width="stretch")
            d2.download_button("⬇  Viršelis (JPG)", result["cover"], file_name=result["name"] + "_virselis.jpg",
                               mime="image/jpeg", width="stretch")
            cap = result.get("caption")
            if cap:
                st.markdown("**Aprašymas**")
                st.markdown(f'<div class="lux-caption">{html.escape(cap["caption"])}</div>'
                            f'<div class="lux-tags">{html.escape(" ".join(cap["hashtags"]))}</div>',
                            unsafe_allow_html=True)
                st.code(cap["caption"] + "\n\n" + " ".join(cap["hashtags"]), language=None)
                if cap.get("hooks"):
                    st.markdown("**Kabliukų idėjos kitam kartui:** " + " · ".join(f"„{h}“" for h in cap["hooks"]))
            elif client is None and plan != "basic":
                st.caption("Aprašymui ir grotažymėms sugeneruoti reikia OpenAI rakto.")

if plan == "admin":
    with st.expander("👑 Administravimas – klientai ir naudojimas šį mėnesį"):
        st.dataframe(accounts.usage_table(), hide_index=True, width="stretch")
        st.caption("Klientai pridedami ir šalinami Streamlit Secrets (⋮ → Settings → Secrets). "
                   "Minučių apskaita išsivalo, kai programa perkraunama ar atnaujinama – "
                   "OpenAI svetainėje nustatykite ir išlaidų ribą.")

st.markdown('<div class="lux-foot"><span class="lux-orn orn"></span>SUKURTA LIETUVOJE · BALTIJOS GINTARAS</div>',
            unsafe_allow_html=True)
