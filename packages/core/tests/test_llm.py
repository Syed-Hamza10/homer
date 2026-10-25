import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import respx
from pydantic import SecretStr

from achilles_core.config import Settings
from achilles_core.llm import (
    PACKAGED_MANIFEST,
    REPO_MANIFEST,
    build_http_client,
    build_model,
    chat_model_tag,
    load_manifest,
)
from achilles_net import BlockedHostError, OutboundCall

HOOK_PATH = Path(__file__).resolve().parents[1] / "hatch_build.py"


def load_build_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hatch_build", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_settings() -> Settings:
    return Settings(
        achilles_passphrase=SecretStr("p"), ollama_url="http://127.0.0.1:11434", _env_file=None
    )


def test_manifest_has_both_tiers() -> None:
    tiers = load_manifest()
    assert set(tiers) == {"supported", "degraded"}
    assert chat_model_tag("supported") == tiers["supported"]["chat"]


def test_packaged_manifest_is_a_copy_of_the_repo_source() -> None:
    assert REPO_MANIFEST.exists()
    if PACKAGED_MANIFEST.exists():
        assert PACKAGED_MANIFEST.read_text() == REPO_MANIFEST.read_text()


def test_build_hook_copies_the_repo_manifest(tmp_path: Path) -> None:
    hook = load_build_hook()
    root = tmp_path / "packages" / "core"
    root.mkdir(parents=True)
    source = tmp_path / "models" / "manifest.json"
    source.parent.mkdir()
    source.write_text('{"tiers": {}}')

    target = hook.copy_manifest(root)
    assert target == root / "achilles_core" / "models" / "manifest.json"
    assert target.read_text() == '{"tiers": {}}'

    source.unlink()
    assert hook.copy_manifest(root).read_text() == '{"tiers": {}}'
    target.unlink()
    with pytest.raises(FileNotFoundError):
        hook.copy_manifest(root)


def test_allowlist_contains_exactly_the_ollama_host() -> None:
    client = build_http_client(make_settings())
    assert client._allowlist.hosts == frozenset({"127.0.0.1:11434"})


@pytest.mark.respx(assert_all_called=False)
async def test_other_hosts_are_refused_and_logged(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get("https://example.com/").respond(200)
    calls: list[OutboundCall] = []
    async with build_http_client(make_settings(), log=calls.append) as client:
        with pytest.raises(BlockedHostError):
            await client.get("https://example.com/")
    assert not route.called
    assert calls[0].host == "example.com"
    assert calls[0].status is None


async def test_ollama_host_is_allowed(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("http://127.0.0.1:11434/api/tags").respond(200, json={"models": []})
    async with build_http_client(make_settings()) as client:
        response = await client.get("http://127.0.0.1:11434/api/tags")
    assert response.status_code == 200


def test_build_model_points_at_ollama_with_thinking_off() -> None:
    settings = make_settings()
    client = build_http_client(settings)
    model = build_model(settings, client)
    assert model.model_name == chat_model_tag("supported") or model.model_name == chat_model_tag(
        "degraded"
    )
    assert model.settings == {"openai_reasoning_effort": "none", "temperature": 0.2}
    assert model.base_url == "http://127.0.0.1:11434/v1/"
