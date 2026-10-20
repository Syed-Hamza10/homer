from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from achilles_core.llm import chat_model_tag
from achilles_core.platform import hardware_tier
from achilles_net import Allowlist, AllowlistedClient
from achilles_net.allowlist import host_key


def default_model() -> str:
    return chat_model_tag(hardware_tier())


def build_model(base_url: str, name: str) -> tuple[Model, AllowlistedClient]:
    client = AllowlistedClient(Allowlist([host_key(base_url)]))
    provider = OpenAIProvider(base_url=base_url, api_key="local", http_client=client)
    model = OpenAIChatModel(
        name,
        provider=provider,
        settings=OpenAIChatModelSettings(openai_reasoning_effort="none", temperature=0.2),
    )
    return model, client
