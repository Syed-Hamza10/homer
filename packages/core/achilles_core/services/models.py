import time

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import Model

from achilles_core.llm import load_manifest
from achilles_core.platform import Tier, hardware_tier

SMOKE_PROMPT = "Reply with exactly the word PONG and nothing else."


class TierOption(BaseModel):
    tier: str
    tag: str
    context: int


class ModelOptions(BaseModel):
    selected_tier: Tier | None
    effective_tier: Tier
    tiers: list[TierOption]


class SmokeResult(BaseModel):
    ok: bool
    text: str = ""
    error: str = ""
    latency_ms: int


def options(selected: Tier | None) -> ModelOptions:
    manifest = load_manifest()
    return ModelOptions(
        selected_tier=selected,
        effective_tier=selected or hardware_tier(),
        tiers=[
            TierOption(tier=tier, tag=data["chat"], context=data["context"])
            for tier, data in manifest.items()
        ],
    )


async def smoke(model: Model) -> SmokeResult:
    started = time.perf_counter()
    try:
        result = await Agent(model, output_type=str).run(SMOKE_PROMPT)
    except Exception as error:
        latency_ms = round((time.perf_counter() - started) * 1000)
        return SmokeResult(
            ok=False, error=f"{type(error).__name__}: {error}", latency_ms=latency_ms
        )
    latency_ms = round((time.perf_counter() - started) * 1000)
    return SmokeResult(ok=True, text=result.output.strip(), latency_ms=latency_ms)
