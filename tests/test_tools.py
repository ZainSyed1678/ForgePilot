import subprocess

import pytest

from forgepilot.tools import RepositoryTools


def test_filesystem_stays_within_repository(tmp_path):
    tools = RepositoryTools(tmp_path)
    tools.write_file("src/answer.py", "answer = 42\n")
    assert tools.read_file("src/answer.py") == "answer = 42\n"
    assert tools.list_files() == ["src/answer.py"]
    with pytest.raises(ValueError, match="escapes"):
        tools.read_file("../secret")
    with pytest.raises(ValueError, match="Git metadata"):
        tools.write_file(".git/config", "bad")


def test_symlink_cannot_escape_repository(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("private")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="escapes"):
        RepositoryTools(tmp_path).read_file("link.txt")


def test_git_inspection_and_patch(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "example.py").write_text("old\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "example.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test",
                    "-c", "user.email=test@example.com", "commit", "-qm", "initial"], check=True)
    tools = RepositoryTools(tmp_path)
    tools.write_file("example.py", "new\n")
    assert "example.py" in tools.git("status", "--short").stdout
    assert "+new" in tools.patch()
    with pytest.raises(ValueError, match="unsupported"):
        tools.git("reset", "--hard")


def test_docker_command_is_bounded(tmp_path, monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    tools = RepositoryTools(tmp_path, image="local:test", timeout=5)
    result = tools.pytest("-q")
    assert result.stdout == "ok"
    assert seen["command"][-5:] == ["local:test", "python", "-m", "pytest", "-q"]
    assert seen["command"][seen["command"].index("--network") + 1] == "none"
    assert seen["timeout"] == 5


def test_timeout_removes_container(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1] == "run":
            raise subprocess.TimeoutExpired(command, 2)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = RepositoryTools(tmp_path).run(["python", "-V"])
    assert result.returncode == 124
    assert calls[1][:3] == ["docker", "rm", "-f"]
    assert calls[1][3] == calls[0][calls[0].index("--name") + 1]
