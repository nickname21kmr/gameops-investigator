from __future__ import annotations

import json
from pathlib import Path

import pytest

from gameops_investigator import orchestrator
from gameops_investigator.orchestrator import DeterministicInvestigator


def assert_safe_failure(result: dict, sentinel: str) -> None:
    assert result["ok"] is False
    assert result["investigation_status"] == "tool_failure"
    assert result["report"]["investigation_status"] == "tool_failure"
    assert result["candidates"] == []
    assert sentinel not in json.dumps(result)


def test_missing_database_does_not_export_its_private_path(monkeypatch, tmp_path: Path):
    sentinel = "PRIVATE_DATABASE_LOCATION_SENTINEL"
    missing_path = tmp_path / sentinel / "missing.sqlite"
    assert not missing_path.exists()
    monkeypatch.setenv("GAMEOPS_DB_PATH", str(missing_path))

    result = DeterministicInvestigator().investigate("tutorial_failure")

    assert_safe_failure(result, sentinel)
    assert any(call["tool"] == "query_metrics" and not call["ok"] for call in result["trace"])
    query_result = next(item["result"] for item in result["evidence"] if item["title"] == "query_metrics")
    assert query_result == {"ok": False, "error": "The investigation tool could not complete."}


@pytest.mark.parametrize("failure", ["returned", "raised"])
def test_report_failure_discards_private_diagnostics_and_payload(monkeypatch, failure: str):
    sentinel = "PRIVATE_REPORT_DIAGNOSTIC_SENTINEL"
    monkeypatch.delenv("GAMEOPS_DB_PATH", raising=False)

    def fail_report(**arguments):
        # This path starts with real supported evidence, then fails at reporting.
        assert arguments["candidates"][0]["status"] == "supported_candidate"
        if failure == "raised":
            raise OSError(sentinel)
        return {
            "ok": False,
            "error": sentinel,
            "markdown": sentinel,
            "diagnostics": {"private_payload": sentinel},
        }

    monkeypatch.setattr(orchestrator, "draft_incident_report", fail_report)

    result = DeterministicInvestigator().investigate("segment_churn")

    assert_safe_failure(result, sentinel)
    assert result["trace"][-1]["tool"] == "draft_incident_report"
    assert result["trace"][-1]["ok"] is False
    assert result["report"]["ok"] is False
    assert result["report"]["citation_check"]["valid"] is False
    assert result["evidence"][-1]["result"] == {
        "ok": False,
        "error": "The investigation tool could not complete.",
    }
