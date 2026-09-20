from __future__ import annotations

import pytest

from gameops_investigator import orchestrator
from gameops_investigator.config import scenario_catalog
from gameops_investigator.metrics import MetricValue, log_rate_z, two_proportion_z
from gameops_investigator.orchestrator import DeterministicInvestigator


def moderate_change(row, direction):
    """Replace one comparison with consistent counts giving medium significance."""
    metric_id = row["current"]["metric_id"]
    unit = row["current"]["unit"]
    dimensions = dict(row["dimensions"])
    if unit == "percent":
        baseline = MetricValue(metric_id, 50, 100, 50.0, unit, dimensions)
        numerator = 50 + direction * 17
        current = MetricValue(metric_id, numerator, 100, float(numerator), unit, dimensions)
        z_score = two_proportion_z(current, baseline)
    else:
        baseline = MetricValue(metric_id, 100, 100, 1.0, unit, dimensions)
        current = MetricValue(metric_id, 140, 100, 1.4, unit, dimensions)
        z_score = log_rate_z(current, baseline)
    assert 1.96 <= abs(z_score) < 3.29
    delta = current.value - baseline.value
    row.update(
        current=current.to_dict(), baseline=baseline.to_dict(),
        delta=delta, relative_delta_pct=delta / baseline.value * 100,
        z_score=z_score, confidence="medium",
    )
    if "severity_score" in row:
        row["severity_score"] = round(abs(z_score), 3)


@pytest.mark.parametrize(
    ("scenario_id", "weaker_metric"),
    [
        ("tutorial_failure", "d1_retention"),
        ("tutorial_failure", "tutorial_completion_rate"),
        ("segment_churn", "d1_retention"),
        ("duplicate_tracking", "system_open_events_per_eligible_user"),
        ("duplicate_tracking", "duplicate_signature_rate"),
    ],
)
def test_candidate_does_not_overstate_its_weaker_required_evidence(monkeypatch, scenario_id, weaker_metric):
    scenario = scenario_catalog()[scenario_id]
    dimension = scenario["breakdown_dimension"]
    focus = scenario["focus_value"]
    direction = 1 if scenario_id == "duplicate_tracking" else -1
    original_anomalies = orchestrator.detect_anomalies
    original_comparisons = orchestrator.compare_cohorts
    changed = []

    def replace_focus(rows):
        for row in rows:
            if row["dimensions"].get(dimension) == focus:
                moderate_change(row, direction)
                changed.append(row)

    def anomalies(**arguments):
        payload = original_anomalies(**arguments)
        if arguments["metric_name"] == weaker_metric:
            replace_focus(payload["all_comparisons"])
            replace_focus(payload["anomalies"])
        return payload

    def comparisons(**arguments):
        payload = original_comparisons(**arguments)
        if arguments["metric_name"] == weaker_metric and arguments.get("group_by") == [dimension]:
            replace_focus(payload["rows"])
        return payload

    monkeypatch.setattr(orchestrator, "detect_anomalies", anomalies)
    monkeypatch.setattr(orchestrator, "compare_cohorts", comparisons)
    result = DeterministicInvestigator().investigate(scenario_id)

    assert changed
    assert result["ok"] is True
    assert result["investigation_status"] == "supported"
    top = result["candidates"][0]
    assert top["status"] == "supported_candidate"
    assert top["confidence"] == "medium"
    assert "- Confidence: `medium`" in result["report"]["markdown"]


def test_duplicate_candidate_cites_every_metric_used_in_its_reasoning():
    result = DeterministicInvestigator().investigate("duplicate_tracking")
    candidate = result["candidates"][0]
    assert candidate["id"] == "duplicate_event_reporting"
    expected_metrics = {
        "system_open_events_per_eligible_user",
        "duplicate_signature_rate",
        "system_adoption_rate",
    }
    cited = set(candidate["evidence_refs"])
    cited_metrics = {
        item["result"]["metric"]["metric_id"]
        for item in result["evidence"]
        if item["evidence_id"] in cited
        and item["title"] in {"detect_anomalies", "compare_cohorts"}
    }
    assert expected_metrics <= cited_metrics
    assert result["report"]["citation_check"]["valid"]
