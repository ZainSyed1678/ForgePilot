import csv

from forgepilot.analysis import summarize
from forgepilot.storage import save_run


def record(run_id, architecture, passed, recovered, tool_failures):
    return {
        "run_id": run_id, "time_utc": "2026-01-01T00:00:00+00:00",
        "task_id": "task", "task_sha256": "fixture-v1",
        "architecture": architecture, "model": "fake-model", "image": "runner:v1",
        "repeat_index": 1, "observability": "partial" if architecture == "reflective" else "full",
        "evidence_coverage": 0.5 if architecture == "reflective" else None,
        "inspection_calls": 2, "passed": passed, "test_passed": 2 if passed else 1,
        "test_total": 2, "regressions": 0 if passed else 1, "baseline_passed": 1,
        "agent_seconds": 2.0, "wall_seconds": 3.0,
        "prompt_tokens": 10, "completion_tokens": 5,
        "tool_failures": tool_failures, "recovered": recovered,
    }


def test_analysis_uses_only_verified_runs_and_writes_outputs(tmp_path):
    database = tmp_path / "runs.sqlite3"
    save_run(database, record("a", "basic", True, True, 1))
    save_run(database, record("b", "basic", False, False, 1))
    save_run(database, record("c", "reflective", None, None, None))
    output = tmp_path / "analysis"
    result = summarize(database, output)
    assert result["runs"] == 3
    assert result["verified"] == 2
    with (output / "summary.csv").open(newline="") as stream:
        rows = {row["architecture"]: row for row in csv.DictReader(stream)}
    assert float(rows["basic"]["success_rate"]) == 0.5
    assert float(rows["basic"]["regression_rate"]) == 0.5
    assert float(rows["basic"]["mean_tokens"]) == 15.0
    assert float(rows["basic"]["recovery_rate"]) == 0.5
    assert rows["reflective"]["success_rate"] == ""
    assert (output / "report.md").exists()
    assert (output / "observability.csv").exists()
    assert "Information availability" in (output / "report.md").read_text()
    assert (output / "success_rate.png").exists()
