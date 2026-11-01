from collections.abc import Iterable
from urllib.parse import urlsplit

DEFAULT_PORTS = {"http": 80, "https": 443}


class BlockedHostError(Exception):
    def __init__(self, host: str) -> None:
        super().__init__(f"outbound call to {host!r} is not allowed")
        self.host = host


def host_key(url: str) -> str:
    """Returns the lowercase hostname, with ':port' appended only when the port is non-default."""
    parts = urlsplit(url)
    if parts.hostname is None:
        raise BlockedHostError(url)
    host = parts.hostname.lower()
    port = parts.port
    if port is None or port == DEFAULT_PORTS.get(parts.scheme):
        return host
    return f"{host}:{port}"


class Allowlist:
    def __init__(self, hosts: Iterable[str]) -> None:
        self.hosts: frozenset[str] = frozenset(host.lower() for host in hosts)

    def check(self, url: str) -> None:
        host = host_key(url)
        if host not in self.hosts:
            raise BlockedHostError(host)
