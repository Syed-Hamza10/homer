import hashlib
import json
import shutil
import subprocess
import threading
import zipfile
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from homer_core import cli
from homer_core.cli import app
from homer_core.update import REPO

pytestmark = pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("curl") is None, reason="uv and curl are needed"
)
runner = CliRunner()
WHEEL = "homer_core-9.9.9-py3-none-any.whl"


def fake_wheel(path: Path, doctor_exit: int) -> None:
    info = "homer_core-9.9.9.dist-info"
    files = {
        "fake_homer.py": (
            "import sys\n\n\ndef main() -> None:\n"
            f"    raise SystemExit({doctor_exit} if sys.argv[1:] == ['doctor', '--quick'] else 2)\n"
        ),
        f"{info}/METADATA": "Metadata-Version: 2.1\nName: homer-core\nVersion: 9.9.9\n",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{info}/entry_points.txt": "[console_scripts]\nhomer = fake_homer:main\n",
    }
    files[f"{info}/RECORD"] = "".join(f"{name},,\n" for name in [*files, f"{info}/RECORD"])
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


class FakeRelease:
    def __init__(self, root: Path, base_url: str) -> None:
        self.assets = root / "assets"
        self.assets.mkdir(parents=True)
        self.metadata = root / "repos" / REPO / "releases" / "latest"
        self.metadata.parent.mkdir(parents=True)
        self.base_url = base_url

    def publish(self, doctor_exit: int = 0, tamper: bool = False) -> None:
        fake_wheel(self.assets / WHEEL, doctor_exit)
        (self.assets / "requirements.lock").write_text("# empty\n")
        digest = hashlib.sha256((self.assets / WHEEL).read_bytes()).hexdigest()
        (self.assets / "SHA256SUMS").write_text(f"{digest}  {WHEEL}\n")
        if tamper:
            (self.assets / WHEEL).write_bytes(b"not the wheel")
        assets = [
            {"name": path.name, "url": f"{self.base_url}/assets/{path.name}"}
            for path in self.assets.iterdir()
        ]
        self.metadata.write_text(json.dumps({"assets": assets}))


@pytest.fixture
def release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRelease]:
    root = tmp_path / "release"
    root.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("HOMER_RELEASE_API", base_url)
    yield FakeRelease(root, base_url)
    server.shutdown()
    server.server_close()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    (path / "venv" / "bin").mkdir(parents=True)
    path.chmod(0o700)
    (path / "venv" / "marker").write_text("live")
    monkeypatch.setenv("HOMER_HOME", str(path))
    monkeypatch.setenv("HOMER_PASSPHRASE", "test-pass")
    return path


@pytest.fixture
def restarts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(cli, "restart_service", lambda: calls.append("restart"))
    return calls


def test_update_stages_verifies_and_swaps(home: Path, release: FakeRelease, restarts: list) -> None:
    release.publish()
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0, result.output
    assert (home / "venv" / "bin" / "homer").exists()
    assert (home / "venv.prev" / "marker").read_text() == "live"
    swapped = subprocess.run([str(home / "venv" / "bin" / "homer"), "doctor", "--quick"])
    assert swapped.returncode == 0
    assert not (home / "venv.new").exists()
    assert restarts == ["restart"]
    assert "venv.prev" in result.output


def test_update_refuses_a_checksum_mismatch(
    home: Path, release: FakeRelease, restarts: list
) -> None:
    release.publish(tamper=True)
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 1
    assert "checksum mismatch" in result.output
    assert (home / "venv" / "marker").read_text() == "live"
    assert not (home / "venv.new").exists()
    assert not (home / "venv.prev").exists()
    assert restarts == []


def test_update_keeps_the_live_venv_when_doctor_fails(
    home: Path, release: FakeRelease, restarts: list
) -> None:
    release.publish(doctor_exit=1)
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 1
    assert "doctor --quick" in result.output
    assert (home / "venv" / "marker").read_text() == "live"
    assert not (home / "venv.new").exists()
    assert restarts == []


def test_rollback_swaps_the_previous_venv_back(
    home: Path, release: FakeRelease, restarts: list
) -> None:
    release.publish()
    assert runner.invoke(app, ["update"]).exit_code == 0
    result = runner.invoke(app, ["rollback"])
    assert result.exit_code == 0, result.output
    assert (home / "venv" / "marker").read_text() == "live"
    assert (home / "venv.prev" / "bin" / "homer").exists()
    assert restarts == ["restart", "restart"]


def test_rollback_without_a_previous_venv_fails(home: Path, restarts: list) -> None:
    result = runner.invoke(app, ["rollback"])
    assert result.exit_code == 1
    assert "venv.prev" in result.output
    assert restarts == []
