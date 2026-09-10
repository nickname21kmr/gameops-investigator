from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evals import run_evals


PRIVACY_MARKER = "privacy-marker"
NOT_RUN = "not_run; use --claude after interactive sign-in"


@pytest.fixture
def export_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "eval_results.json"
    monkeypatch.setattr(run_evals, "RESULTS_PATH", path)
    monkeypatch.setattr(
        run_evals,
        "load_cases",
        lambda: [{"id": "sql-export", "type": "sql_policy", "sql": "SELECT 1", "should_pass": True}],
    )
    monkeypatch.setattr(run_evals, "scenario_catalog", lambda: [])
    monkeypatch.setattr(run_evals, "query_metrics", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        run_evals.ClaudeCodeRunner,
        "availability",
        staticmethod(lambda: {"installed": False, "logged_in": False}),
    )

    def forbid_model_run(*args, **kwargs):
        raise AssertionError("An offline export must not call the model runner.")

    monkeypatch.setattr(run_evals.ClaudeCodeRunner, "run", forbid_model_run)
    return path


def assert_public_export(result: dict, path: Path) -> None:
    exported = path.read_text(encoding="utf-8")
    assert json.loads(exported) == result
    assert PRIVACY_MARKER not in exported
    assert PRIVACY_MARKER not in json.dumps(result, allow_nan=False)
    assert set(result["claude_code"]) == {"installed", "logged_in", "auth_check_failed", "evaluation"}
    assert result["evaluation_mode"] == "deterministic_offline_baseline"
    assert result["case_count"] == 1
    assert result["claude_agent_metrics"] is None
    assert result["metrics"]["claude_single_analysis_cost_usd"] is None


def test_offline_export_omits_local_diagnostics_without_mutating_source(
    monkeypatch: pytest.MonkeyPatch, export_path: Path
):
    local_status = {
        "installed": True,
        "logged_in": False,
        "executable": f"{PRIVACY_MARKER}-local-path",
        "auth_error": f"{PRIVACY_MARKER}-account-diagnostic",
        "auth_method": PRIVACY_MARKER,
        "api_provider": PRIVACY_MARKER,
        "future_field": {"nested": PRIVACY_MARKER},
    }
    original = copy.deepcopy(local_status)
    monkeypatch.setattr(run_evals.ClaudeCodeRunner, "availability", staticmethod(lambda: local_status))

    result = run_evals.run(include_claude=False)

    assert_public_export(result, export_path)
    assert result["claude_code"] == {
        "installed": True,
        "logged_in": False,
        "auth_check_failed": True,
        "evaluation": NOT_RUN,
    }
    assert local_status == original
    assert result["passed"] == 1
    assert result["failed"] == 0
    assert result["metrics"]["sql_execution_success_rate"] == 1.0
    assert result["metrics"]["sql_policy_expected_outcome_rate"] == 1.0


@pytest.mark.parametrize(
    ("installed", "logged_in", "expected_installed", "expected_logged_in"),
    [
        (1, 0, None, None),
        (PRIVACY_MARKER, None, None, None),
        (False, True, False, True),
    ],
)
def test_availability_exports_only_boolean_values(
    monkeypatch: pytest.MonkeyPatch,
    export_path: Path,
    installed,
    logged_in,
    expected_installed,
    expected_logged_in,
):
    local_status = {"installed": installed, "logged_in": logged_in}
    monkeypatch.setattr(run_evals.ClaudeCodeRunner, "availability", staticmethod(lambda: local_status))

    result = run_evals.run()

    assert_public_export(result, export_path)
    assert result["claude_code"] == {
        "installed": expected_installed,
        "logged_in": expected_logged_in,
        "auth_check_failed": False,
        "evaluation": NOT_RUN,
    }
    assert "evaluation" not in local_status


@pytest.mark.parametrize("query_ok", [True, False])
def test_sql_errors_export_fixed_categories_and_preserve_scores(
    monkeypatch: pytest.MonkeyPatch, export_path: Path, query_ok: bool
):
    monkeypatch.setattr(
        run_evals, "query_metrics", lambda *args, **kwargs: {"ok": query_ok, "error": PRIVACY_MARKER}
    )

    result = run_evals.run()

    assert_public_export(result, export_path)
    assert result["details"][0]["error"] == (None if query_ok else "query_rejected_or_unavailable")
    assert result["details"][0]["actual_pass"] is query_ok
    assert result["details"][0]["expected_pass"] is True
    assert result["passed"] == int(query_ok)
    assert result["failed"] == int(not query_ok)
    assert result["metrics"]["sql_execution_success_rate"] == float(query_ok)
    assert result["metrics"]["sql_policy_expected_outcome_rate"] == float(query_ok)


@pytest.mark.parametrize(("ok", "returncode"), [(True, 0), (False, 2), (PRIVACY_MARKER, 3)])
def test_requested_evaluation_exports_summary_without_raw_model_output(
    monkeypatch: pytest.MonkeyPatch, export_path: Path, ok, returncode: int
):
    local_status = {"installed": True, "logged_in": True, "auth_error": None}
    original_status = copy.deepcopy(local_status)
    live_result = {
        "ok": ok,
        "mode": PRIVACY_MARKER,
        "elapsed_ms": 12.5,
        "returncode": returncode,
        "payload": {"result": PRIVACY_MARKER, "future_field": {"account": PRIVACY_MARKER}},
        "error": PRIVACY_MARKER,
        "future_field": PRIVACY_MARKER,
    }
    original_live_result = copy.deepcopy(live_result)
    calls = []

    def fake_model_run(self, question):
        calls.append(question)
        return live_result

    monkeypatch.setattr(run_evals.ClaudeCodeRunner, "availability", staticmethod(lambda: local_status))
    monkeypatch.setattr(run_evals.ClaudeCodeRunner, "run", fake_model_run)

    result = run_evals.run(include_claude=True)

    assert_public_export(result, export_path)
    assert len(calls) == 1
    assert result["claude_code"]["auth_check_failed"] is True
    assert result["claude_code"]["evaluation"] == {
        "ok": ok if isinstance(ok, bool) else None,
        "mode": "claude_code",
        "elapsed_ms": 12.5,
        "returncode": returncode,
        "output_omitted": True,
    }
    assert local_status == original_status
    assert live_result == original_live_result
    assert result["passed"] == 1
    assert result["failed"] == 0


@pytest.mark.parametrize(
    ("elapsed_ms", "returncode", "expected_elapsed_ms", "expected_returncode"),
    [
        (float("nan"), True, None, None),
        (float("inf"), 0.5, None, None),
        (float("-inf"), "1", None, None),
        (True, False, None, None),
        (False, None, None, None),
        (-2, None, None, None),
        (PRIVACY_MARKER, PRIVACY_MARKER, None, None),
        (None, float("inf"), None, None),
        (0, 0, 0, 0),
    ],
)
def test_evaluation_summary_rejects_invalid_numeric_fields(
    monkeypatch: pytest.MonkeyPatch,
    export_path: Path,
    elapsed_ms,
    returncode,
    expected_elapsed_ms,
    expected_returncode,
):
    monkeypatch.setattr(
        run_evals.ClaudeCodeRunner,
        "run",
        lambda *args, **kwargs: {"ok": True, "elapsed_ms": elapsed_ms, "returncode": returncode},
    )

    result = run_evals.run(include_claude=True)

    assert_public_export(result, export_path)
    assert result["claude_code"]["evaluation"] == {
        "ok": True,
        "mode": "claude_code",
        "elapsed_ms": expected_elapsed_ms,
        "returncode": expected_returncode,
        "output_omitted": True,
    }
