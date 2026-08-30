from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source" / "newton_market_analytics.db"
DERIVED = ROOT / "data" / "gameops_demo.db"


def test_source_snapshot_is_preserved():
    with sqlite3.connect(SOURCE) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 5000
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 136164


def test_derived_database_integrity_and_manifest():
    with sqlite3.connect(DERIVED) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        manifest = dict(connection.execute("SELECT key, value FROM dataset_manifest"))
        assert manifest["synthetic"] == "true"
        assert manifest["source_events"] == "136164"
        assert connection.execute("SELECT COUNT(*) FROM incident_catalog").fetchone()[0] == 3


def test_bootstrap_manifest_matches_database():
    manifest = json.loads((ROOT / "artifacts" / "bootstrap_manifest.json").read_text(encoding="utf-8"))
    with sqlite3.connect(DERIVED) as connection:
        assert manifest["derived"]["events"] == connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]

