"""Reels studijos video variklis BE Streamlit – naudojamas API serverio (api/server.py) ir būsimos svetainės.

Visa logika ta pati kaip studijoje (video_editor, reels_studio, animations, fxpack); čia ji tik surinkta į
paprastas funkcijas, kurioms paduodamas nustatymų žodynas:

    clip = engine.add_clip(path)                       # patikrina, sumažina 4K, nustato garsą
    prep = engine.prepare([clip, ...], settings, workdir, client)   # sujungia, iškerpa pauzes, titrai
    res  = engine.build(prep, settings, "out.mp4", workdir, client) # montažas + apdaila
    cap  = engine.caption(prep, settings, client)      # aprašymas ir grotažymės

client – openai.OpenAI arba None (be AI veikia taisyklės).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

import animations
import fxpack
import reels_studio
import video_editor

FORMATS = {"9:16": "9:16 · Reels, TikTok, Shorts", "16:9": "16:9 · YouTube", "1:1": "1:1 · Kvadratas",
           "4:5": "4:5 · Instagram įrašas"}
SUBTITLE_LANGUAGES = {"lt": "Lietuvių", "en": "English", "ru": "Русский", "pl": "Polski", "de": "Deutsch"}

DEFAULTS = {
    "format": "9:16",
    "template": "Baltijos gintaras",
    "accent": None,            # None – pagal šabloną
    "color": None,             # None – pagal šabloną
    "effects": ["Lėtas priartėjimas"],
    "transition": "Be perėjimo",
    "fit": "fill",             # kitokios orientacijos įrašai: fill – užpildo kadrą (apkarpo), blur – su sulietu fonu
    "look": "modern",          # titrų stilius (video_editor.SUBTITLE_LOOKS)
    "subs_pos": "Žemiau",      # reels_studio.SUBTITLE_POSITIONS
    "subs_size": 100,
    "hook": "",
    "hook_pos": "Aukščiau",    # reels_studio.HOOK_POSITIONS
    "hook_duration": 3.0,
    "text_size": 100,
    "cta": "",
    "handle": "",
    "subtitles": True,
    "subtitle_language": "lt",
    "subtitle_text": "",       # jei žinomas tekstas (sufleris) – titrai pagal jį
    "remove_silence": True,
    "denoise": True,
    "key_words": True,
    "punch": True,
    "bubbles": False,
    "anims": {"stickers": False, "marks": False, "cards": False, "phone": False, "fx": False,
              "intro": False, "outro": False},
    "gfx_kinds": [],
    "music": None,             # pavadinimas iš music_library() arba None
    "music_volume": 25,
    "ducking": True,
    "length": "Be ribos",      # reels_studio.LENGTHS
    "speed": 1.0,
    "progress_bar": "Viršuje",
    "image_duration": video_editor.IMAGE_DURATION,
    "moment_at": None,         # „Gintaro akimirka“ – sekundė galutiniame video
    "category": "Prabanga",
    "all_formats": True,       # kuriant galutinį video – kartu dar 2 formatai (9:16, 16:9, 4:5)
    # 🎙 AI įgarsinimas (OpenAI balsas): tekstas skaitomas vietoj / šalia jūsų balso
    "voiceover": {"on": False, "text": "", "voice": "g:Kore"},  # numatytas – natūralus lietuviškas Google balsas
    "clip_gain": 20,           # originalaus garso garsumas, kai yra įgarsinimas (%)
}

VOICES = {"coral": "Koralas – šilta moteris", "nova": "Nova – žvali moteris", "shimmer": "Šimeris – švelni moteris",
          "sage": "Sage – rami moteris", "alloy": "Alloy – neutralus", "ash": "Ash – ramus vyras",
          "echo": "Echo – gilus vyras", "onyx": "Onyx – žemas vyras", "fable": "Fable – pasakotojas"}
# 🇱🇹 Google Gemini balsai (ta pati technologija kaip NotebookLM) – natūralus lietuviškas tarimas.
GEMINI_VOICES = {"g:Kore": "Kore – tvirta, užtikrinta moteris", "g:Aoede": "Aoede – lengva, gyva moteris",
                 "g:Leda": "Leda – jaunatviška moteris", "g:Sulafat": "Sulafat – šilta moteris",
                 "g:Achernar": "Achernar – švelni moteris", "g:Zephyr": "Zephyr – šviesi moteris",
                 "g:Charon": "Charon – informatyvus vyras", "g:Puck": "Puck – linksmas vyras",
                 "g:Orus": "Orus – tvirtas vyras", "g:Fenrir": "Fenrir – energingas vyras",
                 "g:Iapetus": "Iapetus – aiškus vyras", "g:Algieba": "Algieba – ramus vyras"}
GEMINI_TTS_MODELS = ("gemini-3.8-flash-tts", "gemini-2.5-flash-tts", "gemini-2.5-flash-preview-tts",
                     "gemini-2.5-pro-preview-tts")
TTS_VERSION = "3"  # pakeitus įgarsinimo būdą – seni įgarsinimai sukuriami iš naujo (3 – išvalyta pabaiga)
TTS_INSTRUCTIONS = ("Speak in natural, fluent {lang} with correct pronunciation and stress. Warm, confident, "
                    "energetic social-media tone, clear diction, natural pauses at punctuation.")


def settings_with_defaults(settings):
    s = dict(DEFAULTS)
    s.update({k: v for k, v in (settings or {}).items() if k in DEFAULTS and v is not None})
    s["anims"] = dict(DEFAULTS["anims"], **(settings or {}).get("anims", {}) or {})
    s["voiceover"] = dict(DEFAULTS["voiceover"], **(settings or {}).get("voiceover", {}) or {})
    if s["voiceover"]["voice"] not in VOICES and s["voiceover"]["voice"] not in GEMINI_VOICES:
        s["voiceover"]["voice"] = "coral"
    s["voiceover"]["text"] = str(s["voiceover"]["text"])[:4000]
    tpl = reels_studio.TEMPLATES.get(s["template"]) or reels_studio.TEMPLATES[DEFAULTS["template"]]
    if s["template"] not in reels_studio.TEMPLATES:
        s["template"] = DEFAULTS["template"]
    s["accent"] = s["accent"] if s["accent"] in reels_studio.ACCENTS or str(s["accent"]).startswith("#") \
        else tpl["accent"]
    s["color"] = s["color"] if s["color"] in reels_studio.COLOR_FILTERS else tpl["color"]
    s["effects"] = [e for e in s["effects"] if e in reels_studio.EFFECTS]
    s["gfx_kinds"] = [k for k in s["gfx_kinds"] if k in fxpack.KINDS]
    if s["look"] not in video_editor.SUBTITLE_LOOKS:
        s["look"] = "modern"
    if s["format"] not in FORMATS:
        s["format"] = "9:16"
    if s["fit"] not in ("fill", "blur"):
        s["fit"] = "fill"
    if s["transition"] not in video_editor.TRANSITIONS:
        s["transition"] = DEFAULTS["transition"]
    s["speed"] = max(0.5, min(2.0, float(s["speed"])))
    return s


def options():
    """Visi pasirinkimai svetainei (šablonai, filtrai, efektai, titrų stiliai, muzika…)."""
    return {
        "formats": FORMATS,
        "fits": {"fill": "Užpildyti kadrą", "blur": "Visas vaizdas + sulietas fonas"},
        "templates": {k: {"category": v.get("cat"), "accent": v["accent"], "color": v["color"], "kind": v["kind"],
                          "look": v.get("look"), "effects": v.get("effects")}
                      for k, v in reels_studio.TEMPLATES.items()},
        "template_categories": list(reels_studio.TEMPLATE_CATEGORIES),
        "accents": {k: "#" + v[0] for k, v in reels_studio.ACCENTS.items()},
        "colors": list(reels_studio.COLOR_FILTERS),
        "effects": reels_studio.EFFECTS,
        "transitions": list(video_editor.TRANSITIONS),
        "subtitle_looks": {k: v["title"] for k, v in video_editor.SUBTITLE_LOOKS.items()},
        "subtitle_positions": list(reels_studio.SUBTITLE_POSITIONS),
        "hook_positions": list(reels_studio.HOOK_POSITIONS),
        "subtitle_languages": SUBTITLE_LANGUAGES,
        "lengths": list(reels_studio.LENGTHS),
        "music": {k: v["desc"] for k, v in reels_studio.music_library().items()},
        "voices": VOICES,
        "gemini_voices": GEMINI_VOICES,
        "broll_modes": BROLL_MODES,
        "stickers": animations.STICKERS, "marks": animations.MARKS, "fx": animations.FX,
        "gfx": {k: v if isinstance(v, str) else v.get("title", k) for k, v in fxpack.KINDS.items()},
        "defaults": DEFAULTS,
    }


# ---------- medžiaga ----------
def _ffmpeg(args):
    return subprocess.run(video_editor.limit_threads(["ffmpeg", "-y", "-loglevel", "error"] + args),
                          capture_output=True, text=True)


def _video_frames(path, limit=3):
    """Kiek pirmųjų vaizdo kadrų pavyksta IŠKODUOTI (0 – vaizdo nėra arba jo neperskaitom). Tikrinama dekoduojant,
    nes naršyklių (ypač iPhone) įrašų antraštėse kadrų skaičiaus dažnai nėra."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:v:0", "-frames:v", str(limit),
                        "-vf", "scale=16:16,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    return len(r.stdout) // 256


