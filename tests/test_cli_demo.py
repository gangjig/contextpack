"""Demo outcomes and the CLI contract."""

import json

from contextpack.cli import main
from contextpack.demo import run_demo


def test_demo_outcome_by_item():
    result = run_demo()
    assert result.entry_for("system").status == "kept"
    assert result.entry_for("task").status == "kept"
    assert result.entry_for("retrieved_doc").status == "kept"
    assert result.entry_for("recent_history").status == "kept"
    assert result.entry_for("tool_result").status == "truncated"
    assert result.entry_for("old_history").status == "dropped"
    assert result.used_tokens == result.budget_tokens == 260
    assert "old_history" not in result.text
    # The dropped item's content really is absent, not just unlisted.
    assert "password reset emails" not in result.text


def test_cli_demo(capsys):
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "| tool_result | **truncated** |" in out
    assert "## Assembled context" in out


def test_cli_pack_stdout_and_manifest(tmp_path, capsys):
    items = tmp_path / "items.json"
    items.write_text(
        json.dumps(
            [
                {"name": "a", "text": "hello world", "priority": 5},
                {"name": "b", "text": "x" * 200, "priority": 1},
            ]
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "m.json"
    rc = main(
        [
            "pack", str(items), "--budget", "10",
            "--manifest", str(manifest),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "hello world" in captured.out
    assert "kept 1, truncated 0, dropped 1" in captured.err
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["counts"] == {"kept": 1, "truncated": 0, "dropped": 1}


def test_cli_pack_out_file(tmp_path, capsys):
    items = tmp_path / "items.json"
    items.write_text(
        json.dumps([{"name": "a", "text": "only this"}]), encoding="utf-8"
    )
    out_file = tmp_path / "context.txt"
    assert (
        main(["pack", str(items), "--budget", "100", "--out", str(out_file)])
        == 0
    )
    assert out_file.read_text(encoding="utf-8") == "only this"
    assert capsys.readouterr().out == ""


def test_cli_missing_file_returns_2(tmp_path, capsys):
    assert main(["pack", str(tmp_path / "nope.json"), "--budget", "10"]) == 2
    assert "error:" in capsys.readouterr().err
