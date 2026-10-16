from fastapi import APIRouter, Request

from achilles_core import __version__
from achilles_core.api.deps import HttpClientDep, SettingsDep
from achilles_core.api.schemas.health import HealthResponse
from achilles_core.mcp.manager import SERVERS
from achilles_core.services.ollama import model_tags

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request, settings: SettingsDep, client: HttpClientDep) -> HealthResponse:
    try:
        await model_tags(client, settings.ollama_url)
        ollama = "ok"
    except Exception:
        ollama = "down"
    running = request.app.state.runtime.manager.toolsets
    return HealthResponse(
        status="ok",
        version=__version__,
        ollama=ollama,
        model=request.app.state.model.model_name,
        servers={name: "ok" if name in running else "down" for name in SERVERS},
    )
