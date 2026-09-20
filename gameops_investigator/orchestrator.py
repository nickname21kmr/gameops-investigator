from __future__ import annotations

import json
import math
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import PROJECT_ROOT, scenario_catalog
from .tools import (
    compare_cohorts,
    detect_anomalies,
    draft_incident_report,
    evidence_digest,
    get_metric_definition,
    query_metrics,
)


@dataclass
class TraceCall:
    tool: str
    arguments: dict[str, Any]
    elapsed_ms: float
    ok: bool
    evidence_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "ok": self.ok,
            "evidence_id": self.evidence_id,
        }


class DeterministicInvestigator:
    """A reproducible planner used for demos, tests, and Claude-free fallback.

    It calls the exact same deterministic functions exposed through MCP. It is
    deliberately labelled as a replay coordinator rather than an LLM.
    """

    MIN_DENOMINATOR = 20
    Z_THRESHOLD = 1.96

    def __init__(self):
        self.scenarios = scenario_catalog()
        self.trace: list[TraceCall] = []
        self.evidence: list[dict[str, Any]] = []

    def _call(self, name: str, function: Callable[..., dict[str, Any]], **arguments: Any) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = function(**arguments)
        except (OSError, ValueError, sqlite3.Error):
            # Unexpected programming errors still propagate.
            result = {"ok": False}
        if result.get("ok") is False:
            # Both raised and returned failures may contain private diagnostics
            # or arbitrary payloads. Export only this stable failure object.
            result = {"ok": False, "error": "The investigation tool could not complete."}
        elapsed = (time.perf_counter() - started) * 1000
        evidence_id = f"E{len(self.evidence) + 1:02d}"
        self.trace.append(TraceCall(name, arguments, elapsed, bool(result.get("ok", True)), evidence_id))
        self.evidence.append(
            {
                "evidence_id": evidence_id,
                "title": name,
                "digest": evidence_digest(result),
                "sql": arguments.get("sql"),
                "result": result,
            }
        )
        return result

    @staticmethod
    def _window_filters(window: dict[str, Any]) -> dict[str, Any]:
        return dict(window)

    @staticmethod
    def _shared_filters(window: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in window.items() if key not in {"start_date", "end_date"}}

    @staticmethod
    def _find_focus(comparison: dict[str, Any], dimension: str, focus_value: str) -> dict[str, Any] | None:
        return next(
            (row for row in comparison.get("rows", []) if row.get("dimensions", {}).get(dimension) == focus_value),
            None,
        )

    def investigate(self, scenario_id: str) -> dict[str, Any]:
        if scenario_id not in self.scenarios:
            raise KeyError(f"Unknown scenario: {scenario_id}")
        self.trace = []
        self.evidence = []
        started = time.perf_counter()
        scenario = self.scenarios[scenario_id]
        alert_metric = scenario["alert_metric"]
        baseline = self._window_filters(scenario["baseline"])
        current = self._window_filters(scenario["current"])
        dimension = scenario["breakdown_dimension"]
        focus_value = scenario["focus_value"]

        definition_result = self._call(
            "get_metric_definition",
            get_metric_definition,
            metric_name=alert_metric,
        )
        definition = definition_result.get("definition", {"metric_id": alert_metric})
        overall = self._call(
            "compare_cohorts",
            compare_cohorts,
            metric_name=alert_metric,
            current_filters=current,
            baseline_filters=baseline,
            group_by=[],
        )
        anomaly = self._call(
            "detect_anomalies",
            detect_anomalies,
            metric_name=alert_metric,
            current_start=current["start_date"],
            current_end=current["end_date"],
            baseline_start=baseline["start_date"],
            baseline_end=baseline["end_date"],
            dimensions=[dimension],
            filters=self._shared_filters(current),
            min_denominator=self.MIN_DENOMINATOR,
            z_threshold=self.Z_THRESHOLD,
        )

        related: dict[str, dict[str, Any]] = {}
        related_refs: dict[str, str] = {}
        for metric_id in scenario.get("related_metrics", []):
            result = self._call(
                "compare_cohorts",
                compare_cohorts,
                metric_name=metric_id,
                current_filters=current,
                baseline_filters=baseline,
                group_by=[dimension],
            )
            related[metric_id] = result
            related_refs[metric_id] = self.trace[-1].evidence_id

        for sql in scenario.get("evidence_queries", []):
            self._call("query_metrics", query_metrics, sql=sql, row_limit=100, timeout_ms=3000)

        investigation_status, investigation_reason = self._evidence_status(
            overall, anomaly, related, dimension, focus_value,
        )
        candidates = self._rank_candidates(
            scenario_id,
            scenario,
            overall,
            anomaly,
            related,
            related_refs,
            dimension,
            focus_value,
        ) if investigation_status == "supported" else []
        report = self._call(
            "draft_incident_report",
            draft_incident_report,
            title=scenario["title"],
            alert_metric=definition,
            overall_comparison=overall,
            anomaly_result=anomaly,
            candidates=candidates,
            evidence=[
                {key: value for key, value in item.items() if key != "result"}
                for item in self.evidence
            ],
            limitations=["The deterministic coordinator follows a fixed investigation playbook; open-ended planning is delegated to Claude Code."],
            investigation_status=investigation_status,
            investigation_reason=investigation_reason,
        )
        if report.get("ok") is False:
            investigation_status = "tool_failure"
            investigation_reason = "报告生成失败；请检查工具状态后重新调查。"
            candidates = []
            report = {
                **report,
                "review_status": "human_review_required",
                "investigation_status": investigation_status,
                "investigation_reason": investigation_reason,
                "markdown": "# Investigation incomplete\n\nReport generation failed. No cause is supported by this run.\n",
                "citation_check": {"valid": False},
            }
        total_ms = (time.perf_counter() - started) * 1000
        return {
            "ok": investigation_status != "tool_failure",
            "investigation_status": investigation_status,
            "investigation_reason": investigation_reason,
            "scenario_id": scenario_id,
            "title": scenario["title"],
            "mode": "deterministic_replay",
            "plan": [
                "Read the metric contract",
                "Quantify the overall alert",
                f"Break down by {dimension}",
                "Test upstream and data-quality hypotheses",
                "Run read-only evidence SQL",
                "Rank candidates and draft a human-review report",
            ],
            "alert_metric": definition,
            "overall_comparison": overall,
            "anomaly_result": anomaly,
            "related_comparisons": related,
            "candidates": candidates,
            "evidence": self.evidence,
            "trace": [item.to_dict() for item in self.trace],
            "report": report,
            "elapsed_ms": round(total_ms, 3),
        }

    @staticmethod
    def _finite_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def _usable_comparison(self, row: dict[str, Any] | None) -> bool:
        if not row or not self._finite_number(row.get("delta")):
            return False
        for window in ("current", "baseline"):
            sample = row.get(window, {})
            denominator = sample.get("denominator")
            if (
                not self._finite_number(denominator)
                or denominator < self.MIN_DENOMINATOR
                or not self._finite_number(sample.get("value"))
            ):
                return False
        return self._finite_number(row.get("z_score"))

    def _significant_change(self, row: dict[str, Any], direction: int) -> bool:
        return (
            self._usable_comparison(row)
            and row["delta"] * direction > 0
            and row["z_score"] * direction >= self.Z_THRESHOLD
        )

    @staticmethod
    def _supported_confidence(*rows: dict[str, Any]) -> str:
        # Called only after the support gate; retain the weakest supporting
        # comparison's tier instead of promoting every detected change to high.
        ranks = {"high": 2, "medium": 1}
        return min((row.get("confidence", "low") for row in rows), key=lambda value: ranks.get(value, 0))

    def _evidence_status(
        self,
        overall: dict[str, Any],
        anomaly: dict[str, Any],
        related: dict[str, dict[str, Any]],
        dimension: str,
        focus_value: str,
    ) -> tuple[str, str]:
        if any(not call.ok for call in self.trace):
            return "tool_failure", "调查工具执行失败；本次不输出支持的候选原因。"

        focus = self._find_focus({"rows": anomaly.get("all_comparisons", [])}, dimension, focus_value)
        required_rows = [focus]
        duplicate_case = "duplicate_signature_rate" in related
        if duplicate_case:
            required_ids = ("duplicate_signature_rate", "system_adoption_rate")
        elif dimension == "strategy_segment":
            required_ids = ()
        else:
            required_ids = ("tutorial_completion_rate",)
        focus_related = {
            metric_id: self._find_focus(related.get(metric_id, {}), dimension, focus_value)
            for metric_id in required_ids
        }
        required_rows.extend(focus_related.values())
        queries = [item["result"] for item in self.evidence if item["title"] == "query_metrics"]
        if (
            not overall.get("rows")
            or not all(self._usable_comparison(row) for row in required_rows)
            or not queries
            or any(not query.get("rows") for query in queries)
        ):
            return "insufficient_evidence", "缺少可用数据或统计比较：需两个窗口均有足够样本、必需指标和查询证据。"

        detected_focus = self._find_focus({"rows": anomaly.get("anomalies", [])}, dimension, focus_value)
        direction = 1 if duplicate_case else -1
        if not detected_focus or not self._significant_change(focus, direction):
            return "no_supported_candidate", "焦点分群未出现符合该排查假设方向和统计门槛的异常。"
        if duplicate_case:
            duplicate = focus_related["duplicate_signature_rate"]
            adoption = focus_related["system_adoption_rate"]
            if (
                not self._significant_change(duplicate, 1)
                or duplicate["delta"] <= 1
                or self._significant_change(adoption, 1)
            ):
                return "no_supported_candidate", "重复率或玩家采用率证据不符合当前重复上报排查规则；需进一步复核。"
        elif required_ids and not self._significant_change(focus_related["tutorial_completion_rate"], -1):
            return "no_supported_candidate", "教程完成率未出现足够证据支持的同向下降，不能支持上游教程候选。"
        return "supported", "焦点异常与必需证据满足固定排查规则；候选仍需人工复核，不代表因果证明。"

    def _rank_candidates(
        self,
        scenario_id: str,
        scenario: dict[str, Any],
        overall: dict[str, Any],
        anomaly: dict[str, Any],
        related: dict[str, dict[str, Any]],
        related_refs: dict[str, str],
        dimension: str,
        focus_value: str,
    ) -> list[dict[str, Any]]:
        anomaly_ref = self.trace[2].evidence_id
        sql_refs = [item.evidence_id for item in self.trace if item.tool == "query_metrics"]
        focus_anomaly = next(
            (row for row in anomaly.get("all_comparisons", []) if row.get("dimensions", {}).get(dimension) == focus_value),
            None,
        )
        focus_delta = None if not focus_anomaly else focus_anomaly.get("delta")

        if "duplicate_signature_rate" in related:
            duplicate_row = self._find_focus(related["duplicate_signature_rate"], dimension, focus_value)
            adoption_row = self._find_focus(related.get("system_adoption_rate", {}), dimension, focus_value)
            duplicate_delta = None if not duplicate_row else duplicate_row.get("delta")
            adoption_delta = None if not adoption_row else adoption_row.get("delta")
            duplicate_confidence = self._supported_confidence(focus_anomaly, duplicate_row)
            return [
                {
                    "id": "duplicate_event_reporting",
                    "title": "重复埋点上报放大事件级参与强度",
                    "confidence": duplicate_confidence,
                    "status": "supported_candidate",
                    "evidence_refs": [anomaly_ref, related_refs["duplicate_signature_rate"], related_refs["system_adoption_rate"], *sql_refs],
                    "reasoning": f"重复签名率变化为 {duplicate_delta}; 玩家级采用率变化为 {adoption_delta}。事件强度与重复率显著上升，未检出玩家采用率显著上升；未检出不等于证明采用率不变，仍需人工核对埋点。",
                },
                {
                    "id": "real_usage_expansion",
                    "title": "玩家真实提高了高级系统使用频次",
                    "confidence": "low",
                    "status": "not_supported_yet",
                    "evidence_refs": [related_refs.get("system_adoption_rate", anomaly_ref)],
                    "reasoning": "需要玩家级采用率、会话深度或游戏内状态同步上升；当前证据不足。",
                },
                {
                    "id": "channel_mix_shift",
                    "title": "渠道结构变化造成聚合指标偏移",
                    "confidence": "low",
                    "status": "alternative",
                    "evidence_refs": [anomaly_ref],
                    "reasoning": "渠道下钻已定位异常，但仍需校验总体用户构成变化。",
                },
            ]

        if dimension == "strategy_segment":
            confidence = self._supported_confidence(focus_anomaly)
            return [
                {
                    "id": "segment_leveraged_churn",
                    "title": f"{focus_value} 分群发生局部留存退化",
                    "confidence": confidence,
                    "status": "supported_candidate",
                    "evidence_refs": [anomaly_ref, *sql_refs],
                    "reasoning": f"该分群当前窗口相对基线变化 {focus_delta}，且达到样本量与统计门槛；这定位了退化分群，尚未证明业务根因。",
                },
                {
                    "id": "version_wide_regression",
                    "title": "版本级普遍留存退化",
                    "confidence": "low",
                    "status": "alternative",
                    "evidence_refs": [self.trace[1].evidence_id, anomaly_ref],
                    "reasoning": "需结合整体与各分群比较，判断是否同时存在版本级普遍退化；局部分群异常不能单独排除该解释。",
                },
                {
                    "id": "random_cohort_noise",
                    "title": "小样本或随机 cohort 波动",
                    "confidence": "low",
                    "status": "alternative",
                    "evidence_refs": [anomaly_ref],
                    "reasoning": "统计程序已执行最小样本门槛与 z 检验，但仍需更多日期复核稳定性。",
                },
            ]

        tutorial = related.get("tutorial_completion_rate", {})
        tutorial_row = self._find_focus(tutorial, dimension, focus_value)
        tutorial_delta = None if not tutorial_row else tutorial_row.get("delta")
        tutorial_confidence = self._supported_confidence(focus_anomaly, tutorial_row)
        return [
            {
                "id": "upstream_tutorial_drop",
                "title": "教程关键步完成下降是 D1 留存下滑的首要上游候选",
                "confidence": tutorial_confidence,
                "status": "supported_candidate",
                "evidence_refs": [anomaly_ref, related_refs.get("tutorial_completion_rate", anomaly_ref), *sql_refs],
                "reasoning": f"{focus_value} 的教程完成率变化为 {tutorial_delta}，并与同 cohort 的留存方向一致；这仍是关联证据而非因果证明。",
            },
            {
                "id": "downstream_trade_regression",
                "title": "交易环节或后续回合体验退化",
                "confidence": "low",
                "status": "secondary",
                "evidence_refs": [related_refs.get("trade_success_rate", anomaly_ref), related_refs.get("turn5_reach_rate", anomaly_ref)],
                "reasoning": "下游指标受上游样本选择影响，必须先处理教程漏斗变化。",
            },
            {
                "id": "channel_mix_shift",
                "title": "渠道用户结构变化",
                "confidence": "low",
                "status": "alternative",
                "evidence_refs": [anomaly_ref],
                "reasoning": "需要额外的渠道获客与设备属性才能进一步确认。",
            },
        ]


