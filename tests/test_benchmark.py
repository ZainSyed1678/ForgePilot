import subprocess

import pytest

from forgepilot.benchmark import grade, load_tasks, prepare, run_tests
from forgepilot.tools import CommandResult, RepositoryTools


@pytest.mark.parametrize("task", load_tasks(), ids=lambda task: task.id)
def test_fixture_starts_with_failing_test(task, tmp_path):
    workspace = tmp_path / "repo"
    prepare(task, workspace)
    completed = subprocess.run(["python", "-m", "pytest", "-q", "tests"],
                               cwd=workspace, capture_output=True, text=True)
    assert completed.returncode != 0
    assert "FAILED" in completed.stdout
    assert "1 passed" in completed.stdout


def test_task_ids_are_unique():
    tasks = load_tasks()
    assert len(tasks) == 5
    assert len({task.id for task in tasks}) == 5


def test_grader_accepts_fix_and_rejects_original(tmp_path, monkeypatch):
    task = next(task for task in load_tasks() if task.id == "negative_total")
    workspace = tmp_path / "repo"
    prepare(task, workspace)

    def local_pytest(self, *args):
        completed = subprocess.run(["python", "-m", "pytest", *args], cwd=self.root,
                                   capture_output=True, text=True)
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)

    monkeypatch.setattr(RepositoryTools, "pytest", local_pytest)
    tools = RepositoryTools(workspace)
    baseline = run_tests(workspace, tools, ".baseline.xml")
    assert baseline["verified"] is True
    assert sum(value == "passed" for value in baseline["cases"].values()) == 1
    initial = grade(task, workspace, tools, baseline)
    assert initial["passed"] is False
    tools.write_file("calculator.py", "def total(values):\n    return sum(values)\n")
    fixed = grade(task, workspace, tools, baseline)
    assert fixed["passed"] is True
    assert fixed["regressions"] == 0
    tools.write_file("calculator.py", "def total(values):\n    return 0\n")
    broken = grade(task, workspace, tools, baseline)
    assert broken["regressions"] == 1


def test_grader_rejects_missing_baseline_cases(tmp_path, monkeypatch):
    from forgepilot import benchmark

    task = next(task for task in load_tasks() if task.id == "negative_total")
    workspace = tmp_path / "repo"
    prepare(task, workspace)
    baseline = {"verified": True, "cases": {"tests.test_calculator::test_positive_total": "passed"}}
    monkeypatch.setattr(benchmark, "run_tests", lambda *args: {
        "verified": True, "cases": {"tests.test_acceptance::test_ok": "passed"},
        "returncode": 0, "stdout": "1 passed", "stderr": ""})
    result = grade(task, workspace, RepositoryTools(workspace), baseline)
    assert result["passed"] is False
    assert result["regressions"] == 1
