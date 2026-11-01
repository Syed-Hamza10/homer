import json
from pathlib import Path
from typing import TypedDict

from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.providers.ollama import OllamaProvider

from homer_core.config import Settings
from homer_core.platform import Tier, hardware_tier
from homer_net import Allowlist, AllowlistedClient
from homer_net.allowlist import host_key
from homer_net.client import LogFn, no_log

PACKAGED_MANIFEST = Path(__file__).parent / "models" / "manifest.json"
REPO_MANIFEST = Path(__file__).resolve().parents[3] / "models" / "manifest.json"
MANIFEST = PACKAGED_MANIFEST if PACKAGED_MANIFEST.exists() else REPO_MANIFEST


class TierModels(TypedDict):
    chat: str
    embed: str
    context: int


def load_manifest() -> dict[Tier, TierModels]:
    return json.loads(MANIFEST.read_text())["tiers"]


def chat_model_tag(tier: Tier) -> str:
    return load_manifest()[tier]["chat"]


def build_http_client(settings: Settings, log: LogFn = no_log) -> AllowlistedClient:
    return AllowlistedClient(Allowlist([host_key(settings.ollama_url)]), log=log)


def build_model(
    settings: Settings, http_client: AllowlistedClient, tier: Tier | None = None
) -> Model:
    provider = OllamaProvider(base_url=f"{settings.ollama_url}/v1", http_client=http_client)
    return OllamaModel(
        chat_model_tag(tier or hardware_tier()),
        provider=provider,
        settings=OpenAIChatModelSettings(openai_reasoning_effort="none", temperature=0.2),
    )
