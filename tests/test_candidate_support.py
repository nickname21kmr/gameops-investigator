from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from gameops_investigator import orchestrator
from gameops_investigator.config import scenario_catalog
from gameops_investigator.metrics import MetricValue, two_proportion_z
from gameops_investigator.orchestrator import DeterministicInvestigator


EXPECTED_CANDIDATES = {
    "tutorial_failure": "upstream_tutorial_drop",
    "segment_churn": "segment_leveraged_churn",
    "duplicate_tracking": "duplicate_event_reporting",
}
SCENARIOS = tuple(EXPECTED_CANDIDATES)


def _assert_no_support(result: dict[str, Any], status: str) -> None:
    # This is the regression: low-confidence invented causes are not an abstention.
    assert result["candidates"] == []
    assert result["investigation_status"] == status
    assert isinstance(result["investigation_reason"], str)
    assert result["investigation_reason"].strip()
    assert result["ok"] is (status != "tool_failure")
    assert "`supported_candidate`" not in result["report"]["markdown"]


def _patch_scenario(monkeypatch, scenario_id: str, edit) -> None:
    catalog = deepcopy(scenario_catalog())
    edit(catalog[scenario_id])
    monkeypatch.setattr(orchestrator, "scenario_catalog", lambda: catalog)


def _focus_rows(payload: dict[str, Any], scenario: dict[str, Any], key: str):
    return [
        row
        for row in payload.get(key, [])
        if row["dimensions"].get(scenario["breakdown_dimension"]) == scenario["focus_value"]
    ]


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_real_injected_incidents_keep_their_supported_candidate(scenario_id):
    result = DeterministicInvestigator().investigate(scenario_id)
    assert result["candidates"][0]["id"] == EXPECTED_CANDIDATES[scenario_id]
    assert result["candidates"][0]["status"] == "supported_candidate"
    assert result["investigation_status"] == "supported"
    assert result["ok"] is True
    assert result["report"]["citation_check"]["valid"]


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_empty_windows_cannot_invent_a_supported_candidate(monkeypatch, scenario_id):
    def make_empty(scenario):
        # Change only the in-memory scenario, including SQL, so every actual tool
        # reads an empty window from the existing database without altering it.
        replacements = {}
        for index, window in enumerate(("baseline", "current")):
            for day, field in enumerate(("start_date", "end_date"), start=1):
                old_date = scenario[window][field]
                new_date = f"2099-0{index + 1}-0{day}"
                replacements[old_date] = new_date
                scenario[window][field] = new_date
        for index, sql in enumerate(scenario["evidence_queries"]):
            for old_date, new_date in replacements.items():
                sql = sql.replace(old_date, new_date)
            scenario["evidence_queries"][index] = sql

    _patch_scenario(monkeypatch, scenario_id, make_empty)
    result = DeterministicInvestigator().investigate(scenario_id)
    assert result["anomaly_result"]["all_comparisons"] == []
    sql_evidence = [item for item in result["evidence"] if item["title"] == "query_metrics"]
    assert sql_evidence
    assert all(item["result"]["rows"] == [] for item in sql_evidence)
    _assert_no_support(result, "insufficient_evidence")


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_identical_windows_do_not_turn_normal_data_into_an_incident(monkeypatch, scenario_id):
    def use_same_window(scenario):
        scenario["baseline"] = dict(scenario["current"])

    _patch_scenario(monkeypatch, scenario_id, use_same_window)
    result = DeterministicInvestigator().investigate(scenario_id)
    assert result["anomaly_result"]["all_comparisons"]
    assert result["anomaly_result"]["anomaly_count"] == 0
    _assert_no_support(result, "no_supported_candidate")


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_reversing_real_windows_does_not_support_the_original_incident(monkeypatch, scenario_id):
    def reverse_windows(scenario):
        scenario["baseline"], scenario["current"] = scenario["current"], scenario["baseline"]

    _patch_scenario(monkeypatch, scenario_id, reverse_windows)
    result = DeterministicInvestigator().investigate(scenario_id)
    assert result["anomaly_result"]["anomaly_count"] > 0
    _assert_no_support(result, "no_supported_candidate")


@pytest.mark.parametrize("scenario_id", SCENARIOS)
@pytest.mark.parametrize("window", ("current", "baseline"))
def test_focus_requires_both_window_sample_sizes(monkeypatch, scenario_id, window):
    scenario = scenario_catalog()[scenario_id]
    original = orchestrator.detect_anomalies

    def with_low_sample(**arguments):
        payload = original(**arguments)
        for key in ("all_comparisons", "anomalies"):
            for row in _focus_rows(payload, scenario, key):
                row[window]["denominator"] = 19
                row["confidence"] = "low_sample"
        # Retain the detector's anomaly list to ensure a baseline with fewer
        # than 20 observations cannot pass merely by appearing in that list.
        return payload

    monkeypatch.setattr(orchestrator, "detect_anomalies", with_low_sample)
    result = DeterministicInvestigator().investigate(scenario_id)
    _assert_no_support(result, "insufficient_evidence")


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_non_significant_focus_does_not_borrow_another_groups_anomaly(monkeypatch, scenario_id):
    scenario = scenario_catalog()[scenario_id]
    original = orchestrator.detect_anomalies

    def with_non_significant_focus(**arguments):
        payload = original(**arguments)
        for row in _focus_rows(payload, scenario, "all_comparisons"):
            row["z_score"] = 0.5
            row["confidence"] = "low"
        payload["anomalies"] = [
            row for row in payload["anomalies"]
            if row["dimensions"].get(scenario["breakdown_dimension"]) != scenario["focus_value"]
        ]
        payload["anomaly_count"] = len(payload["anomalies"])
        return payload

    monkeypatch.setattr(orchestrator, "detect_anomalies", with_non_significant_focus)
    result = DeterministicInvestigator().investigate(scenario_id)
    _assert_no_support(result, "no_supported_candidate")


