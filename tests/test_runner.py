import sqlite3

from forgepilot.agent import AgentResult
from forgepilot.benchmark import load_tasks
from forgepilot import runner


def baseline(*args):
    return {"verified": True, "cases": {"tests.test_example::test_ok": "passed"},
            "returncode": 1, "stdout": "1 failed, 1 passed", "stderr": ""}


def grade_result(passed):
    return {"passed": passed, "verified": True, "test_passed": 2 if passed else 1,
            "test_total": 2, "regressions": 0, "baseline_passed": 1,
            "cases": {"tests.test_acceptance::test_ok": "passed" if passed else "failed"},
            "returncode": 0 if passed else 1, "stdout": "evidence", "stderr": ""}


def test_runner_records_grader_result_even_if_agent_claims_success(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "run_tests", baseline)
    monkeypatch.setattr(runner, "grade", lambda *args: grade_result(False))
    monkeypatch.setattr(runner.ARCHITECTURES["basic"], "attempt",
                        lambda self, task: AgentResult("Everything passes", 1, "finished"))
    database = tmp_path / "runs.sqlite3"
    result = runner.run_task(load_tasks()[0].id, database, model=object())
    assert result["passed"] is False
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT passed, raw_json FROM runs").fetchone()
    assert row[0] == 0
    assert "Everything passes" in row[1]


def test_runner_records_selected_architecture(tmp_path, monkeypatch):
    architecture = "reflective"
    monkeypatch.setattr(runner, "run_tests", baseline)
    monkeypatch.setattr(runner, "grade", lambda *args: grade_result(True))
    monkeypatch.setattr(runner.ARCHITECTURES[architecture], "attempt",
                        lambda self, task: AgentResult("Checked", 2, "finished"))
    result = runner.run_task(load_tasks()[0].id, tmp_path / "runs.sqlite3",
                             architecture=architecture, model=object())
    assert result["architecture"] == architecture
    assert result["passed"] is True


def test_runner_skips_model_when_baseline_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "run_tests", lambda *args: {
        "verified": False, "cases": {}, "returncode": 125, "stdout": "", "stderr": "Docker unavailable"})

    class UnusedModel:
        def complete(self, messages, **kwargs):
            raise AssertionError("model should not be called")

    result = runner.run_task(load_tasks()[0].id, tmp_path / "runs.sqlite3", model=UnusedModel())
    assert result["passed"] is None
    assert result["agent_seconds"] is None
    assert "skipped" in result["agent_error"]


def test_agent_crash_is_verified_failure_if_grading_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "run_tests", baseline)
    monkeypatch.setattr(runner, "grade", lambda *args: grade_result(True))

    class BrokenModel:
        def complete(self, messages, **kwargs):
            raise RuntimeError("provider down")

    result = runner.run_task(load_tasks()[0].id, tmp_path / "runs.sqlite3", model=BrokenModel())
    assert result["passed"] is False
    assert result["stopped_reason"] == "agent_error"
    assert "provider down" in result["agent_error"]


def test_grading_error_is_recorded_as_unverified(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "run_tests", baseline)
    def broken_grade(*args):
        raise OSError("report unavailable")

    monkeypatch.setattr(runner, "grade", broken_grade)
    monkeypatch.setattr(runner.ARCHITECTURES["basic"], "attempt",
                        lambda self, task: AgentResult("done", 1, "finished"))
    result = runner.run_task(load_tasks()[0].id, tmp_path / "runs.sqlite3", model=object())
    assert result["passed"] is None
    assert "report unavailable" in result["stderr"]


def test_runner_records_partial_task_discovery(tmp_path, monkeypatch):
    task = next(task for task in load_tasks() if task.id == "optional_profile_field")
    monkeypatch.setattr(runner, "run_tests", baseline)
    monkeypatch.setattr(runner, "grade", lambda *args: grade_result(True))

    def observed_attempt(self, prompt):
        self.session.files_read.add("docs/imports.md")
        self.session.inspection_calls = 1
        return AgentResult("Fixed", 2, "finished")

    monkeypatch.setattr(runner.ARCHITECTURES["basic"], "attempt", observed_attempt)
    result = runner.run_task(task.id, tmp_path / "runs.sqlite3", model=object())
    assert result["observability"] == "partial"
    assert result["evidence_coverage"] == 1.0
    assert result["files_read"] == ["docs/imports.md"]
