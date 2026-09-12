from __future__ import annotations

import json
import subprocess
import sys

import pytest

from gameops_investigator import cli, orchestrator


@pytest.fixture
def ready_runner(monkeypatch):
    monkeypatch.setattr(
        orchestrator.ClaudeCodeRunner, "availability",
        staticmethod(lambda: {"installed": True, "logged_in": True, "executable": "mock-claude"}),
    )
    return orchestrator.ClaudeCodeRunner()


@pytest.mark.parametrize("failure, code", [
    (subprocess.TimeoutExpired(["privacy-marker"], 1, output="privacy-marker", stderr="privacy-marker"), "timeout"),
    (FileNotFoundError("privacy-marker"), "launch_failed"),
    (PermissionError("privacy-marker"), "launch_failed"),
])
def test_process_failures_are_structured_without_raw_diagnostics(monkeypatch, ready_runner, failure, code):
    calls = []

    def fail(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 1
        raise failure

    monkeypatch.setattr(orchestrator.subprocess, "run", fail)
    result = ready_runner.run("test question", timeout_seconds=1)
    assert result["ok"] is False
    assert result["mode"] == "claude_code"
    assert result["error_code"] == code
    assert result["error"]
    assert result["elapsed_ms"] >= 0
    assert "privacy-marker" not in json.dumps(result)
    assert "payload" not in result
    assert len(calls) == 1  # No automatic retries or extra model costs.


def test_cli_reports_timeout_as_json_and_failure_exit(monkeypatch, ready_runner, capsys):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("mock-claude", 300)

    monkeypatch.setattr(orchestrator.subprocess, "run", fail)
    monkeypatch.setattr(sys, "argv", ["gameops", "claude", "test question"])
    assert cli.main() == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["error_code"] == "timeout"


def test_success_keeps_payload_and_tool_restrictions(monkeypatch, ready_runner):
    def complete(command, **kwargs):
        assert command[command.index("--allowedTools") + 1] == ready_runner.ALLOWED_TOOLS
        assert command[command.index("--disallowedTools") + 1] == "Bash,Write,Edit,WebFetch,WebSearch"
        assert kwargs["timeout"] == 300
        return subprocess.CompletedProcess(command, 0, '{"result": "test report"}', "")

    monkeypatch.setattr(orchestrator.subprocess, "run", complete)
    result = ready_runner.run("test question")
    assert result["ok"] is True
    assert result["payload"] == {"result": "test report"}
