from __future__ import annotations

from gameops_investigator.orchestrator import DeterministicInvestigator
from gameops_investigator.trace_audit import audit_trace


EXPECTED = {
    "tutorial_failure": "upstream_tutorial_drop",
    "segment_churn": "segment_leveraged_churn",
    "duplicate_tracking": "duplicate_event_reporting",
}


def test_reproducible_incidents_hit_top_candidate_and_cite_evidence():
    for scenario_id, expected in EXPECTED.items():
        result = DeterministicInvestigator().investigate(scenario_id)
        assert result["candidates"][0]["id"] == expected
        assert result["report"]["citation_check"]["valid"]
        assert result["report"]["review_status"] == "human_review_required"
        assert all(call["ok"] for call in result["trace"])
        assert audit_trace(result)["ok"]


def test_segment_case_is_hidden_in_aggregate_but_visible_in_breakdown():
    result = DeterministicInvestigator().investigate("segment_churn")
    overall = result["overall_comparison"]["rows"][0]
    leveraged = next(
        row for row in result["anomaly_result"]["all_comparisons"]
        if row["dimensions"].get("strategy_segment") == "leveraged"
    )
    assert overall["confidence"] == "low"
    assert leveraged["confidence"] in {"medium", "high"}
    assert abs(leveraged["delta"]) > abs(overall["delta"])


def test_report_expresses_uncertainty_and_synthetic_boundary():
    markdown = DeterministicInvestigator().investigate("tutorial_failure")["report"]["markdown"]
    assert "synthetic" in markdown.lower()
    assert "causal proof" in markdown.lower()
