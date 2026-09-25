from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from gameops_investigator.config import scenario_catalog
from gameops_investigator.database import execute_readonly


def build_database(tmp_path: Path, users: list[tuple], events: list[tuple]) -> Path:
    path = tmp_path / "cohort_evidence.sqlite"
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE users (user_id INTEGER PRIMARY KEY, install_date TEXT, "
                "strategy_segment TEXT, app_version TEXT, channel TEXT)"
            )
            connection.execute("CREATE TABLE events (user_id INTEGER, event_name TEXT, event_date TEXT)")
            connection.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", users)
            connection.executemany("INSERT INTO events VALUES (?, ?, ?)", events)
    return path


def evidence_rows(path: Path) -> list[dict]:
    # Exercise the configured SQL that the investigator actually uses, not a test copy.
    sql, = scenario_catalog()["segment_churn"]["evidence_queries"]
    result = execute_readonly(sql, path=path)
    assert not result.truncated
    return result.rows


@pytest.mark.parametrize("events_per_user", [1, 28])
def test_cohort_size_does_not_grow_with_event_volume(tmp_path: Path, events_per_user: int):
    users = [(user_id, "2026-08-11", "leveraged", "0.9.3", "beta") for user_id in range(1, 4)]
    events = [
        (user_id, "session_start", "2026-08-12")
        for user_id in range(1, 4)
        for _ in range(events_per_user)
    ]
    path = build_database(tmp_path, users, events)

    assert evidence_rows(path) == [{
        "install_date": "2026-08-11",
        "strategy_segment": "leveraged",
        "cohort_users": 3,
        "d1_users": 3,
    }]


@pytest.fixture
def mixed_cohort_database(tmp_path: Path) -> Path:
    users = [
        (1, "2026-08-11", "leveraged", "0.9.3", "beta"),
        (2, "2026-08-11", "leveraged", "0.9.3", "beta"),  # No events; still in the cohort.
        (3, "2026-08-11", "leveraged", "0.9.3", "beta"),
        (4, "2026-08-11", "hedged", "0.9.3", "beta"),
        (5, "2026-08-12", "leveraged", "0.9.3", "beta"),
        (6, "2026-08-12", "leveraged", "0.9.3", "beta"),
        (7, "2026-08-13", "hedged", "0.9.3", "beta"),  # Entire group has no events.
        (8, "2026-08-11", "leveraged", "0.9.3", "campus_demo"),
        (9, "2026-08-11", "leveraged", "0.9.2", "beta"),
        (10, "2026-07-31", "leveraged", "0.9.3", "beta"),
        (11, "2026-08-15", "leveraged", "0.9.3", "beta"),
    ]
    events = [
        (1, "session_start", "2026-08-12"),
        (1, "session_start", "2026-08-12"),  # Repeat D1 sessions must count once.
        (1, "trade_completed", "2026-08-12"),
        (1, "session_start", "2026-08-11"),
        (1, "session_start", "2026-08-13"),
        (3, "trade_completed", "2026-08-12"),  # D1 activity alone is not a D1 session.
        (3, "session_start", "2026-08-13"),
        (4, "session_start", "2026-08-12"),
        (5, "session_start", "2026-08-13"),
        (5, "session_start", "2026-08-13"),
        (6, "session_start", "2026-08-12"),
        (8, "session_start", "2026-08-12"),
        (9, "session_start", "2026-08-12"),
        (10, "session_start", "2026-08-01"),
        (11, "session_start", "2026-08-16"),
    ]
    return build_database(tmp_path, users, events)


def test_users_without_events_remain_in_the_cohort(mixed_cohort_database: Path):
    rows = {
        (row["install_date"], row["strategy_segment"]): row
        for row in evidence_rows(mixed_cohort_database)
    }

    assert rows[("2026-08-11", "leveraged")]["cohort_users"] == 3
    assert rows[("2026-08-13", "hedged")]["cohort_users"] == 1
    assert rows[("2026-08-13", "hedged")]["d1_users"] == 0


def test_d1_users_are_distinct_and_require_next_day_sessions(mixed_cohort_database: Path):
    rows = evidence_rows(mixed_cohort_database)

    assert {
        (row["install_date"], row["strategy_segment"]): row["d1_users"] for row in rows
    } == {
        ("2026-08-11", "hedged"): 1,
        ("2026-08-11", "leveraged"): 1,
        ("2026-08-12", "leveraged"): 1,
        ("2026-08-13", "hedged"): 0,
    }
    assert all(0 <= row["d1_users"] <= row["cohort_users"] for row in rows)


def test_each_group_matches_independent_users_only_counts(mixed_cohort_database: Path):
    # The independent denominator never joins events, so event fan-out cannot affect it.
    expected = execute_readonly(
        "SELECT install_date, strategy_segment, COUNT(*) AS cohort_users FROM users "
        "WHERE app_version = '0.9.3' AND channel <> 'campus_demo' "
        "AND install_date BETWEEN '2026-08-01' AND '2026-08-14' "
        "GROUP BY install_date, strategy_segment ORDER BY install_date, strategy_segment",
        path=mixed_cohort_database,
    ).rows
    actual = [
        {key: row[key] for key in ("install_date", "strategy_segment", "cohort_users")}
        for row in evidence_rows(mixed_cohort_database)
    ]

    assert actual == expected
    assert len(actual) == 4
    assert sum(row["cohort_users"] for row in actual) == 7
