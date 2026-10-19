from forgepilot.agent import AgentResult
from forgepilot.benchmark import load_tasks
from forgepilot import runner
from forgepilot.tools import CommandResult


def test_runner_records_grader_result_even_if_agent_claims_success(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.ARCHITECTURES["basic"], "attempt",
                        lambda self, task: AgentResult("Everything passes", 1, "finished"))
    monkeypatch.setattr(runner.RepositoryTools, "pytest",
                        lambda self, *args: CommandResult(1, "1 failed", ""))
    task_id = load_tasks()[0].id
    result = runner.run_task(task_id, tmp_path / "runs.jsonl", model=object())
    assert result["passed"] is False
    assert "1 failed" in (tmp_path / "runs.jsonl").read_text()


def test_runner_records_selected_architecture(tmp_path, monkeypatch):
    architecture = "reflective"
    monkeypatch.setattr(runner.ARCHITECTURES[architecture], "attempt",
                        lambda self, task: AgentResult("Checked", 2, "finished"))
    monkeypatch.setattr(runner.RepositoryTools, "pytest",
                        lambda self, *args: CommandResult(0, "1 passed", ""))
    result = runner.run_task(load_tasks()[0].id, tmp_path / "runs.jsonl",
                             architecture=architecture, model=object())
    assert result["architecture"] == architecture
    assert result["passed"] is True
