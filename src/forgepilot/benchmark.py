"""Fixed benchmark fixtures and deterministic grading."""

from __future__ import annotations

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from forgepilot.tools import RepositoryTools

TASKS_DIR = Path(__file__).resolve().parent / "benchmarks" / "tasks"


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    files: dict[str, str]
    acceptance: str


def load_tasks(directory: Path = TASKS_DIR) -> list[Task]:
    tasks = []
    for file in sorted(directory.glob("*.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        tasks.append(Task(**data))
    if len({task.id for task in tasks}) != len(tasks):
        raise ValueError("duplicate task id")
    return tasks


def prepare(task: Task, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    tools = RepositoryTools(destination)
    for name, content in task.files.items():
        tools.write_file(name, content)
    subprocess.run(["git", "init", "-q", str(destination)], check=True)
    subprocess.run(["git", "-C", str(destination), "add", "."], check=True)
    subprocess.run(["git", "-C", str(destination), "-c", "user.name=ForgePilot",
                    "-c", "user.email=benchmark@local", "commit", "-qm", "fixture"], check=True)


def run_tests(workspace: Path, tools: RepositoryTools, report_name: str) -> dict:
    """Run pytest and read case outcomes from its JUnit XML, if available."""
    report = workspace / report_name
    report.unlink(missing_ok=True)
    try:
        result = tools.pytest("-q", "tests", f"--junitxml={report_name}")
    except OSError as exc:
        return {"verified": False, "cases": {}, "returncode": None, "stdout": "", "stderr": str(exc)}
    cases = {}
    if result.returncode in (0, 1) and report.exists():
        try:
            for case in ET.parse(report).iter("testcase"):
                key = f"{case.get('classname')}::{case.get('name')}"
                cases[key] = "failed" if case.find("failure") is not None or case.find("error") is not None else (
                    "skipped" if case.find("skipped") is not None else "passed")
        except ET.ParseError:
            cases = {}
    report.unlink(missing_ok=True)
    return {"verified": bool(cases), "cases": cases, "returncode": result.returncode,
            "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


def grade(task: Task, workspace: Path, tools: RepositoryTools, baseline: dict | None = None) -> dict:
    """Restore original tests and grade the final code with acceptance tests."""
    tests = workspace / "tests"
    if tests.is_symlink():
        tests.unlink()
    elif tests.exists():
        shutil.rmtree(tests)
    tests.mkdir()
    for name, content in task.files.items():
        if Path(name).parts[0] == "tests":
            tools.write_file(name, content)
    (tests / "test_acceptance.py").write_text(task.acceptance, encoding="utf-8")
    final = run_tests(workspace, tools, ".forgepilot_final.xml")
    if not final["verified"]:
        return {"passed": None, "test_passed": None, "test_total": None,
                "regressions": None, "baseline_passed": None, **final}
    cases = final["cases"]
    acceptance = {key: value for key, value in cases.items()
                  if key.split("::")[0].split(".")[-1] == "test_acceptance"}
    baseline_cases = baseline["cases"] if baseline and baseline["verified"] else {}
    passed_before = {key for key, value in baseline_cases.items() if value == "passed"}
    regressions = sum(cases.get(key) != "passed" for key in passed_before)
    success = (final["returncode"] == 0 and bool(acceptance)
               and set(baseline_cases).issubset(cases)
               and all(value == "passed" for value in cases.values()))
    return {"passed": success,
            "test_passed": sum(value == "passed" for value in cases.values()),
            "test_total": len(cases), "regressions": regressions,
            "baseline_passed": len(passed_before), **final}
