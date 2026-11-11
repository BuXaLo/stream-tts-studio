import pytest

import studio.services.tts_engine as tts_engine


def test_generate_voice_clears_vram_when_inference_fails(monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        raise RuntimeError("inference failed")

    monkeypatch.setattr(tts_engine, "_generate_voice_impl", fail)
    monkeypatch.setattr(tts_engine, "clear_vram", lambda: calls.append("cleared"))
    with pytest.raises(RuntimeError, match="inference failed"):
        tts_engine.generate_voice("text", "voice.wav", "reference", 1.0)
    assert calls == ["cleared"]
