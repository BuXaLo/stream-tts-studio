import requests

from studio.services.streamerbot import send_donation_to_streamerbot


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def invoke(post, journal=None):
    return send_donation_to_streamerbot(
        "Viewer", 10, "RUB", "hello",
        load_da_config=lambda: {
            "streamerbot_url": "http://127.0.0.1:7474/DoAction",
            "streamerbot_action": "Donation",
        },
        journal_failed=journal or (lambda *args: None), post=post,
    )


def test_connection_error_retries_once_then_succeeds():
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise requests.exceptions.ConnectionError("offline")
        return FakeResponse(200)
    result = invoke(post)
    assert result["success"] is True
    assert result["attempts"] == 2
    assert len(calls) == 2
    assert calls[0]["timeout"] == (3, 4)


def test_http_5xx_retries_once():
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return FakeResponse(503 if len(calls) == 1 else 200)
    result = invoke(post)
    assert result["success"] is True
    assert result["attempts"] == 2


def test_http_4xx_does_not_retry_and_is_journaled():
    calls, journal = [], []
    result = invoke(lambda *a, **k: (calls.append(1) or FakeResponse(400, "bad request")), lambda *a: journal.append(a))
    assert result["success"] is False
    assert result["attempts"] == 1
    assert len(calls) == 1
    assert journal and journal[0][5] == 400


def test_timeout_does_not_retry_and_is_journaled():
    calls, journal = [], []
    def post(*args, **kwargs):
        calls.append(1)
        raise requests.exceptions.Timeout("read timeout")
    result = invoke(post, lambda *a: journal.append(a))
    assert result["success"] is False
    assert result["attempts"] == 1
    assert len(calls) == 1
    assert journal
