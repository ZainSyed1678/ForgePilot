"""Run a benchmark task in a fresh workspace and save evidence."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from forgepilot.agent import BasicAgent, ChatModel
from forgepilot.benchmark import grade, load_tasks, prepare
from forgepilot.tools import RepositoryTools


def run_task(task_id: str, output: Path, *, model=None, image: str | None = None) -> dict:
    tasks = {task.id: task for task in load_tasks()}
    if task_id not in tasks:
        raise ValueError(f"unknown task: {task_id}")
    task = tasks[task_id]
    with tempfile.TemporaryDirectory(prefix="forgepilot-") as directory:
        workspace = Path(directory) / "repo"
        prepare(task, workspace)
        tools = RepositoryTools(workspace, image=image)
        active_model = model or ChatModel()
        agent_error = None
        try:
            attempt = BasicAgent(active_model, tools).attempt(task.prompt)
        except Exception as exc:
            agent_error = f"{type(exc).__name__}: {exc}"
            attempt = None
        result = grade(task, workspace, tools)
        if agent_error:
            result["passed"] = None
        record = {"task_id": task.id, "time_utc": datetime.now(timezone.utc).isoformat(),
                  "model": getattr(active_model, "model", type(active_model).__name__),
                  "steps": attempt.steps if attempt else 0,
                  "stopped_reason": attempt.stopped_reason if attempt else "agent_error",
                  "final_message": attempt.final_message if attempt else "",
                  "agent_error": agent_error, **result}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")
    return record
