from pathlib import Path

import typer
import uvicorn

from homer_sim.app import create_app
from homer_sim.state import DEFAULT_SEED


def main(port: int = 8900, seed: Path = DEFAULT_SEED, host: str = "127.0.0.1") -> None:
    uvicorn.run(create_app(seed), host=host, port=port, log_level="warning")


app = typer.Typer(no_args_is_help=False)
app.command()(main)
