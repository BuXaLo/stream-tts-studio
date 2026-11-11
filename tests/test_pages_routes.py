import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from studio.core.validation import same_origin
from studio.routes.pages import create_pages_router


class FakeWSManager:
    def __init__(self):
        self.connections = []

    async def connect(self, websocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket):
        if websocket in self.connections:
            self.connections.remove(websocket)


def test_pages_and_websocket_origin_checks(tmp_path):
    dashboard = tmp_path / "dashboard"
    overlay = tmp_path / "overlay"
    dashboard.mkdir()
    overlay.mkdir()
    (dashboard / "index.html").write_text("dashboard", encoding="utf-8")
    (overlay / "overlay.html").write_text("overlay", encoding="utf-8")
    manager = FakeWSManager()
    app = FastAPI()
    app.include_router(create_pages_router(str(dashboard), str(overlay), manager, same_origin))
    client = TestClient(app, base_url="http://testserver")
    assert client.get("/").text == "dashboard"
    assert client.get("/overlay").text == "overlay"

    with client.websocket_connect("/ws/overlay", headers={"origin": "http://testserver"}):
        assert len(manager.connections) == 1

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/overlay", headers={"origin": "http://evil.test"}):
            pass
    assert exc.value.code == 1008
