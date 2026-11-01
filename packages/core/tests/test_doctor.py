import pytest
import respx

from homer_core.config import Settings
from homer_core.doctor import run_checks
from homer_core.platform import ensure_home


def by_name(checks) -> dict[str, tuple[bool, str]]:  # noqa: ANN001
    return {check.name: (check.ok, check.detail) for check in checks}


@pytest.mark.respx(assert_all_called=False)
async def test_ollama_unreachable(settings: Settings, respx_mock: respx.MockRouter) -> None:
    ensure_home(settings.homer_home)
    respx_mock.get("http://127.0.0.1:11434/api/tags").mock(side_effect=ConnectionRefusedError())
    checks = by_name(await run_checks(settings))
    assert checks["Ollama reachable"][0] is False
    assert checks["Chat model pulled"][0] is False
    assert checks["Allowlist blocks other hosts"][0] is True
    assert checks["Home is private (0700)"][0] is True
    assert checks["Server bound to localhost"][0] is True


@pytest.mark.respx(assert_all_called=False)
async def test_ollama_reachable_but_model_missing(
    settings: Settings, respx_mock: respx.MockRouter
) -> None:
    ensure_home(settings.homer_home)
    respx_mock.get("http://127.0.0.1:11434/api/tags").respond(
        200, json={"models": [{"name": "nomic-embed-text:latest"}]}
    )
    checks = by_name(await run_checks(settings))
    assert checks["Ollama reachable"][0] is True
    assert checks["Chat model pulled"][0] is False


@pytest.mark.respx(assert_all_called=False)
async def test_all_ollama_checks_pass_when_model_is_pulled(
    settings: Settings, respx_mock: respx.MockRouter
) -> None:
    from homer_core.llm import chat_model_tag
    from homer_core.platform import hardware_tier

    ensure_home(settings.homer_home)
    respx_mock.get("http://127.0.0.1:11434/api/tags").respond(
        200, json={"models": [{"name": chat_model_tag(hardware_tier())}]}
    )
    checks = by_name(await run_checks(settings))
    assert checks["Chat model pulled"][0] is True


async def test_missing_home_and_public_host_fail(tmp_path, settings: Settings) -> None:  # noqa: ANN001
    public = settings.model_copy(update={"host": "0.0.0.0"})
    checks = by_name(await run_checks(public))
    assert checks["Home is private (0700)"] == (False, f"{settings.homer_home} missing")
    assert checks["Server bound to localhost"][0] is False


@pytest.mark.respx(assert_all_called=False)
async def test_quick_skips_ollama_and_hardware(
    settings: Settings, respx_mock: respx.MockRouter
) -> None:
    ensure_home(settings.homer_home)
    route = respx_mock.get("http://127.0.0.1:11434/api/tags").respond(200, json={"models": []})
    checks = by_name(await run_checks(settings, quick=True))
    assert set(checks) == {
        "Allowlist blocks other hosts",
        "Home is private (0700)",
        "Server bound to localhost",
    }
    assert all(ok for ok, _ in checks.values())
    assert not route.called
