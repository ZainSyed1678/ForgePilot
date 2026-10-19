"""SQLite storage for raw benchmark attempts."""

import json
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    time_utc TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_sha256 TEXT NOT NULL,
    architecture TEXT NOT NULL,
    model TEXT,
    image TEXT,
    repeat_index INTEGER NOT NULL,
    passed INTEGER,
    test_passed INTEGER,
    test_total INTEGER,
    regressions INTEGER,
    baseline_passed INTEGER,
    agent_seconds REAL,
    wall_seconds REAL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    tool_failures INTEGER,
    recovered INTEGER,
    raw_json TEXT NOT NULL
)
"""


def save_run(database: Path, record: dict) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    columns = ("run_id", "time_utc", "task_id", "task_sha256", "architecture",
               "model", "image", "repeat_index", "passed", "test_passed", "test_total",
               "regressions", "baseline_passed", "agent_seconds", "wall_seconds",
               "prompt_tokens", "completion_tokens", "tool_failures", "recovered")
    values = [record.get(column) for column in columns]
    values.append(json.dumps(record, sort_keys=True))
    with sqlite3.connect(database) as connection:
        connection.execute(SCHEMA)
        connection.execute(
            f"INSERT INTO runs ({', '.join(columns)}, raw_json) VALUES ({', '.join('?' for _ in values)})",
            values,
        )
