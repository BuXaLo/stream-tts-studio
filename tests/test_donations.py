import pytest

from studio.services.donations import parse_donation


@pytest.mark.parametrize("payload", [None, 1, [], "not-json", "{bad}", {"amount": "NaN"}, {"amount": "inf"}])
def test_invalid_donation_payload_is_skipped(payload):
    assert parse_donation(payload) is None


def test_parse_donation_dict_and_decimal_comma():
    assert parse_donation({
        "username": "Viewer", "amount": "12,5",
        "currency": "EUR", "message": "hello"
    }) == {
        "donor": "Viewer", "amount": 12.5,
        "currency": "EUR", "message": "hello"
    }


def test_parse_donation_json_string_and_list():
    assert parse_donation('[{"user":"Alice","sum":10}]') == {
        "donor": "Alice", "amount": 10.0,
        "currency": "RUB", "message": ""
    }
