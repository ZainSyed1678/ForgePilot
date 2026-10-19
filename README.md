# ForgePilot

ForgePilot is a small research platform for testing coding agents on reproducible software engineering tasks. Phase 3 adds planner–executor–critic and reflective agents alongside the basic tool-using agent. All three run against the same five tasks, model API, tools, and budgets. No benchmark results or statistical analysis are claimed yet.

## Setup

Requires Python 3.11+, Git, and Docker with a running engine. From this directory:

```sh
python -m pip install -e ".[dev]"
docker build -t forgepilot-runner:phase1 .
python -m pytest -q
```

The runner uses `forgepilot-runner:phase1` by default. Docker runs commands without network access and with CPU, memory, process, and wall-time limits. See [`.env.example`](.env.example) for configuration. Use a disposable repository; the container can modify it.

## Repository tools

```sh
forgepilot --repo /path/to/repo files
forgepilot --repo /path/to/repo read src/example.py
forgepilot --repo /path/to/repo git status --short
forgepilot --repo /path/to/repo run python -V
forgepilot --repo /path/to/repo test -q
forgepilot --repo /path/to/repo write src/example.py 'new content'
forgepilot --repo /path/to/repo patch
```

The same operations are available through `forgepilot.tools.RepositoryTools`. Git inspection runs on the host; terminal and pytest commands run in Docker. Patch output includes tracked changes. Stage new files in Git before requesting a patch that includes them.

## Benchmark

Five fixed tasks cover arithmetic bugs, a failing text test, configuration dependency discovery, empty-input runtime failure, and port parsing. Each task has a prompt, starter files, and an acceptance test. The agent sees the prompt and starter files. The runner injects the acceptance test only after the attempt and grades it with pytest. A model's final message never determines success.

To use a compatible Chat Completions API, set `FORGEPILOT_API_KEY` and `FORGEPILOT_MODEL`. `FORGEPILOT_API_URL` defaults to OpenAI's Chat Completions endpoint. Do not commit credentials. A live attempt calls a paid model API and can incur charges.

```sh
forgepilot tasks
forgepilot attempt negative_total --architecture basic
forgepilot attempt negative_total --architecture planner-executor-critic
forgepilot attempt negative_total --architecture reflective
forgepilot compare --task negative_total
```

Each architecture is limited to 12 model turns and 24 tool calls. Planning, critique, and reflection turns count toward the same limit. Results append to `results/runs.jsonl`, with task ID, architecture, model, steps, final message, grading output, and an explicit pass/fail/unverified value. Run each task in a fresh temporary repository. You can select a different output file with `--output`.

## Code layout

- `agent.py`: the basic tool-calling loop, shared budgets, and model HTTP client.
- `architectures.py`: planner–executor–critic and reflective agent flows.
- `tools.py`: file, Git, Docker, and pytest operations.
- `benchmark.py`: fixture loading, workspace setup, and acceptance grading.
- `runner.py`: one isolated attempt and JSONL result recording.
- `cli.py`: manual commands.

## Current limits

The three architectures have not yet been evaluated with live model runs. A multi-agent architecture is deferred until baseline results show a reason to add its complexity. The benchmark is intentionally small and its acceptance tests are not a security boundary against an adversarial agent. The local Docker engine is required for actual attempts and grading; a missing engine yields an unverified result. No live model attempts or benchmark success claims are included here. Repeated runs, cost metrics, SQLite storage, and statistical analysis are later phases. The `compare` command runs three paid attempts per selected task (15 attempts by default).
