from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.routes.speak import create_speak_router


class FakeWS:
    def broadcast_sync(self, message):
        self.last_message = message


class FakeTorch:
    class cuda:
        class OutOfMemoryError(Exception):
            pass


def make_client(tmp_path, generate_voice, presets=None, speakable=None):
    char_dir = tmp_path / "characters"
    (char_dir / "alice").mkdir(parents=True, exist_ok=True)
    (char_dir / "alice" / "voice.wav").write_bytes(b"voice")
    app = FastAPI()
    app.include_router(create_speak_router(
        lambda: presets if presets is not None else {"alice": {"name": "Alice", "speed": 3.5, "reference_text": "ref"}},
        lambda: "alice", str(char_dir), generate_voice, FakeWS(),
        speakable or bool, lambda value: value, FakeTorch,
    ))
    return TestClient(app)


def test_speak_returns_expected_client_errors(tmp_path):
    client = make_client(tmp_path, lambda *args: (b"wav", 1.0))
    assert client.post("/speak", json={"text": "!!!"}).status_code == 400
    assert client.post("/speak", json={"text": "hello", "character": "missing"}).status_code == 404


def test_speak_returns_404_when_voice_is_missing(tmp_path):
    client = make_client(tmp_path, lambda *args: (b"wav", 1.0), presets={"alice": {"name": "Alice", "speed": 1.0, "reference_text": ""}})
    (tmp_path / "characters" / "alice" / "voice.wav").unlink()
    assert client.post("/speak", json={"text": "hello"}).status_code == 404


def test_speak_maps_oom_and_unexpected_errors(tmp_path):
    def oom(*args):
        raise FakeTorch.cuda.OutOfMemoryError("oom")
    client = make_client(tmp_path, oom)
    assert client.post("/speak", json={"text": "hello"}).status_code == 503

    client = make_client(tmp_path, lambda *args: (_ for _ in ()).throw(RuntimeError("failure")))
    assert client.post("/speak", json={"text": "hello"}).status_code == 500


def test_speak_clamps_only_explicit_speed(tmp_path):
    speeds = []
    def generate(text, voice, reference, speed):
        speeds.append(speed)
        return b"wav", 1.0
    client = make_client(tmp_path, generate)
    assert client.post("/speak", json={"text": "hello"}).status_code == 200
    assert speeds[-1] == 3.5
    assert client.post("/speak", json={"text": "hello", "speed": 0}).status_code == 200
    assert speeds[-1] == 0.5
    assert client.post("/speak", json={"text": "hello", "speed": 4}).status_code == 200
    assert speeds[-1] == 2.0
