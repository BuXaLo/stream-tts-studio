from types import SimpleNamespace

from studio.core.monitor import EventHub


def test_speak_route_returns_wav_and_delegates_generation(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from studio.routes.speak import create_speak_router

    class OutOfMemoryError(Exception):
        pass
    torch_stub = SimpleNamespace(cuda=SimpleNamespace(OutOfMemoryError=OutOfMemoryError))
    (tmp_path / "hero").mkdir()
    (tmp_path / "hero" / "voice.wav").write_bytes(b"voice")
    def generate(*args):
        return b"RIFF-test", 1.25
    router = create_speak_router(
        lambda: {"hero": {"name": "Hero", "speed": 1.0, "reference_text": "ref"}},
        lambda: "hero", str(tmp_path), generate,
        SimpleNamespace(broadcast_sync=lambda message: None),
        lambda text: True, lambda text: text, torch_stub,
    )
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post("/speak", json={"text": "Hello"})
    assert response.status_code == 200
    assert response.content == b"RIFF-test"
    assert response.headers["content-type"] == "audio/wav"


def test_tts_engine_publishes_events_for_every_generation_caller(monkeypatch):
    from studio.core import monitor
    from studio.services import tts_engine

    test_hub = EventHub()
    monkeypatch.setattr(monitor, "hub", test_hub)
    monkeypatch.setattr(tts_engine, "_generate_voice_impl", lambda *args: (b"wav", 2.5))

    result = tts_engine.generate_voice("Hello from dashboard", "characters/hero/voice.wav", "ref", 1.0)

    assert result == (b"wav", 2.5)
    events = [item for item in test_hub.history() if item.get("type") == "generation"]
    assert [item["status"] for item in events] == ["started", "complete"]
    assert events[0]["text"] == "Hello from dashboard"
    assert events[0]["char_id"] == "hero"
    assert events[1]["audio_duration"] == 2.5
    assert events[1]["synthesis_seconds"] >= 0


def test_tts_engine_publishes_failed_generation(monkeypatch):
    from studio.core import monitor
    from studio.services import tts_engine

    test_hub = EventHub()
    monkeypatch.setattr(monitor, "hub", test_hub)

    def fail(*args):
        raise RuntimeError("synthetic generation failure")

    monkeypatch.setattr(tts_engine, "_generate_voice_impl", fail)
    monkeypatch.setattr(tts_engine, "clear_vram", lambda: None)

    try:
        tts_engine.generate_voice("Hello", "characters/hero/voice.wav", "ref", 1.0)
    except RuntimeError as exc:
        assert str(exc) == "synthetic generation failure"
    else:
        raise AssertionError("generation failure was not propagated")

    events = [item for item in test_hub.history() if item.get("type") == "generation"]
    assert [item["status"] for item in events] == ["started", "error"]
    assert events[-1]["error"] == "synthetic generation failure"
