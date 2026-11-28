"""Balsai: numatytas – natūralus lietuviškas Google balsas; be Google rakto – OpenAI (kad video vis tiek susikurtų)."""
import engine
import server as srv


def test_default_voice_is_google():
    assert engine.settings_with_defaults({})["voiceover"]["voice"].startswith("g:")


def test_voice_fallback_without_google_key(mocks):
    assert srv._voice_for("g:Kore") == "g:Kore"
    mocks["gemini"] = False
    assert srv._voice_for("g:Kore") == "coral"
    assert srv._voice_for("nova") == "nova"


def _voice_file(tmp_path, tail):
    import subprocess
    import numpy as np
    sr = 24000
    t = np.arange(int(sr * 1.2)) / sr
    sp = 0.3 * np.sin(2 * np.pi * 220 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t)) + 0.05 * np.sin(2 * np.pi * 660 * t)
    x = np.concatenate([sp, np.zeros(int(sr * 0.1)), sp, np.zeros(int(sr * 0.35)), tail, np.zeros(int(sr * 0.2))])
    pcm, mp3 = tmp_path / "v.pcm", tmp_path / "v.mp3"
    (x * 32767).astype("<i2").tofile(pcm)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", str(pcm), str(mp3)],
                   check=True)
    return str(mp3)


def _dur(path):
    import video_editor
    return video_editor.media_duration(path)


def test_clean_voice_removes_end_chirp(tmp_path):
    """Google balso pabaigos „čirškėjimas“ nukerpamas (kalba baigiasi ties 2,5 s)."""
    import numpy as np
    sr = 24000
    tt = np.arange(int(sr * 0.3)) / sr
    path = _voice_file(tmp_path, 0.25 * np.sin(2 * np.pi * (3000 + 4000 * tt) * tt))
    engine.clean_voice(path)
    assert _dur(path) < 2.95


def test_clean_voice_keeps_short_last_word(tmp_path):
    """Trumpas paskutinis žodis (pvz. „Ačiū!“) po pauzės paliekamas (baigiasi ties 3,35 s)."""
    import numpy as np
    sr = 24000
    t5 = np.arange(int(sr * 0.5)) / sr
    path = _voice_file(tmp_path, 0.3 * np.sin(2 * np.pi * 230 * t5) + 0.05 * np.sin(2 * np.pi * 690 * t5))
    engine.clean_voice(path)
    assert _dur(path) > 3.4


def _sig_tools():
    import numpy as np
    sr = 24000

    def speech(dur, f0=140):
        t = np.arange(int(dur * sr)) / sr
        v = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 12))
        return 0.25 * v / 3 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t) ** 2)

    def noise(dur, amp):
        return amp * np.diff(np.random.default_rng(1).normal(0, 1, int(dur * sr)), prepend=0)

    def sil(d):
        return np.zeros(int(d * sr))

    def roundtrip(sig):
        import os
        import subprocess
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "v.mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", p],
                       input=sig.astype("<f4").tobytes(), check=True)
        engine.clean_voice(p)
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                           capture_output=True)
        return np.frombuffer(r.stdout, "<f4")
    return np, sr, speech, noise, sil, roundtrip


def test_clean_voice_removes_chirp_glued_to_last_word():
    """Čirškėjimas be pauzės po paskutinio žodžio nukerpamas (lieka ≤0,15 s su užgesimu)."""
    np, sr, speech, noise, sil, roundtrip = _sig_tools()
    out = roundtrip(np.concatenate([speech(1.2), sil(0.3), speech(1.0), noise(0.5, 0.03), sil(0.3)]))
    assert len(out) / sr < 2.5 + 0.15


def test_clean_voice_silences_hiss_in_pauses_keeps_final_s():
    """Šnypštimas pauzėse nuslopinamas, o žodžio gale esantis „s“ nenukerpamas."""
    np, sr, speech, noise, sil, roundtrip = _sig_tools()
    hf = lambda x: float(np.sqrt(np.mean(np.diff(x) ** 2)))  # noqa: E731
    sig = np.concatenate([speech(1.2), noise(0.4, 0.01), speech(1.0), sil(0.3)])
    out = roundtrip(sig)
    assert hf(out[int(1.25 * sr):int(1.55 * sr)]) < hf(sig[int(1.25 * sr):int(1.55 * sr)]) / 8
    out = roundtrip(np.concatenate([speech(1.2), sil(0.3), speech(0.8), noise(0.12, 0.05), sil(0.4)]))
    assert len(out) / sr >= 2.3 + 0.12
