import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "install.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")
def test_install_script_has_valid_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")
def test_install_script_dry_run_changes_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {**os.environ, "HOME": str(tmp_path), "ACHILLES_HOME": str(home)}
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--dry-run",
            "--force",
            "--skip-ollama",
            "--no-service",
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Dry run only" in result.stdout
    assert str(home) in result.stdout
    assert not home.exists()