def _streams_info(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,"
                        "r_frame_rate,nb_frames:format=format_name,duration", "-of", "compact", path],
                       capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()[:600]


def add_clip(path, name=None, recorded=False):
    """Patikrina įkeltą / nufilmuotą failą. Grąžina klipo žodyną (kaip studijoje) arba kelia ValueError."""
    original = path
    if recorded:  # naršyklės įrašuose dažnai trūksta trukmės – perpakuojam (jei vaizdas po to lieka)
        mkv = path + ".mkv"
        if _ffmpeg(["-i", path, "-c", "copy", mkv]).returncode == 0 and _video_frames(mkv) > 0:
            path = mkv
        elif os.path.exists(mkv):
            os.unlink(mkv)
    try:
        info = video_editor.probe(path)
        if not info.get("duration"):
            raise ValueError("nežinoma trukmė")
    except Exception:
        if not recorded:
            raise ValueError("Failo nepavyko atidaryti – įkelkite video (MP4, MOV) arba nuotrauką (JPG, PNG).")
        fixed = path + ".fixed.mp4"
        r = _ffmpeg(["-fflags", "+genpts", "-i", path, "-vf", "format=yuv420p", "-c:v", "libx264", "-preset",
                     "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", fixed])
        if r.returncode != 0:
            raise ValueError("Įrašo nepavyko perskaityti: " + (r.stderr[-200:] or "nežinoma klaida"))
        os.unlink(path)
        path = fixed
        try:
            info = video_editor.probe(path)
        except Exception:
            import sys
            print("Įrašas be vaizdo:", _streams_info(path), file=sys.stderr)
            os.unlink(path)
            raise ValueError("Įraše nėra vaizdo (juodas ekranas). Patikrinkite, ar naršyklei leista naudoti kamerą, "
                             "ir nufilmuokite dar kartą.")
    image = video_editor.is_image(path)
    duration = info["duration"]
    if not image and _video_frames(path) == 0 and recorded and os.path.exists(original):
        # perkoduojam iš originalo – kai kurie telefonai įrašo neįprastos struktūros failus
        fixed = original + ".fixed.mp4"
        _ffmpeg(["-fflags", "+genpts", "-i", original, "-map", "0:v:0?", "-map", "0:a:0?", "-vf", "format=yuv420p",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", fixed])
        if os.path.exists(fixed) and _video_frames(fixed) > 0:
            if path != original and os.path.exists(path):
                os.unlink(path)
            path = fixed
            info = video_editor.probe(path)
            duration = info["duration"]
    if not image and _video_frames(path) == 0:
        import sys
        print("Įrašas be vaizdo:", _streams_info(original if os.path.exists(original) else path), file=sys.stderr)
        for f in {path, original}:
            if os.path.exists(f):
                os.unlink(f)
        raise ValueError("Įraše nėra vaizdo (juodas ekranas). Patikrinkite, ar naršyklei leista naudoti kamerą, "
                         "ir nufilmuokite dar kartą.")
    if path != original and os.path.exists(original):
        os.unlink(original)
    if not image and max(info["width"], info["height"]) > 1920:  # 4K → 1080p darbinė kopija
        small = path + ".1080.mp4"
        scale = "scale=-2:1920" if info["height"] >= info["width"] else "scale=1920:-2"
        if _ffmpeg(["-i", path, "-vf", scale + ",format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-map_metadata", "0", small]).returncode == 0:
            os.unlink(path)
            path = small
            duration = video_editor.probe(path)["duration"]
    state, an = ("none", None) if image else video_editor.audio_status(path)
    return {"path": path, "name": name or os.path.basename(path), "duration": duration, "image": image,
            "audio": state, "levels": an and {k: an[k] for k in ("noise", "loud")},
            "width": info.get("width"), "height": info.get("height")}


def _segments(c):
    if c.get("image"):
        return None
    a, b = c.get("trim") or (0.0, c["duration"])
    if a <= 0.01 and b >= c["duration"] - 0.01:
        return None
    return [(float(a), float(b))]


def tts_gemini(key, text, voice, out_path, language="lt"):
    """Google Gemini balsas: tekstas -> MP3. Bandomi keli TTS modeliai (naujausias pirmas)."""
    import base64
    import urllib.error
    import urllib.request
    lang = video_editor.LANGUAGES.get(language, "Lithuanian")
    body = json.dumps({
        # tik tekstas – Google TTS bet kokius nurodymus perskaito garsiai (kalbą atpažįsta pats)
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {
                                 "voiceName": voice.removeprefix("g:")}}}}}).encode()
    last = None
    for model in GEMINI_TTS_MODELS:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                j = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = f"{model}: {e.code} {e.read()[:200]!r}"
            if e.code in (401, 403):
                raise RuntimeError("Google (Gemini) raktas neveikia – patikrinkite jį „Mano projektuose“.")
            continue  # 404 – modelio nėra, bandom kitą
        parts = (((j.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        data = next((p["inlineData"] for p in parts if p.get("inlineData", {}).get("data")), None)
        if not data:
            last = f"{model}: be garso"
            continue
        rate = 24000
        m = re.search(r"rate=(\d+)", data.get("mimeType", ""))
        if m:
            rate = int(m.group(1))
        raw = out_path + ".pcm"
        with open(raw, "wb") as f:
            f.write(base64.b64decode(data["data"]))
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", raw,
                            "-c:a", "libmp3lame", "-b:a", "160k", out_path], capture_output=True, text=True)
        os.unlink(raw)
        if r.returncode != 0:
            raise RuntimeError("Nepavyko paruošti Google įgarsinimo: " + r.stderr[-200:])
        return out_path
    raise RuntimeError("Google įgarsinimas nepavyko (" + str(last)[:200] + ")")


# ---------- 🎬 Google Veo: AI sukurti video intarpai ----------
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
VEO_FALLBACK = ("veo-3.1-lite-generate-preview", "veo-3.1-fast-generate-preview", "veo-3.0-fast-generate-001",
                "veo-3.1-generate-preview", "veo-3.0-generate-001", "veo-2.0-generate-001")
VEO_SECONDS = 4  # intarpas rodomas 2,5–4 s – mokam tik už tiek (Google ima mokestį už sekundę)
VEO_STYLE = ("{prompt}. Cinematic, realistic, high quality, natural light, smooth camera movement, "
             "no text, no captions, no watermark, no logos.")


def _gapi(key, url, body=None, timeout=60):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url if url.startswith("http") else GEMINI_API + url,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code}: {e.read()[:300].decode(errors='ignore')}")


