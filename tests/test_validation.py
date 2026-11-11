import pytest

from studio.core.validation import same_origin


@pytest.mark.parametrize("origin,host,scheme", [
    ("http://localhost", "localhost:80", "http"),
    ("https://example.test", "example.test:443", "https"),
    ("http://[::1]:8765", "[::1]:8765", "http"),
    ("http://127.0.0.1:8765", "127.0.0.1:8765", "http"),
    ("http://localhost:8765", "localhost:8765", "ws"),
])
def test_same_origin_normalizes_ports_and_ipv6(origin, host, scheme):
    assert same_origin(origin, host, scheme)


@pytest.mark.parametrize("origin,host,scheme", [
    ("http://evil.test", "localhost:8765", "http"),
    ("https://localhost", "localhost:8765", "https"),
    ("http://localhost:8766", "localhost:8765", "http"),
    ("null", "localhost:8765", "http"),
    ("http://user@localhost:8765", "localhost:8765", "http"),
])
def test_same_origin_rejects_foreign_or_malformed_origins(origin, host, scheme):
    assert not same_origin(origin, host, scheme)
