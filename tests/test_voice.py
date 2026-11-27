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
