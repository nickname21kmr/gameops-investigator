from __future__ import annotations

import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from gameops_investigator import orchestrator
from scripts import generate_reports


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def unsuccessful_investigation(monkeypatch):
    """Run the real coordinator with unavailable evidence, without model access."""
    original = orchestrator.DeterministicInvestigator.investigate
    recorded = []
    monkeypatch.setattr(
        orchestrator.ClaudeCodeRunner,
        "availability",
        staticmethod(lambda: {"installed": False, "logged_in": False}),
    )

    def forbid_model(*args, **kwargs):
        pytest.fail("An offline rendering test must not invoke the model.")

    monkeypatch.setattr(orchestrator.ClaudeCodeRunner, "run", forbid_model)

    def configure(mode):
        if mode == "tool_failure":
            def unavailable(*args, **kwargs):
                return {"ok": False, "error": "comparison unavailable"}

            monkeypatch.setattr(orchestrator, "compare_cohorts", unavailable)
            monkeypatch.setattr(orchestrator, "detect_anomalies", unavailable)

        def investigate(self, scenario_id):
            if mode == "no_data":
                scenario = self.scenarios[scenario_id]
                scenario["baseline"].update(start_date="2030-01-01", end_date="2030-01-02")
                scenario["current"].update(start_date="2030-01-03", end_date="2030-01-04")
                scenario["evidence_queries"] = [
                    "SELECT user_id FROM users WHERE install_date BETWEEN '2030-01-01' AND '2030-01-04'"
                ]
            result = original(self, scenario_id)
            recorded.append(result)
            return result

        monkeypatch.setattr(orchestrator.DeterministicInvestigator, "investigate", investigate)
        return recorded

    # The app's replay cache otherwise survives between AppTest runs.
    st.cache_data.clear()
    yield configure
    st.cache_data.clear()


@pytest.mark.parametrize("mode", ["no_data", "tool_failure"])
def test_app_renders_unavailable_evidence_and_explains_no_candidate(unsuccessful_investigation, mode):
    recorded = unsuccessful_investigation(mode)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert len(recorded) == 1
    result = recorded[0]
    assert result["candidates"] == []
    assert result["investigation_status"] == (
        "tool_failure" if mode == "tool_failure" else "insufficient_evidence"
    )
    messages = app.error if mode == "tool_failure" else app.info
    assert result["investigation_reason"] in [message.value for message in messages]
    values = {metric.label: metric.value for metric in app.metric}
    assert values["Baseline"] == values["Current"] == "N/A"
    assert any("No cohort comparisons" in message.value for message in app.info)
    assert not any("class='candidate'" in item.value for item in app.markdown)
    assert result["report"]["markdown"].strip() in [item.value for item in app.markdown]


@pytest.mark.parametrize("mode", ["no_data", "tool_failure"])
def test_report_export_records_empty_candidate_and_status(
    monkeypatch, tmp_path, unsuccessful_investigation, mode
):
    recorded = unsuccessful_investigation(mode)
    monkeypatch.setattr(generate_reports, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(generate_reports, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(generate_reports, "scenario_catalog", lambda: {"tutorial_failure": {}})
    summary = generate_reports.generate()
    result = recorded[0]
    entry = summary["tutorial_failure"]
    assert entry["top_candidate"] is None
    assert entry["investigation_status"] == result["investigation_status"]
    assert entry["investigation_reason"] == result["investigation_reason"]
    assert entry["ok"] is (mode != "tool_failure")
    assert json.loads((tmp_path / "reports" / "index.json").read_text(encoding="utf-8")) == summary
    trace = json.loads((tmp_path / entry["trace"]).read_text(encoding="utf-8"))
    assert trace["candidates"] == []
    assert trace["investigation_status"] == entry["investigation_status"]
    assert (tmp_path / entry["report"]).read_text(encoding="utf-8") == result["report"]["markdown"]
