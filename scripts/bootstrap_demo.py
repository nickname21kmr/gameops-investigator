from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DB = PROJECT_ROOT / "data" / "source" / "newton_market_analytics.db"
TARGET_DB = PROJECT_ROOT / "data" / "gameops_demo.db"
ARTIFACTS = PROJECT_ROOT / "artifacts"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scalar(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(connection.execute(sql, params).fetchone()[0])


def bootstrap() -> dict:
    if not SOURCE_DB.exists():
        raise FileNotFoundError(f"Source database missing: {SOURCE_DB}")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    temporary = TARGET_DB.with_suffix(".building.db")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(SOURCE_DB, temporary)

    connection = sqlite3.connect(temporary)
    connection.execute("PRAGMA foreign_keys = ON")
    source_users = scalar(connection, "SELECT COUNT(*) FROM users")
    source_events = scalar(connection, "SELECT COUNT(*) FROM events")
    if (source_users, source_events) != (5000, 136164):
        raise RuntimeError(f"Unexpected source snapshot: users={source_users}, events={source_events}")

    connection.executescript(
        """
        DROP TABLE IF EXISTS dataset_manifest;
        DROP TABLE IF EXISTS incident_catalog;
        DROP TABLE IF EXISTS incident_ground_truth;

        CREATE TABLE dataset_manifest (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE incident_catalog (
            incident_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            alert_metric TEXT NOT NULL,
            baseline_start TEXT NOT NULL,
            baseline_end TEXT NOT NULL,
            current_start TEXT NOT NULL,
            current_end TEXT NOT NULL,
            review_status TEXT NOT NULL
        );

        CREATE TABLE incident_ground_truth (
            incident_id TEXT PRIMARY KEY,
            root_cause_id TEXT NOT NULL,
            root_cause TEXT NOT NULL,
            injected_entity_count INTEGER NOT NULL,
            injection_notes TEXT NOT NULL
        );
        """
    )

    tutorial_users = [
        row[0]
        for row in connection.execute(
            """
            SELECT user_id
            FROM users
            WHERE app_version = '0.9.3'
              AND channel = 'campus_demo'
              AND install_date BETWEEN '2026-08-11' AND '2026-08-14'
              AND CAST(SUBSTR(user_id, 5) AS INTEGER) % 10 < 7
            """
        )
    ]
    connection.executemany(
        """
        DELETE FROM events
        WHERE user_id = ?
          AND event_name NOT IN ('game_install', 'new_run_start')
          AND NOT (
            event_name = 'session_start'
            AND event_date = (SELECT install_date FROM users WHERE users.user_id = events.user_id)
          )
        """,
        [(user_id,) for user_id in tutorial_users],
    )

    segment_users = [
        row[0]
        for row in connection.execute(
            """
            SELECT user_id
            FROM users
            WHERE app_version = '0.9.3'
              AND channel <> 'campus_demo'
              AND strategy_segment = 'leveraged'
              AND install_date BETWEEN '2026-08-11' AND '2026-08-14'
              AND CAST(SUBSTR(user_id, 5) AS INTEGER) % 10 < 8
            """
        )
    ]
    connection.executemany(
        """
        DELETE FROM events
        WHERE user_id = ?
          AND event_name = 'session_start'
          AND event_date > (SELECT install_date FROM users WHERE users.user_id = events.user_id)
        """,
        [(user_id,) for user_id in segment_users],
    )

    duplicate_source = connection.execute(
        """
        SELECT e.event_id, e.user_id, e.event_name, e.event_time, e.event_date,
               e.session_id, e.run_id, e.turn_no, e.product_type, e.action,
               e.result, e.value_num, e.schema_version, e.app_version,
               e.channel, e.strategy_segment
        FROM events e
        JOIN users u ON u.user_id = e.user_id
        WHERE e.event_name = 'system_opened'
          AND u.app_version = '0.9.2'
          AND u.channel = 'friend_test'
          AND u.install_date BETWEEN '2026-08-08' AND '2026-08-10'
        """
    ).fetchall()
    duplicate_rows = []
    for row in duplicate_source:
        for duplicate_no in range(1, 4):
            copied = list(row)
            copied[0] = f"{row[0]}__dup{duplicate_no}"
            duplicate_rows.append(tuple(copied))
    connection.executemany(
        """
        INSERT INTO events (
            event_id, user_id, event_name, event_time, event_date, session_id,
            run_id, turn_no, product_type, action, result, value_num,
            schema_version, app_version, channel, strategy_segment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        duplicate_rows,
    )

    incident_catalog = [
        (
            "tutorial_failure",
            "教程关键步失败率升高，D1 留存同步下降",
            "d1_retention",
            "2026-08-07",
            "2026-08-10",
            "2026-08-11",
            "2026-08-14",
            "human_review_required",
        ),
        (
            "segment_churn",
            "新版本局部玩家分群流失，被整体平均值掩盖",
            "d1_retention",
            "2026-08-01",
            "2026-08-10",
            "2026-08-11",
            "2026-08-14",
            "human_review_required",
        ),
        (
            "duplicate_tracking",
            "埋点重复上报导致高级系统参与强度虚高",
            "system_open_events_per_eligible_user",
            "2026-08-04",
            "2026-08-07",
            "2026-08-08",
            "2026-08-10",
            "human_review_required",
        ),
    ]
    connection.executemany("INSERT INTO incident_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?)", incident_catalog)
    connection.executemany(
        "INSERT INTO incident_ground_truth VALUES (?, ?, ?, ?, ?)",
        [
            (
                "tutorial_failure",
                "upstream_tutorial_drop",
                "A deterministic subset of campus_demo / 0.9.3 cohorts loses post-start tutorial and return events.",
                len(tutorial_users),
                "Injected only into the derived demo database; the source snapshot is preserved byte-for-byte.",
            ),
            (
                "segment_churn",
                "segment_leveraged_churn",
                "Returning session events are removed for a deterministic leveraged-player subset.",
                len(segment_users),
                "The affected segment is intentionally smaller than the full cohort so the aggregate masks part of the drop.",
            ),
            (
                "duplicate_tracking",
                "duplicate_event_reporting",
                "Three same-signature copies are added for each targeted system_opened event.",
                len(duplicate_rows),
                "The event-level intensity rises while player-level adoption remains unchanged.",
            ),
        ],
    )

    manifest_rows = {
        "dataset_name": "NewtonMarket synthetic player analytics with reproducible injected incidents",
        "source_users": str(source_users),
        "source_events": str(source_events),
        "source_sha256": file_sha256(SOURCE_DB),
        "synthetic": "true",
        "observation_window": "2026-08-01/2026-08-21",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "derived_events": str(scalar(connection, "SELECT COUNT(*) FROM events")),
    }
    connection.executemany("INSERT INTO dataset_manifest VALUES (?, ?)", list(manifest_rows.items()))
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_signature ON events(user_id, event_name, event_time, session_id)")
    connection.execute("ANALYZE")
    connection.commit()

    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    derived_events = scalar(connection, "SELECT COUNT(*) FROM events")
    duplicate_signatures = scalar(
        connection,
        """
        SELECT COUNT(*) FROM (
          SELECT 1 FROM events
          GROUP BY user_id, event_name, event_time, session_id,
                   COALESCE(action, ''), COALESCE(result, ''), COALESCE(product_type, '')
          HAVING COUNT(*) > 1
        )
        """,
    )
    connection.close()
    os.replace(temporary, TARGET_DB)

    result = {
        "ok": integrity == "ok",
        "source": {
            "path": str(SOURCE_DB),
            "users": source_users,
            "events": source_events,
            "sha256": manifest_rows["source_sha256"],
        },
        "derived": {
            "path": str(TARGET_DB),
            "events": derived_events,
            "integrity_check": integrity,
            "duplicate_signature_groups": duplicate_signatures,
        },
        "injections": {
            "tutorial_failure_users": len(tutorial_users),
            "segment_churn_users": len(segment_users),
            "duplicate_event_rows": len(duplicate_rows),
        },
    }
    (ARTIFACTS / "bootstrap_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(bootstrap(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)
