from __future__ import annotations

import json
import subprocess
import sys

import pytest

from evals.run_evals import summarize_claude_status
from gameops_investigator import cli, orchestrator


MARKER = "privacy-marker"


def success_payload(**updates):
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "A synthetic-data investigation report.",
        **updates,
    }


@pytest.fixture
def mock_process(monkeypatch):
    monkeypatch.setattr(
        orchestrator.ClaudeCodeRunner,
        "availability",
        staticmethod(lambda: {"installed": True, "logged_in": True, "executable": "mock-claude"}),
    )

    def configure(stdout, returncode=0, stderr=MARKER):
        calls = []

        def complete(command, **kwargs):
            calls.append(command)
            assert command[command.index("--output-format") + 1] == "json"
            return subprocess.CompletedProcess(command, returncode, stdout, stderr)

        monkeypatch.setattr(orchestrator.subprocess, "run", complete)
        return orchestrator.ClaudeCodeRunner(), calls

    return configure


def assert_failure(result, code, returncode=0):
    assert set(result) == {"ok", "mode", "error_code", "error", "returncode", "elapsed_ms"}
    assert result["ok"] is False
    assert result["mode"] == "claude_code"
    assert result["error_code"] == code
    assert isinstance(result["error"], str) and result["error"].strip()
    assert result["returncode"] == returncode
    assert result["elapsed_ms"] >= 0
    assert MARKER not in json.dumps(result)


def test_success_retains_result_whitespace_and_extra_metadata(mock_process):
    payload = success_payload(result="  Report with original formatting.\n", usage={"input_tokens": 42}, session_id=MARKER)
    runner, calls = mock_process(json.dumps(payload))
    result = runner.run("test question")
    assert set(result) == {"ok", "mode", "payload", "elapsed_ms"}
    assert result["ok"] is True
    assert result["mode"] == "claude_code"
    assert result["payload"] == payload
    assert result["elapsed_ms"] >= 0
    assert len(calls) == 1


@pytest.mark.parametrize("stdout", ["", "privacy-marker", '{"privacy-marker":', "{}\nprivacy-marker"])
def test_invalid_json_fails_without_echoing_raw_output(mock_process, stdout):
    runner, calls = mock_process(stdout)
    assert_failure(runner.run("test question"), "invalid_json")
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [None, [], [success_payload()], MARKER, 5, True])
def test_non_object_json_is_not_a_completed_agent_response(mock_process, payload):
    runner, calls = mock_process(json.dumps(payload))
    assert_failure(runner.run("test question"), "invalid_response")
    assert len(calls) == 1


@pytest.mark.parametrize("field", ["type", "subtype", "is_error", "result"])
def test_missing_required_response_fields_are_rejected(mock_process, field):
    payload = success_payload()
    del payload[field]
    runner, calls = mock_process(json.dumps(payload))
    assert_failure(runner.run("test question"), "invalid_response")
    assert len(calls) == 1


@pytest.mark.parametrize("updates", [
    {"type": "assistant"},
    {"subtype": ""},
    {"subtype": None},
    {"subtype": 1},
    {"subtype": MARKER},
    {"is_error": "false"},
    {"is_error": 0},
    {"is_error": None},
    {"result": ""},
    {"result": " \r\n\t "},
    {"result": None},
    {"result": {"report": MARKER}},
])
def test_invalid_response_shape_or_result_is_rejected(mock_process, updates):
    runner, calls = mock_process(json.dumps(success_payload(**updates)))
    assert_failure(runner.run("test question"), "invalid_response")
    assert len(calls) == 1


@pytest.mark.parametrize("subtype, is_error", [
    ("error_max_turns", True),
    ("error_during_execution", True),
    ("error_max_budget_usd", True),
    ("error_max_structured_output_retries", True),
    ("error_max_turns", False),
])
def test_error_result_subtypes_fail_even_when_process_exits_zero(mock_process, subtype, is_error):
    payload = {"type": "result", "subtype": subtype, "is_error": is_error, "errors": [MARKER]}
    runner, calls = mock_process(json.dumps(payload))
    assert_failure(runner.run("test question"), "agent_result_error")
    assert len(calls) == 1


@pytest.mark.parametrize("subtype", ["success", MARKER])
def test_explicit_agent_error_wins_over_success_or_unknown_subtype(mock_process, subtype):
    runner, calls = mock_process(json.dumps(success_payload(subtype=subtype, is_error=True, result=MARKER)))
    assert_failure(runner.run("test question"), "agent_result_error")
    assert len(calls) == 1


def test_malformed_envelope_is_not_accepted_as_an_agent_error(mock_process):
    runner, calls = mock_process(json.dumps({"is_error": True, "errors": [MARKER]}))
    assert_failure(runner.run("test question"), "invalid_response")
    assert len(calls) == 1


@pytest.mark.parametrize("stdout, returncode", [
    (MARKER, 1),
    (json.dumps(success_payload()), 2),
    (json.dumps(success_payload(is_error=True)), -9),
])
def test_nonzero_process_exit_has_priority_and_redacts_diagnostics(mock_process, stdout, returncode):
    runner, calls = mock_process(stdout, returncode=returncode)
    assert_failure(runner.run("test question"), "process_failed", returncode=returncode)
    assert len(calls) == 1


def test_parser_recursion_failure_returns_sanitized_failure(monkeypatch, mock_process):
    runner, calls = mock_process("[]")

    def fail(*args, **kwargs):
        raise RecursionError(MARKER)

    monkeypatch.setattr(orchestrator.json, "loads", fail)
    assert_failure(runner.run("test question"), "invalid_json")
    assert len(calls) == 1


@pytest.mark.parametrize("stdout, returncode, expected_exit, expected_code", [
    (json.dumps(success_payload()), 0, 0, None),
    (MARKER, 0, 1, "invalid_json"),
    (json.dumps([MARKER]), 0, 1, "invalid_response"),
    (json.dumps(success_payload(is_error=True, result=MARKER)), 0, 1, "agent_result_error"),
    (MARKER, 7, 1, "process_failed"),
])
def test_cli_uses_validated_runner_status_without_live_model(
    monkeypatch, capsys, mock_process, stdout, returncode, expected_exit, expected_code
):
    _, calls = mock_process(stdout, returncode=returncode)
    monkeypatch.setattr(sys, "argv", ["gameops", "claude", "test question"])
    assert cli.main() == expected_exit
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert len(calls) == 1
    if expected_code is None:
        assert result["ok"] is True
        assert result["payload"] == success_payload()
    else:
        assert_failure(result, expected_code, returncode=returncode)


@pytest.mark.parametrize("payload, expected_ok", [
    (success_payload(result=MARKER, session_id=MARKER), True),
    (success_payload(is_error=True, result=MARKER), False),
])
def test_validated_outcome_flows_to_export_without_raw_model_payload(mock_process, payload, expected_ok):
    runner, calls = mock_process(json.dumps(payload))
    live_result = runner.run("test question")
    summary = summarize_claude_status({"installed": True, "logged_in": True}, live_result)
    assert summary["evaluation"]["ok"] is expected_ok
    assert summary["evaluation"]["output_omitted"] is True
    assert set(summary["evaluation"]) == {"ok", "mode", "elapsed_ms", "returncode", "output_omitted"}
    assert MARKER not in json.dumps(summary)
    assert len(calls) == 1
