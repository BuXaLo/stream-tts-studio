import gc
import io
import threading
import wave
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

import studio.services.tts_engine as tts_engine


@pytest.mark.parametrize("cuda_available", [True, False])
def test_clear_vram_respects_cuda_availability(monkeypatch, cuda_available):
    calls = []
    cuda = SimpleNamespace(
        is_available=lambda: cuda_available,
        empty_cache=lambda: calls.append("empty_cache"),
    )
    monkeypatch.setattr(tts_engine, "torch", SimpleNamespace(cuda=cuda))
    monkeypatch.setattr(tts_engine.gc, "collect", lambda: calls.append("gc"))

    tts_engine.clear_vram()

    expected = ["empty_cache", "gc"] if cuda_available else ["gc"]
    assert calls == expected


def test_successful_generation_preserves_model_parameters_and_wav_contract(monkeypatch):
    operations = []
    model_calls = []
    audio = np.linspace(-0.5, 0.5, 2400, dtype=np.float32)

    class FakeTensor:
        def detach(self):
            operations.append("detach")
            return self

        def cpu(self):
            operations.append("cpu")
            return self

        def numpy(self):
            operations.append("numpy")
            return audio

    class FakeFrontend:
        def text_normalize(self, text, **kwargs):
            return text

        def frontend_zero_shot(self, text, prompt, voice_path, sample_rate, extra):
            return {"normalized_text": text}

    class FakeModel:
        sample_rate = 24000
        frontend = FakeFrontend()

        class Inference:
            def tts(self, **kwargs):
                model_calls.append(kwargs)
                yield {"tts_speech": FakeTensor()}

        model = Inference()

    model = FakeModel()
    monkeypatch.setattr(tts_engine, "clear_vram", lambda: operations.append("clear_vram"))
    tts_engine.configure_tts(
        model=model,
        lock=threading.RLock(),
        config_loader=lambda: {"n_timesteps": 9},
        app_logger=Mock(),
        numpy_module=np,
        torch_module=SimpleNamespace(inference_mode=nullcontext),
    )

    wav_bytes, duration = tts_engine._generate_voice_impl(
        "Hello.", "voices/test/voice.wav", "Reference text", speed=1.25
    )

    assert tts_engine.cosyvoice is model
    assert model_calls == [{
        "normalized_text": "Hello.",
        "stream": False,
        "speed": 1.25,
        "n_timesteps": 9,
    }]
    assert operations == ["detach", "cpu", "numpy", "clear_vram"]
    assert duration == 0.1

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 24000
        assert wav.getnframes() == 2400

