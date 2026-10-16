import asyncio

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from achilles_core.config import Settings
from achilles_core.db.session import make_engine, run_migrations
from achilles_core.doctor import run_checks
from achilles_core.platform import ensure_home

app = typer.Typer(no_args_is_help=True)
db = typer.Typer(no_args_is_help=True)
app.add_typer(db, name="db")


@app.command()
def serve() -> None:
    settings = Settings()
    uvicorn.run(
        "achilles_core.main:create_app", factory=True, host=settings.host, port=settings.port
    )


@app.command()
def doctor() -> None:
    checks = asyncio.run(run_checks(Settings()))
    table = Table("Check", "Result", "Detail")
    for check in checks:
        table.add_row(check.name, "[green]ok" if check.ok else "[red]FAIL", check.detail)
    Console().print(table)
    raise typer.Exit(code=0 if all(check.ok for check in checks) else 1)


@db.command()
def upgrade() -> None:
    settings = Settings()
    ensure_home(settings.achilles_home)
    run_migrations(make_engine(settings.achilles_home))
