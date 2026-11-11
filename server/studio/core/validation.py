"""URL origin validation helpers."""
import ipaddress
from urllib.parse import urlsplit


def _host_port(value, scheme):
    parsed = urlsplit("{}://{}".format(scheme, value))
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid port") from exc
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        hostname = ipaddress.ip_address(hostname).compressed
    except ValueError:
        pass
    return hostname, port or (443 if scheme == "https" else 80)


def is_valid_bind_host(value):
    if not isinstance(value, str):
        return False
    host = value.strip()
    if not host or len(host) > 253 or any(char.isspace() for char in host):
        return False
    if host.lower() == "localhost" or host == "0.0.0.0":
        return True
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        pass
    label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    import re
    return re.fullmatch(label + r"(?:\." + label + r")*", host) is not None


def same_origin(origin, host_header, request_scheme):
    try:
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            return False
        expected_scheme = "https" if request_scheme in ("https", "wss") else "http"
        if parsed.scheme != expected_scheme:
            return False
        return _host_port(parsed.netloc, parsed.scheme) == _host_port(host_header, expected_scheme)
    except (TypeError, ValueError):
        return False
