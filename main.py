import base64
import os
import subprocess
import tempfile

import streamlit as st
import streamlit.components.v1 as components

import video_editor

# Filmavimas programoje: kamera + mikrofonas per naršyklę (components/recorder/index.html)
video_recorder = components.declare_component(
    "video_recorder", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "recorder"))

st.set_page_config(page_title="Video montažas", page_icon="🎬")
st.title("🎬 Automatinis video montažas")
st.write("Įkelkite video – programa pati iškirps pauzes ir tylą, pašalins foninį triukšmą, "
         "sutvarkys formatą, garsą ir (jei norite) uždės titrus.")


def openai_client():
    try:
        key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    import openai
    return openai.OpenAI(api_key=key)


def saved_source(source_id, ext, data):
    """Video (įkeltą ar nufilmuotą) išsaugo laikinai vieną kartą ir patikrina, ar jame yra balsas."""
    if st.session_state.get("upload_id") != source_id:
        old = st.session_state.get("upload_path")
        if old and os.path.exists(old):
            os.unlink(old)
        fd, path = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd, "wb") as f:
            f.write(data())
        if source_id.startswith("rec-"):
            # Naršyklės įrašuose (ypač WebM) dažnai trūksta trukmės – perpakuojam į MKV be perkodavimo.
            mkv = path + ".mkv"
            if subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c", "copy", mkv]).returncode == 0:
                os.unlink(path)
                path = mkv
        with st.spinner("Tikrinu įrašą…"):
            try:
                state, an = video_editor.audio_status(path)
                audio = (state, an and {k: an[k] for k in ("noise", "loud")})
            except Exception:
                audio = None  # ne video failas
        st.session_state.update(upload_id=source_id, upload_path=path, upload_audio=audio)
    return st.session_state["upload_path"], st.session_state["upload_audio"]


source = st.radio("Video", ["📁 Įkelti video", "🎥 Filmuoti dabar"], horizontal=True,
                  label_visibility="collapsed")
uploaded = None
if source.startswith("📁"):
    # Be failų tipų apribojimo: telefonuose (ypač iPhone) apribojimas neleidžia pasirinkti
    # video iš galerijos. Ar tai tikrai video, patikrinama po įkėlimo.
    file = st.file_uploader("Įkelkite video", help="Telefone galite pasirinkti video iš galerijos.")
    if file:
        uploaded = (file.file_id, os.path.splitext(file.name)[1].lower() or ".mp4", file.getvalue, file.name)
else:
    rec = video_recorder(key="recorder", default=None)
    if rec and rec.get("data"):
        ext = ".mp4" if "mp4" in (rec.get("mime") or "") else ".webm"
        uploaded = (f"rec-{rec['id']}", ext, lambda: base64.b64decode(rec["data"]), "irasas")
src, audio = saved_source(*uploaded[:3]) if uploaded else (None, ("none", None))
if uploaded and audio is None:
    st.error("Šio failo nepavyko atidaryti kaip video. Įkelkite video failą (pvz. MP4 arba MOV).")
    uploaded, audio = None, ("none", None)
audio_state, levels = audio
speech = audio_state == "speech"
if uploaded:
    st.caption("🔈 Garso takelio nėra" if levels is None else
               f"🔈 Garsas: kalba ~{levels['loud']:.0f} dB, fonas ~{levels['noise']:.0f} dB")
client = openai_client()

fmt_label = st.radio(
    "Formatas",
    ["Originalus", "Vertikalus 9:16 (TikTok, Reels, Shorts)", "Kvadratas 1:1", "Horizontalus 16:9"])
fmt = {"Originalus": "original", "Kvadratas 1:1": "1:1",
       "Horizontalus 16:9": "16:9"}.get(fmt_label, "9:16")

subtitles = st.checkbox("Pridėti titrus", value=True)
subtitle_style = "modern"
if subtitles:
    style_label = st.radio(
        "Titrų stilius",
        ["Modernūs – animuoti (TikTok, Reels)", "Mokymų – ramūs, po vaizdu (vaizdo neuždengia)"],
        help="Mokymų titrai rodomi juodoje juostoje ekrano apačioje, be animacijos.")
    subtitle_style = "training" if style_label.startswith("Mokymų") else "modern"
