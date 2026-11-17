import datetime
import html
import os
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


st.session_state.setdefault(P + "template", "Prabangus auksas")
if P + "accent" not in st.session_state:
    apply_template()

client = clips_ui.openai_client()

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
    c1, c2 = st.columns(2)
    accent = c1.selectbox("Akcento spalva", list(reels_studio.ACCENTS), key=P + "accent")
    color = c2.selectbox("Spalvų korekcija", list(reels_studio.COLOR_FILTERS), key=P + "color")

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
    subtitle_text, subtitle_language = "", "lt"
    if subtitles and clips:
        if client and speech:
            choice = st.selectbox("Titrų kalba", ["Lietuvių", "Kaip kalbama video (be vertimo)", "English",
                                                  "Русский", "Polski", "Deutsch"])
            subtitle_language = {"Lietuvių": "lt", "English": "en", "Русский": "ru", "Polski": "pl",
                                 "Deutsch": "de"}.get(choice)
        else:
            if speech:
                st.caption("Balsui atpažinti reikia OPENAI_API_KEY – įklijuokite tekstą ranka.")
            subtitle_text = st.text_area("Titrų tekstas", placeholder="Tekstas bus tolygiai išdėliotas per video.")

# ---------- IV. Garsas ----------
with st.container(border=True):
    step("IV", "Garsas", "muzika ir švarus balsas")
    music_file = st.file_uploader("Foninė muzika (MP3, M4A, WAV)", key=P + "music",
                                  help="Muzika kartojama per visą video ir švelniai užgęsta pabaigoje.")
    c1, c2 = st.columns(2)
    music_volume = c1.slider("Muzikos garsumas", 0, 100, 22, 1, format="%d%%", disabled=not music_file) / 100
    ducking = c2.toggle("Muzika patyli, kai kalbama", value=True, disabled=not music_file)
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
            reels_studio.make_cover(path, out, at, hook, accent, template, handle, 540, 960)
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
            music = None
            if music_file:
                music = os.path.join(tmp, "music" + (os.path.splitext(music_file.name)[1] or ".mp3"))
                with open(music, "wb") as f:
                    f.write(music_file.getvalue())
            say("Uždedu kabliuką, spalvas, muziką ir apdailą…")
            final = os.path.join(tmp, "reels.mp4")
            fin = reels_studio.finish(
                edited, final, hook, hook_duration, cta, 2.5, handle, accent, template, music, music_volume,
                ducking, reels_studio.LENGTHS[length], speed, color, progress_bar,
                progress=lambda p: bar.progress(0.7 + p * 0.27))
            say("Kuriu viršelį…")
            path, at = source_for_cover()
            cover = os.path.join(tmp, "cover.jpg")
            reels_studio.make_cover(path, cover, at, hook, accent, template, handle)
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
