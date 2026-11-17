import datetime
import html
import os
import subprocess
import sys
import tempfile

import streamlit as st

# Kad puslapis veiktų ir paleistas kaip atskira programa (pagrindinis failas – šis puslapis)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import clips_ui
import reels_studio
import video_editor

P = "reels_"  # šio puslapio būsenos raktų priešdėlis

st.set_page_config(page_title="Reels studija", page_icon="✨", layout="centered")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,700;1,400&family=Inter:wght@400;500;600&display=swap');
:root { --gold: #D4AF37; --gold-2: #F3DE9C; --gold-3: #9C7A26; --ink: #0B0B0C; --line: rgba(212,175,55,.22); }
.stApp {
  background:
    radial-gradient(1200px 500px at 50% -120px, rgba(212,175,55,.13), transparent 70%),
    radial-gradient(800px 400px at 110% 30%, rgba(156,122,38,.07), transparent 70%),
    #0B0B0C;
}
.stApp, .stApp p, .stApp label, .stApp li { font-family: 'Inter', system-ui, sans-serif; }
#MainMenu, footer { visibility: hidden; }
.lux-hero { text-align: center; padding: 1.2rem 0 1.6rem; }
.lux-kicker { letter-spacing: .42em; font-size: .72rem; color: var(--gold); text-transform: uppercase;
  font-weight: 600; }
.lux-title { font-family: 'Playfair Display', Georgia, serif; font-weight: 700; font-size: clamp(2.1rem, 7vw, 3.3rem);
  line-height: 1.08; margin: .5rem 0 .6rem;
  background: linear-gradient(100deg, #9C7A26 0%, #F3DE9C 35%, #D4AF37 55%, #FFF3CF 70%, #B8912E 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.lux-sub { color: #B8AF9C; font-size: 1rem; max-width: 34rem; margin: 0 auto; }
.lux-rule { width: 84px; height: 1px; margin: 1.2rem auto 0;
  background: linear-gradient(90deg, transparent, var(--gold), transparent); }
.lux-step { display: flex; align-items: baseline; gap: .8rem; margin: .2rem 0 .6rem; }
.lux-step .n { font-family: 'Playfair Display', serif; font-style: italic; color: var(--gold); font-size: 1.5rem; }
.lux-step .t { font-family: 'Playfair Display', serif; font-size: 1.35rem; color: #F4EEDF; font-weight: 500; }
.lux-step .d { color: #8F8778; font-size: .85rem; margin-left: auto; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--line) !important;
  background: linear-gradient(180deg, rgba(255,255,255,.025), rgba(255,255,255,.01)); border-radius: 14px; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(100deg, #B8912E, #F3DE9C 45%, #D4AF37 70%, #B8912E);
  color: #0B0B0C; border: 0; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  box-shadow: 0 8px 30px rgba(212,175,55,.18); }
.stButton > button[kind="primary"]:hover { filter: brightness(1.07); color: #0B0B0C; }
.stButton > button[kind="secondary"], .stDownloadButton > button[kind="secondary"] {
  border-color: var(--line); }
[data-testid="stMetricValue"] { font-family: 'Playfair Display', serif; color: var(--gold-2); }
.lux-caption { white-space: pre-wrap; border-left: 2px solid var(--gold); padding: .2rem 0 .2rem 1rem;
  color: #EDE6D6; }
.lux-tags { color: var(--gold-2); font-size: .92rem; margin-top: .6rem; }
.lux-foot { text-align: center; color: #5E584D; font-size: .75rem; letter-spacing: .3em; margin-top: 2rem; }
[class*="st-key-reels_fgrid"] button, [class*="st-key-reels_egrid"] button {
  min-height: 1.9rem; padding: .15rem .3rem; border-radius: 8px; }
[class*="st-key-reels_tile"] button *, [class*="st-key-reels_tsel"] button * {
  font-size: .74rem !important; line-height: 1.15; letter-spacing: 0; text-transform: none; }
[class*="st-key-reels_tsel"] button, [class*="st-key-reels_tsel"] button * { color: #0B0B0C !important; }
[class*="st-key-reels_tile"] img, [class*="st-key-reels_tsel"] img {
  border-radius: 10px 10px 0 0; transition: transform .15s; }
[class*="st-key-reels_tile"] img { opacity: .82; }
[class*="st-key-reels_tsel"] img { outline: 2px solid var(--gold); outline-offset: -2px; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="lux-hero">
  <div class="lux-kicker">Instagram · TikTok · Shorts</div>
  <div class="lux-title">Reels montavimo studija</div>
  <div class="lux-sub">Įkelkite medžiagą – studija iškirps pauzes, išvalys garsą, suspalvins vaizdą,
  uždės titrus, kabliuką, muziką ir paruoš viršelį bei aprašymą.</div>
  <div class="lux-rule"></div>
</div>
""", unsafe_allow_html=True)


def step(n, title, desc=""):
    st.markdown(f'<div class="lux-step"><span class="n">{n}</span><span class="t">{title}</span>'
                f'<span class="d">{desc}</span></div>', unsafe_allow_html=True)


def apply_template():
    t = reels_studio.TEMPLATES[st.session_state[P + "template"]]
    st.session_state[P + "accent"] = t["accent"]
    st.session_state[P + "color"] = t["color"]


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
def thumb(base, color, effects):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "b.jpg")
        with open(src, "wb") as f:
            f.write(base)
        out = reels_studio.thumbnail(src, os.path.join(tmp, "t.jpg"), color, effects)
        with open(out, "rb") as f:
            return f.read()


st.session_state.setdefault(P + "template", "Prabangus auksas")
if P + "accent" not in st.session_state:
    apply_template()

# ---------- I. Medžiaga ----------
with st.container(border=True):
    step("I", "Medžiaga", "video, nuotraukos arba filmavimas")
    clips, image_duration = clips_ui.clip_picker(P)

states = {c["audio"] for c in clips}
speech = "speech" in states

# ---------- II. Stilius ----------
with st.container(border=True):
    step("II", "Stilius", "šablonas, spalvos, akcentas")
    template = st.radio("Šablonas", list(reels_studio.TEMPLATES), key=P + "template", horizontal=True,
                        on_change=apply_template,
                        captions=["Serifinis šriftas, auksas, šilta kino spalva",
                                  "Šampano tonai, ramus kino vaizdas",
                                  "Didelės raidės dėžutėje, sodrios spalvos"])
    accent = st.selectbox("Akcento spalva", list(reels_studio.ACCENTS), key=P + "accent")

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

    st.markdown("**Filtrai**" + ("" if clips else " · <small>įkėlus video čia matysite savo kadrą</small>"),
                unsafe_allow_html=True)
    color = st.session_state[P + "color"]
    grid = st.container(horizontal=True, wrap=True, gap="small", key=P + "fgrid")
    for i, name in enumerate(reels_studio.COLOR_FILTERS):
        sel = name == color
        tile = grid.container(width=96, gap=None, key=f"{P}{'tsel' if sel else 'tile'}_f{i}")
        tile.image(thumb(base, name, ()), width="stretch")
        tile.button(name, key=f"{P}fbtn{i}", type="primary" if sel else "secondary", width="stretch",
                    on_click=pick_color, args=(name,))

    effects = st.session_state[P + "effects"]
    st.markdown("**Efektai** · <small>galima rinktis kelis</small>", unsafe_allow_html=True)
    grid = st.container(horizontal=True, wrap=True, gap="small", key=P + "egrid")
    for i, (name, desc) in enumerate(reels_studio.EFFECTS.items()):
        sel = name in effects
        tile = grid.container(width=96, gap=None, key=f"{P}{'tsel' if sel else 'tile'}_e{i}")
        tile.image(thumb(base, color, (name,)), width="stretch")
        tile.button(("✓ " if sel else "") + name, key=f"{P}ebtn{i}", type="primary" if sel else "secondary",
                    width="stretch", help=desc, on_click=toggle_effect, args=(name,))
    if effects:
        st.caption("Pasirinkta: " + " · ".join(effects))

# ---------- III. Tekstai ----------
with st.container(border=True):
    step("III", "Tekstai", "kabliukas, titrai, kvietimas")
    hook = st.text_input("Kabliukas – pirmų sekundžių antraštė",
                         placeholder="Pvz.: Kaip atrodyti brangiai be didelio biudžeto",
                         help="Trumpa intriguojanti frazė (iki ~8 žodžių) – sustabdo slinkimą.")
    c1, c2 = st.columns(2)
    hook_duration = c1.slider("Kabliuko trukmė (s)", 1.5, 6.0, 3.0, 0.5)
    handle = c2.text_input("Paskyra", placeholder="@jusu.paskyra")
    cta = st.text_input("Kvietimas veikti pabaigoje", placeholder="Pvz.: Išsaugok vėlesniam")

    subtitles = st.toggle("Animuoti titrai", value=True,
                          help="Sakomas žodis paryškinamas akcento spalva.")

    # Balso atpažinimas (OpenAI Whisper): raktas iš Secrets arba įvedamas čia.
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
                                         help="Be OpenAI rakto kalba neatpažįstama – titrams įrašykite tekstą.")

# ---------- IV. Garsas ----------
with st.container(border=True):
    step("IV", "Garsas", "muzika ir švarus balsas")
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
    has_music = music_choice in library or music_file is not None
    c1, c2 = st.columns(2)
    music_volume = c1.slider("Muzikos garsumas", 0, 100, 22, 1, format="%d%%", disabled=not has_music) / 100
    ducking = c2.toggle("Muzika patyli, kai kalbama", value=True, disabled=not has_music)
    c1, c2 = st.columns(2)
    remove_silence = c1.toggle("Iškirpti pauzes", value=True)
    denoise = c2.toggle("Išvalyti foninį triukšmą", value=True)

# ---------- V. Tempas ----------
with st.container(border=True):
    step("V", "Tempas ir trukmė")
    c1, c2 = st.columns(2)
    length = c1.select_slider("Ilgiausia trukmė", list(reels_studio.LENGTHS), value="90 s")
    speed = c2.select_slider("Greitis", [1.0, 1.05, 1.1, 1.15, 1.25, 1.5], value=1.0,
                             format_func=lambda x: f"{x:g}×")
    c1, c2 = st.columns(2)
    progress_bar = c1.radio("Progreso juostelė", ["Viršuje", "Apačioje", "Nėra"], horizontal=True)
    total = float(sum(image_duration if c.get("image") else c["duration"] for c in clips))
    cover_at = c2.slider("Viršelio kadras (s)", 0.0, max(0.1, round(total, 1)), min(1.0, round(total, 1)), 0.1,
                         disabled=not clips)
    topic = st.text_input("Tema / produktas (aprašymui)", placeholder="Pvz.: rudens stiliaus patarimai",
                          disabled=client is None,
                          help="Padeda dirbtiniam intelektui parašyti aprašymą ir grotažymes."
                          if client else "Aprašymui reikia OPENAI_API_KEY.")


def source_for_cover():
    """Pirmas įrašas arba sujungtas video – kadras viršeliui."""
    if len(clips) == 1:
        return clips[0]["path"], cover_at
    t = 0.0
    for c in clips:
        d = image_duration if c.get("image") else c["duration"]
        if cover_at < t + d:
            return c["path"], cover_at - t
        t += d
    return clips[-1]["path"], 0.0


highlight = reels_studio._ass_color(reels_studio.ACCENTS[accent][0])[4:]  # BBGGRR

c1, c2 = st.columns([1, 2])
preview = c1.button("👁  Viršelio peržiūra", width="stretch", disabled=not clips)
create = c2.button("✨  Kurti Reels", type="primary", width="stretch", disabled=not clips)
if not clips:
    st.caption("Pirmiausia įkelkite arba nufilmuokite medžiagą (I žingsnis).")

if preview and clips:
    with tempfile.TemporaryDirectory() as tmp, st.spinner("Kuriu peržiūrą…"):
        path, at = source_for_cover()
        out = os.path.join(tmp, "cover.jpg")
        try:
            reels_studio.make_cover(path, out, at, hook, accent, template, handle, 540, 960, color=color,
                                    effects=effects)
            with open(out, "rb") as f:
                st.session_state[P + "preview"] = f.read()
        except Exception as e:
            st.error(str(e))
if P + "preview" in st.session_state and clips:
    _, mid, _ = st.columns([1, 1.2, 1])
    mid.image(st.session_state[P + "preview"], caption="Peržiūra", width="stretch")

if create and clips:
    st.session_state.pop(P + "preview", None)
    with tempfile.TemporaryDirectory() as tmp:
        status = st.status("Kuriamas Reels…", expanded=True)
        bar = st.progress(0.0)
        say = status.write
        try:
            src, protect = clips[0]["path"], None
            if len(clips) > 1 or clips[0].get("image"):
                say(f"Sujungiu {len(clips)} įrašus…" if len(clips) > 1 else "Ruošiu nuotrauką…")
                src, spans = video_editor.concat_clips([c["path"] for c in clips], os.path.join(tmp, "joined.mkv"),
                                                       "9:16", progress=lambda p: bar.progress(p * 0.25),
                                                       image_duration=image_duration)
                protect = [sp for sp, c in zip(spans, clips) if c["audio"] != "speech"]
            edited = os.path.join(tmp, "edited.mp4")
            res = video_editor.auto_edit(
                src, edited, fmt="9:16", remove_silence=remove_silence, denoise=denoise,
                subtitles=subtitles, client=client, subtitle_language=subtitle_language,
                subtitle_text=subtitle_text, subtitle_style="modern", protect=protect, highlight=highlight,
                status=say, progress=lambda p: bar.progress(0.25 + p * 0.45))
            music = library[music_choice]["path"] if music_choice in library else None
            if music_file:
                music = os.path.join(tmp, "music" + (os.path.splitext(music_file.name)[1] or ".mp3"))
                with open(music, "wb") as f:
                    f.write(music_file.getvalue())
            say("Uždedu kabliuką, spalvas, muziką ir apdailą…")
            final = os.path.join(tmp, "reels.mp4")
            fin = reels_studio.finish(
                edited, final, hook, hook_duration, cta, 2.5, handle, accent, template, music, music_volume,
                ducking, reels_studio.LENGTHS[length], speed, color, progress_bar,
                progress=lambda p: bar.progress(0.7 + p * 0.27), effects=effects)
            say("Kuriu viršelį…")
            path, at = source_for_cover()
            cover = os.path.join(tmp, "cover.jpg")
            reels_studio.make_cover(path, cover, at, hook, accent, template, handle, color=color, effects=effects)
            caption = None
            if client:
                say("Rašau aprašymą ir grotažymes…")
                try:
                    caption = reels_studio.write_caption(client, res.get("text", ""), hook, topic,
                                                         subtitle_language or "lt")
                except Exception as e:
                    say(f"Aprašymo sukurti nepavyko: {e}")
        except Exception as e:
            status.update(label="Nepavyko sukurti Reels", state="error")
            st.error(str(e))
            st.stop()
        bar.progress(1.0)
        status.update(label="Reels paruoštas", state="complete", expanded=False)
        with open(final, "rb") as f:
            video = f.read()
        with open(cover, "rb") as f:
            cover_bytes = f.read()
        st.session_state[P + "result"] = {
            "video": video, "cover": cover_bytes, "caption": caption,
            "before": res["original_duration"], "after": fin["duration"], "cuts": res["cuts"],
            "name": "reels_" + datetime.datetime.now().strftime("%Y%m%d_%H%M")}

result = st.session_state.get(P + "result")
if result:
    with st.container(border=True):
        step("✦", "Rezultatas")
        m1, m2, m3 = st.columns(3)
        m1.metric("Medžiaga", f"{result['before']:.1f} s")
        m2.metric("Reels", f"{result['after']:.1f} s")
        m3.metric("Kirpimų", result["cuts"])
        v, c = st.columns([3, 2])
        v.video(result["video"])
        c.image(result["cover"], caption="Viršelis", width="stretch")
        d1, d2 = st.columns(2)
        d1.download_button("⬇  Atsisiųsti Reels", result["video"], file_name=result["name"] + ".mp4",
                           mime="video/mp4", type="primary", width="stretch")
        d2.download_button("⬇  Viršelis (JPG)", result["cover"], file_name=result["name"] + "_virselis.jpg",
                           mime="image/jpeg", width="stretch")
        cap = result.get("caption")
        if cap:
            st.markdown("**Aprašymas**")
            st.markdown(f'<div class="lux-caption">{html.escape(cap["caption"])}</div>'
                        f'<div class="lux-tags">{html.escape(" ".join(cap["hashtags"]))}</div>', unsafe_allow_html=True)
            st.code(cap["caption"] + "\n\n" + " ".join(cap["hashtags"]), language=None)
            st.caption("☝️ Nukopijuokite mygtuku dešiniajame kampe.")
            if cap.get("hooks"):
                st.markdown("**Kabliukų idėjos kitam kartui:** " + " · ".join(f"„{h}“" for h in cap["hooks"]))
        elif client is None:
            st.caption("Aprašymui ir grotažymėms sugeneruoti reikia OPENAI_API_KEY.")

st.markdown('<div class="lux-foot">REELS STUDIJA</div>', unsafe_allow_html=True)
