from types import SimpleNamespace

from studio.core import monitor
from studio.core.monitor import EventHub


def test_speak_route_emits_monitor_events(tmp_path, monkeypatch):
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
    test_hub = EventHub()
    monkeypatch.setattr(monitor, "hub", test_hub)
    with TestClient(app) as client:
        response = client.post("/speak", json={"text": "Hello"})
    assert response.status_code == 200
    events = [item for item in test_hub.history() if item.get("type") == "generation"]
    assert [item["status"] for item in events] == ["started", "complete"]
    assert events[0]["text"] == "Hello"
    assert events[1]["synthesis_seconds"] >= 0
    assert events[1]["audio_duration"] == 1.25
