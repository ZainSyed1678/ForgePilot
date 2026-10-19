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


class ChatModel:
    def __init__(self):
        self.url = os.getenv("FORGEPILOT_API_URL", "https://api.openai.com/v1/chat/completions")
        self.model = os.environ["FORGEPILOT_MODEL"]
        self.key = os.environ["FORGEPILOT_API_KEY"]

    def complete(self, messages: list[dict]) -> dict:
        payload = json.dumps({"model": self.model, "messages": messages, "tools": SCHEMAS}).encode()
        request = Request(self.url, data=payload, headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urlopen(request, timeout=60) as response:
            data = json.load(response)
        return data["choices"][0]["message"]


@dataclass(frozen=True)
class AgentResult:
    final_message: str
    steps: int
    stopped_reason: str


class BasicAgent:
    def __init__(self, model, tools: RepositoryTools, *, max_steps: int = 12, max_tool_calls: int = 24):
        if max_steps <= 0 or max_tool_calls <= 0:
            raise ValueError("budgets must be positive")
        self.model, self.tools, self.max_steps = model, tools, max_steps
        self.max_tool_calls = max_tool_calls

    def _call(self, name: str, arguments: dict) -> object:
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

    def attempt(self, task: str) -> AgentResult:
        messages = [
            {"role": "system", "content": "You are a coding agent. Inspect the repository, make a focused fix, run relevant tests, then summarize. Use tools for evidence. Do not edit tests to claim success."},
            {"role": "user", "content": task},
        ]
        tool_calls_used = 0
        for step in range(1, self.max_steps + 1):
            message = self.model.complete(messages)
            calls = message.get("tool_calls") or []
            if not calls:
                return AgentResult(message.get("content") or "", step, "finished")
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
            for call in calls:
                if tool_calls_used >= self.max_tool_calls:
                    return AgentResult("", step, "tool_limit")
                tool_calls_used += 1
                try:
                    fn = call["function"]
                    result = self._call(fn["name"], json.loads(fn["arguments"]))
                    output = json.dumps(result)[:12000]
                except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
                    output = json.dumps({"error": str(exc)})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
        return AgentResult("", self.max_steps, "step_limit")
