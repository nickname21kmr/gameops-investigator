from __future__ import annotations

import json
import sys

from gameops_investigator.cli import main as cli_main
from gameops_investigator.database import QueryRejected, validate_readonly_sql
from gameops_investigator.tools import query_metrics


def test_readonly_query_executes_and_is_limited():
    result = query_metrics("SELECT user_id FROM users ORDER BY user_id", row_limit=17)
    assert result["ok"]
    assert result["row_count"] == 17
    assert "LIMIT 17" in result["executed_sql"]


def test_mutations_and_multiple_statements_are_rejected():
    for sql in ("DELETE FROM events", "PRAGMA table_info(events)", "SELECT 1; SELECT 2"):
        try:
            validate_readonly_sql(sql)
        except QueryRejected:
            pass
        else:
            raise AssertionError(sql)


def test_hidden_ground_truth_table_is_blocked_by_authorizer():
    result = query_metrics("SELECT * FROM incident_ground_truth")
    assert not result["ok"]
    assert any(token in result["error"].lower() for token in ("not authorized", "prohibited"))


def test_timeout_and_limit_inputs_are_bounded(monkeypatch, capsys):
    assert not query_metrics("SELECT * FROM users", row_limit=501)["ok"]
    assert not query_metrics("SELECT * FROM users", timeout_ms=49)["ok"]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gameops",
            "query",
            "SELECT user_id FROM users ORDER BY user_id",
            "--row-limit",
            "7",
            "--timeout-ms",
            "750",
        ],
    )
    cli_main()
    result = json.loads(capsys.readouterr().out)
    assert result["ok"]
    assert result["row_count"] == 7
    assert "LIMIT 7" in result["executed_sql"]
