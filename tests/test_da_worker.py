import requests

from studio.services import da_worker as worker_module


def make_response(status_code):
    response = requests.Response()
    response.status_code = status_code
    return response


def configure(monkeypatch, tokens):
    worker_module.configure_worker(
        ".", ".", lambda: {},
        lambda: {"client_id": "client", "client_secret": "secret"},
        lambda: tokens, lambda value: None,
    )
    monkeypatch.setattr(worker_module.requests, "get", lambda *args, **kwargs: make_response(401))
    return worker_module.DonationAlertsWorker()


def test_missing_refresh_token_reports_reauthorization(monkeypatch):
    worker = configure(monkeypatch, {"access_token": "expired"})
    assert worker.get_access_token() is None
    assert "Требуется повторная авторизация" in worker.last_error


def test_failed_refresh_reports_reauthorization(monkeypatch):
    worker = configure(monkeypatch, {"access_token": "expired", "refresh_token": "refresh"})
    monkeypatch.setattr(worker, "refresh_tokens", lambda *args: None)
    assert worker.get_access_token() is None
    assert "Требуется повторная авторизация" in worker.last_error


def test_http_503_is_temporary_not_auth_failure(monkeypatch):
    worker = configure(monkeypatch, {"access_token": "token"})
    monkeypatch.setattr(worker_module.requests, "get", lambda *args, **kwargs: make_response(503))
    assert worker.get_access_token() is None
    assert "временно недоступен" in worker.last_error
