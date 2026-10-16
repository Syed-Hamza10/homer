from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Form

from achilles_sim import errors, routes_calendar, routes_gmail, routes_people
from achilles_sim.deps import Sim
from achilles_sim.errors import ApiError
from achilles_sim.state import DEFAULT_SEED, State

ACCESS_TOKEN_TTL = 3599


def create_app(seed_path: Path = DEFAULT_SEED) -> FastAPI:
    app = FastAPI(title="Achilles Google simulator")
    app.state.sim = State(seed_path)
    errors.install(app)
    app.include_router(routes_gmail.router)
    app.include_router(routes_calendar.router)
    app.include_router(routes_people.router)

    @app.post("/token")
    def token(
        sim: Sim, grant_type: Annotated[str, Form()], refresh_token: Annotated[str, Form()] = ""
    ) -> dict[str, Any]:
        if grant_type != "refresh_token" or not refresh_token:
            raise ApiError(400, "invalid_grant")
        return {
            "access_token": sim.issue_token(),
            "expires_in": ACCESS_TOKEN_TTL,
            "token_type": "Bearer",
        }

    @app.post("/_sim/reset")
    def reset(sim: Sim) -> dict[str, int]:
        sim.reset()
        return sim.counts()

    @app.get("/_sim/state")
    def state(sim: Sim) -> dict[str, int]:
        return sim.counts()

    return app
