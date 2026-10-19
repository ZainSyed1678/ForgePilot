import subprocess

import pytest

from forgepilot.benchmark import grade, load_tasks, prepare
from forgepilot.tools import CommandResult, RepositoryTools


@pytest.mark.parametrize("task", load_tasks(), ids=lambda task: task.id)
def test_fixture_starts_with_failing_test(task, tmp_path):
    workspace = tmp_path / "repo"
    prepare(task, workspace)
    completed = subprocess.run(["python", "-m", "pytest", "-q", "tests"],
                               cwd=workspace, capture_output=True, text=True)
    assert completed.returncode != 0
    assert "FAILED" in completed.stdout


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
    assert grade(task, workspace, tools)["passed"] is False
    tools.write_file("calculator.py", "def total(values):\n    return sum(values)\n")
    assert grade(task, workspace, tools)["passed"] is True
