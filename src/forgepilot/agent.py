"""A bounded, basic tool-using coding agent."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.request import Request, urlopen

from forgepilot.tools import RepositoryTools

TOOLS = [
    {"name": "list_files", "description": "List repository files", "parameters": {"type": "object", "properties": {}}},
    {"name": "read_file", "description": "Read a UTF-8 file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write a UTF-8 file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "run", "description": "Run a command in the isolated container; provide argv, not shell text", "parameters": {"type": "object", "properties": {"argv": {"type": "array", "items": {"type": "string"}}}, "required": ["argv"]}},
    {"name": "pytest", "description": "Run pytest in the isolated container", "parameters": {"type": "object", "properties": {"args": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "git_status", "description": "Inspect Git status", "parameters": {"type": "object", "properties": {}}},
]
SCHEMAS = [{"type": "function", "function": item} for item in TOOLS]
MAX_STEPS = 12
MAX_TOOL_CALLS = 24


class ChatModel:
    def __init__(self):
        self.url = os.getenv("FORGEPILOT_API_URL", "https://api.openai.com/v1/chat/completions")
        self.model = os.environ["FORGEPILOT_MODEL"]
        self.key = os.environ["FORGEPILOT_API_KEY"]
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.usage_reported = False
        self.usage_samples = 0

    def complete(self, messages: list[dict], *, tools_enabled: bool = True) -> dict:
        body = {"model": self.model, "messages": messages}
        if tools_enabled:
            body["tools"] = SCHEMAS
        payload = json.dumps(body).encode()
        request = Request(self.url, data=payload, headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urlopen(request, timeout=60) as response:
            data = json.load(response)
        usage = data.get("usage") or {}
        if "prompt_tokens" in usage and "completion_tokens" in usage:
            self.prompt_tokens += usage["prompt_tokens"]
            self.completion_tokens += usage["completion_tokens"]
            self.usage_reported = True
            self.usage_samples += 1
        return data["choices"][0]["message"]


@dataclass(frozen=True)
class AgentResult:
    final_message: str
    steps: int
    stopped_reason: str


class AgentSession:
    """Shared model and tool budgets for every architecture."""

    def __init__(self, model, tools: RepositoryTools, max_steps: int, max_tool_calls: int):
        if max_steps <= 0 or max_tool_calls <= 0:
            raise ValueError("budgets must be positive")
        self.model, self.tools = model, tools
        self.max_steps, self.max_tool_calls = max_steps, max_tool_calls
        self.steps = 0
        self.tool_calls = 0
        self.failed_tool_calls = 0

    def complete(self, messages: list[dict], *, tools_enabled: bool = True) -> dict | None:
        if self.steps >= self.max_steps:
            return None
        self.steps += 1
        if tools_enabled:
            return self.model.complete(messages)
        return self.model.complete(messages, tools_enabled=False)

    def call(self, name: str, arguments: dict) -> object:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        if name == "list_files":
            return self.tools.list_files()
        if name == "read_file":
            return self.tools.read_file(arguments["path"])
        if name == "write_file":
            self.tools.write_file(arguments["path"], arguments["content"])
            return "written"
        if name == "run":
            return self.tools.run(arguments["argv"]).__dict__
        if name == "pytest":
            return self.tools.pytest(*arguments.get("args", [])).__dict__
        if name == "git_status":
            return self.tools.git("status", "--short").__dict__
        raise ValueError(f"unknown tool: {name}")

    def execute(self, messages: list[dict], message: dict) -> tuple[bool, bool]:
        """Append tool observations; return (failure_seen, tool_limit_hit)."""
        calls = message.get("tool_calls") or []
        messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
        failed = False
        for call in calls:
            if self.tool_calls >= self.max_tool_calls:
                return failed, True
            self.tool_calls += 1
            try:
                fn = call["function"]
                result = self.call(fn["name"], json.loads(fn["arguments"]))
                tool_failed = isinstance(result, dict) and result.get("returncode", 0) != 0
                if tool_failed:
                    self.failed_tool_calls += 1
                failed = failed or tool_failed
                output = json.dumps(result)[:12000]
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
                self.failed_tool_calls += 1
                failed = True
                output = json.dumps({"error": str(exc)})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
        return failed, False


def initial_messages(task: str) -> list[dict]:
    return [
        {"role": "system", "content": "You are a coding agent. Inspect the repository, make a focused fix, run relevant tests, then summarize. Use tools for evidence. Do not edit tests to claim success."},
        {"role": "user", "content": task},
    ]


class BasicAgent:
    def __init__(self, model, tools: RepositoryTools, *, max_steps: int = MAX_STEPS, max_tool_calls: int = MAX_TOOL_CALLS):
        self.session = AgentSession(model, tools, max_steps, max_tool_calls)

    def attempt(self, task: str) -> AgentResult:
        messages = initial_messages(task)
        while message := self.session.complete(messages):
            if not message.get("tool_calls"):
                return AgentResult(message.get("content") or "", self.session.steps, "finished")
            _, limit = self.session.execute(messages, message)
            if limit:
                return AgentResult("", self.session.steps, "tool_limit")
        return AgentResult("", self.session.steps, "step_limit")
