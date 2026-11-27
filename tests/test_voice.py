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
