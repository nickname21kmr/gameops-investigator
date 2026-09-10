from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from gameops_investigator.config import scenario_catalog  # noqa: E402
from gameops_investigator.orchestrator import ClaudeCodeRunner, DeterministicInvestigator  # noqa: E402
from gameops_investigator.tools import get_metric_definition, query_metrics  # noqa: E402


CASES_PATH = Path(__file__).with_name("cases.jsonl")
RESULTS_PATH = PROJECT_ROOT / "artifacts" / "eval_results.json"


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CASES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def route_tool(prompt: str) -> str:
    lowered = prompt.lower()
    if any(token in lowered for token in ("报告", "report", "证据编号")):
        return "draft_incident_report"
    if any(token in lowered for token in ("异常", "z 检验", "z检验", "阈值")):
        return "detect_anomalies"
    if any(token in lowered for token in ("对比", "比较", "cohort", "差多少")):
        return "compare_cohorts"
    if any(token in lowered for token in ("sql", "select", "查询", "明细")):
        return "query_metrics"
    return "get_metric_definition"


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_claude_status(
    status: dict[str, Any], evaluation: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Export an allowlisted summary, not local diagnostics or model output."""
    summary: dict[str, Any] = {
        "installed": status.get("installed") if type(status.get("installed")) is bool else None,
        "logged_in": status.get("logged_in") if type(status.get("logged_in")) is bool else None,
        "auth_check_failed": "auth_error" in status,
        "evaluation": "not_run; use --claude after interactive sign-in",
    }
    if evaluation is not None:
        elapsed_ms = evaluation.get("elapsed_ms")
        valid_elapsed = (
            type(elapsed_ms) is int and elapsed_ms >= 0
        ) or (
            type(elapsed_ms) is float and math.isfinite(elapsed_ms) and elapsed_ms >= 0
        )
        returncode = evaluation.get("returncode")
        summary["evaluation"] = {
            "ok": evaluation.get("ok") if type(evaluation.get("ok")) is bool else None,
            "mode": "claude_code",
            "elapsed_ms": elapsed_ms if valid_elapsed else None,
            "returncode": returncode if type(returncode) is int else None,
            "output_omitted": True,
        }
    return summary


def run(include_claude: bool = False) -> dict[str, Any]:
    cases = load_cases()
    details = []
    scenario_cache: dict[str, dict[str, Any]] = {}
    latencies = []
    for case in cases:
        started = time.perf_counter()
        case_type = case["type"]
        if case_type == "tool_routing":
            actual = route_tool(case["prompt"])
            passed = actual == case["expected_tool"]
            detail = {"actual_tool": actual, "expected_tool": case["expected_tool"]}
        elif case_type == "sql_policy":
            result = query_metrics(case["sql"], row_limit=50, timeout_ms=2000)
            actual_pass = bool(result["ok"])
            passed = actual_pass == case["should_pass"]
            detail = {
                "actual_pass": actual_pass,
                "expected_pass": case["should_pass"],
                "error": None if actual_pass else "query_rejected_or_unavailable",
            }
        elif case_type == "incident_attribution":
            result = scenario_cache.setdefault(case["scenario_id"], DeterministicInvestigator().investigate(case["scenario_id"]))
            candidate_ids = [item["id"] for item in result["candidates"][:3]]
            passed = case["expected_top3"] in candidate_ids
            detail = {"candidate_ids": candidate_ids, "expected_top3": case["expected_top3"]}
        elif case_type == "metric_contract":
            result = get_metric_definition(case["metric_id"])
            serialized = json.dumps(result, ensure_ascii=False)
            missing = [token for token in case["expected_tokens"] if token not in serialized]
            passed = not missing
            detail = {"missing_tokens": missing}
        elif case_type == "governance":
            result = scenario_cache.setdefault(case["scenario_id"], DeterministicInvestigator().investigate(case["scenario_id"]))
            markdown = result["report"]["markdown"]
            checks = {
                "human_review_required": result["report"]["review_status"] == "human_review_required",
                "citation_valid": result["report"]["citation_check"]["valid"],
                "synthetic_disclosure": "synthetic" in markdown.lower(),
                "uncertainty_disclosure": "causal proof" in markdown.lower() or "因果" in markdown,
            }
            passed = checks[case["check"]]
            detail = {"check": case["check"], "actual": passed}
        else:
            passed = False
            detail = {"error": f"unknown case type {case_type}"}
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        details.append({"id": case["id"], "type": case_type, "passed": passed, "elapsed_ms": round(elapsed_ms, 3), **detail})

    def rate(case_type: str) -> float | None:
        subset = [item for item in details if item["type"] == case_type]
        return None if not subset else sum(item["passed"] for item in subset) / len(subset)

    incident_results = [item for item in details if item["type"] == "incident_attribution"]
    safe_sql_results = [item for item in details if item["type"] == "sql_policy" and item["expected_pass"]]
    citation_values = [result["report"]["citation_check"]["valid"] for result in scenario_cache.values()]
    claude_status = ClaudeCodeRunner.availability()
    claude_evaluation = None
    if include_claude:
        claude_evaluation = ClaudeCodeRunner().run(
            "Investigate the tutorial_failure incident from the configured demo windows and return a cited report."
        )

    result = {
        "suite": "gameops-investigator-fixed-evals-v1",
        "evaluation_mode": "deterministic_offline_baseline",
        "evaluation_boundary": "These scores validate the fixed harness, tool functions, replay coordinator, safety controls, and report citations. They are not Claude model scores.",
        "case_count": len(cases),
        "passed": sum(item["passed"] for item in details),
        "failed": sum(not item["passed"] for item in details),
        "metrics": {
            "tool_selection_accuracy": rate("tool_routing"),
            "sql_execution_success_rate": None if not safe_sql_results else sum(item["actual_pass"] for item in safe_sql_results) / len(safe_sql_results),
            "sql_policy_expected_outcome_rate": rate("sql_policy"),
            "root_cause_top3_hit_rate": None if not incident_results else sum(item["passed"] for item in incident_results) / len(incident_results),
            "report_citation_accuracy": None if not citation_values else sum(citation_values) / len(citation_values),
            "metric_contract_accuracy": rate("metric_contract"),
            "governance_behavior_accuracy": rate("governance"),
            "p50_case_latency_ms": round(statistics.median(latencies), 3),
            "p95_case_latency_ms": round(percentile(latencies, 0.95) or 0, 3),
            "deterministic_local_cost_usd": 0.0,
            "claude_single_analysis_cost_usd": None,
            "claude_cost_note": "Not measured until Claude Code completes an authenticated run; no number is inferred from a Pro subscription.",
        },
        "claude_code": summarize_claude_status(claude_status, claude_evaluation),
        "claude_agent_metrics": None,
        "scenario_count": len(scenario_catalog()),
        "details": details,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", action="store_true", help="Also run one authenticated Claude Code evaluation")
    args = parser.parse_args()
    output = run(include_claude=args.claude)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if output["failed"] == 0 else 1)
