from __future__ import annotations

from collections import Counter

import pytest

from evals import run_evals


@pytest.mark.parametrize("order", ["incident_first", "governance_first", "interleaved"])
def test_scenarios_are_reused_within_a_run_but_not_across_runs(monkeypatch, tmp_path, order):
    incidents = [
        {"id": f"incident_{name}", "type": "incident_attribution",
         "scenario_id": name, "expected_top3": name}
        for name in ("alpha", "beta")
    ]
    governance = [
        {"id": f"governance_{index}", "type": "governance",
         "scenario_id": name, "check": check}
        for index, (name, check) in enumerate([
            ("alpha", "human_review_required"), ("beta", "citation_valid"),
            ("alpha", "synthetic_disclosure"), ("alpha", "uncertainty_disclosure"),
        ])
    ]
    cases = {
        "incident_first": incidents + governance,
        "governance_first": governance + incidents,
        "interleaved": [incidents[0], governance[0], incidents[1], *governance[1:]],
    }[order]
    calls = Counter()

    def investigate(self, scenario_id):
        calls[scenario_id] += 1
        return {
            "ok": True,
            "investigation_status": "supported",
            "candidates": [{"id": scenario_id, "status": "supported_candidate"}],
            "report": {"markdown": "Synthetic data, not causal proof.",
                       "review_status": "human_review_required",
                       "citation_check": {"valid": True}},
        }

    monkeypatch.setattr(run_evals, "load_cases", lambda: cases)
    monkeypatch.setattr(run_evals, "scenario_catalog", lambda: ["alpha", "beta"])
    monkeypatch.setattr(run_evals, "RESULTS_PATH", tmp_path / "eval.json")
    monkeypatch.setattr(run_evals.DeterministicInvestigator, "investigate", investigate)
    monkeypatch.setattr(run_evals.ClaudeCodeRunner, "availability", staticmethod(lambda: {}))

    for run_number in (1, 2):
        result = run_evals.run()
        assert calls == Counter(alpha=run_number, beta=run_number)
        assert result["passed"] == result["case_count"] == len(cases)
        assert result["failed"] == 0
        assert [item["id"] for item in result["details"]] == [case["id"] for case in cases]
        for metric in ("root_cause_top3_hit_rate", "governance_behavior_accuracy", "report_citation_accuracy"):
            assert result["metrics"][metric] == 1.0


@pytest.mark.parametrize(
    ("run_ok", "investigation_status", "candidate_status"),
    (
        (False, "supported", "supported_candidate"),
        (True, "insufficient_evidence", "supported_candidate"),
        (True, "supported", "alternative"),
    ),
    ids=("failed_run", "unsupported_investigation", "alternative_only"),
)
def test_attribution_does_not_count_a_matching_id_without_supported_evidence(
    monkeypatch, tmp_path, run_ok, investigation_status, candidate_status
):
    case = {
        "id": "attribution", "type": "incident_attribution",
        "scenario_id": "alpha", "expected_top3": "expected_cause",
    }
    investigation = {
        "ok": run_ok,
        "investigation_status": investigation_status,
        # The expected ID is deliberately present: its name alone must never
        # turn a failed investigation or an unconfirmed alternative into a hit.
        "candidates": [{"id": "expected_cause", "status": candidate_status}],
        "report": {"citation_check": {"valid": True}},
    }
    monkeypatch.setattr(run_evals, "load_cases", lambda: [case])
    monkeypatch.setattr(run_evals, "scenario_catalog", lambda: ["alpha"])
    monkeypatch.setattr(run_evals, "RESULTS_PATH", tmp_path / "eval.json")
    monkeypatch.setattr(
        run_evals.DeterministicInvestigator, "investigate",
        lambda self, scenario_id: investigation,
    )
    monkeypatch.setattr(run_evals.ClaudeCodeRunner, "availability", staticmethod(lambda: {}))

    result = run_evals.run()
    assert result["details"][0]["candidate_ids"] == ["expected_cause"]
    assert result["details"][0]["passed"] is False
    assert result["passed"] == 0
    assert result["failed"] == 1
    assert result["metrics"]["root_cause_top3_hit_rate"] == 0.0
