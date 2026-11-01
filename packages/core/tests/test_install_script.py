import hashlib
import os
import re
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
        "HOMER_HOME": str(home),
        "HOMER_PASSPHRASE": "test-pass",
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


WHEELS = ("homer_core-0.1.0-py3-none-any.whl", "homer_net-0.1.0-py3-none-any.whl")


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
    assert re.search(r"timezone: [A-Za-z_]+(/[A-Za-z_+-]+)*$", result.stdout, re.MULTILINE)
    assert re.search(r"\.env with TIMEZONE=\S+ and pull", result.stdout)
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
    (release / "homer_extra-0.1.0-py3-none-any.whl").write_bytes(b"extra")
    home, result = run_installer(tmp_path, "--wheels-dir", str(release))
    assert result.returncode == 1
    assert "is not listed in SHA256SUMS" in result.stderr
    assert not (home / "venv").exists()


def render(tmp_path: Path, name: str) -> str:
    _, result = run_installer(tmp_path, "--render", name)
    assert result.returncode == 0, result.stderr
    return result.stdout


OLLAMA_ENV = {
    "OLLAMA_CONTEXT_LENGTH": "16384",
    "OLLAMA_KEEP_ALIVE": "30m",
    "OLLAMA_FLASH_ATTENTION": "1",
    "OLLAMA_KV_CACHE_TYPE": "q8_0",
}


@needs_bash
def test_ollama_launch_agent_carries_the_environment(tmp_path: Path) -> None:
    plist = render(tmp_path, "ollama-plist")
    assert "<string>dev.homer.ollama</string>" in plist
    assert "<key>KeepAlive</key><true/>" in plist
    assert "<key>RunAtLoad</key><true/>" in plist
    for key, value in OLLAMA_ENV.items():
        assert f"<key>{key}</key><string>{value}</string>" in plist


@needs_bash
def test_ollama_systemd_dropin_carries_the_environment(tmp_path: Path) -> None:
    dropin = render(tmp_path, "ollama-dropin")
    assert dropin.startswith("[Service]\n")
    for key, value in OLLAMA_ENV.items():
        assert f'Environment="{key}={value}"' in dropin


@needs_bash
def test_server_launch_agent_restarts_and_points_at_the_venv(tmp_path: Path) -> None:
    home = tmp_path / "home"
    plist = render(tmp_path, "server-plist")
    assert "<string>dev.homer.server</string>" in plist
    assert f"<string>{home}/venv/bin/homer</string><string>serve</string>" in plist
    assert f"<key>HOMER_HOME</key><string>{home}</string>" in plist
    assert "<key>KeepAlive</key><true/>" in plist
    assert "<key>RunAtLoad</key><true/>" in plist


@needs_bash
def test_server_systemd_unit_restarts_and_points_at_the_venv(tmp_path: Path) -> None:
    home = tmp_path / "home"
    unit = render(tmp_path, "server-unit")
    assert f"ExecStart={home}/venv/bin/homer serve" in unit
    assert f"Environment=HOMER_HOME={home}" in unit
    assert "Restart=always" in unit
    assert "WantedBy=default.target" in unit


@needs_bash
def test_render_rejects_an_unknown_service(tmp_path: Path) -> None:
    _, result = run_installer(tmp_path, "--render", "nope")
    assert result.returncode == 1
    assert "unknown service definition" in result.stderr
