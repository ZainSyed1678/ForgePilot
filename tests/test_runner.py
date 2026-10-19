from forgepilot.agent import AgentResult
from forgepilot.benchmark import load_tasks
from forgepilot import runner
from forgepilot.tools import CommandResult


def test_runner_records_grader_result_even_if_agent_claims_success(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.BasicAgent, "attempt",
                        lambda self, task: AgentResult("Everything passes", 1, "finished"))
    monkeypatch.setattr(runner.RepositoryTools, "pytest",
                        lambda self, *args: CommandResult(1, "1 failed", ""))
    task_id = load_tasks()[0].id
    result = runner.run_task(task_id, tmp_path / "runs.jsonl", model=object())
    assert result["passed"] is False
    assert "1 failed" in (tmp_path / "runs.jsonl").read_text()
