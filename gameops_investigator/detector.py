from __future__ import annotations

import math
from typing import Any

from .metrics import MetricEngine, MetricValue, log_rate_z, two_proportion_z


def _key(value: MetricValue, group_by: list[str]) -> tuple[Any, ...]:
    return tuple(value.dimensions.get(item) for item in group_by)


def _confidence(z_score: float | None, current_n: float, baseline_n: float) -> str:
    if min(current_n, baseline_n) < 20:
        return "low_sample"
    if z_score is None:
        return "insufficient"
    magnitude = abs(z_score)
    if magnitude >= 3.29:
        return "high"
    if magnitude >= 1.96:
        return "medium"
    return "low"


def compare_cohorts(
    metric_id: str,
    current_filters: dict[str, Any],
    baseline_filters: dict[str, Any],
    *,
    group_by: list[str] | None = None,
    engine: MetricEngine | None = None,
) -> dict[str, Any]:
    group_by = group_by or []
    engine = engine or MetricEngine()
    definition = engine.definition(metric_id)
    current = engine.compute(metric_id, filters=current_filters, group_by=group_by)
    baseline = engine.compute(metric_id, filters=baseline_filters, group_by=group_by)
    current_map = {_key(item, group_by): item for item in current}
    baseline_map = {_key(item, group_by): item for item in baseline}
    rows: list[dict[str, Any]] = []

    for key in sorted(set(current_map) | set(baseline_map), key=lambda item: str(item)):
        current_value = current_map.get(key, MetricValue(metric_id, 0, 0, None, definition["unit"], dict(zip(group_by, key))))
        baseline_value = baseline_map.get(key, MetricValue(metric_id, 0, 0, None, definition["unit"], dict(zip(group_by, key))))
        if definition["unit"] == "percent":
            z_score = two_proportion_z(current_value, baseline_value)
        else:
            z_score = log_rate_z(current_value, baseline_value)
        delta = None
        relative_delta_pct = None
        if current_value.value is not None and baseline_value.value is not None:
            delta = current_value.value - baseline_value.value
            if baseline_value.value != 0:
                relative_delta_pct = delta / abs(baseline_value.value) * 100
        rows.append(
            {
                "dimensions": dict(zip(group_by, key)),
                "current": current_value.to_dict(),
                "baseline": baseline_value.to_dict(),
                "delta": None if delta is None else round(delta, 6),
                "relative_delta_pct": None if relative_delta_pct is None else round(relative_delta_pct, 6),
                "z_score": None if z_score is None or not math.isfinite(z_score) else round(z_score, 6),
                "confidence": _confidence(z_score, current_value.denominator, baseline_value.denominator),
            }
        )

    return {
        "metric": definition,
        "group_by": group_by,
        "current_filters": current_filters,
        "baseline_filters": baseline_filters,
        "comparison_method": "two_proportion_z" if definition["unit"] == "percent" else "log_rate_ratio_z",
        "rows": rows,
    }


def detect_anomalies(
    metric_id: str,
    current_start: str,
    current_end: str,
    baseline_start: str,
    baseline_end: str,
    *,
    dimensions: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    min_denominator: int = 20,
    z_threshold: float = 1.96,
    engine: MetricEngine | None = None,
) -> dict[str, Any]:
    dimensions = dimensions or []
    shared = dict(filters or {})
    current_filters = {**shared, "start_date": current_start, "end_date": current_end}
    baseline_filters = {**shared, "start_date": baseline_start, "end_date": baseline_end}
    comparison = compare_cohorts(
        metric_id,
        current_filters,
        baseline_filters,
        group_by=dimensions,
        engine=engine,
    )
    anomalies = []
    for row in comparison["rows"]:
        denominator = min(row["current"]["denominator"], row["baseline"]["denominator"])
        z_score = row["z_score"]
        if denominator >= min_denominator and z_score is not None and abs(z_score) >= z_threshold:
            direction = "increase" if (row["delta"] or 0) > 0 else "decrease"
            anomalies.append({**row, "direction": direction, "severity_score": round(abs(z_score), 3)})
    anomalies.sort(key=lambda item: item["severity_score"], reverse=True)
    return {
        "method": comparison["comparison_method"],
        "threshold": {"z_score": z_threshold, "min_denominator": min_denominator},
        "metric": comparison["metric"],
        "windows": {
            "baseline": [baseline_start, baseline_end],
            "current": [current_start, current_end],
        },
        "dimensions": dimensions,
        "filters": shared,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "all_comparisons": comparison["rows"],
        "interpretation_boundary": "Statistical association is not causal proof; small cohorts are explicitly downgraded.",
    }

