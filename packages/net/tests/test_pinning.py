import asyncio
import datetime
import ssl
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from homer_net import Allowlist, AllowlistedClient, OutboundCall
from homer_net.pinning import PinnedTransport

HOSTNAME = "pinned.example"


@dataclass
class TlsServer:
    port: int
    cafile: Path
    sni: list[str | None] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)


def write_certificate(directory: Path, hostname: str) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "cert.pem"
    key_path = directory / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@pytest.fixture
async def tls_server(tmp_path: Path) -> AsyncIterator[TlsServer]:
    cert_path, key_path = write_certificate(tmp_path, HOSTNAME)
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert_path, key_path)
    server_state = TlsServer(port=0, cafile=cert_path)

    def on_sni(_: ssl.SSLObject, name: str | None, __: ssl.SSLContext) -> None:
        server_state.sni.append(name)

    context.sni_callback = on_sni

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode()
        host = next(line for line in head.split("\r\n") if line.lower().startswith("host:"))
        server_state.hosts.append(host.split(":", 1)[1].strip())
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)
    server_state.port = server.sockets[0].getsockname()[1]
    async with server:
        yield server_state


async def test_connects_to_pinned_address_with_hostname_for_tls(tls_server: TlsServer) -> None:
    lookups: list[str] = []

    async def pin(host: str) -> str:
        lookups.append(host)
        return "127.0.0.1"

    calls: list[OutboundCall] = []
    verify = ssl.create_default_context(cafile=tls_server.cafile)
    host = f"{HOSTNAME}:{tls_server.port}"
    transport = PinnedTransport(pin, verify=verify)
    async with AllowlistedClient(Allowlist([host]), calls.append, transport=transport) as client:
        first = await client.get(f"https://{host}/one")
        second = await client.get(f"https://{host}/two")

    assert (first.text, second.text) == ("ok", "ok")
    assert lookups == [HOSTNAME]
    assert tls_server.sni == [HOSTNAME, HOSTNAME]
    assert tls_server.hosts == [host, host]
    assert [(call.host, call.path, call.status) for call in calls] == [
        (host, "/one", 200),
        (host, "/two", 200),
    ]


async def test_certificate_must_match_the_hostname(tls_server: TlsServer) -> None:
    async def pin(host: str) -> str:
        return "127.0.0.1"

    verify = ssl.create_default_context(cafile=tls_server.cafile)
    host = f"other.example:{tls_server.port}"
    transport = PinnedTransport(pin, verify=verify)
    async with AllowlistedClient(Allowlist([host]), transport=transport) as client:
        with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
            await client.get(f"https://{host}/")
