import os
import tempfile

import streamlit as st

import accounts
import clips_ui
import video_editor

APP_VERSION = "13"  # didinama su kiekvienu pakeitimu – matosi puslapio apačioje

st.set_page_config(page_title="Video montažas", page_icon="🎬")
accounts.require_login()
st.title("🎬 Automatinis video montažas")
st.write("Įkelkite video – programa pati iškirps pauzes ir tylą, pašalins foninį triukšmą, "
         "sutvarkys formatą, garsą ir (jei norite) uždės titrus.")


clips, image_duration = clips_ui.clip_picker()

uploaded = bool(clips)
states = {c["audio"] for c in clips}
audio_state = "speech" if "speech" in states else "silent" if "silent" in states else "none"
speech = audio_state == "speech"
client = clips_ui.openai_client()

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
        st.success("🎙️ Aptiktas balsas – kalba bus atpažinta automatiškai.")
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
        elif all(c.get("image") for c in clips):
            st.info("🖼️ Nuotraukose garso nėra – įklijuokite tekstą, kurį norite matyti titruose.")
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
    st.caption("👆 Pirmiausia viršuje įkelkite video („Upload“) arba nufilmuokite („Filmuoti dabar“). "
               "Galima pridėti kelis video – jie bus sujungti į vieną. "
               "Jei atidarėte per Messenger ar Facebook ir nepavyksta – atidarykite nuorodą Safari arba Chrome.")
if uploaded and clicked:
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "sumontuota.mp4")

        status = st.empty()
        bar = st.progress(0.0)
        try:
            src, protect = clips[0]["path"], None
            if len(clips) > 1 or clips[0].get("image"):
                status.info(f"Sujungiu {len(clips)} video į vieną…" if len(clips) > 1 else "Ruošiu nuotrauką…")
                src, spans = video_editor.concat_clips([c["path"] for c in clips],
                                                       os.path.join(tmp, "sujungta.mkv"), fmt,
                                                       progress=lambda p: bar.progress(p),
                                                       image_duration=image_duration)
                # Įrašų be balso tylos kirpimas neliečia – jie paliekami visi.
                protect = [sp for sp, c in zip(spans, clips) if c["audio"] != "speech"]
                bar.progress(0.0)
            res = video_editor.auto_edit(
                src, dst, fmt=fmt, remove_silence=remove_silence, noise_db=noise_db,
                min_silence=min_silence, padding=padding, loudnorm=loudnorm, fades=fades,
                denoise=denoise,
                subtitles=subtitles, client=client, subtitle_language=subtitle_language,
                subtitle_text=subtitle_text, subtitle_style=subtitle_style, protect=protect,
                status=lambda m: status.info(m), progress=lambda p: bar.progress(p))
        except Exception as e:
            status.error(f"Nepavyko sumontuoti: {e}")
            st.stop()

        bar.progress(1.0)
        if res.get("subtitle_mode") in ("voice", "translated"):
            accounts.add_minutes(res["original_duration"] / 60)
        if subtitles and not res["words"]:
            status.warning("✅ Video sumontuotas, bet titrų nepavyko sukurti "
                           "(neatpažinta kalba arba neįvestas tekstas).")
        else:
            status.success("✅ Video sumontuotas!")
        with open(dst, "rb") as f:
            st.session_state["result"] = f.read()
        st.session_state["summary"] = res
        base = os.path.splitext(clips[0]["name"])[0] if len(clips) == 1 else "video"
        st.session_state["name"] = base.replace(" ", "_") + "_sumontuota.mp4"

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

st.caption(f"Programos versija: {APP_VERSION}")
