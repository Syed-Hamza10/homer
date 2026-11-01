import asyncio
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from homer_net import Allowlist, AllowlistedClient
from homer_net.allowlist import host_key

STARTUP_TIMEOUT = 30.0


class Simulator:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.client = AllowlistedClient(Allowlist([host_key(self.url)]), timeout=10.0)

    async def reset(self) -> None:
        response = await self.client.post(f"{self.url}/_sim/reset")
        response.raise_for_status()

    async def state(self) -> dict[str, Any]:
        response = await self.client.get(f"{self.url}/_sim/state")
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def find_simulator() -> str:
    found = shutil.which("homer-sim")
    if found:
        return found
    candidate = Path(sys.executable).parent / "homer-sim"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError("homer-sim is not installed")


async def wait_until_ready(sim: Simulator) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        try:
            await sim.state()
            return
        except Exception:
            await asyncio.sleep(0.2)
    raise RuntimeError(f"simulator did not become ready at {sim.url}")


@asynccontextmanager
async def simulator(url: str | None = None) -> AsyncIterator[Simulator]:
    if url:
        live = Simulator(url)
        await wait_until_ready(live)
        try:
            yield live
        finally:
            await live.close()
        return

    port = free_port()
    process = subprocess.Popen(
        [find_simulator(), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    live = Simulator(f"http://127.0.0.1:{port}")
    try:
        await wait_until_ready(live)
        yield live
    finally:
        await live.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
