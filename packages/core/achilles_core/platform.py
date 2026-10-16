import platform
import shutil
from pathlib import Path
from typing import Literal

import psutil

Tier = Literal["supported", "degraded"]
HOME_DIRS = ("data", "credentials", "logs")


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
