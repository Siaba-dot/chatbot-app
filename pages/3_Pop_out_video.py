import io
import os
import tempfile

import streamlit as st
from PIL import Image, ImageOps

import popout

st.set_page_config(page_title="Pop-out video", page_icon="📱")
st.title("📱 Ranka išlenda iš nuotraukos")
st.write("Įkelkite nuotrauką, kurioje žmogus laiko telefoną su **žaliu ekranu**. Programa įdės jūsų "
         "ekraną, o ranka su telefonu išlįs iš nuotraukos ir uždengs komentarus po ja.")


def secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name)


fal_key = secret("FAL_KEY")

photo_file = st.file_uploader("Nuotrauka su žaliu telefono ekranu",
                              help="Tinka ir AI sugeneruota nuotrauka. Telefono ekranas turi būti ryškiai žalias.")
photo_bytes = photo_file.getvalue() if photo_file else None
if photo_bytes:
    try:
        st.image(ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes))), width=260)
    except Exception:
        st.error("Šio failo nepavyko atidaryti kaip nuotraukos.")
        photo_bytes = None

st.subheader("Telefono ekranas")
screen_mode = st.radio("Ekranas", ["Sukurti pagal tekstą", "Įkelti savo paveikslėlį"], horizontal=True,
                       label_visibility="collapsed")
if screen_mode == "Įkelti savo paveikslėlį":
    screen_file = st.file_uploader("Ekrano paveikslėlis (vertikalus, pvz. ekrano kopija)", key="screen")
    screen = Image.open(screen_file) if screen_file else None
else:
    c1, c2 = st.columns(2)
    title = c1.text_input("Antraštė", "Automatizacijos")
    status = c2.text_input("Būsena", "Veikia 24/7")
    items = st.text_area("Pranešimai (po vieną eilutėje, iki 4)",
                         "Užklausa gauta\nAtsakymas išsiųstas\nSąskaita sukurta\nĮrašyta į CRM")
    c1, c2, c3 = st.columns(3)
    big_label = c1.text_input("Rezultato užrašas", "Šią savaitę sutaupyta")
    big_value = c2.text_input("Rezultatas", "12 val.")
    big_note = c3.text_input("Paaiškinimas", "≈ 1,5 darbo dienos")
    screen = popout.render_screen(title, status, [i for i in items.splitlines() if i.strip()][:4],
                                  big_label, big_value, big_note)
if screen is not None:
    with st.expander("Ekrano peržiūra"):
        st.image(screen, width=200)

st.subheader("Komentarai po nuotrauka")
c1, c2 = st.columns(2)
reactions = c1.text_input("Reakcijų skaičius", "247")
comment_count = c2.text_input("Komentarų užrašas", "18 komentarų")
comments_text = st.text_area(
    "Komentarai: tekstas | laikas | laikų skaičius (po vieną eilutėje)",
    "\n".join(" | ".join(c) for c in popout.DEFAULT_COMMENTS),
    help="Vardai rodomi anonimiškai – tik raidė ir pilka juostelė.")
comments = []
for line in comments_text.splitlines():
    parts = [p.strip() for p in line.split("|")] + ["", ""]
    if parts[0]:
        comments.append((parts[0], parts[1], parts[2]))

st.subheader("Video")
mode = st.radio("Kaip sukurti video?", [
    "AI video pagal užklausą (natūralus rankos judesys)",
    "Be AI – animuoti nuotrauką",
    "Turiu savo video – uždėti efektą"])
prompt, duration, own_video = None, "5", None
if mode.startswith("AI"):
    if not fal_key:
        st.warning("AI video reikia fal.ai rakto: Streamlit nustatymuose (Secrets) įrašykite "
                   "`FAL_KEY = \"...\"`. Raktą gausite fal.ai → Dashboard → Keys.")
    prompt = st.text_area("Užklausa (angliškai veikia geriausiai)", popout.DEFAULT_PROMPT, height=120)
    duration = st.radio("Trukmė", ["5", "10"], horizontal=True, format_func=lambda s: f"{s} s")
    st.caption("Užklausoje palikite „the phone screen stays bright green“ – tada ekraną galima pakeisti "
               "kiekviename kadre.")
elif mode.startswith("Turiu"):
    own_video = st.file_uploader("Video su žaliu telefono ekranu", key="own_video")

ready = photo_bytes and screen is not None and (not mode.startswith("AI") or fal_key) \
    and (not mode.startswith("Turiu") or own_video)
if st.button("🚀 Sukurti", type="primary", width="stretch", disabled=not ready):
    photo = ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes))).convert("RGB")
    status_box, bar = st.empty(), st.progress(0.0)
    with tempfile.TemporaryDirectory() as tmp:
        png, mp4 = os.path.join(tmp, "popout.png"), os.path.join(tmp, "popout.mp4")
        try:
            status_box.info("Kuriu nuotrauką…")
            popout.make_from_photo(photo, screen, comments, reactions, comment_count, still_path=png)
            if mode.startswith("Be AI"):
                status_box.info("Kuriu animaciją…")
                popout.make_from_photo(photo, screen, comments, reactions, comment_count,
                                       video_path=mp4, progress=bar.progress)
            else:
                src = os.path.join(tmp, "src.mp4")
                if own_video:
                    with open(src, "wb") as f:
                        f.write(own_video.getvalue())
                else:
                    buf = io.BytesIO()
                    photo.save(buf, "PNG")
                    data = popout.generate_ai_video(
                        buf.getvalue(), prompt, fal_key, duration,
                        status=lambda s, t: status_box.info(f"AI kuria video… ({s}, {int(t)} s). "
                                                            "Tai gali užtrukti kelias minutes."))
                    with open(src, "wb") as f:
                        f.write(data)
                    st.session_state["popout_ai_raw"] = data
                status_box.info("Dedu ekraną ir ranką ant komentarų kiekviename kadre…")
                popout.make_from_video(src, screen, comments, mp4, reactions, comment_count,
                                       progress=bar.progress)
        except popout.NoGreenScreen as e:
            status_box.error(f"{e} Patikrinkite, ar telefono ekranas ryškiai žalias ir gerai matomas.")
            st.stop()
        except Exception as e:
            status_box.error(f"Nepavyko: {e}")
            st.stop()
        bar.progress(1.0)
        status_box.success("✅ Paruošta!")
        with open(png, "rb") as f:
            st.session_state["popout_png"] = f.read()
        with open(mp4, "rb") as f:
            st.session_state["popout_mp4"] = f.read()

if "popout_mp4" in st.session_state:
    st.video(st.session_state["popout_mp4"])
    st.download_button("⬇️ Atsisiųsti video", st.session_state["popout_mp4"], file_name="popout.mp4",
                       mime="video/mp4")
    st.image(st.session_state["popout_png"])
    st.download_button("⬇️ Atsisiųsti nuotrauką", st.session_state["popout_png"], file_name="popout.png",
                       mime="image/png")
    if "popout_ai_raw" in st.session_state:
        st.download_button("⬇️ Originalus AI video (be efekto)", st.session_state["popout_ai_raw"],
                           file_name="ai_video.mp4", mime="video/mp4")
