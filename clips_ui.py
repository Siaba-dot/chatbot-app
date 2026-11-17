"""Bendras video / nuotraukų įkėlimas ir filmavimas – naudojamas montažo ir Reels studijos puslapiuose.

prefix atskiria puslapių būsenas (session_state), kad perėjus į kitą puslapį įkelti failai
nedingtų ir nesimaišytų."""
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


def add_clip(prefix, clip_id, ext, data, name, kind):
    """Prideda video (įkeltą ar nufilmuotą) į sąrašą: išsaugo laikinai ir patikrina garsą."""
    clips = st.session_state.setdefault(prefix + "clips", [])
    skip = st.session_state.setdefault(prefix + "skip_clips", set())  # netinkami arba ranka pašalinti
    if clip_id in skip or any(c["id"] == clip_id for c in clips):
        return
    fd, path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(data())
    if kind == "rec":
        # Naršyklės įrašuose (ypač WebM) dažnai trūksta trukmės – perpakuojam į MKV be perkodavimo.
        mkv = path + ".mkv"
        if subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c", "copy", mkv]).returncode == 0:
            os.unlink(path)
            path = mkv
    with st.spinner(f"Tikrinu „{name}“…"):
        try:
            duration = video_editor.probe(path)["duration"]
            image = video_editor.is_image(path)
            state, an = ("none", None) if image else video_editor.audio_status(path)
        except Exception:
            os.unlink(path)
            skip.add(clip_id)
            st.error(f"„{name}“ nepavyko atidaryti. Įkelkite video (pvz. MP4, MOV) arba nuotrauką (JPG, PNG).")
            return
    clips.append({"id": clip_id, "path": path, "name": name, "kind": kind, "duration": duration,
                  "image": image,
                  "audio": state, "levels": an and {k: an[k] for k in ("noise", "loud")}})


def move_clip(prefix, i, step):
    clips = st.session_state[prefix + "clips"]
    if step == 0:
        c = clips.pop(i)
        st.session_state.setdefault(prefix + "skip_clips", set()).add(c["id"])  # kad nebūtų pridėtas iš naujo
        if os.path.exists(c["path"]):
            os.unlink(c["path"])
    else:
        clips[i], clips[i + step] = clips[i + step], clips[i]


def clip_segments(c):
    """Įrašo paliekamos dalys pagal apkarpymą: [(nuo, iki), ...] arba None (visas įrašas)."""
    if c.get("image"):
        return None
    a, b = c.get("trim") or (0.0, c["duration"])
    cut = c.get("cut")
    segs = [(a, b)]
    if cut and a < cut[0] < cut[1] < b:
        segs = [(a, cut[0]), (cut[1], b)]
    if len(segs) == 1 and a <= 0.01 and b >= c["duration"] - 0.01:
        return None
    return segs


def clip_length(c, image_duration):
    if c.get("image"):
        return image_duration
    segs = clip_segments(c)
    return sum(b - a for a, b in segs) if segs else c["duration"]


