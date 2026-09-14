from __future__ import annotations

import copy
import json
import sys

import pytest

from gameops_investigator import cli
from gameops_investigator.trace_audit import audit_trace


def investigation_result():
    tools = [
        "get_metric_definition",
        "compare_cohorts",
        "detect_anomalies",
        "query_metrics",
        "draft_incident_report",
    ]
    return {
        "mode": "deterministic_replay",
        "scenario_id": "tutorial_failure",
        "trace": [{"tool": tool, "arguments": {}, "ok": True} for tool in tools],
        "report": {"markdown": "Synthetic demonstration; human review required."},
    }


@pytest.fixture
def invoke_investigate(monkeypatch, capsys):
    def unexpected(*args, **kwargs):
        pytest.fail("Investigation audit must not call a model, query, or file auditor")

    monkeypatch.setattr(cli.ClaudeCodeRunner, "run", unexpected)
    monkeypatch.setattr(cli.ClaudeCodeRunner, "availability", staticmethod(unexpected))
    monkeypatch.setattr(cli, "query_metrics", unexpected)
    monkeypatch.setattr(cli, "audit_trace_file", unexpected)

    def invoke(payload, options):
        calls = []

        def investigate(self, scenario):
            calls.append(scenario)
            return payload

        monkeypatch.setattr(cli.DeterministicInvestigator, "investigate", investigate)
        monkeypatch.setattr(sys, "argv", ["gameops", "investigate", "tutorial_failure", *options])
        exit_code = cli.main()
        captured = capsys.readouterr()
        assert captured.err == ""
        assert calls == ["tutorial_failure"]
        return exit_code, json.loads(captured.out)

    return invoke


@pytest.mark.parametrize("options, budget", [
    (["--audit"], 20),
    (["--audit", "--max-tool-calls", "5"], 5),
    (["--max-tool-calls", "10000", "--audit"], 10000),
])
def test_audit_checks_exact_fresh_result_once_without_rerunning_investigation(
    monkeypatch, invoke_investigate, options, budget
):
    payload = investigation_result()
    before = copy.deepcopy(payload)
    audit_calls = []

    def inspect(result, max_tool_calls=20):
        assert result is payload
        audit_calls.append(max_tool_calls)
        return audit_trace(result, max_tool_calls=max_tool_calls)

    monkeypatch.setattr(cli, "audit_trace", inspect, raising=False)
    exit_code, output = invoke_investigate(payload, options)

    assert exit_code == 0
    assert output["ok"] is True
    assert output["trajectory_audit"] == audit_trace(before, max_tool_calls=budget)
    assert {key: value for key, value in output.items() if key not in {"ok", "trajectory_audit"}} == before
    assert output["mode"] == "deterministic_replay"
    assert output["report"] == before["report"]
    assert payload == before
    assert audit_calls == [budget]


def test_budget_violation_returns_failure_without_discarding_report(invoke_investigate):
    payload = investigation_result()
    before = copy.deepcopy(payload)
    exit_code, output = invoke_investigate(payload, ["--audit", "--max-tool-calls", "4"])
    assert exit_code == 1
    assert output["ok"] is False
    assert output["trajectory_audit"]["violations"] == [{"code": "tool_budget_exceeded", "step": None}]
    assert output["trajectory_audit"]["call_count"] == 5
    assert output["report"] == before["report"]
    assert payload == before


def test_failed_tool_step_causes_audit_and_cli_failure(invoke_investigate):
    payload = investigation_result()
    payload["trace"][3]["ok"] = False
    before = copy.deepcopy(payload)
    exit_code, output = invoke_investigate(payload, ["--audit"])
    assert exit_code == 1
    assert output["ok"] is False
    assert output["trajectory_audit"]["ok"] is False
    assert {"code": "tool_call_failed", "step": 4} in output["trajectory_audit"]["violations"]
    assert output["report"] == before["report"]
    assert payload == before


def test_original_failed_status_is_not_overridden_by_passing_audit(invoke_investigate):
    payload = investigation_result()
    payload["ok"] = False
    payload["error"] = "Investigation failed before result delivery."
    before = copy.deepcopy(payload)
    exit_code, output = invoke_investigate(payload, ["--audit"])
    assert exit_code == 1
    assert output["ok"] is False
    assert output["trajectory_audit"]["ok"] is True
    assert output["error"] == before["error"]
    assert output["mode"] == before["mode"]
    assert payload == before


