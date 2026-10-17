# ForgePilot

Phase 1 provides a small repository tool layer for future coding agents. It supports file inspection and edits, read-only Git inspection, Docker-isolated terminal commands, pytest, and patch output. No LLM agent, benchmark runner, or experiment storage is implemented yet.

## Setup

Requires Python 3.11+, Git, and Docker with a running engine. From this directory:

```sh
python -m pip install -e ".[dev]"
docker build -t forgepilot-runner:phase1 .
python -m pytest
```

Set `FORGEPILOT_DOCKER_IMAGE=forgepilot-runner:phase1` (or pass it in your shell environment). Other options are in [`.env.example`](.env.example); the application reads environment variables directly. Do not put secrets in the repository.

## Use

Point the CLI at an existing Git repository:

```sh
forgepilot --repo /path/to/repo files
forgepilot --repo /path/to/repo read src/example.py
forgepilot --repo /path/to/repo git status --short
forgepilot --repo /path/to/repo run python -V
forgepilot --repo /path/to/repo test -q
forgepilot --repo /path/to/repo write src/example.py 'new content'
forgepilot --repo /path/to/repo patch
```

The Python API is `forgepilot.tools.RepositoryTools`. Its `run` method takes an argument list, without a shell. Docker runs without network access and with CPU, memory, process, and wall-time limits. Run against disposable repositories: the container has write access to the selected repository so it can modify code. Git inspection runs on the host.

## Architecture

`tools.py` owns filesystem, Git, and Docker operations. `cli.py` is a thin manual interface. Future agents can call the same tool methods. Phase 1 does not automatically generate code or decide which commands to run.

## Limitations

- Docker must be available and the runner image must be built locally.
- Patch output includes tracked changes; add new files to Git's index before calling `patch`.
- The runner image contains Python and pytest only. Repositories needing other dependencies need a compatible custom image.
- Docker resource flags are an initial boundary, not a hardened sandbox for hostile code.
