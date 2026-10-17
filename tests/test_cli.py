import sys

from forgepilot.cli import main


def test_cli_reads_file(tmp_path, monkeypatch, capsys):
    (tmp_path / "example.py").write_text("answer = 42\n")
    monkeypatch.setattr(sys, "argv", ["forgepilot", "--repo", str(tmp_path), "read", "example.py"])
    assert main() == 0
    assert capsys.readouterr().out == "answer = 42\n"