@pytest.mark.parametrize("original_ok", [True, False, None])
def test_without_opt_in_keeps_original_output_structure(monkeypatch, invoke_investigate, original_ok):
    payload = investigation_result()
    if original_ok is not None:
        payload["ok"] = original_ok
    before = copy.deepcopy(payload)

    def unexpected(*args, **kwargs):
        pytest.fail("Default investigate must not run trajectory audit")

    monkeypatch.setattr(cli, "audit_trace", unexpected, raising=False)
    exit_code, output = invoke_investigate(payload, [])
    assert exit_code == (1 if original_ok is False else 0)
    assert output == before
    assert "trajectory_audit" not in output
    assert ("ok" in output) is (original_ok is not None)
    assert payload == before


@pytest.mark.parametrize("audit_ok", [None, False, "true", 1])
def test_only_explicit_true_audit_status_can_mark_investigation_success(
    monkeypatch, invoke_investigate, audit_ok
):
    payload = investigation_result()
    payload["ok"] = True
    monkeypatch.setattr(cli, "audit_trace", lambda *args, **kwargs: {"ok": audit_ok}, raising=False)
    exit_code, output = invoke_investigate(payload, ["--audit"])
    assert exit_code == 1
    assert output["ok"] is False
    assert payload["ok"] is True


@pytest.mark.parametrize("options", [
    ["--max-tool-calls", "20"],
    ["--max-tool-calls", "5"],
    ["--audit", "--max-tool-calls", "0"],
    ["--audit", "--max-tool-calls", "-1"],
    ["--audit", "--max-tool-calls", "10001"],
    ["--audit", "--max-tool-calls", "1.5"],
    ["--audit", "--max-tool-calls", "true"],
    ["--audit", "--max-tool-calls"],
])
def test_invalid_options_exit_before_any_investigation(monkeypatch, capsys, options):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid CLI options must be rejected before investigation or audit")

    monkeypatch.setattr(cli.DeterministicInvestigator, "investigate", unexpected)
    monkeypatch.setattr(cli.ClaudeCodeRunner, "run", unexpected)
    monkeypatch.setattr(cli, "audit_trace", unexpected, raising=False)
    monkeypatch.setattr(sys, "argv", ["gameops", "investigate", "tutorial_failure", *options])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err.lower()


def test_complete_output_is_preserved_but_added_audit_is_redacted(invoke_investigate):
    payload = investigation_result()
    payload["trace"][3]["arguments"] = {"sql": "SELECT 'privacy-marker'"}
    payload["report"]["markdown"] += " privacy-marker"
    before = copy.deepcopy(payload)
    exit_code, output = invoke_investigate(payload, ["--audit"])
    assert exit_code == 0
    assert "privacy-marker" in json.dumps(output)
    assert "privacy-marker" not in json.dumps(output["trajectory_audit"])
    assert output["trace"] == before["trace"]
    assert output["report"] == before["report"]
    assert payload == before


@pytest.mark.parametrize("scenario", ["tutorial_failure", "segment_churn", "duplicate_tracking"])
def test_real_scenario_cli_audit_preserves_replay_and_human_review(monkeypatch, capsys, scenario):
    def unexpected(*args, **kwargs):
        pytest.fail("Deterministic investigation must not call Claude")

    monkeypatch.setattr(cli.ClaudeCodeRunner, "run", unexpected)
    monkeypatch.setattr(cli.ClaudeCodeRunner, "availability", staticmethod(unexpected))
    monkeypatch.setattr(sys, "argv", ["gameops", "investigate", scenario, "--audit"])
    assert cli.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    output = json.loads(captured.out)
    assert output["ok"] is True
    assert output["mode"] == "deterministic_replay"
    assert output["scenario_id"] == scenario
    assert output["trajectory_audit"]["ok"] is True
    assert output["trajectory_audit"]["violations"] == []
    assert output["trajectory_audit"]["call_count"] == len(output["trace"])
    assert output["report"]["review_status"] == "human_review_required"
