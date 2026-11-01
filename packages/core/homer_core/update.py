import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "Syed-Hamza10/homer"
GITHUB_API = "https://api.github.com"
RELEASE_FILES = ("SHA256SUMS", "requirements.lock")


class UpdateError(Exception):
    pass


def release_api() -> str:
    return os.environ.get("HOMER_RELEASE_API", GITHUB_API)


def read_token(home: Path) -> str | None:
    if token := os.environ.get("GITHUB_TOKEN"):
        return token
    path = home / "github_token"
    return path.read_text().strip() if path.exists() else None


def curl(url: str, token: str | None, accept: str, output: Path | None = None) -> bytes:
    command = ["curl", "-fsSL", "-H", f"Accept: {accept}"]
    if token:
        command += ["-H", f"Authorization: Bearer {token}"]
    if output is not None:
        command += ["-o", str(output)]
    result = subprocess.run([*command, url], capture_output=True, check=False)
    if result.returncode:
        raise UpdateError(f"download failed for {url}: {result.stderr.decode().strip()}")
    return result.stdout


def release_assets(api: str, version: str, token: str | None) -> dict[str, str]:
    path = "releases/latest" if version == "latest" else f"releases/tags/{version}"
    body = curl(f"{api}/repos/{REPO}/{path}", token, "application/vnd.github+json")
    return {asset["name"]: asset["url"] for asset in json.loads(body)["assets"]}


def download_release(api: str, version: str, token: str | None, target: Path) -> list[Path]:
    assets = release_assets(api, version, token)
    wanted = [name for name in assets if name.endswith(".whl") or name in RELEASE_FILES]
    missing = sorted(set(RELEASE_FILES) - set(wanted))
    if missing:
        raise UpdateError(f"release {version} has no {', '.join(missing)}")
    for name in wanted:
        curl(assets[name], token, "application/octet-stream", target / name)
    wheels = sorted(target.glob("*.whl"))
    if not wheels:
        raise UpdateError(f"release {version} has no wheels")
    return wheels


def verify_checksums(directory: Path, wheels: list[Path]) -> None:
    sums: dict[str, str] = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        digest, _, name = line.partition(" ")
        sums[name.strip().lstrip("*")] = digest
    for wheel in wheels:
        expected = sums.get(wheel.name)
        if expected is None:
            raise UpdateError(f"{wheel.name} is not listed in SHA256SUMS")
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != expected:
            raise UpdateError(f"checksum mismatch for {wheel.name}")


def uv_binary() -> str:
    found = shutil.which("uv") or shutil.which("uv", path=str(Path.home() / ".local" / "bin"))
    if found is None:
        raise UpdateError("uv is not installed; re-run the installer")
    return found


def run(command: list[str], env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    if result.returncode:
        raise UpdateError(
            f"{' '.join(command[:2])} failed:\n{result.stdout}{result.stderr}".strip()
        )
    return result.stdout


def build_venv(target: Path, wheels: list[Path], constraints: Path) -> None:
    uv = uv_binary()
    run([uv, "venv", "--python", sys.executable, str(target)])
    python = str(target / "bin" / "python")
    run([uv, "pip", "install", "--python", python, "-c", str(constraints), *map(str, wheels)])


def check_venv(venv: Path, home: Path) -> None:
    env = {**os.environ, "HOMER_HOME": str(home)}
    try:
        run([str(venv / "bin" / "homer"), "doctor", "--quick"], env)
    except UpdateError as error:
        raise UpdateError(f"the new environment failed doctor --quick:\n{error}") from error


def swap(home: Path) -> None:
    live, new, previous = home / "venv", home / "venv.new", home / "venv.prev"
    shutil.rmtree(previous, ignore_errors=True)
    live.rename(previous)
    new.rename(live)


def update(home: Path, version: str) -> None:
    """Stages the release in venv.new and swaps it in only after doctor passes there."""
    new = home / "venv.new"
    shutil.rmtree(new, ignore_errors=True)
    try:
        with tempfile.TemporaryDirectory(prefix="homer-update-") as temporary:
            directory = Path(temporary)
            wheels = download_release(release_api(), version, read_token(home), directory)
            verify_checksums(directory, wheels)
            build_venv(new, wheels, directory / "requirements.lock")
        check_venv(new, home)
    except UpdateError:
        shutil.rmtree(new, ignore_errors=True)
        raise
    swap(home)


def rollback(home: Path) -> None:
    live, previous, staging = home / "venv", home / "venv.prev", home / "venv.rollback"
    if not previous.exists():
        raise UpdateError("no previous environment in venv.prev to roll back to")
    live.rename(staging)
    previous.rename(live)
    staging.rename(previous)
