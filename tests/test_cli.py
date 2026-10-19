import sys

from forgepilot.cli import main


def test_cli_reads_file(tmp_path, monkeypatch, capsys):
    (tmp_path / "example.py").write_text("answer = 42\n")
    monkeypatch.setattr(sys, "argv", ["forgepilot", "--repo", str(tmp_path), "read", "example.py"])
    assert main() == 0
    assert capsys.readouterr().out == "answer = 42\n"


def test_compare_uses_each_architecture_for_same_task(monkeypatch, capsys):
    from forgepilot import cli

    seen = []

    def fake_run(task_id, output, *, architecture):
        seen.append((task_id, architecture))
        return {"passed": False}

    monkeypatch.setattr(cli, "run_task", fake_run)
    monkeypatch.setattr(sys, "argv", ["forgepilot", "compare", "--task", "negative_total"])
    assert cli.main() == 0
    assert seen == [("negative_total", name) for name in cli.ARCHITECTURES]
    assert len(capsys.readouterr().out.splitlines()) == 3
