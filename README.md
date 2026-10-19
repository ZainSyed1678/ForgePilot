# ForgePilot

ForgePilot tests coding agent architectures on reproducible software engineering tasks. It has nine fixed tasks and three architectures: basic tool use, planner–executor–critic, and reflection after tool failures. Four tasks introduce partial observability: the key requirement or failure cause must be found in repository documentation or dependencies. Runs are stored in SQLite and summarized descriptively. No live model benchmark results are included.

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

## Run experiments

The five original tasks cover arithmetic bugs, failing tests, dependencies, and runtime failures. Four partial-observability tasks cover optional profile fields, timeout configuration, legacy event aliases, and timezone-aware scheduling. Each task has a prompt, starter files, and a predefined acceptance test. The agent sees the prompt and starter files. The runner restores the original tests and adds the acceptance test after the attempt. Its grading result comes from pytest, never from the agent's final message.

To use a compatible Chat Completions API, set `FORGEPILOT_API_KEY` and `FORGEPILOT_MODEL`. `FORGEPILOT_API_URL` defaults to OpenAI's Chat Completions endpoint. Do not commit credentials. Live attempts can incur model API charges.

```sh
forgepilot tasks
forgepilot tasks --observability partial
forgepilot attempt negative_total --architecture basic
forgepilot attempt negative_total --architecture planner-executor-critic
forgepilot attempt negative_total --architecture reflective
forgepilot compare --task negative_total --repeats 3
forgepilot compare --observability partial --repeats 3
forgepilot analyze
```

`compare` without `--task` runs all five tasks for all three architectures. `--repeats 3` makes three fresh attempts per architecture and task. Each architecture uses the same 12-model-turn and 24-tool-call limits; planning, critique, and reflection spend turns from that budget. A Docker preflight runs before any model call. If it fails, the attempt is recorded as unverified and the model is not called.

Raw records go to `results/experiments.sqlite3` by default. Use `--output` on `attempt` or `compare` to select another database. `forgepilot analyze --database PATH --output-dir PATH` writes `summary.csv`, `observability.csv`, `report.md`, and (when verified runs exist) `success_rate.png`. The report flags uneven task coverage. It provides descriptive rates only.

## Measurements

- **Task success rate:** successful verified runs divided by verified runs. Success requires all restored original and acceptance tests to pass.
- **Test pass rate:** passing final pytest cases divided by collected final cases.
- **Regression rate:** baseline passing cases that fail after the attempt divided by baseline passing cases.
- **Execution time:** measured agent wall time; total wall time is also stored.
- **Token usage:** prompt and completion counts reported by the model API. Missing usage stays blank.
- **Recovery rate:** verified runs with at least one failed tool call that later pass grading, divided by verified runs with a failed tool call.

Each SQLite row also stores the fixture hash, model name, runner image tag, resource limits, steps, errors, raw grading evidence, and which clue files the agent read. `observability.csv` reports success and mean clue coverage by architecture and information availability. Clue coverage counts only explicit `read_file` calls; an agent may discover information through other tools. The analysis does not infer statistical significance.

## Code layout

- `agent.py`: the basic loop, shared budgets, and model HTTP client.
- `architectures.py`: planner–executor–critic and reflective flows.
- `tools.py`: file, Git, Docker, and pytest operations.
- `benchmark.py`: fixtures, setup, and JUnit-based grading.
- `runner.py`: isolated attempts and measured results.
- `storage.py`: SQLite raw result storage.
- `analysis.py`: pandas summary and matplotlib chart.
- `cli.py`: manual commands.

## Current limits

The local Docker engine is required for real attempts and grading. The nine tasks are a small initial benchmark, and tests are not a hardened security boundary against an adversarial agent. Runner image tags and model names are recorded, but immutable image digests and provider model snapshots are not pinned. The Docker image and all four partial-task graders have been run locally, including a scripted agent attempt. No paid model attempts have been run here. A multi-agent design remains deferred until baseline results justify it.