@pytest.mark.parametrize(
    ("scenario_id", "required_metric"),
    (("tutorial_failure", "tutorial_completion_rate"), ("duplicate_tracking", "duplicate_signature_rate")),
)
@pytest.mark.parametrize(
    ("condition", "expected_status"),
    (
        ("missing", "insufficient_evidence"),
        ("low_sample", "insufficient_evidence"),
        ("not_significant", "no_supported_candidate"),
        ("opposite_direction", "no_supported_candidate"),
    ),
)
def test_required_related_metric_must_support_the_hypothesis(
    monkeypatch, scenario_id, required_metric, condition, expected_status
):
    scenario = scenario_catalog()[scenario_id]
    original = orchestrator.compare_cohorts

    def with_unsupported_related(**arguments):
        payload = original(**arguments)
        if arguments["metric_name"] != required_metric:
            return payload
        focus = _focus_rows(payload, scenario, "rows")
        assert focus, "The unchanged demo must provide the required focus metric."
        if condition == "missing":
            payload["rows"] = [row for row in payload["rows"] if row not in focus]
        else:
            for row in focus:
                if condition == "low_sample":
                    row["baseline"]["denominator"] = 19
                    row["confidence"] = "low_sample"
                elif condition == "not_significant":
                    row["z_score"] = 0.5
                    row["confidence"] = "low"
                else:
                    row["current"], row["baseline"] = row["baseline"], row["current"]
                    row["delta"] = -row["delta"]
                    row["z_score"] = -row["z_score"]
        return payload

    monkeypatch.setattr(orchestrator, "compare_cohorts", with_unsupported_related)
    result = DeterministicInvestigator().investigate(scenario_id)
    _assert_no_support(result, expected_status)


@pytest.mark.parametrize(
    ("condition", "expected_status"),
    (
        ("missing", "insufficient_evidence"),
        ("low_sample", "insufficient_evidence"),
        ("significant_increase", "no_supported_candidate"),
    ),
)
def test_duplicate_candidate_requires_a_usable_player_level_cross_check(
    monkeypatch, condition, expected_status
):
    scenario = scenario_catalog()["duplicate_tracking"]
    original = orchestrator.compare_cohorts

    def with_player_level_change(**arguments):
        payload = original(**arguments)
        if arguments["metric_name"] != "system_adoption_rate":
            return payload
        focus = _focus_rows(payload, scenario, "rows")
        assert focus
        if condition == "missing":
            payload["rows"] = [row for row in payload["rows"] if row not in focus]
        else:
            for row in focus:
                if condition == "low_sample":
                    row["baseline"]["denominator"] = 19
                    row["confidence"] = "low_sample"
                else:
                    # A genuinely significant rise in player adoption weakens
                    # the playbook's "event growth without adoption" argument.
                    row["current"]["numerator"] = row["current"]["denominator"]
                    row["current"]["value"] = 100.0
                    row["delta"] = 100.0 - row["baseline"]["value"]
                    row["z_score"] = two_proportion_z(
                        MetricValue(**row["current"]), MetricValue(**row["baseline"])
                    )
                    assert row["z_score"] > 3.29
                    row["confidence"] = "high"
        return payload

    monkeypatch.setattr(orchestrator, "compare_cohorts", with_player_level_change)
    result = DeterministicInvestigator().investigate("duplicate_tracking")
    _assert_no_support(result, expected_status)


@pytest.mark.parametrize("failure", ("returned", "raised"))
def test_evidence_query_failure_prevents_supported_candidates(monkeypatch, failure):
    diagnostic = "private-database-location-and-driver-diagnostic"

    def fail_query(**arguments):
        if failure == "raised":
            raise OSError(diagnostic)
        return {"ok": False, "error": diagnostic, "policy": "read_only_allowlist"}

    monkeypatch.setattr(orchestrator, "query_metrics", fail_query)
    result = DeterministicInvestigator().investigate("tutorial_failure")
    _assert_no_support(result, "tool_failure")
    assert diagnostic not in result["investigation_reason"]
    failed_queries = [call for call in result["trace"] if call["tool"] == "query_metrics" and not call["ok"]]
    assert failed_queries
