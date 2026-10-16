from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic_ai.models import Model
from sqlmodel import Session

from achilles_core import __version__
from achilles_core.agent.agent import build_agent
from achilles_core.api import auth, chat, conversations, health
from achilles_core.auth import LoginLimiter, origin_middleware
from achilles_core.config import Settings, own_origins, session_secret
from achilles_core.db.session import make_engine, run_migrations
from achilles_core.llm import build_http_client, build_model
from achilles_core.platform import ensure_home
from achilles_core.services.errors import DomainError
from achilles_core.services.outbound_log import make_logger
from achilles_core.services.users import ensure_first_user

STATIC = Path(__file__).parent / "static"


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


def create_app(settings: Settings | None = None, model: Model | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ensure_home(settings.achilles_home)
        engine = make_engine(settings.achilles_home)
        run_migrations(engine)
        with Session(engine) as session:
            ensure_first_user(session, settings.user_name, settings.timezone)
        http_client = build_http_client(settings, make_logger(engine))
        app.state.engine = engine
        app.state.session_secret = session_secret(settings)
        app.state.limiter = LoginLimiter()
        app.state.http_client = http_client
        app.state.model = model or build_model(settings, http_client)
        app.state.agent = build_agent(app.state.model)
        yield
        await http_client.aclose()

    app = FastAPI(title="Achilles", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.middleware("http")(origin_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(own_origins(settings)),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(DomainError, domain_error_handler)
    for router in (health.router, auth.router, chat.router, conversations.router):
        app.include_router(router)
    if (STATIC / "index.html").exists():
        mount_spa(app, STATIC)
    return app


def mount_spa(app: FastAPI, static: Path) -> None:
    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = (static / path).resolve()
        if target.is_file() and target.is_relative_to(static):
            return FileResponse(target)
        return FileResponse(static / "index.html")
