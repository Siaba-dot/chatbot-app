import os
import tempfile

import streamlit as st

import video_editor

st.set_page_config(page_title="Video montažas", page_icon="🎬")
st.title("🎬 Automatinis video montažas")
st.write("Įkelkite video – programa pati iškirps pauzes ir tylą, sutvarkys formatą, "
         "garsą ir (jei norite) uždės modernius titrus.")


uploaded = st.file_uploader("Įkelkite video", type=["mp4", "mov", "m4v", "avi", "mkv", "webm"])

with st.expander("⚙️ Nustatymai", expanded=True):
    fmt_label = st.radio(
        "Formatas",
        ["Originalus", "Vertikalus 9:16 (TikTok, Reels, Shorts)", "Kvadratas 1:1", "Horizontalus 16:9"],
        horizontal=False)
    fmt = {"Originalus": "original", "Kvadratas 1:1": "1:1",
           "Horizontalus 16:9": "16:9"}.get(fmt_label, "9:16")

    remove_silence = st.checkbox("Iškirpti tylą ir pauzes", value=True)
    col1, col2 = st.columns(2)
    min_silence = col1.slider("Trumpiausia iškerpama pauzė (s)", 0.2, 2.0, 0.5, 0.1,
                              disabled=not remove_silence)
    noise_db = col2.slider("Tylos riba (dB)", -60, -20, -35, 1, disabled=not remove_silence,
                           help="Kuo didesnis skaičius, tuo daugiau garso laikoma tyla "
                                "(naudinga, jei fone triukšmas).")
    padding = st.slider("Palikti „oro“ aplink kalbą (s)", 0.0, 0.5, 0.15, 0.05,
                        disabled=not remove_silence)

    loudnorm = st.checkbox("Suvienodinti garsumą", value=True)
    fades = st.checkbox("Švelni pradžia ir pabaiga (fade)", value=True)

    subtitles = st.checkbox("Pridėti animuotus titrus")
    subtitle_text = ""
    if subtitles:
        subtitle_text = st.text_area(
            "Ką sakote video? (įklijuokite tekstą)",
            placeholder="Pvz.: Sveiki! Šiandien parodysiu, kaip greitai sumontuoti video.",
            help="Programa pati sulygins žodžius su kalba. Laikai apytiksliai – "
                 "kuo tiksliau tekstas atitinka tai, kas pasakyta, tuo geriau.")

if uploaded and st.button("🚀 Sumontuoti", type="primary"):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "input" + os.path.splitext(uploaded.name)[1].lower())
        dst = os.path.join(tmp, "sumontuota.mp4")
        with open(src, "wb") as f:
            f.write(uploaded.getbuffer())

        status = st.empty()
        bar = st.progress(0.0)
        try:
            res = video_editor.auto_edit(
                src, dst, fmt=fmt, remove_silence=remove_silence, noise_db=noise_db,
                min_silence=min_silence, padding=padding, loudnorm=loudnorm, fades=fades,
                subtitle_text=subtitle_text if subtitles else "",
                status=lambda m: status.info(m), progress=lambda p: bar.progress(p))
        except Exception as e:
            status.error(f"Nepavyko sumontuoti: {e}")
            st.stop()

        bar.progress(1.0)
        status.success("✅ Video sumontuotas!")
        with open(dst, "rb") as f:
            st.session_state["result"] = f.read()
        st.session_state["summary"] = res
        st.session_state["name"] = os.path.splitext(uploaded.name)[0] + "_sumontuota.mp4"

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
