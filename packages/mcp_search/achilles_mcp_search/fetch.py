import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

import trafilatura

from achilles_mcp_search.settings import LogFn
from achilles_mcp_search.untrusted import wrap
from achilles_net import Allowlist, AllowlistedClient, BlockedHostError
from achilles_net.allowlist import host_key

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 15
USER_AGENT = "Achilles/0.1 (+local assistant)"


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


async def resolve_public(hostname: str) -> str | None:
    """Returns an error code when the hostname is unresolvable or maps to a non-public address."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(hostname, None)
    except socket.gaierror:
        return "unresolvable_host"
    addresses = [info[4][0] for info in infos]
    if not addresses or not all(is_public(address) for address in addresses):
        return "private_address"
    return None


def extract(body: bytes, url: str) -> tuple[str, str]:
    document = trafilatura.bare_extraction(body, url=url, with_metadata=True)
    if document is None:
        return "", ""
    return document.title or "", document.text or ""


async def read_capped(client: AllowlistedClient, url: str) -> tuple[bytes, str] | dict[str, Any]:
    async with client.stream("GET", url) as response:
        if response.status_code >= 400:
            return {"error": "http_error", "status": response.status_code}
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body += chunk
            if len(body) > MAX_BYTES:
                return {"error": "too_large"}
        return bytes(body), str(response.url)


async def fetch_page(url: str, log: LogFn) -> dict[str, Any]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return {"error": "invalid_url"}
    refusal = await resolve_public(parts.hostname)
    if refusal:
        return {"error": refusal}
    allowlist = Allowlist([host_key(url)])
    headers = {"User-Agent": USER_AGENT}
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            async with AllowlistedClient(
                allowlist, log, timeout=TIMEOUT_SECONDS, headers=headers
            ) as c:
                outcome = await read_capped(c, url)
    except BlockedHostError as error:
        return {"error": "blocked_host", "host": error.host}
    except TimeoutError:
        return {"error": "timeout"}
    except Exception as error:
        return {"error": "fetch_failed", "detail": f"{type(error).__name__}: {error}"}
    if isinstance(outcome, dict):
        return outcome
    body, final_url = outcome
    title, text = await asyncio.to_thread(extract, body, final_url)
    return {"title": wrap(title), "text": wrap(text), "url": final_url}
