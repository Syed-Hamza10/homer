import asyncio
import subprocess
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from sqlmodel import Session

from achilles_core.config import Settings
from achilles_core.db.models import User
from achilles_core.db.session import make_engine, run_migrations
from achilles_core.doctor import run_checks
from achilles_core.llm import load_manifest
from achilles_core.mcp.manager import find_executable
from achilles_core.platform import ensure_home, restart_service, tail_file
from achilles_core.privacy_hosts import privacy_markdown
from achilles_core.services.backup import create_backup
from achilles_core.services.rules import get_rules, save_rules
from achilles_core.services.users import first_user, forget_user
from achilles_core.update import UpdateError
from achilles_core.update import rollback as rollback_venv
from achilles_core.update import update as update_venv

TIERS = ("supported", "degraded")

app = typer.Typer(no_args_is_help=True)
db = typer.Typer(no_args_is_help=True)
model = typer.Typer(no_args_is_help=True)
setup = typer.Typer(no_args_is_help=True)
app.add_typer(db, name="db")
app.add_typer(model, name="model")
app.add_typer(setup, name="setup")


def open_session(settings: Settings) -> Session:
    ensure_home(settings.achilles_home)
    engine = make_engine(settings.achilles_home)
    run_migrations(engine)
    return Session(engine)


@app.command()
def serve() -> None:
    settings = Settings()
    uvicorn.run(
        "achilles_core.main:create_app", factory=True, host=settings.host, port=settings.port
    )


@app.command()
def doctor(
    quick: Annotated[
        bool, typer.Option("--quick", help="Skip the Ollama and hardware checks.")
    ] = False,
) -> None:
    checks = asyncio.run(run_checks(Settings(), quick=quick))
    table = Table("Check", "Result", "Detail")
    for check in checks:
        table.add_row(check.name, "[green]ok" if check.ok else "[red]FAIL", check.detail)
    Console().print(table)
    raise typer.Exit(code=0 if all(check.ok for check in checks) else 1)


@app.command()
def backup(
    include_secrets: Annotated[
        bool, typer.Option("--include-secrets", help="Also archive credentials/ and .env.")
    ] = False,
) -> None:
    path = create_backup(Settings().achilles_home, include_secrets=include_secrets)
    Console().print(f"Backup written to {path}")
    if not include_secrets:
        Console().print("Secrets were left out; pass --include-secrets to archive them.")


@app.command()
def restart() -> None:
    restart_service()
    Console().print("Achilles restarted.")


@app.command()
def logs(follow: Annotated[bool, typer.Option("--follow", "-f")] = False) -> None:
    path = Settings().achilles_home / "logs" / "achilles.log"
    if not path.exists():
        raise typer.BadParameter(f"{path} does not exist yet")
    tail_file(path, 200, follow)


@app.command()
def privacy(output: Annotated[Path | None, typer.Option("--output", "-o")] = None) -> None:
    text = privacy_markdown()
    if output is None:
        Console().print(text)
        return
    output.write_text(text)
    Console().print(f"Wrote {output}")


@app.command()
def forget(
    user: Annotated[int | None, typer.Option(help="User id; defaults to the first user.")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Delete without asking.")] = False,
) -> None:
    settings = Settings()
    with open_session(settings) as session:
        target = session.get(User, user) if user is not None else first_user(session)
        if target is None:
            raise typer.BadParameter(f"user {user} not found")
        if not yes:
            Console().print(f"Would delete user {target.id} and every local row. Pass --yes.")
            raise typer.Exit(code=1)
        deleted = forget_user(session, target)
    summary = ", ".join(f"{count} {name}" for name, count in sorted(deleted.items()))
    Console().print(f"Deleted {summary}.")


def restart_or_explain(done: str) -> None:
    try:
        restart_service()
    except (OSError, subprocess.CalledProcessError):
        Console().print(f"{done}; restart the Achilles service manually.")
    else:
        Console().print(f"{done} and restarted.")


@app.command()
def update(
    version: Annotated[str, typer.Option(help="Release tag, or 'latest'.")] = "latest",
) -> None:
    home = Settings().achilles_home
    try:
        update_venv(home, version)
    except UpdateError as error:
        Console().print(f"[red]Update aborted; the current install is untouched.[/red]\n{error}")
        raise typer.Exit(code=1) from error
    restart_or_explain(f"Updated to {version}; the previous environment is in {home / 'venv.prev'}")


@app.command()
def rollback() -> None:
    home = Settings().achilles_home
    try:
        rollback_venv(home)
    except UpdateError as error:
        Console().print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    restart_or_explain("Rolled back to the previous environment")


@model.command("use")
def model_use(choice: str) -> None:
    manifest = load_manifest()
    by_tag = {data["chat"]: tier for tier, data in manifest.items()}
    selected = choice if choice in TIERS else by_tag.get(choice)
    if selected is None:
        raise typer.BadParameter(
            f"choose a tag ({', '.join(by_tag)}) or a tier ({', '.join(TIERS)})"
        )
    settings = Settings()
    with open_session(settings) as session:
        user = first_user(session)
        if user is None:
            raise typer.BadParameter("no user yet; start Achilles once first")
        rules = get_rules(session, user.id)
        rules.model_tier = selected
        save_rules(session, user.id, rules)
    Console().print(f"Model tier set to {selected} ({choice}). Run `achilles restart` to load it.")


@setup.command("google")
def setup_google() -> None:
    executable = find_executable("achilles-mcp-google-setup")
    if executable is None:
        raise typer.BadParameter("achilles-mcp-google-setup is not installed")
    subprocess.run([executable], check=True)


@db.command()
def upgrade() -> None:
    settings = Settings()
    ensure_home(settings.achilles_home)
    run_migrations(make_engine(settings.achilles_home))
