"""Bounded repository access and Docker-isolated command execution."""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class RepositoryTools:
    def __init__(self, root: Path, *, image: str | None = None, timeout: int | None = None):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("repository root must be a directory")
        self.image = image or os.getenv("FORGEPILOT_DOCKER_IMAGE", "forgepilot-runner:phase1")
        self.timeout = timeout or int(os.getenv("FORGEPILOT_TIMEOUT_SECONDS", "30"))
        self.memory_mb = int(os.getenv("FORGEPILOT_MEMORY_MB", "512"))
        self.cpus = float(os.getenv("FORGEPILOT_CPUS", "1"))
        if self.timeout <= 0 or self.memory_mb <= 0 or self.cpus <= 0:
            raise ValueError("resource limits must be positive")

    def _path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("path escapes repository")
        if ".git" in path.relative_to(self.root).parts:
            raise ValueError("Git metadata is not accessible")
        return path

    def list_files(self) -> list[str]:
        excluded = {".git", ".venv", ".pytest_cache", "__pycache__"}
        return sorted(str(p.relative_to(self.root)).replace("\\", "/") for p in self.root.rglob("*")
                      if p.is_file() and not p.is_symlink()
                      and not excluded.intersection(p.relative_to(self.root).parts)
                      and not any(part.endswith(".egg-info") for part in p.relative_to(self.root).parts))

    def read_file(self, relative: str) -> str:
        return self._path(relative).read_text(encoding="utf-8")

    def write_file(self, relative: str, content: str) -> None:
        path = self._path(relative)
        if path == self.root:
            raise ValueError("expected a file path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def git(self, *args: str) -> CommandResult:
        if not args or args[0] not in {"status", "diff", "log"}:
            raise ValueError("unsupported git inspection command")
        completed = subprocess.run(["git", "-C", str(self.root), *args],
                                   capture_output=True, text=True, timeout=self.timeout, check=False)
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)

    def run(self, argv: list[str]) -> CommandResult:
        if not argv:
            raise ValueError("command must not be empty")
        container_name = f"forgepilot-{uuid.uuid4().hex}"
        command = ["docker", "run", "--rm", "--name", container_name, "--network", "none", "--pids-limit", "128",
                   "--memory", f"{self.memory_mb}m", "--cpus", str(self.cpus),
                   "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
                   "--user", "65534:65534", "-v", f"{self.root}:/workspace:rw",
                   "-w", "/workspace", self.image, *argv]
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       timeout=self.timeout, check=False)
            return CommandResult(completed.returncode, completed.stdout, completed.stderr)
        except subprocess.TimeoutExpired as exc:
            subprocess.run(["docker", "rm", "-f", container_name],
                           capture_output=True, text=True, timeout=10, check=False)
            output = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
            return CommandResult(124, output, "command timed out")

    def pytest(self, *args: str) -> CommandResult:
        return self.run(["python", "-m", "pytest", *args])

    def patch(self) -> str:
        result = self.git("diff", "--binary", "HEAD", "--")
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return result.stdout
