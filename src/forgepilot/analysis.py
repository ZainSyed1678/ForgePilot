"""Descriptive analysis of recorded experiments."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def task_complexity(task_id: str) -> str:
    """Predeclared fixture grouping; independent of an agent's outcome."""
    from forgepilot.benchmark import load_tasks

    tasks = {task.id: task for task in load_tasks()}
    task = tasks.get(task_id)
    if task is None:
        return "unknown"
    source_files = [name for name in task.files if not name.startswith("tests/")
                    and not name.lower().endswith(".md")]
    return "multi-file" if len(source_files) > 1 else "single-file"


def summarize(database: Path, output_dir: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    if not database.exists():
        raise ValueError(f"database not found: {database}")
    with sqlite3.connect(database) as connection:
        runs = pd.read_sql_query("SELECT * FROM runs", connection)
    if runs.empty:
        raise ValueError("database has no runs")
    raw = runs["raw_json"].map(json.loads)
    runs["observability"] = raw.map(lambda item: item.get("observability", "full"))
    runs["evidence_coverage"] = raw.map(lambda item: item.get("evidence_coverage"))
    runs["inspection_calls"] = raw.map(lambda item: item.get("inspection_calls"))
    runs["failure_type"] = raw.map(lambda item: item.get("failure_type", "unknown"))
    runs["steps"] = raw.map(lambda item: item.get("steps"))
    runs["complexity"] = runs["task_id"].map(task_complexity)
    rows = []
    coverage = {}
    for architecture, part in runs.groupby("architecture", sort=True):
        verified = part[part["passed"].notna()]
        test_total = verified["test_total"].sum()
        baseline_passed = verified["baseline_passed"].sum()
        recoverable = verified[verified["tool_failures"].fillna(0) > 0]
        tokens = verified.dropna(subset=["prompt_tokens", "completion_tokens"])
        rows.append({
            "architecture": architecture,
            "runs": len(part),
            "verified": len(verified),
            "unverified": len(part) - len(verified),
            "success_rate": float(verified["passed"].mean()) if len(verified) else None,
            "test_pass_rate": float(verified["test_passed"].sum() / test_total) if test_total else None,
            "regression_rate": float(verified["regressions"].sum() / baseline_passed) if baseline_passed else None,
            "mean_agent_seconds": float(verified["agent_seconds"].mean()) if verified["agent_seconds"].notna().any() else None,
            "mean_tokens": float((tokens["prompt_tokens"] + tokens["completion_tokens"]).mean()) if len(tokens) else None,
            "token_reported_runs": len(tokens),
            "recovery_rate": float(recoverable["recovered"].mean()) if len(recoverable) else None,
        })
        coverage[architecture] = verified.groupby(["task_id", "task_sha256", "model", "image"], dropna=False).size().to_dict()
    matched = (len(coverage) > 1 and all(coverage.values())
               and all(items == next(iter(coverage.values())) for items in coverage.values()))
    summary = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_dir / "summary.csv", index=False)
    observability_rows = []
    for (architecture, level), part in runs.groupby(["architecture", "observability"], sort=True):
        verified = part[part["passed"].notna()]
        observed = part.dropna(subset=["evidence_coverage"])
        inspected = part.dropna(subset=["inspection_calls"])
        observability_rows.append({
            "architecture": architecture, "observability": level,
            "runs": len(part), "verified": len(verified),
            "success_rate": float(verified["passed"].mean()) if len(verified) else None,
            "mean_evidence_coverage": float(observed["evidence_coverage"].mean()) if len(observed) else None,
            "mean_inspection_calls": float(inspected["inspection_calls"].mean()) if len(inspected) else None,
        })
    pd.DataFrame(observability_rows).to_csv(output_dir / "observability.csv", index=False)
    dimension_rows = []
    for dimension in ("complexity", "steps", "observability", "failure_type"):
        for (architecture, value), part in runs.groupby(["architecture", dimension], dropna=False, sort=True):
            verified = part[part["passed"].notna()]
            dimension_rows.append({
                "dimension": dimension, "architecture": architecture,
                "value": "missing" if pd.isna(value) else value,
                "runs": len(part), "verified": len(verified),
                "successes": int(verified["passed"].sum()),
                "success_rate": float(verified["passed"].mean()) if len(verified) else None,
            })
    pd.DataFrame(dimension_rows).to_csv(output_dir / "dimensions.csv", index=False)
    verified_rows = summary.dropna(subset=["success_rate"])
    if not verified_rows.empty:
        figure, axis = plt.subplots(figsize=(7, 4))
        axis.bar(verified_rows["architecture"], verified_rows["success_rate"] * 100)
        axis.set_ylim(0, 100)
        axis.set_ylabel("Task success rate (%)")
        axis.set_title("Observed benchmark runs")
        axis.tick_params(axis="x", rotation=15)
        figure.tight_layout()
        figure.savefig(output_dir / "success_rate.png", dpi=150)
        plt.close(figure)
    lines = ["# ForgePilot run summary", "",
             f"Recorded runs: {len(runs)}. Verified runs: {int(runs['passed'].notna().sum())}.",
             f"Matched task coverage across architectures: {'yes' if matched else 'no'}.", "",
             "Rates are descriptive. Success uses only verified runs. Test pass rate counts final pytest cases. "
             "Regression rate counts baseline passing cases that failed later. Recovery rate counts "
             "verified runs with a failed tool call that subsequently passed grading. Missing denominators "
             "are left blank. No statistical significance is inferred.", "",
             "| Architecture | Runs | Verified | Success | Test pass | Regression | Recovery | Mean agent seconds | Mean tokens | Token data |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|" ]
    for row in rows:
        def rate(value):
            return "—" if value is None else f"{value:.1%}"
        def number(value):
            return "—" if value is None else f"{value:.1f}"
        lines.append(f"| {row['architecture']} | {row['runs']} | {row['verified']} | "
                     f"{rate(row['success_rate'])} | {rate(row['test_pass_rate'])} | "
                     f"{rate(row['regression_rate'])} | {rate(row['recovery_rate'])} | "
                     f"{number(row['mean_agent_seconds'])} | {number(row['mean_tokens'])} | "
                     f"{row['token_reported_runs']} |")
    lines.extend(["", "## Information availability", "",
                  "Evidence coverage is the fraction of listed clue files read with the read_file tool. "
                  "Other forms of investigation are not counted.", "",
                  "| Architecture | Availability | Runs | Verified | Success | Evidence read | Mean inspection calls |",
                  "|---|---|---:|---:|---:|---:|---:|"])
    for row in observability_rows:
        lines.append(f"| {row['architecture']} | {row['observability']} | {row['runs']} | "
                     f"{row['verified']} | {rate(row['success_rate'])} | "
                     f"{rate(row['mean_evidence_coverage'])} | "
                     f"{number(row['mean_inspection_calls'])} |")
    lines.extend(["", "## Task complexity, agent steps, and failure type", "",
                  "Complexity is classified before outcomes: a fixture with more than one non-test, "
                  "non-document source file is multi-file; otherwise it is single-file. "
                  "Steps are observed agent turns, so step groups are descriptive and cannot establish causation. "
                  "Unrecognized historical task IDs have unknown complexity. Missing steps are shown separately.", "",
                  "| Dimension | Architecture | Value | Runs | Verified | Successes | Success |",
                  "|---|---|---|---:|---:|---:|---:|"])
    for row in dimension_rows:
        lines.append(f"| {row['dimension']} | {row['architecture']} | {row['value']} | "
                     f"{row['runs']} | {row['verified']} | {row['successes']} | "
                     f"{rate(row['success_rate'])} |")
    lines.extend(["", "## Interpretation and limits", "",
                  "The rows above describe recorded attempts only. Task difficulty, model behavior, and "
                  "sampling variation may confound architecture comparisons. A comparison requires the same "
                  "task hashes, model, runner image, and repeat counts for each architecture. "
                  f"Matched coverage: {'yes' if matched else 'no'}. "
                  "No confidence intervals or statistical significance are claimed."])
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"runs": len(runs), "verified": int(runs["passed"].notna().sum()),
            "matched_coverage": matched, "output_dir": str(output_dir)}
