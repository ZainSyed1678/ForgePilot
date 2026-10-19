import json

from forgepilot.agent import BasicAgent
from forgepilot.tools import RepositoryTools


class FakeModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.messages = []

    def complete(self, messages):
        self.messages = messages.copy()
        return next(self.replies)


def call(name, arguments, id="call_1"):
    return {"id": id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


def test_agent_edits_file_and_uses_tool_result(tmp_path):
    model = FakeModel([
        {"role": "assistant", "content": None, "tool_calls": [call("write_file", {"path": "fix.py", "content": "fixed\n"})]},
        {"role": "assistant", "content": "Fixed it."},
    ])
    result = BasicAgent(model, RepositoryTools(tmp_path)).attempt("Fix it")
    assert (tmp_path / "fix.py").read_text() == "fixed\n"
    assert model.messages[-1]["role"] == "tool"
    assert result.stopped_reason == "finished"


def test_agent_respects_step_limit(tmp_path):
    model = FakeModel([{"role": "assistant", "content": None,
                        "tool_calls": [call("list_files", {})]}])
    result = BasicAgent(model, RepositoryTools(tmp_path), max_steps=1).attempt("Inspect")
    assert result.stopped_reason == "step_limit"
    assert result.steps == 1


def test_unknown_tool_returns_error_to_model(tmp_path):
    model = FakeModel([
        {"role": "assistant", "content": None, "tool_calls": [call("delete_everything", {})]},
        {"role": "assistant", "content": "Done"},
    ])
    BasicAgent(model, RepositoryTools(tmp_path)).attempt("No")
    assert "unknown tool" in model.messages[-1]["content"]
