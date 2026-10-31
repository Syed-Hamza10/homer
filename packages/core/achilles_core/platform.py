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


def restart_service() -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/dev.achilles.server"],
            check=True,
        )
        return
    if system == "Linux":
        subprocess.run(["systemctl", "--user", "restart", "achilles"], check=True)
        return
    raise RuntimeError(f"unsupported platform: {system}")
