"""Run one isolated benchmark attempt and save its evidence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from forgepilot.agent import ChatModel, MAX_STEPS, MAX_TOOL_CALLS
from forgepilot.architectures import ARCHITECTURES
from forgepilot.benchmark import grade, load_tasks, prepare, run_tests
from forgepilot.storage import save_run
from forgepilot.tools import RepositoryTools


def run_task(task_id: str, output: Path, *, architecture: str = "basic", model=None,
             image: str | None = None, repeat_index: int = 1) -> dict:
    if architecture not in ARCHITECTURES:
        raise ValueError(f"unknown architecture: {architecture}")
    if repeat_index <= 0:
        raise ValueError("repeat_index must be positive")
    tasks = {task.id: task for task in load_tasks()}
    if task_id not in tasks:
        raise ValueError(f"unknown task: {task_id}")
    task = tasks[task_id]
    started = time.monotonic()
    task_hash = hashlib.sha256(json.dumps(asdict(task), sort_keys=True).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="forgepilot-") as directory:
        workspace = Path(directory) / "repo"
        prepare(task, workspace)
        tools = RepositoryTools(workspace, image=image)
        baseline = run_tests(workspace, tools, ".forgepilot_baseline.xml")
        active_model = model
        agent = None
        attempt = None
        agent_error = None
        agent_seconds = None
        tokens_before = (0, 0, 0)
        if baseline["verified"]:
            agent_started = time.monotonic()
            try:
                active_model = model or ChatModel()
                tokens_before = (getattr(active_model, "prompt_tokens", 0),
                                 getattr(active_model, "completion_tokens", 0),
                                 getattr(active_model, "usage_samples", 0))
                agent = ARCHITECTURES[architecture](active_model, tools)
                attempt = agent.attempt(task.prompt)
            except Exception as exc:
                agent_error = f"{type(exc).__name__}: {exc}"
            agent_seconds = time.monotonic() - agent_started
            try:
                final = grade(task, workspace, tools, baseline)
            except Exception as exc:
                final = {"passed": None, "verified": False, "test_passed": None,
                         "test_total": None, "regressions": None, "baseline_passed": None,
                         "cases": {}, "returncode": None, "stdout": "",
                         "stderr": f"grading error: {type(exc).__name__}: {exc}"}
            if agent_error and final["verified"]:
                final["passed"] = False
        else:
            agent_error = "baseline tests could not run; model call skipped"
            final = {"passed": None, "verified": False, "test_passed": None,
                     "test_total": None, "regressions": None, "baseline_passed": None,
                     "cases": {}, "returncode": None, "stdout": "", "stderr": baseline["stderr"]}
        tool_failures = agent.session.failed_tool_calls if agent else None
        files_read = sorted(agent.session.files_read) if agent else []
        evidence_paths = set(task.evidence_paths)
        evidence_coverage = (len(evidence_paths.intersection(files_read)) / len(evidence_paths)
                             if evidence_paths and agent else None)
        passed = final["passed"]
        usage_reported = (active_model is not None
                          and getattr(active_model, "usage_samples", 0) > tokens_before[2])
        record = {
            "run_id": str(uuid.uuid4()),
            "task_id": task.id, "task_sha256": task_hash, "architecture": architecture,
            "observability": task.observability, "failure_type": task.failure_type,
            "evidence_paths": sorted(evidence_paths), "files_read": files_read,
            "inspection_calls": agent.session.inspection_calls if agent else None,
            "evidence_coverage": evidence_coverage,
            "time_utc": datetime.now(timezone.utc).isoformat(),
            "repeat_index": repeat_index,
            "model": getattr(active_model, "model", os.getenv("FORGEPILOT_MODEL")),
            "image": tools.image, "timeout_seconds": tools.timeout,
            "memory_mb": tools.memory_mb, "cpus": tools.cpus,
            "max_steps": MAX_STEPS, "max_tool_calls": MAX_TOOL_CALLS,
            "steps": attempt.steps if attempt else 0,
            "stopped_reason": attempt.stopped_reason if attempt else (
                "agent_error" if baseline["verified"] else "unverified"),
            "final_message": attempt.final_message if attempt else "",
            "agent_error": agent_error,
            "agent_seconds": agent_seconds, "wall_seconds": time.monotonic() - started,
            "prompt_tokens": active_model.prompt_tokens - tokens_before[0] if usage_reported else None,
            "completion_tokens": active_model.completion_tokens - tokens_before[1] if usage_reported else None,
            "tool_failures": tool_failures,
            "recovered": bool(passed and tool_failures) if passed is not None and tool_failures is not None else None,
            "baseline_cases": baseline["cases"],
            "baseline_returncode": baseline["returncode"],
            "baseline_stdout": baseline["stdout"],
            "baseline_stderr": baseline["stderr"],
            **final,
        }
    save_run(output, record)
    return record
