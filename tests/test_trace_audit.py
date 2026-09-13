from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from gameops_investigator import cli
from gameops_investigator.trace_audit import MAX_TRACE_BYTES, audit_trace, audit_trace_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = [
    "get_metric_definition",
    "compare_cohorts",
    "detect_anomalies",
    "query_metrics",
    "draft_incident_report",
]


def successful_trace():
    return [{"tool": tool, "arguments": {}, "ok": True} for tool in TOOLS]


def issue_codes(result):
    return {issue["code"] for issue in result["violations"]}


def assert_summary_contract(result):
    assert set(result) == {"ok", "audit_mode", "call_count", "max_tool_calls", "violations"}
    assert result["audit_mode"] == "deterministic_trajectory_rules"
    assert type(result["ok"]) is bool
    assert type(result["call_count"]) is int
    assert result["ok"] is (not result["violations"])
    for issue in result["violations"]:
        assert set(issue) == {"code", "step"}
        assert issue["step"] is None or (type(issue["step"]) is int and issue["step"] >= 1)


@pytest.mark.parametrize("wrapped", [False, True])
def test_valid_trace_accepts_bare_list_or_investigation_result_without_mutation(wrapped):
    trace = successful_trace()
    trace[0]["ignored"] = {"private_note": "privacy-marker"}
    trace[3]["arguments"] = {"sql": "SELECT 'privacy-marker'"}
    payload = {"trace": trace, "private_note": "privacy-marker"} if wrapped else trace
    original = copy.deepcopy(payload)

    result = audit_trace(payload)

    assert_summary_contract(result)
    assert result["ok"] is True
    assert result["call_count"] == 5
    assert result["max_tool_calls"] == 20
    assert "privacy-marker" not in json.dumps(result)
    assert payload == original


@pytest.mark.parametrize("scenario", ["tutorial_failure", "segment_churn", "duplicate_tracking"])
def test_existing_published_replay_traces_satisfy_rules(scenario):
    payload = json.loads((PROJECT_ROOT / "reports" / f"{scenario}.trace.json").read_text(encoding="utf-8"))
    result = audit_trace(payload)
    assert_summary_contract(result)
    assert result["ok"] is True
    assert result["call_count"] == len(payload["trace"])


@pytest.mark.parametrize("payload", [None, {}, {"trace": {}}, {"trace": None}, "privacy-marker", [], {"trace": []}])
def test_missing_or_empty_trace_is_rejected_without_fabricated_missing_steps(payload):
    result = audit_trace(payload)
    assert_summary_contract(result)
    assert result["call_count"] == 0
    assert result["violations"] == [{"code": "invalid_trace", "step": None}]
    assert "privacy-marker" not in json.dumps(result)


@pytest.mark.parametrize("budget", [None, False, True, 0, -1, 10001, 2.5, "privacy-marker"])
def test_invalid_budget_early_returns_without_echoing_value(budget):
    result = audit_trace(successful_trace(), max_tool_calls=budget)
    assert_summary_contract(result)
    assert result["call_count"] == 0
    assert result["max_tool_calls"] is None
    assert result["violations"] == [{"code": "invalid_budget", "step": None}]
    assert "privacy-marker" not in json.dumps(result)


def test_budget_is_inclusive_and_all_calls_count():
    trace = successful_trace()
    trace[1:1] = [{"tool": "compare_cohorts", "arguments": {}, "ok": True}] * 15
    assert audit_trace(trace)["ok"] is True
    assert audit_trace(trace, max_tool_calls=20)["call_count"] == 20

    trace.insert(1, {"tool": "compare_cohorts", "arguments": {}, "ok": True})
    result = audit_trace(trace)
    assert result["call_count"] == 21
    assert issue_codes(result) == {"tool_budget_exceeded"}

    trace[1]["ok"] = False
    trace[2] = {"tool": "privacy-marker", "arguments": {}, "ok": True}
    result = audit_trace(trace)
    assert result["call_count"] == 21
    assert {"tool_budget_exceeded", "tool_call_failed", "unknown_tool"} <= issue_codes(result)
    assert "privacy-marker" not in json.dumps(result)


