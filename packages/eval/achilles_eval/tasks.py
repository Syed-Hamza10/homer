from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

TASKS_DIR = Path(__file__).parent / "tasks"

Category = Literal["email", "calendar", "search", "multi", "safety"]


class Expect(BaseModel):
    tools: list[str] = Field(default_factory=list)
    tools_any: list[str] = Field(default_factory=list)
    no_tools: list[str] = Field(default_factory=list)
    answer_contains: list[str] = Field(default_factory=list)
    approval_actions: list[str] = Field(default_factory=list)
    no_approvals: bool = False
    reject_pending: bool = False
    sim: dict[str, int] = Field(default_factory=dict)


class Task(BaseModel):
    id: str
    category: Category
    prompt: str
    expect: Expect = Field(default_factory=Expect)


def load_tasks(directory: Path = TASKS_DIR) -> list[Task]:
    tasks: list[Task] = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        entries = data.get("tasks", []) if isinstance(data, dict) else data
        tasks.extend(Task.model_validate(entry) for entry in entries)
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("task ids must be unique")
    return tasks
