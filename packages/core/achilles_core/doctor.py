import stat
from dataclasses import dataclass

from achilles_core.config import Settings
from achilles_core.llm import build_http_client, chat_model_tag
from achilles_core.platform import free_disk_gb, hardware_tier, total_ram_gb
from achilles_core.services.ollama import model_tags
from achilles_net import BlockedHostError

MIN_RAM_GB = 16
MIN_DISK_GB = 30
BLOCKED_PROBE = "https://example.com"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


async def run_checks(settings: Settings) -> list[Check]:
    tag = chat_model_tag(hardware_tier())
    home = settings.achilles_home
    checks: list[Check] = []
    async with build_http_client(settings) as client:
        try:
            tags = await model_tags(client, settings.ollama_url)
            checks.append(Check("Ollama reachable", True, settings.ollama_url))
            checks.append(Check("Chat model pulled", tag in tags, tag))
        except Exception as error:
            checks.append(Check("Ollama reachable", False, f"{settings.ollama_url}: {error}"))
            checks.append(Check("Chat model pulled", False, f"{tag}: Ollama unreachable"))
        try:
            await client.get(BLOCKED_PROBE)
            checks.append(Check("Allowlist blocks other hosts", False, f"{BLOCKED_PROBE} allowed"))
        except BlockedHostError:
            checks.append(Check("Allowlist blocks other hosts", True, f"{BLOCKED_PROBE} refused"))

    ram = total_ram_gb()
    checks.append(Check(f"RAM >= {MIN_RAM_GB} GB", ram >= MIN_RAM_GB, f"{ram:.1f} GB"))
    disk_path = home if home.exists() else home.parent
    disk = free_disk_gb(disk_path)
    checks.append(Check(f"Free disk >= {MIN_DISK_GB} GB", disk >= MIN_DISK_GB, f"{disk:.1f} GB"))
    if home.exists():
        mode = stat.S_IMODE(home.stat().st_mode)
        checks.append(Check("Home is private (0700)", mode == 0o700, f"{home} is {mode:o}"))
    else:
        checks.append(Check("Home is private (0700)", False, f"{home} missing"))
    checks.append(Check("Server bound to localhost", settings.host == "127.0.0.1", settings.host))
    return checks