class ClaudeCodeRunner:
    ALLOWED_TOOLS = (
        "mcp__gameops__get_metric_definition,"
        "mcp__gameops__query_metrics,"
        "mcp__gameops__compare_cohorts,"
        "mcp__gameops__detect_anomalies,"
        "mcp__gameops__draft_incident_report"
    )

    @staticmethod
    def _executable() -> str | None:
        system = shutil.which("claude")
        if system:
            return system
        local = PROJECT_ROOT / ".tools" / "claude" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        return str(local) if local.exists() else None

    @staticmethod
    def availability() -> dict[str, Any]:
        executable = ClaudeCodeRunner._executable()
        status: dict[str, Any] = {
            "installed": executable is not None,
            "executable": executable,
            "logged_in": False,
            "auth_method": "not_available" if not executable else "unknown",
        }
        if executable:
            try:
                completed = subprocess.run(
                    [executable, "auth", "status", "--json"],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=8,
                    check=False,
                )
                payload = json.loads(completed.stdout)
                status["logged_in"] = bool(payload.get("loggedIn"))
                status["auth_method"] = payload.get("authMethod", "none")
                status["api_provider"] = payload.get("apiProvider")
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                status["auth_error"] = str(exc)
        return status

    def run(self, question: str, timeout_seconds: int = 300) -> dict[str, Any]:
        availability = self.availability()
        executable = availability.get("executable")
        if not availability.get("installed") or not executable:
            return {"ok": False, "error": "Claude Code is not installed.", "mode": "claude_code"}
        if not availability.get("logged_in"):
            return {
                "ok": False,
                "error": "Claude Code is installed, but interactive sign-in and project MCP approval are still required.",
                "mode": "claude_code",
            }
        prompt = (
            "You are the planning and interpretation layer for GameOps Investigator. "
            "Use only the gameops MCP tools for data access and calculations. Read the metric definition first, "
            "let detect_anomalies determine whether a change is abnormal, include SQL evidence, rank up to three causes, "
            "and state uncertainty. Never claim causality from correlation. Question: " + question
        )
        command = [
            executable,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            "16",
            "--mcp-config",
            str(PROJECT_ROOT / ".mcp.json"),
            "--allowedTools",
            self.ALLOWED_TOOLS,
            "--disallowedTools",
            "Bash,Write,Edit,WebFetch,WebSearch",
        ]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
                env=os.environ.copy(),
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            timed_out = isinstance(exc, subprocess.TimeoutExpired)
            # Exception text may contain the full prompt, paths, or partial output.
            return {
                "ok": False,
                "mode": "claude_code",
                "error_code": "timeout" if timed_out else "launch_failed",
                "error": (
                    "Claude Code exceeded the time limit. Try a smaller investigation question."
                    if timed_out else
                    "Claude Code could not start. Check the local installation and executable permissions."
                ),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        elapsed_ms = (time.perf_counter() - started) * 1000

        def response_failure(code: str, message: str) -> dict[str, Any]:
            return {
                "ok": False,
                "mode": "claude_code",
                "error_code": code,
                "returncode": completed.returncode,
                "error": message,
                "elapsed_ms": round(elapsed_ms, 3),
            }

        if completed.returncode != 0:
            return response_failure(
                "process_failed", "Claude Code exited unsuccessfully. Inspect the run locally before retrying."
            )
        try:
            payload = json.loads(completed.stdout)
        except (json.JSONDecodeError, RecursionError):
            return response_failure(
                "invalid_json", "Claude Code returned unreadable JSON. Check the local CLI version and output format."
            )
        invalid_response_message = "Claude Code returned an unsupported result. Check the local CLI version and output format."
        if (
            not isinstance(payload, dict)
            or payload.get("type") != "result"
            or not isinstance(payload.get("subtype"), str)
            or not payload["subtype"]
            or type(payload.get("is_error")) is not bool
        ):
            return response_failure("invalid_response", invalid_response_message)
        error_subtypes = {
            "error_max_turns", "error_during_execution",
            "error_max_budget_usd", "error_max_structured_output_retries",
        }
        if payload["is_error"] or payload["subtype"] in error_subtypes:
            return response_failure(
                "agent_result_error", "Claude Code reported a failed or incomplete run. Inspect the run locally before retrying."
            )
        if (
            payload["subtype"] != "success"
            or not isinstance(payload.get("result"), str)
            or not payload["result"].strip()
        ):
            return response_failure("invalid_response", invalid_response_message)
        return {"ok": True, "mode": "claude_code", "payload": payload, "elapsed_ms": round(elapsed_ms, 3)}
