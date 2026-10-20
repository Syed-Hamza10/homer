import statistics
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from sqlmodel import Session

from achilles_core.agent.runtime import Runtime
from achilles_core.db.models import User
from achilles_core.db.session import make_engine, run_migrations
from achilles_core.platform import ensure_home
from achilles_core.services import approvals, chat
from achilles_core.services.users import ensure_first_user
from achilles_eval.tasks import Task


class SimSource(Protocol):
    async def reset(self) -> None: ...

    async def state(self) -> dict[str, int]: ...


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    category: str
    run: int
    passed: bool
    failures: tuple[str, ...]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    tools: tuple[str, ...]
    approval_actions: tuple[str, ...]
    answer: str


@dataclass(frozen=True)
class TaskSummary:
    task_id: str
    category: str
    runs: int
    passed: int
    mean_latency_ms: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Summary:
    total: int
    passed: int
    pass_rate: float
    mean_latency_ms: int
    p95_latency_ms: int
    input_tokens: int
    output_tokens: int
    tasks: tuple[TaskSummary, ...]


def _reject_pending(session: Session, user: User) -> None:
    pending = approvals.list_pending(session, user)
    if not pending:
        approvals.create_from_tool_result(
            session,
            user.id,
            "google",
            {
                "approval_required": True,
                "action": "mail_send",
                "payload": {"draft_id": "d1"},
                "preview": "Send draft d1",
            },
        )
        pending = approvals.list_pending(session, user)
    for approval in pending:
        approvals.reject(session, user, approval.id)


def check_task(
    task: Task, tools: list[str], answer: str, approval_actions: list[str], sim: dict[str, int]
) -> list[str]:
    failures: list[str] = []
    for name in task.expect.tools:
        if name not in tools:
            failures.append(f"missing tool {name}")
    if task.expect.tools_any and not any(name in tools for name in task.expect.tools_any):
        failures.append(f"none of the tools {task.expect.tools_any} were called")
    for name in task.expect.no_tools:
        if name in tools:
            failures.append(f"unexpected tool {name}")
    for text in task.expect.answer_contains:
        if text.lower() not in answer.lower():
            failures.append(f"answer does not contain {text!r}")
    for action in task.expect.approval_actions:
        if action not in approval_actions:
            failures.append(f"missing approval for {action}")
    if task.expect.no_approvals and approval_actions:
        failures.append(f"unexpected approvals {approval_actions}")
    for key, expected in task.expect.sim.items():
        actual = sim.get(key)
        if actual != expected:
            failures.append(f"sim {key} is {actual}, expected {expected}")
    return failures


async def run_task(
    session: Session,
    user: User,
    runtime: Runtime,
    sim: SimSource,
    task: Task,
    run: int = 1,
) -> TaskResult:
    await sim.reset()
    started = time.perf_counter()
    events = [event async for event in chat.stream(session, user, runtime, None, task.prompt)]
    latency_ms = round((time.perf_counter() - started) * 1000)

    tools = [event.data["name"] for event in events if event.name == "tool_call"]
    approval_actions = [
        event.data["action"] for event in events if event.name == "approval_required"
    ]
    answer = "".join(event.data["text"] for event in events if event.name == "token")
    done = next((event.data for event in events if event.name == "done"), {})
    errors = [event.data["message"] for event in events if event.name == "error"]

    if task.expect.reject_pending:
        _reject_pending(session, user)
    state = await sim.state()
    failures = check_task(task, tools, answer, approval_actions, state)
    failures.extend(f"chat error: {message}" for message in errors)

    return TaskResult(
        task_id=task.id,
        category=task.category,
        run=run,
        passed=not failures,
        failures=tuple(failures),
        latency_ms=latency_ms,
        input_tokens=int(done.get("input_tokens", 0)),
        output_tokens=int(done.get("output_tokens", 0)),
        tools=tuple(tools),
        approval_actions=tuple(approval_actions),
        answer=answer,
    )


async def run_suite(
    runtime: Runtime,
    sim: SimSource,
    tasks: list[Task],
    runs: int = 3,
    user_name: str = "Eval",
    timezone: str = "UTC",
) -> list[TaskResult]:
    results: list[TaskResult] = []
    for task in tasks:
        for run in range(1, runs + 1):
            with tempfile.TemporaryDirectory(prefix="achilles-eval-") as home:
                path = Path(home)
                ensure_home(path)
                engine = make_engine(path)
                run_migrations(engine)
                try:
                    with Session(engine) as session:
                        user = ensure_first_user(session, user_name, timezone)
                        results.append(await run_task(session, user, runtime, sim, task, run))
                finally:
                    engine.dispose()
    return results


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def summarise(results: list[TaskResult]) -> Summary:
    grouped: dict[str, list[TaskResult]] = {}
    for result in results:
        grouped.setdefault(result.task_id, []).append(result)
    tasks = []
    for task_id, rows in grouped.items():
        tasks.append(
            TaskSummary(
                task_id=task_id,
                category=rows[0].category,
                runs=len(rows),
                passed=sum(row.passed for row in rows),
                mean_latency_ms=round(statistics.mean(row.latency_ms for row in rows)),
                input_tokens=sum(row.input_tokens for row in rows),
                output_tokens=sum(row.output_tokens for row in rows),
            )
        )
    latencies = [result.latency_ms for result in results]
    passed = sum(result.passed for result in results)
    return Summary(
        total=len(results),
        passed=passed,
        pass_rate=passed / len(results) if results else 0.0,
        mean_latency_ms=round(statistics.mean(latencies)) if latencies else 0,
        p95_latency_ms=percentile(latencies, 0.95),
        input_tokens=sum(result.input_tokens for result in results),
        output_tokens=sum(result.output_tokens for result in results),
        tasks=tuple(tasks),
    )


def results_json(results: list[TaskResult]) -> dict:
    return {
        "summary": asdict(summarise(results)),
        "results": [asdict(result) for result in results],
    }
