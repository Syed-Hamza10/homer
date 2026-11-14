import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psutil

Tier = Literal["supported", "degraded"]
HOME_DIRS = ("data", "credentials", "documents", "logs", "backups")
SERVER_LABEL = "dev.homer.server"
OLLAMA_LABEL = "dev.homer.ollama"
SYSTEMD_UNIT = "homer.service"
OLLAMA_DROPIN = Path("/etc/systemd/system/ollama.service.d/homer.conf")


def total_ram_gb() -> float:
    return psutil.virtual_memory().total / 2**30


def free_disk_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 2**30


def hardware_tier() -> Tier:
    apple_silicon = platform.system() == "Darwin" and platform.machine() == "arm64"
    if apple_silicon or shutil.which("nvidia-smi"):
        return "supported"
    return "degraded"


def known_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def localtime_zone(localtime: Path = Path("/etc/localtime")) -> str | None:
    """Reads the IANA name from a /etc/localtime symlink into a zoneinfo directory."""
    if not localtime.is_symlink():
        return None
    _, found, name = os.readlink(localtime).rpartition("zoneinfo/")
    return name if found and name else None


def timedatectl_zone() -> str | None:
    if shutil.which("timedatectl") is None:
        return None
    result = subprocess.run(
        ["timedatectl", "show", "-p", "Timezone", "--value"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def etc_timezone() -> str | None:
    path = Path("/etc/timezone")
    if not path.is_file():
        return None
    return path.read_text().strip() or None


def system_timezone() -> str | None:
    """Returns the machine's IANA timezone, or None when it cannot be detected."""
    if platform.system() == "Darwin":
        sources = (localtime_zone,)
    else:
        sources = (timedatectl_zone, etc_timezone, localtime_zone)
    for source in sources:
        name = source()
        if name and known_timezone(name):
            return name
    return None


def ensure_home(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    for name in HOME_DIRS:
        (path / name).mkdir(mode=0o700, exist_ok=True)
        (path / name).chmod(0o700)


def tail_file(path: Path, lines: int, follow: bool) -> None:
    subprocess.run(["tail", "-n", str(lines), *(["-f"] if follow else []), str(path)], check=True)


def launch_agent(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def server_service_file() -> Path:
    if platform.system() == "Darwin":
        return launch_agent(SERVER_LABEL)
    return Path.home() / ".config" / "systemd" / "user" / SYSTEMD_UNIT


def ollama_service_file() -> Path | None:
    """The Ollama launch agent the installer adds on macOS; Linux uses a root-owned drop-in."""
    return launch_agent(OLLAMA_LABEL) if platform.system() == "Darwin" else None


def restart_service() -> None:
    path = server_service_file()
    if not path.exists():
        raise FileNotFoundError(f"no Homer service at {path}; start Homer with homer serve")
    if platform.system() == "Darwin":
        command = ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{SERVER_LABEL}"]
    else:
        command = ["systemctl", "--user", "restart", SYSTEMD_UNIT]
    subprocess.run(command, check=True)


def remove_service(path: Path) -> None:
    """Unloads a launch agent or systemd user unit and deletes its file."""
    if platform.system() == "Darwin":
        command = ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)]
    else:
        command = ["systemctl", "--user", "disable", "--now", path.name]
    subprocess.run(command, capture_output=True, check=False)
    path.unlink()