def gemini_models(key):
    """Visi šiam raktui prieinami Gemini API modeliai: [{"name", "methods"}]."""
    out, token = [], ""
    for _ in range(10):
        j = _gapi(key, "/models?pageSize=200" + (f"&pageToken={token}" if token else ""))
        out += [{"name": m["name"].split("/", 1)[1], "methods": m.get("supportedGenerationMethods") or [],
                 "title": m.get("displayName", "")} for m in j.get("models", [])]
        token = j.get("nextPageToken")
        if not token:
            break
    return out


VEO_DIAG = {"seen": [], "error": None, "omni": [], "listed": False}  # ką Google siūlo (rodoma klaidos pranešime)


def veo_models(key):
    """Video modeliai, kuriuos leidžia šis raktas: visi su „predictLongRunning“ (taip kuriami video) ir/ar
    „veo“ / „video“ / „omni“ pavadinime. Pigiausi ir naujausi – pirmi; nepavykus – žinomų sąrašas."""
    try:
        models = gemini_models(key)
        video_like = [m for m in models if "predictLongRunning" in m["methods"]
                      or re.search(r"veo|video|omni", m["name"] + " " + m["title"], re.I)]
        omni = [m["name"] for m in models if "omni" in m["name"].lower()]
        ver2 = lambda n: [int(x) for x in re.findall(r"\d+", n)] or [0]  # noqa: E731
        VEO_DIAG.update(seen=[f"{m['name']} ({', '.join(m['methods']) or '–'})" for m in video_like], error=None,
                        omni=sorted(omni, key=lambda n: ("flash" not in n, [-v for v in ver2(n)], "preview" in n)),
                        listed=True)
        names = [m["name"] for m in video_like if "predictLongRunning" in m["methods"]]
        if not names and omni:
            return []  # senų Veo modelių nebėra – video kuriamas per Gemini Omni
        if names:
            ver = lambda n: [int(x) for x in re.findall(r"\d+", n.split("-generate")[0])] or [0]  # noqa: E731
            tier = lambda n: 0 if "lite" in n else 1 if "fast" in n else 2  # noqa: E731 – pigiausi pirmi
            return sorted(names, key=lambda n: (tier(n), [-v for v in ver(n)], "preview" in n))
    except Exception as e:
        VEO_DIAG.update(seen=[], error=str(e)[:200])
    return list(VEO_FALLBACK)


OMNI_FALLBACK = ("gemini-omni-flash-preview", "gemini-omni-1.1-flash-preview", "gemini-omni-1.1-flash")


def _save_b64_or_uri(key, item, out_path):
    import base64
    import urllib.request
    if item.get("data"):
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(item["data"]))
        return out_path
    uri = item.get("uri")
    if not uri:
        raise RuntimeError("Google atsakyme nėra video")
    req = urllib.request.Request(uri, headers={"x-goog-api-key": key})
    tmp = out_path + ".part"
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    os.replace(tmp, out_path)
    return out_path


def _omni_wait(key, it, background, say, timeout):
    import time as _t
    say("Google kuria video kadrą (1–3 min.)…")
    t0 = _t.time()
    while background and it.get("status") not in ("completed", "failed", "cancelled"):
        if _t.time() - t0 > timeout:
            raise RuntimeError("Google neatsakė per 7 min. – pabandykite dar kartą.")
        _t.sleep(8)
        it = _gapi(key, f"/interactions/{it['id']}")
    if it.get("status") in ("failed", "cancelled"):
        import sys
        print("Omni nepavyko:", json.dumps(it, ensure_ascii=False)[:2000], file=sys.stderr)
        raise OmniFailed(_omni_reason(it))
    return it


class OmniFailed(RuntimeError):
    pass


