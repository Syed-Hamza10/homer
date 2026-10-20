import asyncio
import json
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from pydantic import SecretStr
from rich.console import Console
from rich.table import Table

from achilles_core.agent.runtime import build_runtime
from achilles_core.config import Settings
from achilles_core.mcp.manager import McpManager
from achilles_core.platform import ensure_home
from achilles_eval.model import build_model, default_model
from achilles_eval.runner import results_json, run_suite, summarise
from achilles_eval.simulator import simulator
from achilles_eval.tasks import load_tasks

app = typer.Typer(no_args_is_help=False)
SIM_TOKEN = "sim-access-token"
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = default_model()


def harness_settings(home: Path, sim_url: str, web_search: bool) -> Settings:
    return Settings(
        achilles_home=home,
        achilles_passphrase=SecretStr("eval"),
        google_api_base=sim_url,
        google_token_url=f"{sim_url}/token",
        web_search=web_search,
        scheduler_enabled=False,
        user_name="Eval",
        timezone="UTC",
        _env_file=None,
    )


def write_token(home: Path) -> None:
    token = {
        "token": SIM_TOKEN,
        "refresh_token": "sim-refresh",
        "client_id": "",
        "client_secret": "",
    }
    path = home / "credentials" / "google_token.json"
    path.write_text(json.dumps(token))
    path.chmod(0o600)


async def evaluate(
    base_url: str,
    model_name: str,
    runs: int,
    sim_url: str | None,
    task_ids: list[str],
    output: Path | None,
    web_search: bool,
) -> int:
    all_tasks = load_tasks()
    if task_ids:
        selected = [task for task in all_tasks if task.id in set(task_ids)]
        missing = set(task_ids) - {task.id for task in selected}
        if missing:
            raise typer.BadParameter(f"unknown tasks: {', '.join(sorted(missing))}")
    else:
        selected = all_tasks

    async with simulator(sim_url) as sim:
        with tempfile.TemporaryDirectory(prefix="achilles-eval-home-") as home:
            home_path = Path(home)
            ensure_home(home_path)
            write_token(home_path)
            settings = harness_settings(home_path, sim.url, web_search)
            manager = McpManager.discover(settings)
            await manager.start()
            client = None
            try:
                needed = {"google", "system"}
                if any(task.category in ("search", "multi") for task in selected):
                    needed.add("search")
                missing_servers = needed - set(manager.toolsets)
                if missing_servers:
                    raise RuntimeError(
                        f"MCP servers not running: {', '.join(sorted(missing_servers))}"
                    )
                model, client = build_model(base_url, model_name)
                runtime = build_runtime(model, manager)
                results = await run_suite(runtime, sim, selected, runs)
            finally:
                await manager.stop()
                if client is not None:
                    await client.aclose()

    summary = summarise(results)
    table = Table("Task", "Category", "Runs", "Pass", "Mean ms", "Tokens")
    for task in summary.tasks:
        table.add_row(
            task.task_id,
            task.category,
            str(task.runs),
            f"{task.passed}/{task.runs}",
            str(task.mean_latency_ms),
            str(task.input_tokens + task.output_tokens),
        )
    console = Console()
    console.print(table)
    console.print(
        f"Overall: {summary.passed}/{summary.total} passed "
        f"({summary.pass_rate:.0%}), mean {summary.mean_latency_ms} ms, "
        f"p95 {summary.p95_latency_ms} ms, "
        f"{summary.input_tokens + summary.output_tokens} tokens."
    )

    if output:
        output.write_text(json.dumps(results_json(results), indent=2))
        console.print(f"Wrote {output}")
    return 0 if summary.total and summary.passed == summary.total else 1


@app.command()
def main(
    base_url: Annotated[str, typer.Option(help="OpenAI-compatible base URL.")] = DEFAULT_BASE_URL,
    model: Annotated[str, typer.Option(help="Model name at that endpoint.")] = DEFAULT_MODEL,
    runs: Annotated[int, typer.Option(min=1, help="Runs per task.")] = 3,
    sim_url: Annotated[
        str | None, typer.Option(help="Use an existing simulator instead of starting one.")
    ] = None,
    task: Annotated[list[str] | None, typer.Option(help="Only run these task ids.")] = None,
    output: Annotated[Path | None, typer.Option(help="Write detailed JSON here.")] = None,
    web_search: Annotated[bool, typer.Option(help="Expose web search to the tasks.")] = True,
) -> None:
    code = asyncio.run(
        evaluate(base_url, model, runs, sim_url, list(task or []), output, web_search)
    )
    raise typer.Exit(code=code)
