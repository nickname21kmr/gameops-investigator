from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "gameops_demo.db"


def database_path() -> Path:
    configured = os.environ.get("GAMEOPS_DB_PATH")
    if not configured:
        return DEFAULT_DB_PATH
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_json(name: str) -> dict[str, Any]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def metric_catalog() -> dict[str, Any]:
    return load_json("metrics.json")


def scenario_catalog() -> dict[str, Any]:
    return load_json("scenarios.json")

