"""Bendras video / nuotraukų įkėlimas ir filmavimas – naudojamas montažo ir Reels studijos puslapiuose.

prefix atskiria puslapių būsenas (session_state), kad perėjus į kitą puslapį įkelti failai
nedingtų ir nesimaišytų."""
import base64
import os
import shutil
import subprocess
import tempfile

import streamlit as st
import streamlit.components.v1 as components

import video_editor

# Filmavimas programoje: kamera + mikrofonas per naršyklę (components/recorder/index.html)
video_recorder = components.declare_component(
    "video_recorder", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "recorder"))
# Kadrų takelis apkarpymui: miniatiūros, tempiamos rankenėlės, „Skelti čia“ (components/timeline/index.html)
trim_timeline = components.declare_component(
    "trim_timeline", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "timeline"))


def add_clip(prefix, clip_id, ext, data, name, kind):
    """Prideda video (įkeltą ar nufilmuotą) į sąrašą: išsaugo laikinai ir patikrina garsą."""
    clips = st.session_state.setdefault(prefix + "clips", [])
    skip = st.session_state.setdefault(prefix + "skip_clips", set())  # netinkami arba ranka pašalinti
    if clip_id in skip or any(c["id"] == clip_id for c in clips):
        return
    fd, path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        if hasattr(data, "read"):  # įkeltas failas – rašom į diską dalimis, be papildomos kopijos atmintyje
            data.seek(0)
            shutil.copyfileobj(data, f, 1 << 20)
        else:
            f.write(data())
    if kind == "rec":
        # Naršyklės įrašuose (ypač WebM) dažnai trūksta trukmės – perpakuojam į MKV be perkodavimo.
        mkv = path + ".mkv"
        if subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c", "copy", mkv]).returncode == 0:
            os.unlink(path)
            path = mkv
    with st.spinner(f"Tikrinu „{name}“…"):
        try:
            try:
                info = video_editor.probe(path)
                if not info.get("duration"):
                    raise ValueError("nežinoma trukmė")
            except Exception:
                if kind != "rec":
                    raise
                # Kai kurių naršyklių (ypač iPhone Safari) įrašai – neįprastos struktūros: perkoduojam į MP4
                fixed = path + ".fixed.mp4"
                cmd = video_editor.limit_threads(
                    ["ffmpeg", "-y", "-loglevel", "error", "-fflags", "+genpts", "-i", path, "-vf", "format=yuv420p",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", fixed])
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    raise RuntimeError(r.stderr[-300:] or "nepavyko perkoduoti")
                os.unlink(path)
                path = fixed
                info = video_editor.probe(path)
            duration = info["duration"]
            image = video_editor.is_image(path)
            if not image and max(info["width"], info["height"]) > 1920:
                # 4K telefono video – darbinė 1080p kopija: Reels'ui pakanka, o serveriui reikia daug mažiau atminties
                with st.spinner(f"Optimizuoju „{name}“ (4K → 1080p)…"):
                    small = path + ".1080.mp4"
                    w, h = info["width"], info["height"]
                    scale = "scale=-2:1920" if h >= w else "scale=1920:-2"
                    cmd = video_editor.limit_threads(
                        ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", scale + ",format=yuv420p",
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
                         "-map_metadata", "0", small])
                    if subprocess.run(cmd).returncode == 0:
                        os.unlink(path)
                        path = small
                        duration = video_editor.probe(path)["duration"]
            state, an = ("none", None) if image else video_editor.audio_status(path)
        except Exception as e:
            if os.path.exists(path):
                os.unlink(path)
            skip.add(clip_id)
            st.session_state[prefix + "last_error"] = (clip_id, f"„{name}“ nepavyko atidaryti ({e})".strip())
            st.error(f"„{name}“ nepavyko atidaryti. Įkelkite video (pvz. MP4, MOV) arba nuotrauką (JPG, PNG)."
                     + (f" Priežastis: {str(e)[:200]}" if kind == "rec" else ""))
            return
    clips.append({"id": clip_id, "path": path, "name": name, "kind": kind, "duration": duration,
                  "image": image,
                  "audio": state, "levels": an and {k: an[k] for k in ("noise", "loud")}})


def clear_clips(prefix):
    """Pašalina visus įrašus (pvz. nebereikalingą nufilmuotą medžiagą)."""
    clips = st.session_state.get(prefix + "clips", [])
    for i in range(len(clips) - 1, -1, -1):
        move_clip(prefix, i, 0)
    st.session_state.pop(prefix + "rec_status", None)


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
    if c.get("segments"):  # kadrų takelis: bet kiek dalių
        segs = [(float(a), float(b)) for a, b in c["segments"] if b - a >= 0.1]
        if not segs or (len(segs) == 1 and segs[0][0] <= 0.01 and segs[0][1] >= c["duration"] - 0.01):
            return None
        return segs
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


@st.cache_data(max_entries=40, show_spinner=False)
def _filmstrip(path, duration, n=14, height=200):
    """Kadrų miniatiūros takeliui (data URL sąrašas), tolygiai per visą įrašą."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf",
                        f"fps={n / max(0.5, duration):.5f},scale=-2:{height}", "-frames:v", str(n),
                        "-q:v", "6", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"], capture_output=True)
    data, out, i = r.stdout, [], 0
    while True:  # JPEG kadrai vienas po kito: FFD8 … FFD9
        a = data.find(b"\xff\xd8", i)
        if a < 0:
            break
        b = data.find(b"\xff\xd9", a)
        if b < 0:
            break
        out.append("data:image/jpeg;base64," + base64.b64encode(data[a:b + 2]).decode())
        i = b + 2
    return out


def _trim_controls(prefix, c, box):
    d = round(c["duration"], 1)
    if d < 1.0:
        return
    with box.expander("✂️ Apkarpyti – kadrų takelis"):
        thumbs = _filmstrip(c["path"], c["duration"])
        segs = c.get("segments") or [list(x) for x in (clip_segments(c) or [(0.0, c["duration"])])]
        val = trim_timeline(duration=float(c["duration"]), segments=[list(x) for x in segs], thumbs=thumbs,
                            key=f"{prefix}tl-{c['id']}", default=None)
        if val and val.get("segments") and val.get("t") != c.get("seg_t"):
            c["segments"] = [list(x) for x in val["segments"]]
            c["seg_t"] = val.get("t")
            c.pop("trim", None)
            c.pop("cut", None)
            st.rerun()  # perskaičiuoja trukmes ir peržiūrą


def _recorder(prefix):
    """Filmavimas programoje. Įrašas siunčiamas dalimis (po 256 KB): didesnės komponento žinutės (>~512 KB) nepereina.
    Veikia kaip fragmentas – kiekviena dalis perpiešia tik šį langą (greita); gavus visą įrašą – visas puslapis."""
    @st.fragment
    def frag():
        key = prefix + "recorder"
        rec = st.session_state.get(key)
        up = st.session_state.setdefault(prefix + "rec_up", {})  # gaunami įrašai: id -> {path, next, total, mime}
        status = st.session_state.get(prefix + "rec_status")
        if rec and rec.get("data") is not None and "idx" in rec:
            rid, idx, total = rec["id"], int(rec["idx"]), max(1, int(rec["total"]))
            u = up.get(rid)
            if u is None and idx == 0:
                fd, path = tempfile.mkstemp(suffix=".part")
                os.close(fd)
                u = up[rid] = {"path": path, "next": 0, "total": total, "mime": rec.get("mime") or ""}
            if u and idx == u["next"]:
                with open(u["path"], "ab") as f:
                    f.write(base64.b64decode(rec["data"]))
                u["next"] += 1
                status = {"id": rid, "got": idx, "total": total}
                if u["next"] >= total:  # visas įrašas gautas – tikrinam ir pridedam
                    cid = f"rec-{rid}"
                    n = sum(c["kind"] == "rec" for c in st.session_state[prefix + "clips"]) + 1
                    try:
                        with open(u["path"], "rb") as fh:
                            add_clip(prefix, cid, ".mp4" if "mp4" in u["mime"] else ".webm", fh, f"Įrašas {n}", "rec")
                    except Exception as e:
                        st.session_state.setdefault(prefix + "skip_clips", set()).add(cid)
                        st.session_state[prefix + "last_error"] = (cid, f"Įrašo nepavyko priimti ({e})")
                    finally:
                        if os.path.exists(u["path"]):
                            os.unlink(u["path"])
                        up.pop(rid, None)
                    ok = any(c["id"] == cid for c in st.session_state[prefix + "clips"])
                    err = st.session_state.get(prefix + "last_error") or (None, "")
                    status = {"id": rid, "ok": ok,
                              "msg": "" if ok else (err[1] if err[0] == cid else "Įrašas nepriimtas.")}
                    st.session_state[prefix + "rec_status"] = status
                    if ok:
                        st.rerun(scope="app")  # visas puslapis – kad įrašas atsirastų sąraše ir peržiūroje
            elif u:  # pakartotinai atsiųsta dalis – patvirtinam dar kartą
                status = {"id": rid, "got": u["next"] - 1, "total": total}
        video_recorder(key=key, default=None, status=status, script=st.session_state.get(prefix + "script", ""))
    frag()


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
        upk = st.session_state.setdefault(prefix + "upk", 0)
        files = st.file_uploader("Įkelkite video ar nuotraukas (galima kelis)", accept_multiple_files=True,
                                 key=f"{prefix}uploader{upk}" if prefix else None,
                                 help="Telefone galite pasirinkti kelis video ar nuotraukas iš galerijos iš karto. "
                                      "Nuotraukos rodomos po kelias sekundes.")
        current = {f.file_id for f in files}
        # Failą pašalinus iš įkėlimo lauko – pašalinam jį ir iš sąrašo.
        for i in [i for i, c in enumerate(st.session_state[prefix + "clips"])
                  if c["kind"] == "upload" and c["id"] in st.session_state.get(ids_key, set()) - current][::-1]:
            move_clip(prefix, i, 0)
        st.session_state[ids_key] = current
        for f in files:
            add_clip(prefix, f.file_id, os.path.splitext(f.name)[1].lower() or ".mp4", f, f.name, "upload")
        if prefix and files:
            # Failai jau diske: išvalom įkėlimo lauką, kad Streamlit nebelaikytų jų atmintyje
            # (įrašai lieka sąraše žemiau, juos šalinti – ✖).
            st.session_state[prefix + "upk"] = upk + 1
            st.session_state[ids_key] = set()
            st.rerun()
    else:
        st.session_state[ids_key] = set()  # įkėlimo laukas paslėptas – jo būsena išsivalo
        _recorder(prefix)
        st.caption("📱 Telefone galite filmuoti ir įprasta kamera: pasirinkite „📁 Įkelti video“ → "
                   "„Filmuoti video“ (iPhone) ar „Kamera“ (Android) – kokybė būna geresnė.")

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
        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        c1.caption("➕ Galite pridėti daugiau video – įkelti iš albumo arba nufilmuoti.")
        c2.button("🗑 Išvalyti viską", key=prefix + "clear_all", on_click=clear_clips, args=(prefix,),
                  width="stretch", help="Pašalinti visus įrašus ir pradėti iš naujo")
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
