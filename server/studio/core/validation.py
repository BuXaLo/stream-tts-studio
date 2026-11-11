"""Input validation helpers shared by API routes and tests."""
import ipaddress
import re
from urllib.parse import urlsplit


def validate_port(value):
    """Accept integer ports (or digit-only strings) in the full TCP port range."""
    if isinstance(value, bool):
        raise ValueError("port must be an integer")
    if isinstance(value, int):
        port = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        port = int(value.strip())
    else:
        raise ValueError("port must be an integer")
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    return port


def _host_port(value, scheme):
    parsed = urlsplit("{}://{}".format(scheme, value))
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid host")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("invalid host components")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid port")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        hostname = ipaddress.ip_address(hostname).compressed
    except ValueError:
        pass
    return hostname, port if port is not None else (443 if scheme == "https" else 80)


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



def validate_http_url(value):
    """Validate a non-credentialed HTTP(S) URL with an optional valid port."""
    if not isinstance(value, str):
        raise ValueError("URL must be a string")
    value = value.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("malformed URL") from exc
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or (port is not None and not 1 <= port <= 65535)
        or parsed.fragment
    ):
        raise ValueError("URL must be an HTTP(S) URL with a valid host and port")
    return value
