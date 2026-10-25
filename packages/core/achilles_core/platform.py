import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Literal

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
