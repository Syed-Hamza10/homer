import stat
from pathlib import Path

from pydantic import SecretStr

from achilles_core.config import Settings, own_origins, session_secret


def test_home_is_expanded() -> None:
    settings = Settings(
        achilles_home=Path("~/x"), achilles_passphrase=SecretStr("p"), _env_file=None
    )
    assert "~" not in str(settings.achilles_home)
    assert settings.achilles_home.is_absolute()


def test_own_origins_include_both_loopback_names_and_extras() -> None:
    settings = Settings(
        achilles_passphrase=SecretStr("p"),
        port=9000,
        extra_origins=["http://localhost:5173"],
        _env_file=None,
    )
    assert own_origins(settings) == {
        "http://127.0.0.1:9000",
        "http://localhost:9000",
        "http://localhost:5173",
    }


def test_session_secret_is_created_once_with_private_mode(tmp_path: Path) -> None:
    settings = Settings(achilles_home=tmp_path, achilles_passphrase=SecretStr("p"), _env_file=None)
    first = session_secret(settings)
    second = session_secret(settings)
    assert first == second
    assert len(first) >= 32
    assert stat.S_IMODE((tmp_path / "session_secret").stat().st_mode) == 0o600


def test_settings_read_env_file(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    (tmp_path / ".env").write_text("ACHILLES_PASSPHRASE=from-file\nPORT=8123\n")
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=tmp_path / ".env")
    assert settings.achilles_passphrase.get_secret_value() == "from-file"
    assert settings.port == 8123


def test_timezone_falls_back_to_the_system_then_utc(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("TIMEZONE", raising=False)
    monkeypatch.setattr("achilles_core.config.system_timezone", lambda: "Europe/Paris")
    assert Settings(achilles_passphrase=SecretStr("p"), _env_file=None).timezone == "Europe/Paris"
    monkeypatch.setattr("achilles_core.config.system_timezone", lambda: None)
    assert Settings(achilles_passphrase=SecretStr("p"), _env_file=None).timezone == "UTC"
    monkeypatch.setenv("TIMEZONE", "Asia/Karachi")
    assert Settings(achilles_passphrase=SecretStr("p"), _env_file=None).timezone == "Asia/Karachi"
