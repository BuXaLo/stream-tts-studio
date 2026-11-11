from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from studio.core.storage import get_file_lock
from studio.routes.system import create_system_router


def make_client(tmp_path):
    state = {"host": "127.0.0.1", "port": 8765, "n_timesteps": 6, "auto_open_browser": True}
    saves = []

    def load_config():
        return dict(state)

    def save_config(value):
        state.clear()
        state.update(value)
        saves.append(dict(value))

    def validate_host(value):
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail="Host должен быть строкой.")
        return value.strip()

    app = FastAPI()
    app.include_router(create_system_router(
        load_config, save_config, get_file_lock, str(tmp_path / "config.json"),
        type("WS", (), {"active_connections": []})(),
        validate_host,
        __import__("studio.core.validation", fromlist=["validate_port"]).validate_port,
    ))
    return TestClient(app), state, saves


def test_system_config_accepts_default_and_high_ports(tmp_path):
    client, state, saves = make_client(tmp_path)
    response = client.post("/api/system_config", json={"port": 8765})
    assert response.status_code == 200
    assert response.json()["config"]["port"] == 8765
    response = client.post("/api/system_config", json={"port": 65535})
    assert response.status_code == 200
    assert state["port"] == 65535
    assert len(saves) == 2


def test_system_config_rejects_invalid_ports_without_saving(tmp_path):
    client, state, saves = make_client(tmp_path)
    for value in [0, -1, 65536, True, 8765.9, "8765.9"]:
        response = client.post("/api/system_config", json={"port": value})
        assert response.status_code == 400, value
    assert state["port"] == 8765
    assert saves == []


def test_system_config_rejects_non_string_host(tmp_path):
    client, state, saves = make_client(tmp_path)
    response = client.post("/api/system_config", json={"host": None})
    assert response.status_code == 400
    assert saves == []