@pytest.mark.parametrize("step", [
    None,
    "privacy-marker",
    {},
    {"tool": [], "arguments": {}, "ok": True},
    {"tool": "get_metric_definition", "arguments": [], "ok": True},
    {"tool": "get_metric_definition", "arguments": {}, "ok": "true"},
    {"tool": "get_metric_definition", "arguments": {}, "ok": 1},
])
def test_malformed_steps_never_satisfy_prerequisites(step):
    trace = successful_trace()
    trace[0] = step
    result = audit_trace(trace)
    assert_summary_contract(result)
    assert {"code": "invalid_step", "step": 1} in result["violations"]
    assert {"invalid_step", "definition_required", "missing_get_metric_definition"} <= issue_codes(result)
    assert "privacy-marker" not in json.dumps(result)


def test_unknown_tool_does_not_count_as_successful_definition():
    trace = successful_trace()
    trace[0]["tool"] = "privacy-marker"
    result = audit_trace(trace)
    assert {"code": "unknown_tool", "step": 1} in result["violations"]
    assert {"definition_required", "missing_get_metric_definition"} <= issue_codes(result)
    assert "privacy-marker" not in json.dumps(result)


@pytest.mark.parametrize("analysis_tool", TOOLS[1:4])
def test_definition_is_required_before_each_analysis_tool(analysis_tool):
    trace = successful_trace()
    analysis = trace.pop(TOOLS.index(analysis_tool))
    trace.insert(0, analysis)
    result = audit_trace(trace)
    assert {"code": "definition_required", "step": 1} in result["violations"]
    assert "missing_get_metric_definition" not in issue_codes(result)


def test_failed_definition_cannot_authorize_analysis():
    trace = successful_trace()
    trace[0]["ok"] = False
    result = audit_trace(trace)
    assert {"code": "tool_call_failed", "step": 1} in result["violations"]
    assert {"definition_required", "report_prerequisites_missing", "missing_get_metric_definition"} <= issue_codes(result)


@pytest.mark.parametrize("missing_tool", TOOLS)
def test_missing_successful_required_tool_is_reported(missing_tool):
    trace = [step for step in successful_trace() if step["tool"] != missing_tool]
    result = audit_trace(trace)
    assert f"missing_{missing_tool}" in issue_codes(result)
    if missing_tool != "draft_incident_report":
        assert "report_prerequisites_missing" in issue_codes(result)


@pytest.mark.parametrize("failed_tool", TOOLS)
def test_failed_calls_remain_violations_and_do_not_satisfy_required_steps(failed_tool):
    trace = successful_trace()
    index = TOOLS.index(failed_tool)
    trace[index]["ok"] = False
    result = audit_trace(trace)
    assert {"code": "tool_call_failed", "step": index + 1} in result["violations"]
    assert f"missing_{failed_tool}" in issue_codes(result)


def test_successful_retry_does_not_erase_failure_but_can_supply_report_prerequisite():
    trace = successful_trace()
    trace.insert(3, {"tool": "query_metrics", "arguments": {}, "ok": False})
    result = audit_trace(trace)
    assert result["violations"] == [{"code": "tool_call_failed", "step": 4}]


def test_report_must_be_last_and_later_analysis_cannot_retroactively_supply_evidence():
    trace = successful_trace()
    trace.insert(1, trace.pop())
    result = audit_trace(trace)
    assert {"code": "report_not_last", "step": 2} in result["violations"]
    assert {"code": "report_prerequisites_missing", "step": 2} in result["violations"]


def test_reordered_and_repeated_analysis_is_allowed_after_definition():
    base = successful_trace()
    trace = [base[0], base[3], base[2], base[1], base[3], base[4]]
    assert audit_trace(trace)["ok"] is True


def test_separate_audits_do_not_share_success_state():
    assert audit_trace(successful_trace())["ok"] is True
    result = audit_trace([successful_trace()[-1]])
    assert "report_prerequisites_missing" in issue_codes(result)
    assert {f"missing_{tool}" for tool in TOOLS[:-1]} <= issue_codes(result)


