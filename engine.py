"""Reels studijos video variklis BE Streamlit – naudojamas API serverio (api/server.py) ir būsimos svetainės.

Visa logika ta pati kaip studijoje (video_editor, reels_studio, animations, fxpack); čia ji tik surinkta į
paprastas funkcijas, kurioms paduodamas nustatymų žodynas:

    clip = engine.add_clip(path)                       # patikrina, sumažina 4K, nustato garsą
    prep = engine.prepare([clip, ...], settings, workdir, client)   # sujungia, iškerpa pauzes, titrai
    res  = engine.build(prep, settings, "out.mp4", workdir, client) # montažas + apdaila
    cap  = engine.caption(prep, settings, client)      # aprašymas ir grotažymės

client – openai.OpenAI arba None (be AI veikia taisyklės).
"""
import os
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
    # 🎙 AI įgarsinimas (OpenAI balsas): tekstas skaitomas vietoj / šalia jūsų balso
    "voiceover": {"on": False, "text": "", "voice": "coral"},
    "clip_gain": 20,           # originalaus garso garsumas, kai yra įgarsinimas (%)
}

VOICES = {"coral": "Koralas – šilta moteris", "nova": "Nova – žvali moteris", "shimmer": "Šimeris – švelni moteris",
          "sage": "Sage – rami moteris", "alloy": "Alloy – neutralus", "ash": "Ash – ramus vyras",
          "echo": "Echo – gilus vyras", "onyx": "Onyx – žemas vyras", "fable": "Fable – pasakotojas"}
TTS_INSTRUCTIONS = ("Speak in natural, fluent {lang} with correct pronunciation and stress. Warm, confident, "
                    "energetic social-media tone, clear diction, natural pauses at punctuation.")


def settings_with_defaults(settings):
    s = dict(DEFAULTS)
    s.update({k: v for k, v in (settings or {}).items() if k in DEFAULTS and v is not None})
    s["anims"] = dict(DEFAULTS["anims"], **(settings or {}).get("anims", {}) or {})
    s["voiceover"] = dict(DEFAULTS["voiceover"], **(settings or {}).get("voiceover", {}) or {})
    if s["voiceover"]["voice"] not in VOICES:
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
        "templates": {k: {"category": v.get("cat"), "accent": v["accent"], "color": v["color"], "kind": v["kind"]}
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
        "stickers": animations.STICKERS, "marks": animations.MARKS, "fx": animations.FX,
        "gfx": {k: v if isinstance(v, str) else v.get("title", k) for k, v in fxpack.KINDS.items()},
        "defaults": DEFAULTS,
    }


# ---------- medžiaga ----------
def _ffmpeg(args):
    return subprocess.run(video_editor.limit_threads(["ffmpeg", "-y", "-loglevel", "error"] + args),
                          capture_output=True, text=True)


def add_clip(path, name=None, recorded=False):
    """Patikrina įkeltą / nufilmuotą failą. Grąžina klipo žodyną (kaip studijoje) arba kelia ValueError."""
    if recorded:  # naršyklės įrašuose dažnai trūksta trukmės – perpakuojam
        mkv = path + ".mkv"
        if _ffmpeg(["-i", path, "-c", "copy", mkv]).returncode == 0:
            os.unlink(path)
            path = mkv
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
        info = video_editor.probe(path)
    image = video_editor.is_image(path)
    duration = info["duration"]
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


def tts(client, text, voice, out_path, language="lt"):
    """AI įgarsinimas (OpenAI): tekstas -> MP3. Naujesnis modelis priima nurodymus (tarimas, tonas)."""
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
    return out_path


def voice_text(client, topic, language="lt", seconds=30):
    """AI parašo įgarsinimo tekstą Reels'ui (kabliukas, 2–3 mintys, kvietimas)."""
    lang = video_editor.LANGUAGES.get(language, "Lithuanian")
    j = reels_studio._ai_json(client, (
        f"You write voiceover scripts for short vertical videos (Reels/TikTok) in {lang}, with perfect grammar and "
        f"diacritics. About {int(seconds * 2.2)} words (~{seconds} s). Start with a strong hook sentence, then 2–4 short, "
        "concrete sentences, end with a short call to action. Natural spoken language, no emojis, no hashtags. "
        "Reply only JSON: {\"text\": \"...\"}"), {"topic": topic})
    return str(j.get("text", "")).strip()


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
    src, spans = video_editor.concat_clips([c["path"] for c in clips], src, s["format"],
                                           progress=lambda p: prog(p * 0.5), image_duration=s["image_duration"],
                                           segments=[_segments(c) for c in clips], transition=s["transition"],
                                           fill=s["fit"] == "fill")
    protect = [sp for sp, c in zip(spans, clips) if c["audio"] != "speech"]
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
    return {"src": src, "analysis": analysis, "format": s["format"], "vo": vo_path,
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


def overlay_broll(src, out_path, items, keep=None, speed=1.0, fade=0.25):
    """Intarpai ant medžiagos (garsas lieka jūsų). items – [{"path", "t", "d"}], laikai – galutinio video
    (įgarsinimo atveju) arba sumontuoto video laiku; užpildo visą kadrą, švelniai išnyra ir išnyksta."""
    info = video_editor.probe(src)
    W, H, fps = info["width"], info["height"], info["fps"] or 30
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src]
    chains, last, n = [], "0:v", 0
    for it in items:
        if not it.get("path") or not os.path.exists(it["path"]):
            continue
        t0 = _to_src(float(it["t"]) * speed, keep)
        t1 = _to_src((float(it["t"]) + float(it["d"])) * speed, keep)
        d = max(0.6, t1 - t0)
        if t0 >= info["duration"] - 0.3:
            continue
        n += 1
        cmd += ["-stream_loop", "-1", "-i", it["path"]]
        f = min(fade, d / 3)
        chains.append(f"[{n}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,scale={W}:{H}:force_original_aspect_ratio="
                      f"increase,crop={W}:{H},fps={fps},format=yuva420p,fade=t=in:st=0:d={f:.2f}:alpha=1,"
                      f"fade=t=out:st={d - f:.3f}:d={f:.2f}:alpha=1,setpts=PTS+{t0:.3f}/TB[b{n}]")
        chains.append(f"[{last}][b{n}]overlay=eof_action=pass:format=auto[o{n}]")
        last = f"o{n}"
    if not n:
        return src
    cmd += ["-filter_complex", ";".join(chains), "-map", f"[{last}]", "-map", "0:a?", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", out_path]
    r = subprocess.run(video_editor.limit_threads(cmd), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("Nepavyko įdėti intarpų: " + r.stderr[-300:])
    return out_path


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


def anim_spec(words, s, client=None):
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
        bubble_list, anims = bubbles(words, s, client), anim_spec(words, s, client)
        src = prep["src"]
        if broll:
            prog(0.02)
            src = overlay_broll(src, os.path.join(tmp, "broll.mkv"), broll,
                                None if vo else prep["analysis"].get("keep"), s["speed"] if vo else 1.0)
        highlight = reels_studio._ass_color(reels_studio.accent_colors(s["accent"])[0])[4:]
        subs_y = reels_studio.SUBTITLE_POSITIONS.get(s["subs_pos"], 0.72)
        edited = os.path.join(tmp, "edited.mp4")
        video_editor.render_edit(
            src, edited, prep["analysis"], words, fmt=prep.get("format", s["format"]),
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
            bubbles=bubble_list, anims=anims, voiceover=vo, clip_gain=s["clip_gain"] / 100 if vo else 1.0,
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