subtitle_text, subtitle_language = "", "lt"
if subtitles and uploaded:
    if client and audio_state != "none" and speech:
        st.success("🎙️ Įraše aptiktas balsas – kalba bus atpažinta automatiškai.")
        sub_choice = st.selectbox(
            "Titrų kalba",
            ["Lietuvių", "Kaip kalbama video (be vertimo)", "English", "Русский", "Polski", "Deutsch"],
            help="Jei video kalbama kita kalba, titrai bus išversti.")
        subtitle_language = {"Lietuvių": "lt", "English": "en", "Русский": "ru", "Polski": "pl",
                             "Deutsch": "de"}.get(sub_choice)
    else:
        if speech:
            st.warning("Įraše yra balsas, bet automatiniam atpažinimui trūksta OPENAI_API_KEY – "
                       "įklijuokite tekstą rankiniu būdu.")
        elif audio_state == "none":
            st.info("🔇 Įraše nėra garso – įklijuokite tekstą, kurį norite matyti titruose. "
                    "(Jei filmavote per naršyklę, patikrinkite, ar jai leista naudoti mikrofoną.)")
        else:
            st.info("🔇 Įraše balso neaptikta – įklijuokite tekstą, kurį norite matyti titruose."
                    + (" Jei balsas vis dėlto yra, palikite laukelį tuščią – programa pabandys "
                       "atpažinti kalbą." if client else ""))
        subtitle_text = st.text_area(
            "Titrų tekstas",
            placeholder="Pvz.: Naujas sezonas jau prasidėjo! Užsuk ir išbandyk.",
            help="Tekstas bus suskirstytas į trumpas frazes ir tolygiai išdėliotas per video.")

with st.expander("⚙️ Papildomi nustatymai"):
    remove_silence = st.checkbox("Iškirpti tylą ir pauzes", value=True)
    col1, col2 = st.columns(2)
    min_silence = col1.slider("Trumpiausia iškerpama pauzė (s)", 0.2, 2.0, 0.5, 0.1,
                              disabled=not remove_silence)
    auto_db = col2.checkbox("Tylos riba automatiškai", value=True, disabled=not remove_silence,
                            help="Riba parenkama pagal įrašo kalbos ir fono garsumą "
                                 "(tinka ir tyliems įrašams).")
    noise_db = col2.slider("Tylos riba (dB)", -70, -20, -35, 1,
                           disabled=not remove_silence or auto_db,
                           help="Kuo didesnis skaičius, tuo daugiau garso laikoma tyla "
                                "(naudinga, jei fone triukšmas).")
    if auto_db:
        noise_db = None
    padding = st.slider("Palikti „oro“ aplink kalbą (s)", 0.0, 0.5, 0.15, 0.05,
                        disabled=not remove_silence)

    denoise = st.checkbox("Pašalinti foninį triukšmą", value=True,
                          help="Sumažina ūžesį, šnypštimą, vėją, ventiliaciją ir kitą pastovų foną.")
    loudnorm = st.checkbox("Suvienodinti garsumą", value=True)
    fades = st.checkbox("Švelni pradžia ir pabaiga (fade)", value=True)


clicked = st.button("🚀 Sumontuoti", type="primary", width="stretch", disabled=not uploaded)
if not uploaded:
    st.caption("👆 Pirmiausia viršuje įkelkite video („Upload“) arba nufilmuokite jį („Filmuoti dabar“). "
               "Jei atidarėte per Messenger ar Facebook ir nepavyksta – atidarykite nuorodą Safari arba Chrome.")
if uploaded and clicked:
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "sumontuota.mp4")

        status = st.empty()
        bar = st.progress(0.0)
        try:
            res = video_editor.auto_edit(
                src, dst, fmt=fmt, remove_silence=remove_silence, noise_db=noise_db,
                min_silence=min_silence, padding=padding, loudnorm=loudnorm, fades=fades,
                denoise=denoise,
                subtitles=subtitles, client=client, subtitle_language=subtitle_language,
                subtitle_text=subtitle_text, subtitle_style=subtitle_style,
                status=lambda m: status.info(m), progress=lambda p: bar.progress(p))
        except Exception as e:
            status.error(f"Nepavyko sumontuoti: {e}")
            st.stop()

        bar.progress(1.0)
        if subtitles and not res["words"]:
            status.warning("✅ Video sumontuotas, bet titrų nepavyko sukurti "
                           "(neatpažinta kalba arba neįvestas tekstas).")
        else:
            status.success("✅ Video sumontuotas!")
        with open(dst, "rb") as f:
            st.session_state["result"] = f.read()
        st.session_state["summary"] = res
        st.session_state["name"] = os.path.splitext(uploaded[3])[0] + "_sumontuota.mp4"

if "result" in st.session_state:
    res = st.session_state["summary"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Buvo", f"{res['original_duration']:.1f} s")
    c2.metric("Liko", f"{res['duration']:.1f} s",
              f"-{res['original_duration'] - res['duration']:.1f} s", delta_color="inverse")
    c3.metric("Kirpimų", res["cuts"])
    st.video(st.session_state["result"])
    st.download_button("⬇️ Atsisiųsti video", st.session_state["result"],
                       file_name=st.session_state["name"], mime="video/mp4")
