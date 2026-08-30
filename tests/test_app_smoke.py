from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_renders_without_exception():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not app.exception
    assert {metric.label for metric in app.metric} >= {
        "Baseline",
        "Current",
        "Detected slices",
        "Tool calls",
    }

