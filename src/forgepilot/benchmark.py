"""Fixed benchmark fixtures and deterministic grading."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from forgepilot.tools import RepositoryTools

TASKS_DIR = Path(__file__).resolve().parent / "benchmarks" / "tasks"


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    files: dict[str, str]
    acceptance: str


def load_tasks(directory: Path = TASKS_DIR) -> list[Task]:
    tasks = []
    for file in sorted(directory.glob("*.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        tasks.append(Task(**data))
    if len({task.id for task in tasks}) != len(tasks):
        raise ValueError("duplicate task id")
    return tasks


def prepare(task: Task, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    tools = RepositoryTools(destination)
    for name, content in task.files.items():
        tools.write_file(name, content)
    subprocess.run(["git", "init", "-q", str(destination)], check=True)
    subprocess.run(["git", "-C", str(destination), "add", "."], check=True)
    subprocess.run(["git", "-C", str(destination), "-c", "user.name=ForgePilot",
                    "-c", "user.email=benchmark@local", "commit", "-qm", "fixture"], check=True)


def grade(task: Task, workspace: Path, tools: RepositoryTools) -> dict:
    tests = workspace / "tests"
    if tests.exists():
        shutil.rmtree(tests)
    tests.mkdir()
    (tests / "test_acceptance.py").write_text(task.acceptance, encoding="utf-8")
    try:
        result = tools.pytest("-q", "tests/test_acceptance.py")
    except OSError as exc:
        return {"passed": None, "returncode": None, "stdout": "", "stderr": str(exc)}
    passed = None if result.returncode == 125 else result.returncode == 0
    return {"passed": passed, "returncode": result.returncode,
            "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}
