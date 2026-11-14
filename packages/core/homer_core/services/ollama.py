import structlog
from pydantic_ai import Agent

from homer_core.agent.intents import Intents, prime
from homer_net import AllowlistedClient

log = structlog.get_logger(__name__)

KEEP_ALIVE = "10m"
WARM_TIMEOUT = 120.0


async def model_tags(client: AllowlistedClient, ollama_url: str, timeout: float = 2.0) -> list[str]:
    response = await client.get(f"{ollama_url}/api/tags", timeout=timeout)
    response.raise_for_status()
    return [model["name"] for model in response.json()["models"]]


async def warm(client: AllowlistedClient, ollama_url: str, model: str) -> bool:
    """Loads the model into memory without generating anything, and keeps it loaded for
    KEEP_ALIVE; a failure is logged, never raised."""
    try:
        response = await client.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "keep_alive": KEEP_ALIVE},
            timeout=WARM_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as error:
        log.warning("model_warm_failed", model=model, error=str(error))
        return False
    log.info("model_warm", model=model)
    return True


async def warm_up(
    client: AllowlistedClient, ollama_url: str, model: str, intents: Agent[None, Intents]
) -> None:
    """Loads the model, then caches the intent prompt's static prefix."""
    if await warm(client, ollama_url, model):
        await prime(intents)
