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


def test_chat_model_accumulates_reported_tokens(monkeypatch):
    import io
    from forgepilot import agent

    monkeypatch.setenv("FORGEPILOT_MODEL", "test-model")
    monkeypatch.setenv("FORGEPILOT_API_KEY", "test-key")
    class Response(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

    def fake_urlopen(request, timeout):
        assert timeout == 60
        return Response(json.dumps({"choices": [{"message": {"content": "ok"}}],
                                    "usage": {"prompt_tokens": 7, "completion_tokens": 3}}).encode())

    monkeypatch.setattr(agent, "urlopen", fake_urlopen)
    model = agent.ChatModel()
    assert model.complete([{"role": "user", "content": "hello"}])["content"] == "ok"
    assert (model.prompt_tokens, model.completion_tokens) == (7, 3)
    assert model.usage_reported is True


def test_session_records_files_read_for_discovery(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "contract.md").write_text("clue")
    model = FakeModel([
        {"role": "assistant", "content": None, "tool_calls": [call("read_file", {"path": "docs/contract.md"})]},
        {"role": "assistant", "content": "Done"},
    ])
    agent = BasicAgent(model, RepositoryTools(tmp_path))
    agent.attempt("Investigate")
    assert agent.session.files_read == {"docs/contract.md"}
    assert agent.session.inspection_calls == 1
