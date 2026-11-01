import stat
from dataclasses import dataclass
from pathlib import Path

from homer_core.config import Settings
from homer_core.llm import build_http_client, chat_model_tag
from homer_core.platform import free_disk_gb, hardware_tier, total_ram_gb
from homer_core.services.ollama import model_tags
from homer_net import AllowlistedClient, BlockedHostError

MIN_RAM_GB = 16
MIN_DISK_GB = 30
BLOCKED_PROBE = "https://example.com"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


async def ollama_checks(settings: Settings, client: AllowlistedClient) -> list[Check]:
    tag = chat_model_tag(hardware_tier())
    try:
        tags = await model_tags(client, settings.ollama_url)
    except Exception as error:
        return [
            Check("Ollama reachable", False, f"{settings.ollama_url}: {error}"),
            Check("Chat model pulled", False, f"{tag}: Ollama unreachable"),
        ]
    return [
        Check("Ollama reachable", True, settings.ollama_url),
        Check("Chat model pulled", tag in tags, tag),
    ]


def hardware_checks(home: Path) -> list[Check]:
    ram = total_ram_gb()
    disk = free_disk_gb(home if home.exists() else home.parent)
    return [
        Check(f"RAM >= {MIN_RAM_GB} GB", ram >= MIN_RAM_GB, f"{ram:.1f} GB"),
        Check(f"Free disk >= {MIN_DISK_GB} GB", disk >= MIN_DISK_GB, f"{disk:.1f} GB"),
    ]


async def run_checks(settings: Settings, quick: bool = False) -> list[Check]:
    """Quick skips Ollama and hardware: it checks the installed code and home, not the machine."""
    home = settings.homer_home
    checks: list[Check] = []
    async with build_http_client(settings) as client:
        if not quick:
            checks += await ollama_checks(settings, client)
        try:
            await client.get(BLOCKED_PROBE)
            checks.append(Check("Allowlist blocks other hosts", False, f"{BLOCKED_PROBE} allowed"))
        except BlockedHostError:
            checks.append(Check("Allowlist blocks other hosts", True, f"{BLOCKED_PROBE} refused"))
    if not quick:
        checks += hardware_checks(home)
    if home.exists():
        mode = stat.S_IMODE(home.stat().st_mode)
        checks.append(Check("Home is private (0700)", mode == 0o700, f"{home} is {mode:o}"))
    else:
        checks.append(Check("Home is private (0700)", False, f"{home} missing"))
    checks.append(Check("Server bound to localhost", settings.host == "127.0.0.1", settings.host))
    return checks
