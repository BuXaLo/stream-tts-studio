import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.routes.characters import create_characters_router
from studio.routes.fonts import create_fonts_router
from studio.routes.speak import create_speak_router
from studio.routes.tools import create_tools_router


class FakeWS:
    def __init__(self):
        self.events = []

    def broadcast_sync(self, message):
        self.events.append(message)


class FakeTorch:
    class cuda:
        class OutOfMemoryError(Exception):
            pass


def test_character_and_font_routers_use_injected_paths(tmp_path):
    char_dir = tmp_path / "characters"
    char_dir.mkdir()
    (char_dir / "alice").mkdir()
    (char_dir / "alice" / "avatar.png").write_bytes(b"png")
    presets = {"alice": {"name": "Alice", "theme": {}}}
    app = FastAPI()
    app.include_router(create_characters_router(
        lambda: dict(presets), lambda value: presets.update(value),
        lambda: "alice", lambda value: None, {"theme": {}}, lambda value: value,
        str(char_dir), str(tmp_path / "presets.json"), str(tmp_path / "active.json"),
        lambda path: __import__("contextlib").nullcontext(), lambda path, data: None,
        lambda raw: raw, {},
    ))
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "Custom.ttf").write_bytes(b"font")
    app.include_router(create_fonts_router(str(fonts_dir), lambda path, data: None))
    client = TestClient(app)
    response = client.get("/api/presets")
    assert response.status_code == 200
    assert response.json()["presets"]["alice"]["has_avatar"] is True
    assert client.get("/api/fonts").json()["custom_fonts"][0]["name"] == "Custom"


def test_tools_preview_router_broadcasts_overlay_event(tmp_path):
    ws = FakeWS()
    app = FastAPI()
    app.include_router(create_tools_router(
        str(tmp_path), "whisper", "ffmpeg", None, None, FakeTorch, None, None,
        None, lambda raw: raw, lambda: None, lambda *args: (b"wav", 1.0),
        lambda text: bool(text), lambda text: text, ws, lambda value: value,
        str(tmp_path), lambda: "alice",
    ))
    response = TestClient(app).post("/api/trigger_overlay_preview", json={"text": "hello"})
    assert response.status_code == 200
    assert ws.events[0]["event"] == "mita_dialogue"
    assert ws.events[0]["text"] == "hello"


def test_speak_router_preserves_wav_and_overlay_contract(tmp_path):
    char_dir = tmp_path / "characters"
    (char_dir / "alice").mkdir(parents=True)
    (char_dir / "alice" / "voice.wav").write_bytes(b"voice")
    ws = FakeWS()
    app = FastAPI()
    app.include_router(create_speak_router(
        lambda: {"alice": {"name": "Alice", "speed": 1.0, "reference_text": "ref"}},
        lambda: "alice", str(char_dir), lambda *args: (b"RIFFtest", 0.5),
        ws, lambda text: bool(text), lambda text: text, FakeTorch,
    ))
    response = TestClient(app).post("/speak", json={"text": "hello"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFtest"
    assert ws.events[0]["event"] == "mita_dialogue"
