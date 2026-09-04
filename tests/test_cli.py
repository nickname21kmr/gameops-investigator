from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from gameops_investigator import cli


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "gameops_investigator.cli", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    ("args", "expected_code", "expected_ok"),
    [
        pytest.param(["SELECT 1 AS value"], 0, True, id="success"),
        pytest.param(
            ["SELECT user_id FROM users", "--row-limit", "7", "--timeout-ms", "750"],
            0, True, id="custom-bounds",
        ),
        pytest.param(["DELETE FROM users"], 1, False, id="mutation-rejected"),
        pytest.param(["SELECT 1", "--row-limit", "501"], 1, False, id="row-limit-rejected"),
        pytest.param(["SELECT 1", "--timeout-ms", "49"], 1, False, id="timeout-rejected"),
        pytest.param(["SELECT * FROM incident_ground_truth"], 1, False, id="hidden-table-rejected"),
        pytest.param(["SELECT FROM users"], 1, False, id="invalid-sql"),
    ],
)
def test_query_process_exit_status(args, expected_code, expected_ok):
    completed = run_cli("query", *args)
    payload = json.loads(completed.stdout)
    assert completed.returncode == expected_code
    assert payload["ok"] is expected_ok
    assert payload["policy"] == "read_only_allowlist"
    assert completed.stderr == ""
    if not expected_ok:
        assert payload["error"]


@pytest.mark.parametrize("args", [[], ["SELECT 1", "--row-limit", "not-an-integer"]])
def test_query_usage_errors_exit_with_code_two(args):
    completed = run_cli("query", *args)
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "usage:" in completed.stderr.lower()


@pytest.mark.parametrize(
    ("options", "row_limit", "timeout_ms"),
    [([], 200, 2000), (["--row-limit", "7", "--timeout-ms", "750"], 7, 750)],
)
def test_query_main_forwards_bounds_and_returns_success(monkeypatch, capsys, options, row_limit, timeout_ms):
    def query(sql, **kwargs):
        assert sql == "SELECT 1"
        assert kwargs == {"row_limit": row_limit, "timeout_ms": timeout_ms}
        return {"ok": True}

    monkeypatch.setattr(cli, "query_metrics", query)
    monkeypatch.setattr(sys, "argv", ["gameops", "query", "SELECT 1", *options])
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True}


@pytest.mark.parametrize(
    ("command", "argument", "runner", "method", "payload", "expected_code"),
    [
        ("investigate", "tutorial_failure", cli.DeterministicInvestigator, "investigate", {"report": {}}, 0),
        ("claude", "test question", cli.ClaudeCodeRunner, "run", {"ok": True, "payload": {}}, 0),
        ("claude", "test question", cli.ClaudeCodeRunner, "run", {"ok": False, "error": "Unavailable"}, 1),
    ],
)
def test_other_commands_return_status_without_live_calls(
    monkeypatch, capsys, command, argument, runner, method, payload, expected_code
):
    monkeypatch.setattr(runner, method, lambda self, value: payload)
    monkeypatch.setattr(sys, "argv", ["gameops", command, argument])
    assert cli.main() == expected_code
    assert json.loads(capsys.readouterr().out) == payload
