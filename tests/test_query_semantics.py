from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from gameops_investigator.database import QueryRejected, execute_readonly


@pytest.fixture
def sample_database(tmp_path: Path) -> Path:
    path = tmp_path / "query_semantics.sqlite"
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY)")
            connection.executemany("INSERT INTO users VALUES (?)", [(value,) for value in range(1, 11)])
            connection.execute("CREATE TABLE incident_ground_truth (secret INTEGER)")
            connection.execute("INSERT INTO incident_ground_truth VALUES (42)")
    return path


@pytest.mark.parametrize(
    ("sql", "parameters"),
    [
        pytest.param(
            "WITH sample AS (SELECT user_id FROM users ORDER BY user_id LIMIT 8) "
            "SELECT COUNT(*) AS n, SUM(user_id) AS total FROM sample",
            (),
            id="cte-aggregate",
        ),
        pytest.param(
            "SELECT COUNT(*) AS n, SUM(user_id) AS total FROM "
            "(SELECT user_id FROM users ORDER BY user_id LIMIT 8)",
            (),
            id="subquery-aggregate",
        ),
        pytest.param(
            "SELECT user_id FROM (SELECT user_id FROM users ORDER BY user_id LIMIT 8) "
            "WHERE user_id >= 6 ORDER BY user_id",
            (),
            id="filter-after-nested-limit",
        ),
        pytest.param(
            "SELECT user_id FROM (SELECT user_id FROM users ORDER BY user_id LIMIT 8) "
            "ORDER BY user_id DESC LIMIT 2",
            (),
            id="outer-limit-after-nested-limit",
        ),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT (2 + 3)", (), id="parenthesized-limit"),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT 10 - 8", (), id="subtraction-limit"),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT 10 / 2", (), id="division-limit"),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT -1", (), id="negative-limit"),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT ?", (2,), id="bound-limit-below-cap"),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT ?", (8,), id="bound-limit-above-cap"),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT 8 OFFSET 2", (), id="count-offset"),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT 2, 8", (), id="offset-count"),
        pytest.param(
            "SELECT user_id FROM users ORDER BY user_id LIMIT (2 + 3) OFFSET (1 + 1)",
            (),
            id="expression-offset",
        ),
        pytest.param(
            "SELECT user_id FROM users ORDER BY user_id LIMIT ? OFFSET ?",
            (2, 3),
            id="bound-count-offset",
        ),
        pytest.param("SELECT user_id FROM users ORDER BY user_id LIMIT ?, ?", (3, 2), id="bound-offset-count"),
    ],
)
def test_output_cap_preserves_original_sql_semantics(sample_database: Path, sql: str, parameters: tuple):
    with closing(sqlite3.connect(sample_database)) as connection:
        connection.row_factory = sqlite3.Row
        expected = [dict(row) for row in connection.execute(sql, parameters).fetchall()]

    result = execute_readonly(sql, parameters, row_limit=3, path=sample_database)

    assert result.rows == expected[:3]
    assert result.row_count == min(len(expected), 3)
    assert result.truncated is (len(expected) > 3)


@pytest.mark.parametrize(
    ("sql", "expected_ids", "truncated"),
    [
        pytest.param("SELECT user_id FROM users WHERE user_id < 0", [], False, id="empty-result"),
        pytest.param("SELECT user_id FROM users LIMIT 0", [], False, id="zero-explicit-limit"),
        pytest.param(
            "SELECT user_id FROM users WHERE user_id <= 3 ORDER BY user_id", [1, 2, 3], False, id="exact-cap"
        ),
        pytest.param(
            "SELECT user_id FROM users WHERE user_id <= 4 ORDER BY user_id", [1, 2, 3], True, id="cap-plus-one"
        ),
        pytest.param(
            "SELECT user_id FROM users ORDER BY user_id LIMIT 3", [1, 2, 3], False, id="explicit-limit-at-cap"
        ),
    ],
)
def test_truncation_describes_only_omitted_output_rows(
    sample_database: Path, sql: str, expected_ids: list[int], truncated: bool
):
    result = execute_readonly(sql, row_limit=3, path=sample_database)

    assert result.rows == [{"user_id": value} for value in expected_ids]
    assert result.row_count == len(expected_ids)
    assert result.truncated is truncated


def test_expensive_aggregate_still_times_out(sample_database: Path):
    sql = (
        "WITH RECURSIVE series(n) AS ("
        "SELECT 1 UNION ALL SELECT n + 1 FROM series WHERE n < 10000000"
        ") SELECT SUM(n) AS total FROM series"
    )

    with pytest.raises(QueryRejected, match="Query timed out"):
        execute_readonly(sql, row_limit=3, timeout_ms=50, path=sample_database)


@pytest.mark.parametrize(
    "sql",
    [
        "WITH hidden AS (SELECT secret FROM incident_ground_truth LIMIT 1) SELECT * FROM hidden",
        "SELECT * FROM (SELECT secret FROM incident_ground_truth LIMIT 1)",
    ],
)
def test_nested_queries_still_reject_hidden_tables(sample_database: Path, sql: str):
    with pytest.raises(QueryRejected, match="not authorized|prohibited"):
        execute_readonly(sql, row_limit=3, path=sample_database)
