"""Architectures compared on the same tools and budgets."""

from forgepilot.agent import AgentResult, AgentSession, BasicAgent, initial_messages
from forgepilot.tools import RepositoryTools

MAX_STEPS = 12
MAX_TOOL_CALLS = 24


class PlannerExecutorCritic:
    def __init__(self, model, tools: RepositoryTools):
        self.session = AgentSession(model, tools, MAX_STEPS, MAX_TOOL_CALLS)

    def attempt(self, task: str) -> AgentResult:
        messages = initial_messages(task)
        messages.append({"role": "user", "content": "First make a short plan. Do not use tools yet."})
        planning = self.session.complete(messages, tools_enabled=False)
        plan = (planning or {}).get("content") or ""
        if not plan.strip():
            return AgentResult("", self.session.steps, "planning_failed")
        messages.append({"role": "assistant", "content": plan})
        messages.append({"role": "user", "content": "Execute the plan using tools. Run relevant tests before your draft answer."})
        revised = False
        while True:
            message = self.session.complete(messages)
            if message is None:
                return AgentResult("", self.session.steps, "step_limit")
            if message.get("tool_calls"):
                _, limit = self.session.execute(messages, message)
                if limit:
                    return AgentResult("", self.session.steps, "tool_limit")
                continue
            draft = message.get("content") or ""
            if revised:
                return AgentResult(draft, self.session.steps, "finished")
            messages.append({"role": "assistant", "content": draft})
            messages.append({"role": "user", "content": "Critique the work against the task and tool evidence. Reply APPROVE if supported, otherwise explain a concrete revision. Do not use tools."})
            critique = self.session.complete(messages, tools_enabled=False)
            if critique is None:
                return AgentResult("", self.session.steps, "step_limit")
            feedback = (critique.get("content") or "").strip()
            if feedback.upper().startswith("APPROVE"):
                return AgentResult(draft, self.session.steps, "finished")
            messages.append({"role": "assistant", "content": feedback})
            messages.append({"role": "user", "content": "Revise the implementation based on the critique. Use tools and report the result."})
            revised = True


class ReflectiveAgent:
    def __init__(self, model, tools: RepositoryTools):
        self.session = AgentSession(model, tools, MAX_STEPS, MAX_TOOL_CALLS)

    def attempt(self, task: str) -> AgentResult:
        messages = initial_messages(task)
        reflections = 0
        while True:
            message = self.session.complete(messages)
            if message is None:
                return AgentResult("", self.session.steps, "step_limit")
            if not message.get("tool_calls"):
                return AgentResult(message.get("content") or "", self.session.steps, "finished")
            failed, limit = self.session.execute(messages, message)
            if limit:
                return AgentResult("", self.session.steps, "tool_limit")
            if failed and reflections < 2:
                messages.append({"role": "user", "content": "A tool failed. Explain the likely cause and revise your next steps. Do not use tools in this reflection."})
                reflection = self.session.complete(messages, tools_enabled=False)
                if reflection is None:
                    return AgentResult("", self.session.steps, "step_limit")
                messages.append({"role": "assistant", "content": reflection.get("content") or ""})
                messages.append({"role": "user", "content": "Continue with the revised approach and verify the fix."})
                reflections += 1


ARCHITECTURES = {
    "basic": BasicAgent,
    "planner-executor-critic": PlannerExecutorCritic,
    "reflective": ReflectiveAgent,
}
