import pytest

from studio.core.validation import is_valid_bind_host, same_origin, validate_port


@pytest.mark.parametrize("origin,host,scheme", [
    ("http://localhost", "localhost:80", "http"),
    ("https://example.test", "example.test:443", "https"),
    ("http://[::1]:8765", "[::1]:8765", "http"),
    ("http://127.0.0.1:8765", "127.0.0.1:8765", "http"),
    ("http://localhost:8765", "localhost:8765", "ws"),
    ("https://[::1]", "[::1]:443", "https"),
])
def test_same_origin_normalizes_ports_and_ipv6(origin, host, scheme):
    assert same_origin(origin, host, scheme)


@pytest.mark.parametrize("origin,host,scheme", [
    ("http://evil.test", "localhost:8765", "http"),
    ("https://localhost", "localhost:8765", "https"),
    ("http://localhost:8766", "localhost:8765", "http"),
    ("null", "localhost:8765", "http"),
    ("http://user@localhost:8765", "localhost:8765", "http"),
    ("http://localhost:0", "localhost:0", "http"),
    ("http://localhost:65536", "localhost:65536", "http"),
    ("http://localhost:8765", "localhost:8765/path", "http"),
])
def test_same_origin_rejects_foreign_or_malformed_origins(origin, host, scheme):
    assert not same_origin(origin, host, scheme)


@pytest.mark.parametrize("host", [
    "localhost", "0.0.0.0", "127.0.0.1", "::1", "[::1]",
    "studio.local", "my-pc.example.test"
])
def test_valid_bind_hosts(host):
    assert is_valid_bind_host(host)


@pytest.mark.parametrize("host", [
    "", "not a host", "http://localhost", "localhost:8765",
    "evil/path", "-bad.example", "bad-.example", "a" * 254, None, 123
])
def test_invalid_bind_hosts(host):
    assert not is_valid_bind_host(host)


@pytest.mark.parametrize("value,expected", [
    (1, 1), (8765, 8765), (65535, 65535), ("8765", 8765), (" 8765 ", 8765)
])
def test_validate_port_accepts_full_range(value, expected):
    assert validate_port(value) == expected


@pytest.mark.parametrize("value", [
    0, -1, 65536, True, False, 8765.0, 8765.9, None, "8765.0", "", "port"
])
def test_validate_port_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        validate_port(value)