def _omni_reason(it):
    """Kodėl Google nesukūrė video – visi „message“ / „reason“ laukai iš atsakymo."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("message", "reason", "finish_reason", "finishReason", "block_reason", "status_message") \
                        and isinstance(v, str) and v not in found and v not in ("failed", "completed"):
                    found.append(v)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk({k: v for k, v in it.items() if k not in ("steps",)})
    walk([st for st in it.get("steps") or [] if st.get("type") != "user_input"])
    return "; ".join(found)[:300] or "Google priežasties nenurodė"


def omni_generate(key, prompt, aspect, out_path, status=None, timeout=420, hq=False):
    """AI video kadras per Gemini Omni Flash (Interactions API). Bandomi keli užklausos variantai (Google pavyzdžio
    forma, trukmė 4 s → numatyta), kol vienas pavyksta; nepavykę bandymai Google neapmokestinami."""
    say = status or (lambda m: None)
    models = VEO_DIAG.get("omni") or list(OMNI_FALLBACK)
    text = VEO_STYLE.format(prompt=prompt.strip().rstrip("."))
    ar = aspect if aspect in ("9:16", "16:9") else "9:16"
    parts = [{"type": "text", "text": text}]
    task = {"video_config": {"task": "text_to_video"}}
    variants = [  # (įvestis, generation_config, response_format, fone)
        (text, None, {"type": "video", "aspect_ratio": ar, "duration": "4s", "resolution": "720p"}, True),
        (parts, task, {"type": "video", "aspect_ratio": ar, "duration": "4s", "resolution": "720p"}, True),
        (parts, task, {"type": "video", "aspect_ratio": ar}, True),
        (parts, task, {"type": "video", "aspect_ratio": ar}, False),
    ]
    if hq:  # geresnė kokybė: 1080p, 8 s (nepavykus – 720p, tada įprasti variantai)
        variants = [
            (text, None, {"type": "video", "aspect_ratio": ar, "duration": "8s", "resolution": "1080p"}, True),
            (parts, task, {"type": "video", "aspect_ratio": ar, "duration": "8s", "resolution": "1080p"}, True),
            (text, None, {"type": "video", "aspect_ratio": ar, "duration": "8s", "resolution": "720p"}, True),
        ] + variants
    last = None
    for model in models[:2]:
        for n, (inp, gc, fmt, background) in enumerate(variants, 1):
            body = {"model": model, "input": inp, "response_format": fmt}
            if gc:
                body["generation_config"] = gc
            if background:
                body.update(background=True, store=True)
            if n > 1:
                say(f"Bandau kitą būdą ({n}/{len(variants)})…")
            try:
                it = _gapi(key, "/interactions", body, timeout=60 if background else 400)
                it = _omni_wait(key, it, background, say, timeout)
            except OmniFailed as e:
                last = f"{model}: {e}"
                if re.search(r"people|person|safety|policy|region|prohibit|not allowed|filter", str(e), re.I):
                    raise RuntimeError(f"Google nesukūrė video ({e}). Pabandykite aprašyti kitaip – ES Google dažnai "
                                       "neleidžia kurti tikroviškų žmonių.")
                continue
            except RuntimeError as e:
                last = f"{model}: {e}"
                if str(e).startswith(("401", "403")):
                    raise RuntimeError("Google raktas neleidžia kurti video – patikrinkite mokėjimus AI Studio.")
                if str(e).startswith("429") and re.search(r"free tier|limit: 0", str(e), re.I):
                    raise RuntimeError(
                        "Jūsų Google raktas – nemokamo lygio (Free Tier), o jame AI video kurti negalima. "
                        "AI Studio → Billing užbaikite išankstinį apmokėjimą (Set up prepay), o API Keys patikrinkite, "
                        "ar raktas priklauso projektui su mokėjimais (ne „Free“ lygis).")
                if str(e).startswith("429"):
                    raise RuntimeError("Google šiuo metu riboja užklausas – pabandykite po kelių minučių.")
                if str(e).startswith("404"):
                    break  # tokio modelio nėra – kitas modelis
                continue  # 400 ir pan. – kitas užklausos variantas
            for step in it.get("steps") or []:
                if step.get("type") == "model_output":
                    for c in step.get("content") or []:
                        if c.get("type") == "video":
                            return _save_b64_or_uri(key, c, out_path)
            last = f"{model}: atsakyme nėra video"
    raise RuntimeError("Google nesukūrė video (" + str(last)[:220] + "). Pabandykite vėliau – Omni modelis dar "
                       "bandomasis (preview).")


def veo_generate(key, prompt, aspect, out_path, status=None, timeout=420, hq=False):
    """AI video kadras (Google Veo) pagal aprašymą. aspect – „9:16“ arba „16:9“. Grąžina kelią.
    hq – geresnė kokybė: pilnas (ne „fast“/„lite“) modelis, 1080p, 8 s (brangiau)."""
    import time as _t
    import urllib.request
    say = status or (lambda m: None)
    body = {"instances": [{"prompt": VEO_STYLE.format(prompt=prompt.strip().rstrip("."))}],
            "parameters": {"aspectRatio": aspect if aspect in ("9:16", "16:9") else "9:16",
                           "negativePrompt": "text, subtitles, watermark, logo, blurry, distorted faces"}}
    op, last = None, None
    models = veo_models(key)
    if not models:  # Google dabar video kuria per Gemini Omni
        return omni_generate(key, prompt, aspect, out_path, status, timeout, hq=hq)
    if hq:  # kokybiškiausi modeliai pirmi
        tier = lambda n: 0 if not re.search(r"fast|lite", n) else 1 if "fast" in n else 2  # noqa: E731
        models = sorted(models, key=tier)
    for model in models:
        for secs in ((8, 6, None) if hq else (VEO_SECONDS, 5, None)):  # pigiausia – 4 s; senesni modeliai – nuo 5 s
            b = json.loads(json.dumps(body))
            if secs:
                b["parameters"]["durationSeconds"] = secs
            if hq and secs:
                b["parameters"]["resolution"] = "1080p"
            try:
                op = _gapi(key, f"/models/{model}:predictLongRunning", b)
                break
            except RuntimeError as e:
                last = f"{model}: {e}"
                if str(e).startswith(("401", "403")):
                    raise RuntimeError("Google raktas neleidžia kurti video (Veo) – gali reikėti įjungti mokėjimus "
                                       "Google AI Studio (Veo nemokamai nepasiekiamas).")
                if not (str(e).startswith("400") and re.search(r"duration|resolution", str(e), re.I)):
                    break  # ne trukmės klaida – bandom kitą modelį
        if op:
            break
    if (not op or not op.get("name")) and VEO_DIAG.get("omni"):
        return omni_generate(key, prompt, aspect, out_path, status, timeout, hq=hq)
    if not op or not op.get("name"):
        seen = "; ".join(VEO_DIAG["seen"][:12]) or (
            "modelių sąrašo gauti nepavyko: " + VEO_DIAG["error"] if VEO_DIAG["error"] else "video modelių nėra")
        raise RuntimeError("Google Veo nepasiekiamas (" + str(last)[:160] + "). Google šiam raktui siūlo: " + seen)
    say("Google kuria video kadrą (1–3 min.)…")
    t0 = _t.time()
    while not op.get("done"):
        if _t.time() - t0 > timeout:
            raise RuntimeError("Google Veo neatsakė per 7 min. – pabandykite dar kartą.")
        _t.sleep(8)
        op = _gapi(key, "/" + op["name"])
    if op.get("error"):
        raise RuntimeError("Google Veo: " + str(op["error"].get("message", op["error"]))[:250])
    resp = op.get("response") or {}
    samples = ((resp.get("generateVideoResponse") or {}).get("generatedSamples") or resp.get("generatedVideos") or [])
    uri = next((((x.get("video") or {}).get("uri")) for x in samples if (x.get("video") or {}).get("uri")), None)
    if not uri:
        reason = (resp.get("generateVideoResponse") or {}).get("raiMediaFilteredReasons")
        raise RuntimeError("Google nesukūrė video" + (f" ({reason[0]})" if reason else
                                                       " – pabandykite kitaip aprašyti kadrą."))
    req = urllib.request.Request(uri, headers={"x-goog-api-key": key})
    tmp = out_path + ".part"
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    os.replace(tmp, out_path)
    return out_path


def clean_voice(path):
    """Įgarsinimo valymas: nukerpamas pabaigos „čirškėjimas“ / triukšmas po paskutinio sakinio, tyla pabaigoje
    sutrumpinama, uždedamas švelnus užgesimas (be spragtelėjimo) ir nuimami aukšti cypiantys dažniai."""
    import numpy as np
    sr = 24000
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return path
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    hop = int(sr * 0.02)
    n = len(x) // hop
    if n < 10:
        return path
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))
    thr = max(0.012, float(np.percentile(rms, 90)) * 0.12)
    voiced = rms > thr
    segs, i = [], 0  # kalbos atkarpos (tarpai trumpesni nei 0,18 s – sujungiami)
    while i < n:
        if voiced[i]:
            j = i
            while j < n and (voiced[j] or (j + 9 < n and voiced[j:j + 9].any())):
                j += 1
            segs.append([i, j])
            i = j
        else:
            i += 1
    if not segs:
        return path
    end = segs[-1][1]

    def centroid(a, b):  # spektro „aukštumas“ (Hz) – čirškėjimas daug aukštesnis už kalbą
        seg = x[a * hop: b * hop]
        if len(seg) < 256:
            return 0.0
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / sr)
        return float((spec * f).sum() / (spec.sum() + 1e-9))
    speech_c = float(np.median([centroid(a, b) for a, b in segs[:-1]] or [0]))
    speech_e = float(np.median(rms[voiced]))
    # pabaigos „čirškėjimas“: trumpa (<0,7 s), nuo kalbos atskirta (≥0,2 s) atkarpa, kuri skamba ne kaip kalba
    # (daug aukštesni dažniai arba gerokai tylesnė) – paskutinis tikras žodis (pvz. „Ačiū!“) paliekamas
    while len(segs) > 1:
        a, b = segs[-1]
        gap = a - segs[-2][1]
        odd = centroid(a, b) > max(1.6 * speech_c, 1800) or float(rms[a:b].mean()) < 0.35 * speech_e
        if (b - a) * 0.02 < 0.7 and gap * 0.02 >= 0.2 and odd:
            segs.pop()
            end = segs[-1][1]
        else:
            break
    cut = min(len(x) / sr, end * 0.02 + 0.25)
    fade = 0.18
    tmp = path + ".clean.mp3"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-t", f"{cut:.3f}", "-af",
                        f"lowpass=f=9500,afade=t=in:d=0.02,afade=t=out:st={max(0.0, cut - fade):.3f}:d={fade}",
                        "-c:a", "libmp3lame", "-b:a", "160k", tmp], capture_output=True)
    if r.returncode == 0 and os.path.exists(tmp):
        os.replace(tmp, path)
    return path


def tts(client, text, voice, out_path, language="lt", gemini_key=None):
    """AI įgarsinimas: tekstas -> MP3. „g:…“ balsai – Google Gemini (natūralus lietuviškas tarimas), kiti – OpenAI."""
    if voice.startswith("g:"):
        if not gemini_key:
            raise RuntimeError("Google balsams reikia Google (Gemini) rakto – „Mano projektai“ → Google raktas.")
        return clean_voice(tts_gemini(gemini_key, text, voice, out_path, language))
    lang = video_editor.LANGUAGES.get(language, "Lithuanian")
    try:
        with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts", voice=voice, input=text, response_format="mp3",
                instructions=TTS_INSTRUCTIONS.format(lang=lang)) as r:
            r.stream_to_file(out_path)
    except Exception:
        with client.audio.speech.with_streaming_response.create(
                model="tts-1-hd", voice=voice if voice in ("alloy", "echo", "fable", "onyx", "nova", "shimmer")
                else "nova", input=text, response_format="mp3") as r:
            r.stream_to_file(out_path)
    return clean_voice(out_path)


def voice_text(client, topic, language="lt", seconds=30):
    """AI parašo įgarsinimo tekstą Reels'ui (kabliukas, 2–3 mintys, kvietimas)."""
    lang = video_editor.LANGUAGES.get(language, "Lithuanian")
    j = reels_studio._ai_json(client, (
        f"You write voiceover scripts for short vertical videos (Reels/TikTok) in {lang}, with perfect grammar and "
        f"diacritics. About {int(seconds * 2.2)} words (~{seconds} s). Start with a strong hook sentence, then 2–4 short, "
        "concrete sentences, end with a short call to action. Natural spoken language, no emojis, no hashtags. "
        "Reply only JSON: {\"text\": \"...\"}"), {"topic": topic})
    return str(j.get("text", "")).strip()


