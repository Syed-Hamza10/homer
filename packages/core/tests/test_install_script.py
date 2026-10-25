import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "install.sh"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")
needs_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not available")


def run_installer(tmp_path: Path, *args: str, env: dict[str, str] | None = None) -> tuple:
    home = tmp_path / "home"
    environment = {
        **os.environ,
        "ACHILLES_HOME": str(home),
        "ACHILLES_PASSPHRASE": "test-pass",
        **(env or {}),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), "--force", "--skip-ollama", "--no-service", *args],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return home, result


def write_release(directory: Path, names: tuple[str, ...]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in names:
        path = directory / name
        path.write_bytes(name.encode())
        lines.append(f"{hashlib.sha256(name.encode()).hexdigest()}  {name}")
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n")


WHEELS = ("achilles_core-0.1.0-py3-none-any.whl", "achilles_net-0.1.0-py3-none-any.whl")


@needs_bash
def test_install_script_has_valid_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


@needs_bash
def test_install_script_pins_tool_versions() -> None:
    text = SCRIPT.read_text()
    assert 'UV_VERSION="' in text
    assert 'OLLAMA_VERSION="' in text
    assert "https://astral.sh/uv/${UV_VERSION}/install.sh" in text
    assert 'OLLAMA_VERSION="$OLLAMA_VERSION" sh' in text
    assert "ollama-darwin.tgz" in text


@needs_bash
def test_install_script_dry_run_changes_nothing(tmp_path: Path) -> None:
    home, result = run_installer(tmp_path, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "Dry run only" in result.stdout
    assert str(home) in result.stdout
    assert "install uv 0." in result.stdout
    assert "install Ollama 0." in result.stdout
    assert "verify every wheel against SHA256SUMS" in result.stdout
    assert "requirements.lock as constraints" in result.stdout
    assert not home.exists()


@needs_bash
def test_install_script_warns_about_the_passphrase_flag(tmp_path: Path) -> None:
    _, result = run_installer(tmp_path, "--dry-run", "--passphrase", "p")
    assert result.returncode == 0, result.stderr
    assert "shell history" in result.stderr


@needs_bash
@needs_uv
def test_install_script_refuses_a_checksum_mismatch(tmp_path: Path) -> None:
    release = tmp_path / "release"
    write_release(release, (*WHEELS, "requirements.lock"))
    (release / WHEELS[1]).write_bytes(b"tampered")
    home, result = run_installer(tmp_path, "--wheels-dir", str(release))
    assert result.returncode == 1
    assert "checksum mismatch" in result.stderr
    assert not (home / "venv").exists()


@needs_bash
@needs_uv
def test_install_script_refuses_an_unlisted_wheel(tmp_path: Path) -> None:
    release = tmp_path / "release"
    write_release(release, (*WHEELS, "requirements.lock"))
    (release / "achilles_extra-0.1.0-py3-none-any.whl").write_bytes(b"extra")
    home, result = run_installer(tmp_path, "--wheels-dir", str(release))
    assert result.returncode == 1
    assert "is not listed in SHA256SUMS" in result.stderr
    assert not (home / "venv").exists()
