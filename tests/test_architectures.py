import json

import pytest

from forgepilot.architectures import ARCHITECTURES, PlannerExecutorCritic, ReflectiveAgent
from forgepilot.tools import CommandResult, RepositoryTools


class ScriptModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def complete(self, messages, *, tools_enabled=True):
        self.calls.append((tools_enabled, [message.copy() for message in messages]))
        return next(self.replies)


def tool_call(name, arguments, id="c1"):
    return {"id": id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


def test_planner_executor_critic_uses_distinct_turns(tmp_path):
    model = ScriptModel([
        {"content": "Inspect, fix, test"},
        {"content": None, "tool_calls": [tool_call("write_file", {"path": "fix.py", "content": "ok"})]},
        {"content": "Fixed"},
        {"content": "APPROVE: the fix is supported"},
    ])
    result = PlannerExecutorCritic(model, RepositoryTools(tmp_path)).attempt("Fix the bug")
    assert (tmp_path / "fix.py").read_text() == "ok"
    assert result.steps == 4
    assert result.stopped_reason == "finished"
    assert [call[0] for call in model.calls] == [False, True, True, False]


def test_critic_can_request_revision(tmp_path):
    model = ScriptModel([
        {"content": "Plan"},
        {"content": "Draft"},
        {"content": "Tests are missing"},
        {"content": None, "tool_calls": [tool_call("write_file", {"path": "fix.py", "content": "revised"})]},
        {"content": "Revised"},
    ])
    result = PlannerExecutorCritic(model, RepositoryTools(tmp_path)).attempt("Fix")
    assert result.final_message == "Revised"
    assert (tmp_path / "fix.py").read_text() == "revised"
    assert result.steps == 5


def test_reflection_follows_failed_test(tmp_path, monkeypatch):
    monkeypatch.setattr(RepositoryTools, "pytest", lambda self, *args: CommandResult(1, "failed", ""))
    model = ScriptModel([
        {"content": None, "tool_calls": [tool_call("pytest", {"args": ["-q"]})]},
        {"content": "The test failed; inspect the implementation"},
        {"content": "Done"},
    ])
    result = ReflectiveAgent(model, RepositoryTools(tmp_path)).attempt("Fix")
    assert result.steps == 3
    assert [call[0] for call in model.calls] == [True, False, True]
    assert "failed" in json.dumps(model.calls[1][1])


@pytest.mark.parametrize("name", list(ARCHITECTURES))
def test_every_architecture_respects_twelve_model_turns(name, tmp_path):
    class EndlessModel:
        calls = 0

        def complete(self, messages, *, tools_enabled=True):
            self.calls += 1
            if not tools_enabled:
                return {"content": "plan"}
            return {"content": None, "tool_calls": [tool_call("list_files", {})]}

    model = EndlessModel()
    result = ARCHITECTURES[name](model, RepositoryTools(tmp_path)).attempt("Fix")
    assert model.calls <= 12
    assert result.steps <= 12
