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



def test_last_result_tensor_is_alive_when_vram_cleanup_runs(monkeypatch):
    import weakref

    tensor_ref = None
    cleanup_observations = []
    audio = np.linspace(-0.25, 0.25, 2400, dtype=np.float32)

    class FakeTensor:
        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return audio

    class FakeFrontend:
        def text_normalize(self, text, **kwargs):
            return text

        def frontend_zero_shot(self, text, prompt, voice_path, sample_rate, extra):
            return {"normalized_text": text}

    class FakeInference:
        def tts(self, **kwargs):
            nonlocal tensor_ref
            tensor = FakeTensor()
            tensor_ref = weakref.ref(tensor)
            yield {"tts_speech": tensor}

    class FakeModel:
        sample_rate = 24000
        frontend = FakeFrontend()
        model = FakeInference()

    def observe_cleanup():
        cleanup_observations.append(tensor_ref() is not None)

    model = FakeModel()
    monkeypatch.setattr(tts_engine, "clear_vram", observe_cleanup)
    tts_engine.configure_tts(
        model=model,
        lock=threading.RLock(),
        config_loader=lambda: {"n_timesteps": 6},
        app_logger=Mock(),
        numpy_module=np,
        torch_module=SimpleNamespace(inference_mode=nullcontext),
    )

    tts_engine._generate_voice_impl(
        "Hello.", "voices/test/voice.wav", "Reference text"
    )

    # Characterizes current code: the loop variable result still holds the
    # last result dictionary (and tensor) when clear_vram() is called.
    assert cleanup_observations == [True]


def test_successful_generation_combines_multiple_tts_results(monkeypatch):
    audio_parts = [
        np.full(1200, 0.1, dtype=np.float32),
        np.full(1200, -0.1, dtype=np.float32),
    ]
    calls = []

    class FakeTensor:
        def __init__(self, values):
            self.values = values

        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self.values

    class FakeFrontend:
        def text_normalize(self, text, **kwargs):
            return text

        def frontend_zero_shot(self, text, prompt, voice_path, sample_rate, extra):
            return {"normalized_text": text}

    class FakeInference:
        def tts(self, **kwargs):
            calls.append(kwargs)
            for values in audio_parts:
                yield {"tts_speech": FakeTensor(values)}

    class FakeModel:
        sample_rate = 24000
        frontend = FakeFrontend()
        model = FakeInference()

    cleanup_calls = []
    model = FakeModel()
    monkeypatch.setattr(
        tts_engine, "clear_vram", lambda: cleanup_calls.append("clear")
    )
    tts_engine.configure_tts(
        model=model,
        lock=threading.RLock(),
        config_loader=lambda: {"n_timesteps": 6},
        app_logger=Mock(),
        numpy_module=np,
        torch_module=SimpleNamespace(inference_mode=nullcontext),
    )

    wav_bytes, duration = tts_engine._generate_voice_impl(
        "Hello.", "voices/test/voice.wav", "Reference text"
    )

    assert len(calls) == 1
    assert cleanup_calls == ["clear"]
    assert duration == 0.1
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        assert wav.getnframes() == 2400
        assert wav.getframerate() == 24000
