from __future__ import annotations

import json
import sqlite3
import sys

import pytest

from gameops_investigator.cli import main as cli_main
from gameops_investigator import database
from gameops_investigator.database import QueryRejected, validate_readonly_sql
from gameops_investigator.tools import query_metrics


def test_readonly_query_executes_and_is_limited():
    result = query_metrics("SELECT user_id FROM users ORDER BY user_id", row_limit=17)
    assert result["ok"]
    assert result["row_count"] == 17
    assert result["truncated"] is True
    assert result["executed_sql"] == "SELECT user_id FROM users ORDER BY user_id"


def test_explicit_limit_within_bound_is_not_reported_as_safety_truncation():
    result = query_metrics("SELECT user_id FROM users ORDER BY user_id LIMIT 5", row_limit=17)
    assert result["ok"]
    assert result["row_count"] == 5
    assert result["truncated"] is False
    assert result["executed_sql"].endswith("LIMIT 5")


def test_mutations_and_multiple_statements_are_rejected():
    for sql in ("DELETE FROM events", "PRAGMA table_info(events)", "SELECT 1; SELECT 2"):
        try:
            validate_readonly_sql(sql)
        except QueryRejected:
            pass
        else:
            raise AssertionError(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 'It''s safe; drop -- text' AS note",
        'SELECT "delete" FROM (SELECT 1 AS "delete")',
        "SELECT `update` FROM (SELECT 1 AS `update`)",
        "SELECT [pragma] FROM (SELECT 1 AS [pragma])",
    ],
)
def test_quoted_text_and_identifiers_are_not_treated_as_sql(sql):
    result = query_metrics(sql)
    assert result["ok"]
    assert result["row_count"] == 1


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT user_id FROM users LIMIT 999",
        "SELECT user_id FROM users LIMIT 999 OFFSET 10",
        "SELECT user_id FROM users LIMIT 10, 999",
    ],
)
def test_limit_forms_preserve_sql_and_bound_returned_rows(sql):
    assert validate_readonly_sql(sql, row_limit=3) == sql
    result = query_metrics(sql, row_limit=3)
    assert result["ok"]
    assert result["executed_sql"] == sql
    assert result["row_count"] == 3
    assert result["truncated"] is True


def test_limit_text_inside_a_literal_is_preserved():
    sql = "SELECT 'limit 999' AS note"
    assert validate_readonly_sql(sql, row_limit=3) == sql


def test_unterminated_quotes_are_rejected():
    with pytest.raises(QueryRejected, match="unterminated"):
        validate_readonly_sql("SELECT 'unfinished")


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
    assert result["truncated"] is True
    assert result["executed_sql"] == "SELECT user_id FROM users ORDER BY user_id"


@pytest.mark.parametrize("sql", ["SELECT 1 AS value", "SELECT 1 UNION ALL SELECT 2", "SELECT missing_column"])
def test_query_connection_is_closed_after_success_truncation_or_error(monkeypatch, sql):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    monkeypatch.setattr(database, "connect_readonly", lambda path: connection)
    result = query_metrics(sql, row_limit=1)
    assert result["ok"] is ("missing_column" not in sql)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
