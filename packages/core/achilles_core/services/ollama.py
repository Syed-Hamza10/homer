from achilles_net import AllowlistedClient


async def model_tags(client: AllowlistedClient, ollama_url: str, timeout: float = 2.0) -> list[str]:
    response = await client.get(f"{ollama_url}/api/tags", timeout=timeout)
    response.raise_for_status()
    return [model["name"] for model in response.json()["models"]]
