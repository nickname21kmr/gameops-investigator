"""Offline workflow checks over recorded tool calls; never execute trace content."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_TOOLS = (
    "get_metric_definition", "compare_cohorts", "detect_anomalies",
    "query_metrics", "draft_incident_report",
)
ANALYSIS_TOOLS = frozenset(REQUIRED_TOOLS[1:4])
REPORT_PREREQUISITES = frozenset(REQUIRED_TOOLS[:4])
MAX_TRACE_BYTES = 2 * 1024 * 1024


def _result(count: int, budget: int | None, violations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": not violations,
        "audit_mode": "deterministic_trajectory_rules",
        "call_count": count,
        "max_tool_calls": budget,
        "violations": violations,
    }


def _valid_budget(value: Any) -> bool:
    return type(value) is int and 1 <= value <= 10000


def audit_trace(payload: Any, max_tool_calls: int = 20) -> dict[str, Any]:
    """Check a complete successful investigation, not answer quality or authenticity."""
    if not _valid_budget(max_tool_calls):
        return _result(0, None, [{"code": "invalid_budget", "step": None}])
    trace = payload.get("trace") if isinstance(payload, dict) else payload
    if not isinstance(trace, list) or not trace:
        return _result(0, max_tool_calls, [{"code": "invalid_trace", "step": None}])
    violations: list[dict[str, Any]] = []

    def flag(code: str, step: int | None = None) -> None:
        # Codes are constants; never echo untrusted tool names or arguments.
        violations.append({"code": code, "step": step})

    if len(trace) > max_tool_calls:
        flag("tool_budget_exceeded")
    succeeded: set[str] = set()
    for step, call in enumerate(trace, start=1):
        if (
            not isinstance(call, dict)
            or not isinstance(call.get("tool"), str)
            or not isinstance(call.get("arguments"), dict)
            or type(call.get("ok")) is not bool
        ):
            flag("invalid_step", step)
            continue
        tool = call["tool"]
        if tool not in REQUIRED_TOOLS:
            flag("unknown_tool", step)
            continue
        if call["ok"] is False:
            flag("tool_call_failed", step)
        if tool in ANALYSIS_TOOLS and "get_metric_definition" not in succeeded:
            flag("definition_required", step)
        if tool == "draft_incident_report":
            if not REPORT_PREREQUISITES <= succeeded:
                flag("report_prerequisites_missing", step)
            if step != len(trace):
                flag("report_not_last", step)
        if call["ok"] is True:
            succeeded.add(tool)
    for tool in REQUIRED_TOOLS:
        if tool not in succeeded:
            flag(f"missing_{tool}")
    return _result(len(trace), max_tool_calls, violations)


def audit_trace_file(path: str | Path, max_tool_calls: int = 20) -> dict[str, Any]:
    """Read at most 2 MiB plus a sentinel byte; return redacted input errors."""
    if not _valid_budget(max_tool_calls):
        return audit_trace(None, max_tool_calls)
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_TRACE_BYTES + 1)
    except (OSError, ValueError):
        return _result(0, max_tool_calls, [{"code": "trace_file_unreadable", "step": None}])
    if len(content) > MAX_TRACE_BYTES:
        return _result(0, max_tool_calls, [{"code": "trace_file_too_large", "step": None}])
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, ValueError, RecursionError):
        return _result(0, max_tool_calls, [{"code": "invalid_json", "step": None}])
    return audit_trace(payload, max_tool_calls)
