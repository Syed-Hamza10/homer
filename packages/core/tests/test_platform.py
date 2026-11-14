import subprocess
from pathlib import Path

import pytest

from homer_core import platform


def link_localtime(tmp_path: Path, target: str) -> Path:
    link = tmp_path / "localtime"
    link.symlink_to(target)
    return link


def test_localtime_zone_reads_the_name_after_zoneinfo(tmp_path: Path) -> None:
    link = link_localtime(tmp_path, "/var/db/timezone/zoneinfo/Europe/London")
    assert platform.localtime_zone(link) == "Europe/London"


def test_localtime_zone_handles_relative_links(tmp_path: Path) -> None:
    link = link_localtime(tmp_path, "../usr/share/zoneinfo/America/Sao_Paulo")
    assert platform.localtime_zone(link) == "America/Sao_Paulo"


def test_localtime_zone_ignores_files_and_foreign_links(tmp_path: Path) -> None:
    (tmp_path / "plain").write_bytes(b"TZif")
    assert platform.localtime_zone(tmp_path / "plain") is None
    assert platform.localtime_zone(link_localtime(tmp_path, "/somewhere/else")) is None
    assert platform.localtime_zone(tmp_path / "missing") is None


def test_known_timezone() -> None:
    assert platform.known_timezone("Asia/Karachi")
    assert not platform.known_timezone("Mars/Olympus")
    assert not platform.known_timezone("")


def test_darwin_uses_localtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "localtime_zone", lambda: "Europe/Paris")
    monkeypatch.setattr(platform, "timedatectl_zone", lambda: "Asia/Tokyo")
    assert platform.system_timezone() == "Europe/Paris"


def test_linux_prefers_timedatectl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform.platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "timedatectl_zone", lambda: "Asia/Tokyo")
    monkeypatch.setattr(platform, "etc_timezone", lambda: "Europe/Paris")
    monkeypatch.setattr(platform, "localtime_zone", lambda: "Europe/London")
    assert platform.system_timezone() == "Asia/Tokyo"


def test_linux_falls_through_to_etc_timezone_then_localtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform.platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "timedatectl_zone", lambda: None)
    monkeypatch.setattr(platform, "etc_timezone", lambda: "Not/AZone")
    monkeypatch.setattr(platform, "localtime_zone", lambda: "Europe/London")
    assert platform.system_timezone() == "Europe/London"


def test_system_timezone_is_none_when_nothing_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform.platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "timedatectl_zone", lambda: None)
    monkeypatch.setattr(platform, "etc_timezone", lambda: None)
    monkeypatch.setattr(platform, "localtime_zone", lambda: None)
    assert platform.system_timezone() is None


def test_timedatectl_zone_without_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform.shutil, "which", lambda name: None)
    assert platform.timedatectl_zone() is None


def test_timedatectl_zone_reads_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform.shutil, "which", lambda name: "/usr/bin/timedatectl")
    monkeypatch.setattr(
        platform.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="Europe/Berlin\n", stderr=""),
    )
    assert platform.timedatectl_zone() == "Europe/Berlin"


def test_restart_without_a_service_file_explains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(platform.platform, "system", lambda: "Darwin")
    calls: list[list[str]] = []
    monkeypatch.setattr(platform.subprocess, "run", lambda command, **_: calls.append(command))
    with pytest.raises(FileNotFoundError, match="homer serve"):
        platform.restart_service()
    assert calls == []


def test_restart_kicks_the_launch_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(platform.platform, "system", lambda: "Darwin")
    agent = platform.server_service_file()
    agent.parent.mkdir(parents=True)
    agent.write_text("<plist/>")
    calls: list[list[str]] = []
    monkeypatch.setattr(platform.subprocess, "run", lambda command, **_: calls.append(command))
    platform.restart_service()
    assert calls[0][:3] == ["launchctl", "kickstart", "-k"]
    assert calls[0][3].endswith("/dev.homer.server")


def test_remove_service_unloads_and_deletes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(platform.platform, "system", lambda: "Linux")
    unit = platform.server_service_file()
    assert unit == tmp_path / ".config" / "systemd" / "user" / "homer.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("[Unit]")
    calls: list[list[str]] = []
    monkeypatch.setattr(platform.subprocess, "run", lambda command, **_: calls.append(command))
    platform.remove_service(unit)
    assert calls == [["systemctl", "--user", "disable", "--now", "homer.service"]]
    assert not unit.exists()
