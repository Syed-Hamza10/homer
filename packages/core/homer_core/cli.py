import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from sqlmodel import Session

from homer_core.config import HOME, Settings
from homer_core.db.models import User
from homer_core.db.session import make_engine, run_migrations
from homer_core.doctor import run_checks
from homer_core.llm import load_manifest
from homer_core.mcp.manager import find_executable
from homer_core.platform import (
    OLLAMA_DROPIN,
    ensure_home,
    ollama_service_file,
    remove_service,
    restart_service,
    server_service_file,
    tail_file,
)
from homer_core.privacy_hosts import privacy_markdown
from homer_core.services.backup import create_backup
from homer_core.services.rules import get_rules, save_rules
from homer_core.services.users import first_user, forget_user
from homer_core.update import UpdateError
from homer_core.update import rollback as rollback_venv
from homer_core.update import update as update_venv

TIERS = ("supported", "degraded")
PROGRAM_DIRS = ("venv", "venv.new", "venv.prev", "venv.rollback", "bin")

app = typer.Typer(no_args_is_help=True)
db = typer.Typer(no_args_is_help=True)
model = typer.Typer(no_args_is_help=True)
setup = typer.Typer(no_args_is_help=True)
app.add_typer(db, name="db", help="Database maintenance.")
app.add_typer(model, name="model", help="Choose the AI model tier.")
app.add_typer(setup, name="setup", help="Connect accounts.")


def open_session(settings: Settings) -> Session:
    ensure_home(settings.homer_home)
    engine = make_engine(settings.homer_home)
    run_migrations(engine)
    return Session(engine)


@app.command(help="Run Homer in the foreground.")
def serve() -> None:
    settings = Settings()
    uvicorn.run("homer_core.main:create_app", factory=True, host=settings.host, port=settings.port)


@app.command(help="Check Ollama, the model, the allowlist and the home folder.")
def doctor(
    quick: Annotated[
        bool, typer.Option("--quick", help="Skip the Ollama and hardware checks.")
    ] = False,
) -> None:
    checks = asyncio.run(run_checks(Settings(), quick=quick))
    table = Table("Check", "Result", "Detail")
    for check in checks:
        result = "[green]ok" if check.ok else "[red]FAIL" if check.required else "[yellow]WARN"
        table.add_row(check.name, result, check.detail)
    Console().print(table)
    raise typer.Exit(code=0 if all(check.ok for check in checks if check.required) else 1)


@app.command(help="Write a backup of the database to ~/.homer/backups.")
def backup(
    include_secrets: Annotated[
        bool, typer.Option("--include-secrets", help="Also archive credentials/ and .env.")
    ] = False,
) -> None:
    path = create_backup(Settings().homer_home, include_secrets=include_secrets)
    Console().print(f"Backup written to {path}")
    if not include_secrets:
        Console().print("Secrets were left out; pass --include-secrets to archive them.")


@app.command(help="Restart the Homer background service.")
def restart() -> None:
    try:
        restart_service()
    except (OSError, subprocess.CalledProcessError) as error:
        Console().print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    Console().print("Homer restarted.")


@app.command(help="Show the Homer log.")
def logs(follow: Annotated[bool, typer.Option("--follow", "-f")] = False) -> None:
    path = Settings().homer_home / "logs" / "homer.log"
    if not path.exists():
        raise typer.BadParameter(f"{path} does not exist yet")
    tail_file(path, 200, follow)


@app.command(help="Print the list of hosts Homer may contact.")
def privacy(output: Annotated[Path | None, typer.Option("--output", "-o")] = None) -> None:
    text = privacy_markdown()
    if output is None:
        Console().print(text)
        return
    output.write_text(text)
    Console().print(f"Wrote {output}")


@app.command(help="Delete the local user and all of their data.")
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
        Console().print(f"{done}; restart the Homer service manually.")
    else:
        Console().print(f"{done} and restarted.")


@app.command(help="Install the newest release beside the current one, then switch.")
def update(
    version: Annotated[str, typer.Option(help="Release tag, or 'latest'.")] = "latest",
) -> None:
    home = Settings().homer_home
    try:
        update_venv(home, version)
    except UpdateError as error:
        Console().print(f"[red]Update aborted; the current install is untouched.[/red]\n{error}")
        raise typer.Exit(code=1) from error
    restart_or_explain(f"Updated to {version}; the previous environment is in {home / 'venv.prev'}")


@app.command(help="Switch back to the environment before the last update.")
def rollback() -> None:
    home = Settings().homer_home
    try:
        rollback_venv(home)
    except UpdateError as error:
        Console().print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    restart_or_explain("Rolled back to the previous environment")


@app.command(help="Remove the services and the program; keep the data unless --purge.")
def uninstall(
    purge: Annotated[
        bool, typer.Option("--purge", help="Also delete all data, credentials and backups.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Remove without asking.")] = False,
) -> None:
    console = Console()
    found = (server_service_file(), ollama_service_file())
    services = [path for path in found if path is not None and path.exists()]
    if purge:
        targets = [HOME] if HOME.exists() else []
    else:
        targets = [HOME / name for name in PROGRAM_DIRS if (HOME / name).exists()]
    if not services and not targets:
        console.print(f"Nothing to remove: no Homer service and nothing in {HOME}.")
        return
    console.print("This removes:")
    for path in [*services, *targets]:
        console.print(f"  {path}")
    if purge:
        console.print("[red]That includes every conversation, credential and backup.[/red]")
    else:
        console.print(f"Your data stays in {HOME}; pass --purge to delete it too.")
    if not yes and not typer.confirm("Remove Homer?", default=False):
        console.print("Nothing removed.")
        raise typer.Exit(code=1)
    tags = sorted({tier[key] for tier in load_manifest().values() for key in ("chat", "embed")})
    for path in services:
        remove_service(path)
    for path in targets:
        shutil.rmtree(path, ignore_errors=True)
    console.print("Homer is uninstalled.")
    console.print(f"The models stay in Ollama. To free the space: ollama rm {' '.join(tags)}")
    if OLLAMA_DROPIN.exists():
        console.print(f"Remove the Ollama settings Homer added: sudo rm {OLLAMA_DROPIN}")


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
            raise typer.BadParameter("no user yet; start Homer once first")
        rules = get_rules(session, user.id)
        rules.model_tier = selected
        save_rules(session, user.id, rules)
    Console().print(f"Model tier set to {selected} ({choice}). Run `homer restart` to load it.")


@app.command("eval", help="Run the model smoke suite (developer tool).")
def eval_(
    smoke: Annotated[
        bool, typer.Option("--smoke", help="Run the 10-task smoke suite, 3 runs each.")
    ] = False,
) -> None:
    if not smoke:
        typer.echo("Pass --smoke; it is the only mode available.", err=True)
        raise typer.Exit(code=2)
    executable = find_executable("homer-eval")
    if executable is None:
        raise typer.BadParameter("homer-eval is not installed; it ships with the dev workspace")
    raise typer.Exit(code=subprocess.run([executable, "--runs", "3"], check=False).returncode)


@setup.command("google", help="Connect a Google account in the browser.")
def setup_google() -> None:
    executable = find_executable("homer-mcp-google-setup")
    if executable is None:
        raise typer.BadParameter("homer-mcp-google-setup is not installed")
    subprocess.run([executable], check=True)


@db.command()
def upgrade() -> None:
    settings = Settings()
    ensure_home(settings.homer_home)
    run_migrations(make_engine(settings.homer_home))
