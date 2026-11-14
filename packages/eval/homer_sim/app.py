from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Form

from homer_sim import errors, routes_calendar, routes_gmail, routes_people
from homer_sim.deps import Sim
from homer_sim.errors import ApiError
from homer_sim.state import DEFAULT_SEED, State

ACCESS_TOKEN_TTL = 3599


def create_app(seed_path: Path = DEFAULT_SEED) -> FastAPI:
    app = FastAPI(title="Homer Google simulator")
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

    @app.post("/_sim/expire-history")
    def expire_history(sim: Sim) -> dict[str, int]:
        sim.mailbox.expire_history()
        return sim.counts()

    @app.post("/_sim/people-cold")
    def people_cold(sim: Sim, times: int = 1) -> dict[str, int]:
        sim.people_cold = times
        return {"people_cold": times}

    @app.get("/_sim/people-queries")
    def people_queries(sim: Sim) -> list[str]:
        return sim.people_queries

    @app.post("/_sim/fail-once")
    def fail_once(sim: Sim, body: dict[str, list[str]]) -> dict[str, int]:
        """The next fetch of each listed message id answers 500, once."""
        sim.failing_once.update(body["message_ids"])
        return sim.counts()

    @app.post("/_sim/unknown-calendars")
    def unknown_calendars(sim: Sim, body: dict[str, list[str]]) -> dict[str, int]:
        """freeBusy reports these addresses as notFound, as Google does for calendars it
        cannot see."""
        sim.unknown_calendars.update(body["emails"])
        return sim.counts()

    @app.post("/_sim/events-page-size")
    def events_page_size(sim: Sim, body: dict[str, int]) -> dict[str, int]:
        sim.events_page_size = body["size"]
        return sim.counts()

    @app.get("/_sim/state")
    def state(sim: Sim) -> dict[str, int]:
        return sim.counts()

    @app.get("/_sim/calendar-writes")
    def calendar_writes(sim: Sim) -> list[dict[str, Any]]:
        return sim.calendar_writes

    return app
