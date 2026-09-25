from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from gameops_investigator.detector import detect_anomalies
from gameops_investigator.metrics import MetricEngine


@pytest.mark.parametrize("minimum", [20, 50])
def test_significant_retention_changes_require_both_real_cohort_sizes(tmp_path, minimum):
    """A large z score must not rescue either undersized side of a comparison."""
    path = tmp_path / "retention_samples.sqlite"
    sizes = {
        "small_baseline": (minimum - 1, minimum * 2),
        "small_current": (minimum * 2, minimum - 1),
        "at_boundary": (minimum, minimum),
    }
    users = []
    events = []
    for channel, (baseline_size, current_size) in sizes.items():
        for install_date, session_date, count, retained_fraction in (
            ("2026-01-01", "2026-01-02", baseline_size, 0.9),
            ("2026-02-01", "2026-02-02", current_size, 0.1),
        ):
            for index in range(count):
                user_id = len(users) + 1
                users.append((user_id, install_date, channel))
                if index < round(count * retained_fraction):
                    events.append((user_id, "session_start", session_date))
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE users (user_id INTEGER PRIMARY KEY, install_date TEXT, channel TEXT)"
            )
            connection.execute("CREATE TABLE events (user_id INTEGER, event_name TEXT, event_date TEXT)")
            connection.executemany("INSERT INTO users VALUES (?, ?, ?)", users)
            connection.executemany("INSERT INTO events VALUES (?, ?, ?)", events)

    result = detect_anomalies(
        "d1_retention",
        current_start="2026-02-01", current_end="2026-02-01",
        baseline_start="2026-01-01", baseline_end="2026-01-01",
        dimensions=["channel"], min_denominator=minimum,
        engine=MetricEngine(path),
    )

    # These are real SQL-derived comparisons with pronounced retention drops,
    # not patched sample sizes or invented statistical outputs.
    rows = {row["dimensions"]["channel"]: row for row in result["all_comparisons"]}
    assert set(rows) == set(sizes)
    for channel, (baseline_size, current_size) in sizes.items():
        row = rows[channel]
        assert row["baseline"]["denominator"] == baseline_size
        assert row["current"]["denominator"] == current_size
        assert row["z_score"] < -1.96
    assert result["anomaly_count"] == 1
    assert [row["dimensions"]["channel"] for row in result["anomalies"]] == ["at_boundary"]
    assert result["anomalies"][0]["direction"] == "decrease"
