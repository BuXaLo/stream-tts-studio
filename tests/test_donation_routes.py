from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.core.storage import get_file_lock
from studio.routes.donations import create_donation_router


class FakeWorker:
    authorized_user = "Streamer"
    is_connected = False
    last_error = ""

    def get_redirect_uri(self):
        return "http://127.0.0.1:8765/api/da/callback"

    def send_to_streamerbot(self, *args):
        return {"success": False, "status_code": 503, "error": "offline", "attempts": 2}


def make_client(tmp_path):
    config = {
        "enabled": False, "client_id": "client", "client_secret": "secret",
        "streamerbot_url": "http://127.0.0.1:7474/DoAction",
        "streamerbot_action": "Donation",
    }
    app = FastAPI()
    app.include_router(create_donation_router(
        FakeWorker(), lambda: dict(config), lambda value: config.update(value),
        lambda: None, lambda value: None, get_file_lock,
        str(tmp_path / "da_config.json"), str(tmp_path / "da_tokens.json"),
        lambda value: value,
    ))
    return TestClient(app), config


def test_da_config_never_returns_secret_and_preserves_it(tmp_path):
    client, config = make_client(tmp_path)
    response = client.get("/api/da/config")
    assert response.status_code == 200
    assert response.json()["config"]["client_secret"] == ""
    assert response.json()["client_secret_set"] is True
    response = client.post("/api/da/config", json={"client_id": "new-client"})
    assert response.status_code == 200
    assert config["client_secret"] == "secret"


def test_oauth_state_is_required_and_callback_escapes_error(tmp_path):
    client, _ = make_client(tmp_path)
    auth = client.get("/api/da/auth_url")
    assert auth.status_code == 200
    state = parse_qs(urlsplit(auth.json()["auth_url"]).query)["state"][0]
    callback = client.get("/api/da/callback", params={"state": state, "error": "<svg/onload=alert(1)>"})
    assert callback.status_code == 200
    assert "&lt;svg/onload=alert(1)&gt;" in callback.text
    assert "<svg/onload" not in callback.text
    assert client.get("/api/da/callback", params={"state": state, "error": "again"}).status_code == 400


def test_da_test_donation_returns_502_with_delivery_details(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post("/api/da/test_donation", json={"username": "Viewer", "amount": 10})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["status_code"] == 503
    assert detail["error"] == "offline"
