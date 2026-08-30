from __future__ import annotations

import hashlib
import json
from typing import Any

from .database import QueryRejected, execute_readonly
from .detector import compare_cohorts as compare_cohorts_impl
from .detector import detect_anomalies as detect_anomalies_impl
from .metrics import MetricEngine
from .reporting import draft_report


def get_metric_definition(metric_name: str | None = None) -> dict[str, Any]:
    """Return one metric definition, or the complete metric catalog."""
    engine = MetricEngine()
    if metric_name:
        return {"ok": True, "definition": engine.definition(metric_name)}
    return {"ok": True, "definitions": engine.list_definitions()}


def query_metrics(sql: str, row_limit: int = 200, timeout_ms: int = 2000) -> dict[str, Any]:
    """Execute validated read-only SQL over public synthetic analytics tables."""
    try:
        result = execute_readonly(sql, row_limit=row_limit, timeout_ms=timeout_ms)
        return {"ok": True, **result.to_dict(), "policy": "read_only_allowlist"}
    except (QueryRejected, FileNotFoundError) as exc:
        return {"ok": False, "error": str(exc), "policy": "read_only_allowlist"}


def compare_cohorts(
    metric_name: str,
    current_filters: dict[str, Any],
    baseline_filters: dict[str, Any],
    group_by: list[str] | None = None,
) -> dict[str, Any]:
    """Compare two cohorts with deterministic metric code and significance diagnostics."""
    return {
        "ok": True,
        **compare_cohorts_impl(metric_name, current_filters, baseline_filters, group_by=group_by),
    }


def detect_anomalies(
    metric_name: str,
    current_start: str,
    current_end: str,
    baseline_start: str,
    baseline_end: str,
    dimensions: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    min_denominator: int = 20,
    z_threshold: float = 1.96,
) -> dict[str, Any]:
    """Detect statistically supported cohort changes; never infer anomalies from LLM intuition."""
    return {
        "ok": True,
        **detect_anomalies_impl(
            metric_name,
            current_start,
            current_end,
            baseline_start,
            baseline_end,
            dimensions=dimensions,
            filters=filters,
            min_denominator=min_denominator,
            z_threshold=z_threshold,
        ),
    }


def draft_incident_report(
    title: str,
    alert_metric: dict[str, Any],
    overall_comparison: dict[str, Any],
    anomaly_result: dict[str, Any],
    candidates: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Create an auditable report draft whose citations are validated against an evidence ledger."""
    return {
        "ok": True,
        **draft_report(
            title=title,
            alert_metric=alert_metric,
            overall_comparison=overall_comparison,
            anomaly_result=anomaly_result,
            candidates=candidates,
            evidence=evidence,
            limitations=limitations,
        ),
    }


def evidence_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
