"""Validation for URLs the server will contact on a member's behalf."""
import ipaddress
import socket
from urllib.parse import urlparse

from .. import config

PRIVATE_HOST_SUFFIXES = (".local", ".lan", ".internal", ".home.arpa")
PRIVATE_HOSTS = {"localhost", "host.docker.internal"}


def _ip_is_private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        # not is_global also covers shared address space (100.64.0.0/10, used by Tailscale and CGNAT),
        # benchmarking and documentation ranges, which is_private leaves out.
        return (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast)
    except ValueError:
        return False


def _resolves_private(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for info in infos:
        ip = info[4][0]
        if _ip_is_private(ip):
            return True
    return False


def validate_outbound_url(url: str, *, label: str = "URL", allow_private: bool | None = None) -> str:
    """Reject malformed or local-network URLs unless explicitly allowed.

    This protects user-editable webhook/provider URLs from accidentally turning
    the FinVault server into a request proxy for localhost or LAN services.
    """
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{label} must start with http:// or https://.")
    private_allowed = config.ALLOW_PRIVATE_OUTBOUND_URLS if allow_private is None else allow_private
    host = parsed.hostname.lower()
    if private_allowed:
        return value
    if host in PRIVATE_HOSTS or host.endswith(PRIVATE_HOST_SUFFIXES) or "." not in host:
        raise ValueError(f"{label} must be a public internet address, not a local network host.")
    if _ip_is_private(host) or _resolves_private(host):
        raise ValueError(f"{label} resolves to a private network address.")
    return value