@st.cache_data(max_entries=300, show_spinner=False)
def _frame_at(path, t):
    """Mažas kadras (JPG) iš video ties t sekunde – apkarpymo vietoms parodyti."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", path, "-frames:v", "1",
                        "-vf", "scale=180:-2", "-q:v", "5", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
                       capture_output=True)
    return r.stdout or None


def _frames_strip(c, points):
    """Kadrų juostelė: [(užrašas, laikas)] – kiekvienas kadras su užrašu po juo."""
    strip = st.container(horizontal=True, wrap=True, gap="small")
    for label, t in points:
        img = _frame_at(c["path"], round(min(t, c["duration"] - 0.05), 1))
        tile = strip.container(width=84, gap=None)
        if img:
            tile.image(img, width="stretch")
        tile.caption(f"{label}  \n{t:.1f} s")


def _trim_controls(prefix, c, box):
    d = round(c["duration"], 1)
    if d < 1.0:
        return
    with box.expander("✂️ Apkarpyti"):
        t = st.slider("Palikti nuo – iki (s)", 0.0, d, tuple(c.get("trim") or (0.0, d)), 0.1,
                      key=f"{prefix}trim-{c['id']}")
        c["trim"] = (float(t[0]), float(t[1]))
        cut_on = st.checkbox("Išmesti dalį iš vidurio", value=bool(c.get("cut")), key=f"{prefix}cuton-{c['id']}")
        if cut_on and t[1] - t[0] > 0.6:
            lo, hi = float(t[0]), float(t[1])
            cur = c.get("cut") or (lo + (hi - lo) * 0.4, lo + (hi - lo) * 0.6)
            cur = (min(max(cur[0], lo), hi), min(max(cur[1], lo), hi))
            x = st.slider("Išmesti nuo – iki (s)", lo, hi, cur, 0.1, key=f"{prefix}cut-{c['id']}")
            c["cut"] = (float(x[0]), float(x[1])) if x[1] - x[0] >= 0.1 else None
        else:
            c["cut"] = None
        a, b = c["trim"]
        points = [("Pradžia", a)]
        if c["cut"]:
            points += [("✂️ Išmetama nuo", c["cut"][0]), ("✂️ Išmetama iki", c["cut"][1])]
        points.append(("Pabaiga", max(a, b - 0.1)))
        _frames_strip(c, points)
        st.caption(f"Liks {clip_length(c, 0):.1f} s iš {c['duration']:.1f} s.")
        if not c["path"].endswith(".mkv"):  # naršyklės įrašų (MKV) telefonai negroja
            st.video(c["path"], start_time=a, end_time=b, width=240)
            st.caption("▶ Grojama palikta dalis." + (" Išmetama vidurio dalis čia nepraleidžiama – ją matysite "
                                                    "greitoje peržiūroje." if c["cut"] else ""))


def clip_picker(prefix="", trim=False):
    """Įkėlimo / filmavimo laukas ir įrašų sąrašas su tvarkos keitimu (ir apkarpymu, jei trim=True).
    Grąžina (įrašai, kiek sekundžių rodyti nuotrauką)."""
    st.session_state.setdefault(prefix + "clips", [])
    source = st.radio("Video", ["📁 Įkelti video", "🎥 Filmuoti dabar"], horizontal=True,
                      label_visibility="collapsed", key=prefix + "source" if prefix else None)
    ids_key = prefix + "uploader_ids"
    if source.startswith("📁"):
        # Be failų tipų apribojimo: telefonuose (ypač iPhone) apribojimas neleidžia pasirinkti
        # video iš galerijos. Ar tai tikrai video, patikrinama po įkėlimo.
        files = st.file_uploader("Įkelkite video ar nuotraukas (galima kelis)", accept_multiple_files=True,
                                 key=prefix + "uploader" if prefix else None,
                                 help="Telefone galite pasirinkti kelis video ar nuotraukas iš galerijos iš karto. "
                                      "Nuotraukos rodomos po kelias sekundes.")
        current = {f.file_id for f in files}
        # Failą pašalinus iš įkėlimo lauko – pašalinam jį ir iš sąrašo.
        for i in [i for i, c in enumerate(st.session_state[prefix + "clips"])
                  if c["kind"] == "upload" and c["id"] in st.session_state.get(ids_key, set()) - current][::-1]:
            move_clip(prefix, i, 0)
        st.session_state[ids_key] = current
        for f in files:
            add_clip(prefix, f.file_id, os.path.splitext(f.name)[1].lower() or ".mp4", f.getvalue, f.name, "upload")
    else:
        st.session_state[ids_key] = set()  # įkėlimo laukas paslėptas – jo būsena išsivalo
        rec = video_recorder(key=prefix + "recorder", default=None)
        if rec and rec.get("data"):
            n = sum(c["kind"] == "rec" for c in st.session_state[prefix + "clips"]) + 1
            add_clip(prefix, f"rec-{rec['id']}", ".mp4" if "mp4" in (rec.get("mime") or "") else ".webm",
                     lambda: base64.b64decode(rec["data"]), f"Įrašas {n}", "rec")

    clips = st.session_state[prefix + "clips"]
    image_duration = video_editor.IMAGE_DURATION
    if any(c.get("image") for c in clips):
        image_duration = st.slider("Kiek sekundžių rodyti kiekvieną nuotrauką", 1.0, 10.0,
                                   video_editor.IMAGE_DURATION, 0.5,
                                   key=prefix + "image_duration" if prefix else None)
    if clips:
        st.markdown(f"**Video ({len(clips)}) – bus sujungti šia tvarka:**" if len(clips) > 1 else "**Video:**")
        for i, c in enumerate(clips):
            info = ("🖼️ nuotrauka" if c.get("image") else "🔈 balsas" if c["audio"] == "speech"
                    else "🔇 be garso" if c["audio"] == "none" else "🔈 balso neaptikta")
            # Horizontalus konteineris (ne stulpeliai) – telefone neišsidėsto į atskiras eilutes.
            box = st.container(border=True, gap=None) if trim else st
            row = box.container(horizontal=True, wrap=False, vertical_alignment="center", gap="small",
                                border=not trim)
            name = c["name"] if len(c["name"]) <= 18 else c["name"][:8] + "…" + c["name"][-7:]
            dur = clip_length(c, image_duration) if trim else image_duration if c.get("image") else c["duration"]
            label = row.empty()
            row.button("⬆️", key=f"{prefix}up-{c['id']}", disabled=i == 0, on_click=move_clip,
                       args=(prefix, i, -1), help="Perkelti aukščiau")
            row.button("⬇️", key=f"{prefix}down-{c['id']}", disabled=i == len(clips) - 1, on_click=move_clip,
                       args=(prefix, i, 1), help="Perkelti žemiau")
            row.button("✖️", key=f"{prefix}del-{c['id']}", on_click=move_clip, args=(prefix, i, 0),
                       help="Pašalinti")
            if trim and not c.get("image"):
                _trim_controls(prefix, c, box)
                dur = clip_length(c, image_duration)
            label.markdown(f"**{i + 1}.** {name}  \n{dur:.1f} s · {info}", width="stretch")
        if len(clips) > 1:
            total = sum(clip_length(c, image_duration) if trim else image_duration if c.get("image")
                        else c["duration"] for c in clips)
            st.caption(f"Bendra trukmė prieš montažą: {total:.1f} s")
        st.caption("➕ Galite pridėti daugiau video – įkelti iš albumo arba nufilmuoti.")
    return clips, image_duration


def configured_key():
    """OpenAI raktas iš Streamlit Secrets arba aplinkos kintamųjų."""
    try:
        return st.secrets["OPENAI_API_KEY"]
    except Exception:
        return os.environ.get("OPENAI_API_KEY")


def openai_client():
    """OpenAI klientas: raktas iš Secrets / aplinkos arba įvestas programoje (laikomas tik šioje sesijoje)."""
    import accounts
    if accounts.enabled():
        # Svetainė su klientais: naudojamas tik savininko raktas ir tik Premium / administratoriui.
        if not accounts.ai_allowed():
            return None
        key = configured_key()
    else:
        key = configured_key() or st.session_state.get("openai_key", "").strip()
    if not key:
        return None
    import openai
    return openai.OpenAI(api_key=key)
