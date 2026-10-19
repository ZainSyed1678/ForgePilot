"""Optional end-to-end benchmark checks using the built Docker image."""

import shutil
import subprocess

import pytest

from forgepilot.benchmark import grade, load_tasks, prepare, run_tests
from forgepilot.tools import RepositoryTools


REFERENCE_FIXES = {
    "optional_profile_field": ("profiles.py",
        'def display_name(row):\n    return (row.get("nickname") or "").strip() or row["name"]\n'),
    "timeout_configuration": ("worker.py",
        'import os\nfrom settings import DEFAULT_TIMEOUT\n\ndef timeout_seconds():\n    raw = os.getenv("JOB_TIMEOUT_SECONDS")\n    return int(raw) if raw and raw.strip() else DEFAULT_TIMEOUT\n'),
    "legacy_event_alias": ("router.py",
        'from contracts import CANONICAL_EVENTS, LEGACY_ALIASES\n\ndef route(event_name):\n    return CANONICAL_EVENTS.get(LEGACY_ALIASES.get(event_name, event_name))\n'),
    "timestamp_ordering": ("scheduler.py",
        'from datetime import datetime, timezone\n\ndef earliest(jobs):\n    return min(jobs, key=lambda job: datetime.fromisoformat(job["at"].replace("Z", "+00:00")).astimezone(timezone.utc))\n'),
}


@pytest.fixture(scope="module")
def docker_image():
    if not shutil.which("docker"):
        pytest.skip("Docker CLI unavailable")
    try:
        result = subprocess.run(["docker", "image", "inspect", "forgepilot-runner:phase1"],
                                capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker engine unavailable")
    if result.returncode:
        pytest.skip("ForgePilot runner image not built")


@pytest.mark.parametrize("task_id", sorted(REFERENCE_FIXES))
def test_partial_task_grades_inside_docker(tmp_path, docker_image, task_id):
    task = next(task for task in load_tasks() if task.id == task_id)
    workspace = tmp_path / "repo"
    prepare(task, workspace)
    tools = RepositoryTools(workspace)
    baseline = run_tests(workspace, tools, ".baseline.xml")
    assert baseline["verified"], baseline["stderr"]
    assert list(baseline["cases"].values()) == ["passed"]
    file, source = REFERENCE_FIXES[task_id]
    tools.write_file(file, source)
    result = grade(task, workspace, tools, baseline)
    assert result["passed"] is True, result["stdout"] + result["stderr"]
    assert result["regressions"] == 0


def test_scripted_agent_attempt_records_discovery_in_docker(tmp_path, docker_image):
    import json
    from forgepilot.runner import run_task

    class ScriptModel:
        model = "scripted-local"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"content": None, "tool_calls": [{"id": "read", "type": "function",
                    "function": {"name": "read_file", "arguments": json.dumps({"path": "docs/imports.md"})}}]}
            if self.calls == 2:
                file, source = REFERENCE_FIXES["optional_profile_field"]
                return {"content": None, "tool_calls": [{"id": "write", "type": "function",
                    "function": {"name": "write_file", "arguments": json.dumps({"path": file, "content": source})}}]}
            return {"content": "Fixed and checked"}

    result = run_task("optional_profile_field", tmp_path / "runs.sqlite3", model=ScriptModel())
    assert result["passed"] is True
    assert result["evidence_coverage"] == 1.0
    assert result["files_read"] == ["docs/imports.md"]