@pytest.fixture
def block_live_execution(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Trace audit must not invoke a model, query, or investigator")

    monkeypatch.setattr(cli.ClaudeCodeRunner, "run", unexpected)
    monkeypatch.setattr(cli.ClaudeCodeRunner, "availability", staticmethod(unexpected))
    monkeypatch.setattr(cli.DeterministicInvestigator, "investigate", unexpected)
    monkeypatch.setattr(cli, "query_metrics", unexpected)


@pytest.mark.parametrize("budget, expected_exit", [(5, 0), (4, 1)])
def test_cli_reads_file_without_replaying_tools(tmp_path, monkeypatch, capsys, block_live_execution, budget, expected_exit):
    trace_path = tmp_path / "privacy-marker.json"
    payload = {"trace": successful_trace(), "private_note": "privacy-marker"}
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["gameops", "audit-trace", str(trace_path), "--max-tool-calls", str(budget)])
    assert cli.main() == expected_exit
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert_summary_contract(result)
    assert result == audit_trace(payload, max_tool_calls=budget)
    assert "privacy-marker" not in captured.out


@pytest.mark.parametrize("case, expected_code", [
    ("missing", "trace_file_unreadable"),
    ("invalid-json", "invalid_json"),
    ("oversize", "trace_file_too_large"),
])
def test_cli_file_errors_are_sanitized(tmp_path, monkeypatch, capsys, block_live_execution, case, expected_code):
    trace_path = tmp_path / "privacy-marker.json"
    if case == "invalid-json":
        trace_path.write_text("{privacy-marker", encoding="utf-8")
    elif case == "oversize":
        trace_path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    monkeypatch.setattr(sys, "argv", ["gameops", "audit-trace", str(trace_path)])
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert_summary_contract(result)
    assert result["violations"] == [{"code": expected_code, "step": None}]
    assert "privacy-marker" not in captured.out


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_trace_file_accepts_utf8_with_or_without_bom(tmp_path, encoding):
    trace_path = tmp_path / "record.json"
    trace_path.write_text(json.dumps(successful_trace()), encoding=encoding)
    assert audit_trace_file(trace_path) == audit_trace(successful_trace())


def test_file_size_limit_accepts_exact_boundary(tmp_path):
    trace_path = tmp_path / "record.json"
    content = json.dumps(successful_trace()).encode("utf-8")
    trace_path.write_bytes(content + b" " * (MAX_TRACE_BYTES - len(content)))
    assert audit_trace_file(trace_path)["ok"] is True


def test_invalid_encoding_has_safe_parse_error(tmp_path):
    trace_path = tmp_path / "privacy-marker.json"
    trace_path.write_bytes(b"\xffprivacy-marker")
    result = audit_trace_file(trace_path)
    assert_summary_contract(result)
    assert result["violations"] == [{"code": "invalid_json", "step": None}]
    assert "privacy-marker" not in json.dumps(result)


def test_json_parser_recursion_failure_has_safe_error(tmp_path, monkeypatch):
    trace_path = tmp_path / "privacy-marker.json"
    trace_path.write_text("[]", encoding="utf-8")

    def reject_deep_json(*args, **kwargs):
        raise RecursionError("privacy-marker")

    # Parser depth limits differ by Python version; force its documented error.
    monkeypatch.setattr("gameops_investigator.trace_audit.json.loads", reject_deep_json)
    result = audit_trace_file(trace_path)
    assert_summary_contract(result)
    assert result["violations"] == [{"code": "invalid_json", "step": None}]
    assert "privacy-marker" not in json.dumps(result)


@pytest.mark.parametrize("options", [[], ["example.json", "--max-tool-calls", "not-integer"]])
def test_cli_usage_errors_exit_two_without_live_execution(monkeypatch, capsys, block_live_execution, options):
    monkeypatch.setattr(sys, "argv", ["gameops", "audit-trace", *options])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err.lower()
