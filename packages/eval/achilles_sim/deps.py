from typing import Annotated

from fastapi import Depends, Header, Request

from achilles_sim.errors import ApiError
from achilles_sim.state import State


def state(request: Request) -> State:
    return request.app.state.sim


def bearer(
    sim: Annotated[State, Depends(state)], authorization: Annotated[str | None, Header()] = None
) -> None:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme != "Bearer" or token not in sim.tokens:
        raise ApiError(401, "Request had invalid authentication credentials.")


Sim = Annotated[State, Depends(state)]
Authed = Depends(bearer)