def photo_duration(clips, s, vo_path=None):
    """Kiek rodyti vieną nuotrauką. Su įgarsinimu – kad nuotraukos (ir video) truktų tiek, kiek kalba:
    likęs įgarsinimo laikas tolygiai padalijamas nuotraukoms (≥ 1,2 s)."""
    imgs = [c for c in clips if c.get("image")]
    if not vo_path or not imgs:
        return s["image_duration"]
    vo = video_editor.media_duration(vo_path)
    videos = sum((sum(b - a for a, b in _segments(c)) if _segments(c) else c["duration"])
                 for c in clips if not c.get("image"))
    overlap = (len(clips) - 1) * video_editor.TRANSITION_DURATION if video_editor.TRANSITIONS.get(s["transition"]) else 0
    need = vo * s["speed"] + 0.6 + overlap - videos  # vaizdas pagreitinamas, įgarsinimas – ne
    return round(max(1.2, min(30.0, need / len(imgs))), 2)


AUTO_FORMATS = ("9:16", "16:9", "4:5")
FORMAT_SIZES = {"9:16": (1080, 1920), "16:9": (1280, 720), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def extra_formats(main):
    """Kiti du formatai šalia pagrindinio (iš 9:16, 16:9, 4:5)."""
    return [f for f in AUTO_FORMATS if f != main][:2]


def _mostly_portrait(clips):
    """Ar dauguma medžiagos (pagal trukmę) – stati."""
    tall = sum(c.get("duration") or 0 for c in clips if (c.get("height") or 0) > (c.get("width") or 0) * 1.1)
    total = sum(c.get("duration") or 0 for c in clips) or 1
    return tall / total > 0.5


# ---------- 🎵 kadrui skirta muzika / įgarsinimas ----------
def clip_sound_file(c, s):
    """Garso failas kadrui (muzika iš bibliotekos arba kadro įgarsinimas) arba None."""
    snd = c.get("sound") or {}
    if snd.get("kind") == "music":
        lib = reels_studio.music_library()
        return lib[snd["track"]]["path"] if snd.get("track") in lib else None
    if snd.get("kind") in ("voice", "file") and snd.get("path") and os.path.exists(snd["path"]):
        return snd["path"]
    return None


def _clip_src(c, s, image_duration):
    """Kadro failas montažui: jei kadrui parinkta sava muzika ar įgarsinimas – kopija su tuo garsu
    (garsas prasideda ten, kur prasideda apkarpyta kadro dalis). Grąžina (kelias, nuotrauka?)."""
    snd_file = clip_sound_file(c, s)
    if not snd_file:
        return c["path"], c.get("image")
    snd = c["sound"]
    vol = max(0, min(200, int(snd.get("volume", 100)))) / 100
    orig = max(0, min(200, int(snd.get("orig", 100)))) / 100
    voice = snd["kind"] == "voice" or (snd["kind"] == "file" and snd.get("voice"))
    key = hashlib.sha1(json.dumps([c["path"], snd_file, vol, orig, image_duration, c.get("trim")],
                                  sort_keys=True).encode()).hexdigest()[:10]
    out = f"{c['path']}.snd{key}.mkv"
    if os.path.exists(out):
        return out, False
    tmp = out + ".part.mkv"
    if c.get("image"):  # nuotrauka -> video; su įgarsinimu – tiek, kiek trunka įgarsinimas
        d = float(image_duration)
        if voice:
            d = max(d, video_editor.media_duration(snd_file) + 0.4)
        fo = max(0.0, d - 0.6)
        cmd = ["-loop", "1", "-t", f"{d:.3f}", "-i", c["path"], "-stream_loop", "-1", "-i", snd_file,
               "-filter_complex",
               f"[0:v]scale='min(1920,iw)':-2,scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30,format=yuv420p[v];"
               f"[1:a]atrim=duration={d:.3f},volume={vol:.2f},afade=t=out:st={fo:.3f}:d=0.6,"
               f"aformat=sample_rates=48000:channel_layouts=stereo[a]",
               "-map", "[v]", "-map", "[a]", "-t", f"{d:.3f}", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "18", "-c:a", "aac", "-b:a", "192k", tmp]
    else:
        a, b = c.get("trim") or (0.0, c["duration"])
        seg = max(0.3, float(b) - float(a))
        fo = max(0.0, seg - 0.6)
        has_audio = video_editor.probe(c["path"]).get("has_audio")
        music = (f"[1:a]atrim=duration={seg:.3f},asetpts=PTS-STARTPTS,volume={vol:.2f},"
                 + ("" if voice else "afade=t=in:d=0.3,") + f"afade=t=out:st={fo:.3f}:d=0.6,"
                 f"adelay={int(float(a) * 1000)}:all=1,aformat=sample_rates=48000:channel_layouts=stereo[m]")
        if has_audio and orig > 0:
            mix = (f"{music};[0:a]volume={orig:.2f},aformat=sample_rates=48000:channel_layouts=stereo[o];"
                   f"[o][m]amix=inputs=2:duration=first:normalize=0[a]")
        else:  # be originalaus garso – tik parinktas garsas (tyla iki kadro pradžios ir po jo)
            mix = (f"{music};anullsrc=r=48000:cl=stereo,atrim=duration={c['duration']:.3f}[z];"
                   f"[z][m]amix=inputs=2:duration=first:normalize=0[a]")
        cmd = ["-i", c["path"], "-stream_loop", "-1", "-i", snd_file, "-filter_complex", mix,
               "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", tmp]
    r = _ffmpeg(cmd)
    if r.returncode != 0 or not os.path.exists(tmp):
        raise RuntimeError("Nepavyko pridėti kadro garso: " + (r.stderr or "")[-300:])
    os.replace(tmp, out)
    return out, False


def _clip_paths(clips, s, image_duration):
    return [_clip_src(c, s, image_duration)[0] for c in clips]


def source_for_format(clips, settings, workdir, fmt, vo_path=None, progress=None):
    """Ta pati medžiaga kitu formatu (analizė – pauzės, titrai – lieka ta pati)."""
    s = settings_with_defaults(dict(settings, format=fmt))
    src = os.path.join(workdir, f"joined_{fmt.replace(':', 'x')}.mkv")
    # Gulsčias papildomas formatas (YouTube 16:9) iš stačios medžiagos – visas vaizdas per vidurį su sulietu
    # fonu (užpildant būtų nukirsta didžioji viršaus ir apačios dalis – žmonės liktų be galvų)
    # YouTube (16:9): stačias kadras visada rodomas visas su sulietu fonu, gulsčias – per visą kadrą
    # (anksčiau sprendžiama pagal visą medžiagą – automatiškai parinkti ilgi gulsti video „nusverdavo“)
    fill = s["fit"] == "fill" and fmt != "16:9"
    idur = photo_duration(clips, s, vo_path)
    src, _ = video_editor.concat_clips(_clip_paths(clips, s, idur), src, fmt, progress=progress,
                                       image_duration=idur,
                                       segments=[_segments(c) for c in clips], transition=s["transition"],
                                       fill=fill)
    return src


def prepare(clips, settings, workdir, client=None, status=None, progress=None, vo_path=None):
    """Sujungia medžiagą, suranda pauzes, atpažįsta kalbą (titrai). Grąžina prep žodyną (JSON-draugišką).
    vo_path – įgarsinimas: tada pauzės nekerpamos, o titrai daromi iš įgarsinimo (jo laiko skalė)."""
    s = settings_with_defaults(settings)
    say = status or (lambda m: None)
    prog = progress or (lambda p: None)
    if not clips:
        raise ValueError("Nėra medžiagos")
    say(f"Sujungiu {len(clips)} įrašus…" if len(clips) > 1 else "Ruošiu medžiagą…")
    src = os.path.join(workdir, f"joined_{s['format'].replace(':', 'x')}.mkv")
    image_duration = photo_duration(clips, s, vo_path)
    if image_duration != s["image_duration"]:
        say(f"Nuotraukos – po {image_duration:.1f} s, kad tilptų visas įgarsinimas…")
    src, spans = video_editor.concat_clips(_clip_paths(clips, s, image_duration), src, s["format"],
                                           progress=lambda p: prog(p * 0.5), image_duration=image_duration,
                                           segments=[_segments(c) for c in clips], transition=s["transition"],
                                           fill=s["fit"] == "fill")
    protect = [sp for sp, c in zip(spans, clips) if c["audio"] != "speech" or clip_sound_file(c, s)]
    say("Ieškau pauzių ir atpažįstu kalbą…")
    analysis = video_editor.analyze(src, remove_silence=s["remove_silence"] and not vo_path,
                                    subtitles=s["subtitles"] and not vo_path,
                                    client=client, subtitle_language=s["subtitle_language"],
                                    subtitle_text=s["subtitle_text"], protect=protect, status=say)
    if vo_path:  # titrai iš įgarsinimo: AI atpažįsta tikslius laikus, be AI – žinomas tekstas pagal pauzes
        words, mode = video_editor.analyze_voice(vo_path, s["subtitles"], client, None, s["subtitle_language"],
                                                 "" if client is not None else s["voiceover"]["text"], status=say)
        analysis["words"], analysis["subtitle_mode"] = words, mode
    prog(1.0)
    keep = analysis.get("keep") or [(0.0, analysis["info"]["duration"])]

    def edited(t):  # sujungtos medžiagos laikas -> sumontuoto video laikas (iškirptos pauzės)
        return sum(max(0.0, min(b, t) - a) for a, b in keep)
    return {"src": src, "analysis": analysis, "format": s["format"], "vo": vo_path,
            "spans": [[round(edited(a), 3), round(edited(b), 3)] if (a is not None) else None
                      for a, b in ((sp or (None, None)) for sp in spans)],
            "lines": video_editor.edit_lines(analysis["words"])}


# ---------- 🎞 intarpai (Pexels ir kt.) ----------
def _to_src(t, keep):
    """Sumontuoto video laikas -> paruoštos medžiagos laikas (pauzės iškirptos)."""
    acc = 0.0
    for a, b in keep or []:
        if t <= acc + (b - a):
            return a + (t - acc)
        acc += b - a
    return keep[-1][1] if keep else t


BROLL_MODES = {"card": "Kortelė – matotės ir jūs", "split": "Pusė ekrano", "full": "Visas kadras"}


def _card_images(cw, ch, tmp):
    """Kortelės kaukė (užapvalinti kampai) ir baltas rėmelis su šešėliu – PNG."""
    from PIL import Image, ImageDraw, ImageFilter
    r = max(8, cw // 14)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), r, fill=255)
    b, pad = max(4, cw // 70), max(12, cw // 22)
    fw, fh = cw + 2 * (b + pad), ch + 2 * (b + pad)
    frame = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    sh = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + b, fw - pad, fh - pad + b), r + b, fill=(0, 0, 0, 120))
    frame.alpha_composite(sh.filter(ImageFilter.GaussianBlur(pad / 2)))
    ImageDraw.Draw(frame).rounded_rectangle((pad, pad, fw - pad - 1, fh - pad - 1), r + b, fill=(255, 255, 255, 255))
    ImageDraw.Draw(frame).rounded_rectangle((pad + b, pad + b, pad + b + cw - 1, pad + b + ch - 1), r, fill=(0, 0, 0, 0))
    mp, fp = os.path.join(tmp, f"mask_{cw}x{ch}.png"), os.path.join(tmp, f"frame_{cw}x{ch}.png")
    mask.save(mp)
    frame.save(fp)
    return mp, fp, b + pad


def _face_box(src, t0, d, W, H):
    """Veido sritis intarpo metu (dalimis 0–1) arba None. Papildoma funkcija: bet kokia klaida – None
    (kortelė tada dedama įprastai), video kūrimas niekada nesustoja."""
    try:
        return _face_box_cv(src, t0, d, W, H)
    except Exception as e:  # pvz. kitokia OpenCV versija
        import sys
        print("Veido paieška neveikia:", e, file=sys.stderr)
        return None


def _face_box_cv(src, t0, d, W, H):
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    w = 270
    h = max(2, round(H * w / W))
    boxes = []
    for t in (t0 + 0.1, t0 + d / 2, t0 + max(0.1, d - 0.2)):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", "1",
                            "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True)
        if len(r.stdout) < w * h:
            continue
        img = np.frombuffer(r.stdout[:w * h], np.uint8).reshape(h, w)
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        found = casc.detectMultiScale(cv2.equalizeHist(img), 1.1, 5, minSize=(w // 10, w // 10))
        if len(found):
            x, y, fw, fh = max(found, key=lambda f: f[2] * f[3])
            boxes.append((x / w, y / h, (x + fw) / w, (y + fh) / h))
    if not boxes:
        return None
    # veidas + plaukai / smakras: šiek tiek didesnė sritis
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    mx, my = (x1 - x0) * 0.15, (y1 - y0) * 0.25
    return max(0, x0 - mx), max(0, y0 - my), min(1, x1 + mx), min(1, y1 + my)


def _card_place(W, H, face, pos="auto"):
    """Kortelės vieta ir dydis (x, y, plotis, aukštis) – kad neuždengtų veido."""
    even = lambda v: int(v) // 2 * 2  # noqa: E731
    tall = H >= W
    ratio = 1.2 if tall else 0.5625
    cw = even(min(W * 0.42, H * 0.33)) if tall else even(W * 0.3)
    m = even(W * 0.045)
    top = even(H * 0.06)

    def rect(corner, w):
        h = even(w * ratio)
        x = m if corner == "tl" else W - w - m
        return x, top, w, h

    def overlap(r):
        if not face:
            return 0.0
        fx0, fy0, fx1, fy1 = face[0] * W, face[1] * H, face[2] * W, face[3] * H
        x, y, w, h = r
        ox = max(0, min(x + w, fx1) - max(x, fx0))
        oy = max(0, min(y + h, fy1) - max(y, fy0))
        return ox * oy
    if pos in ("tl", "tr"):
        return rect(pos, cw)
    best = min(("tr", "tl"), key=lambda c: overlap(rect(c, cw)))
    w = cw
    while overlap(rect(best, w)) > 0 and w > W * 0.24:  # mažinam, kol nebeuždengia (iki ~¼ pločio)
        w = even(w * 0.9)
    if overlap(rect(best, w)) > 0:
        w = cw if overlap(rect(best, cw)) < overlap(rect(best, w)) * 1.5 else w
    return rect(best, w)


def overlay_broll(src, out_path, items, keep=None, speed=1.0, fade=0.25):
    """Intarpai ant medžiagos (garsas lieka jūsų). items – [{"path", "t", "d", "mode"}], laikai – galutinio video
    (įgarsinimo atveju) arba sumontuoto video laiku. mode: card – kortelė kampe (jūs matotės; pos: auto – kampas
    be veido, tl / tr – viršuje kairėje / dešinėje), split – pusė ekrano
    (intarpas viršuje, jūs apačioje), full – visas kadras. Švelniai išnyra ir išnyksta."""
    info = video_editor.probe(src)
    W, H, fps = info["width"], info["height"], info["fps"] or 30
    if _video_frames(src) == 0:
        raise ValueError("Medžiagoje nėra vaizdo (juodas įrašas) – pašalinkite jį ir nufilmuokite iš naujo.")
    tall = H >= W
    tmp = tempfile.mkdtemp(dir=os.path.dirname(out_path) or None)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src]
    chains, last, n, k = [], "0:v", 0, 0
    even = lambda v: int(v) // 2 * 2  # noqa: E731
    for it in items:
        if not it.get("path") or not os.path.exists(it["path"]):
            continue
        t0 = _to_src(float(it["t"]) * speed, keep)
        t1 = _to_src((float(it["t"]) + float(it["d"])) * speed, keep)
        d = max(0.6, t1 - t0)
        if t0 >= info["duration"] - 0.3:
            continue
        mode = it.get("mode") if it.get("mode") in BROLL_MODES else "full"
        n += 1
        k += 1
        bi = k
        cmd += ["-stream_loop", "-1", "-i", it["path"]]
        f = min(fade, d / 3)
        fades = (f"fade=t=in:st=0:d={f:.2f}:alpha=1,fade=t=out:st={d - f:.3f}:d={f:.2f}:alpha=1,"
                 f"setpts=PTS+{t0:.3f}/TB")
        base = f"[{bi}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,fps={fps},"
        if mode == "card":  # vieta – ten, kur nėra veido (arba pasirinkta ranka)
            x, y, cw, ch = _card_place(W, H, _face_box(src, t0, d, W, H) if it.get("pos", "auto") == "auto" else None,
                                       it.get("pos", "auto"))
            mp, fp, off = _card_images(cw, ch, tmp)
            cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", mp, "-loop", "1", "-t", f"{d:.3f}", "-i", fp]
            mi, fi = k + 1, k + 2
            k += 2
            chains.append(f"{base}scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch},format=yuva420p"
                          f"[c{n}];[{mi}:v]format=gray,fps={fps}[m{n}];[c{n}][m{n}]alphamerge,{fades}[b{n}]")
            chains.append(f"[{fi}:v]format=rgba,fps={fps},{fades}[f{n}]")
            chains.append(f"[{last}][f{n}]overlay={x - off}:{y - off}:eof_action=pass:format=auto[p{n}]")
            chains.append(f"[p{n}][b{n}]overlay={x}:{y}:eof_action=pass:format=auto[o{n}]")
        elif mode == "split":  # intarpas – viena pusė, jūs (veido sritis) – kita
            en = f"enable='between(t,{t0:.3f},{t0 + d:.3f})'"
            if tall:
                bw, bh, sx, sy, ox, oy = W, even(H / 2), 0, even(H * 0.12), 0, even(H / 2)
            else:
                bw, bh, sx, sy, ox, oy = even(W / 2), H, even(W / 4), 0, even(W / 2), 0
            chains.append(f"[{last}]split[a{n}][s{n}];[s{n}]crop={bw}:{bh}:{sx}:{sy}[sp{n}];"
                          f"[a{n}][sp{n}]overlay={ox}:{oy}:{en}[q{n}]")
            chains.append(f"{base}scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                          f"format=yuva420p,{fades}[b{n}]")
            chains.append(f"[q{n}][b{n}]overlay=0:0:eof_action=pass:format=auto[o{n}]")
        else:
            chains.append(f"{base}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuva420p,"
                          f"{fades}[b{n}]")
            chains.append(f"[{last}][b{n}]overlay=eof_action=pass:format=auto[o{n}]")
        last = f"o{n}"
    try:
        if not n:
            return src
        cmd += ["-filter_complex", ";".join(chains), "-map", f"[{last}]", "-map", "0:a?", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", out_path]
        proc = video_editor.popen(video_editor.limit_threads(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True)
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError("Nepavyko įdėti intarpų: " + (err or "")[-300:])
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- AI / taisyklės ----------
def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


def marked(words, client=None):
    """Svarbiausi žodžiai: naudotojo *žymės*, AI arba taisyklė."""
    words = list(words)
    if not words or any(video_editor.is_key(w) for w, _, _ in words):
        return words
    if client is not None:
        idx = _safe(reels_studio.ai_key_word_indices, client, words)
        if idx:
            return reels_studio.mark_indices(words, idx)
    return video_editor.mark_key_words(words)


def bubbles(words, s, client=None):
    words = list(words or [])
    if not s["bubbles"] or not words:
        return None
    if client is not None:
        b = _safe(reels_studio.ai_bubbles, client, words)
        if b:
            return b
    return reels_studio.auto_bubbles(words)


def anim_spec(words, s, client=None, cuts=()):
    """Animacijų planas (kaip studijoje): AI arba taisyklės. None – viskas išjungta."""
    an = s["anims"]
    if not (any(an.values()) or s["gfx_kinds"]):
        return None
    words = list(words or [])
    plan = {}
    if words and any(an[k] for k in ("stickers", "marks", "cards", "phone", "fx")):
        if client is not None:
            plan = _safe(animations.ai_plan, client, words, reels_studio._ai_json) or {}
        if not any(plan.values()):
            plan = animations.auto_plan(words)
    gfx = []
    if s["gfx_kinds"] and words:
        busy = list(plan.get("phone", []) if an["phone"] else [])
        if client is not None:
            gfx = _safe(fxpack.ai_plan, client, words, s["gfx_kinds"], reels_studio._ai_json, busy) or []
        if not gfx:
            gfx = fxpack.auto_plan(words, s["gfx_kinds"], busy)
    gfx = [g for g in gfx if g.get("kind") != "gold3d"]
    if "gold3d" in s["gfx_kinds"] and words:  # ✨ auksinės raidės – visada su pirmu ištartu žodžiu
        t0 = words[0][1]
        gap = fxpack.LEN["gold3d"] + 1.0
        gfx = [{"kind": "gold3d", "t": round(t0, 2), "text": video_editor.plain(words[0][0])}] + \
              [g for g in gfx if g["t"] - t0 >= gap]
    gfx = [g for g in gfx if g.get("kind") != "shatter3d"]
    if "shatter3d" in s["gfx_kinds"] and words:  # 💥 dūžtantis ekranas – ties kadrų sandūra (po šukėmis kitas kadras)
        L = fxpack.LEN["shatter3d"]
        busy_t = [g["t"] for g in gfx]
        pre = fxpack.SHATTER_AT * L
        end = words[-1][2]
        cand = [c - pre for c in cuts if c - pre > 0.3 and c + L * (1 - fxpack.SHATTER_AT) < end + 0.5]
        if not cand:  # vienas kadras – dūžta antrojo sakinio pradžioje
            starts = [w[1] for i, w in enumerate(words) if i and re.search(r"[.!?…]$", words[i - 1][0])]
            cand = [x for x in starts if x + L < end + 0.5] or ([words[0][1] + 0.5] if end > L + 1 else [])
        free = [c for c in cand if all(abs(c - b) >= L + 0.5 for b in busy_t)]
        if free:
            gfx = sorted(gfx + [{"kind": "shatter3d", "t": round(free[0], 2)}], key=lambda g: g["t"])
    if gfx and plan.get("fx"):
        plan = dict(plan, fx=[(t, k) for t, k in plan["fx"] if all(abs(t - g["t"]) >= 2.8 for g in gfx)])
    return {"gfx": gfx, "plan": {k: plan.get(k, []) if an[k] else [] for k in
                                 ("stickers", "marks", "cards", "phone", "fx")},
            "intro": an["intro"], "outro": an["outro"], "handle": s["handle"]}


# ---------- montažas ----------
def build(prep, settings, out_path, workdir, client=None, words=None, quick=False, progress=None,
          logo=None, end_card=None, music_file=None, broll=None):
    """Montažas + Reels apdaila. words – pataisyti titrai (None – atpažinti). quick – greita peržiūra.
    broll – intarpai [{"path", "t", "d"}] (laikai – kaip titrų)."""
    s = settings_with_defaults(settings)
    prog = progress or (lambda p: None)
    tmp = tempfile.mkdtemp(dir=workdir)
    vo = prep.get("vo") if prep.get("vo") and os.path.exists(prep["vo"]) else None
    try:
        words = prep["analysis"]["words"] if words is None else words
        words = (marked(words, client) if s["key_words"]
                 else [(video_editor.plain(w), a, b) for w, a, b in words])
        if vo:  # įgarsinimo titrai – galutinio video laiku; montaže jie pagreitinami kartu su vaizdu
            words = [(w, a * s["speed"], b * s["speed"]) for w, a, b in words]
        bubble_list, anims = bubbles(words, s, client), anim_spec(
            words, s, client, [sp[1] for sp in (prep.get("spans") or []) if sp][:-1])
        src = prep["src"]
        if broll:
            prog(0.02)
            src = overlay_broll(src, os.path.join(tmp, "broll.mkv"), broll,
                                None if vo else prep["analysis"].get("keep"), s["speed"] if vo else 1.0)
        highlight = reels_studio._ass_color(reels_studio.accent_colors(s["accent"])[0])[4:]
        subs_y = reels_studio.SUBTITLE_POSITIONS.get(s["subs_pos"], 0.72)
        edited = os.path.join(tmp, "edited.mp4")
        # pakeitus greitį titrai piešiami apdailoje (galutiniu laiku) – kad sluoksniai nelįstų vienas ant kito
        # titrai visada piešiami apdailoje – po priartėjimo efektų, todėl niekada neišlenda už ekrano kraštų
        late_subs = True
        analysis = prep["analysis"]
        si = video_editor.probe(src)  # kitas formatas – kadro dydis iš jo medžiagos (analizė – ta pati)
        if (si["width"], si["height"]) != (analysis["info"]["width"], analysis["info"]["height"]):
            analysis = dict(analysis, info=dict(analysis["info"], width=si["width"], height=si["height"]))
        video_editor.render_edit(
            src, edited, analysis, [] if late_subs else words, fmt=prep.get("format", s["format"]),
            fades=not vo,
            denoise=s["denoise"] and not quick, loudnorm=not quick, subtitle_style="modern", highlight=highlight,
            subtitle_look=s["look"], ypos=subs_y, subtitle_size=s["subs_size"] / 100,
            progress=lambda p: prog(p * 0.6), max_side=640 if quick else 1920,
            preset="ultrafast" if quick else "veryfast", crf=30 if quick else 20)
        lib = reels_studio.music_library()
        music = music_file or (lib[s["music"]]["path"] if s["music"] in lib else None)
        fin = reels_studio.finish(
            edited, out_path, s["hook"], s["hook_duration"], s["cta"], 2.5, s["handle"], s["accent"], s["template"],
            music, s["music_volume"] / 100, s["ducking"], reels_studio.LENGTHS.get(s["length"]), s["speed"],
            s["color"], s["progress_bar"], progress=lambda p: prog(0.6 + p * 0.4), effects=s["effects"],
            preview=quick, subs_words=words, subs_look=s["look"], subs_ypos=subs_y,
            hook_ypos=reels_studio.HOOK_POSITIONS.get(s["hook_pos"], 0.2), subs_size=s["subs_size"] / 100,
            text_size=s["text_size"] / 100, punch=s["key_words"] and s["punch"], logo=logo, end_card=end_card,
            bubbles=bubble_list, anims=anims, subs_burn=late_subs, subs_highlight=highlight, voiceover=vo, clip_gain=s["clip_gain"] / 100 if vo else 1.0,
            moment_at=(s["moment_at"] if s["moment_at"] is not None else 3.0)
            if "Gintaro akimirka" in s["effects"] else None)
        prog(1.0)
        return fin
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cover(video_path, out_path, settings, at=0.5, width=1080, height=1920):
    """Viršelis su kabliuku. video_path – geriausia paruošta medžiaga (prep["src"]) – be video užrašų."""
    s = settings_with_defaults(settings)
    reels_studio.make_cover(video_path, out_path, at, s["hook"], s["accent"], s["template"], s["handle"],
                            width, height, color=s["color"],
                            effects=tuple(e for e in s["effects"] if e != "Gintaro akimirka"),
                            text_size=s["text_size"] / 100)
    return out_path


def caption(prep, settings, client=None):
    """Aprašymas ir grotažymės: AI (jei yra raktas) arba taisyklės."""
    s = settings_with_defaults(settings)
    words = prep["analysis"]["words"] if prep else []
    text = video_editor.plain_text(words) if words else ""
    if client is not None:
        c = _safe(reels_studio.write_caption, client, text, s["hook"], "", s["subtitle_language"])
        if c:
            return c
    category = reels_studio.TEMPLATES.get(s["template"], {}).get("cat") or s["category"]
    return reels_studio.simple_caption(text, s["hook"], "", s["cta"], category, words)
