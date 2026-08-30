from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import database_path, metric_catalog


DIMENSIONS = {
    "install_date": "u.install_date",
    "app_version": "u.app_version",
    "channel": "u.channel",
    "strategy_segment": "u.strategy_segment",
}
FILTERS = set(DIMENSIONS) | {"channel_not", "strategy_segment_not", "start_date", "end_date"}


@dataclass(frozen=True)
class MetricValue:
    metric_id: str
    numerator: float
    denominator: float
    value: float | None
    unit: str
    dimensions: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "numerator": round(self.numerator, 6),
            "denominator": round(self.denominator, 6),
            "value": None if self.value is None else round(self.value, 6),
            "unit": self.unit,
            "dimensions": self.dimensions,
        }


def _condition(alias: str, spec: dict[str, Any], params: list[Any]) -> str:
    clauses = [f"{alias}.event_name = ?"]
    params.append(spec["event_name"])
    if "result" in spec:
        clauses.append(f"{alias}.result = ?")
        params.append(spec["result"])
    if "product_type" in spec:
        clauses.append(f"{alias}.product_type = ?")
        params.append(spec["product_type"])
    if "turn_no_gte" in spec:
        clauses.append(f"{alias}.turn_no >= ?")
        params.append(spec["turn_no_gte"])
    return " AND ".join(clauses)


def _filters_sql(filters: dict[str, Any], params: list[Any]) -> str:
    unknown = set(filters) - FILTERS
    if unknown:
        raise ValueError(f"Unsupported filters: {sorted(unknown)}")
    clauses: list[str] = []
    for key in ("install_date", "app_version", "channel", "strategy_segment"):
        if key in filters:
            clauses.append(f"{DIMENSIONS[key]} = ?")
            params.append(filters[key])
    if "channel_not" in filters:
        clauses.append("u.channel <> ?")
        params.append(filters["channel_not"])
    if "strategy_segment_not" in filters:
        clauses.append("u.strategy_segment <> ?")
        params.append(filters["strategy_segment_not"])
    if "start_date" in filters:
        clauses.append("u.install_date >= ?")
        params.append(filters["start_date"])
    if "end_date" in filters:
        clauses.append("u.install_date <= ?")
        params.append(filters["end_date"])
    return " AND ".join(clauses) if clauses else "1 = 1"


class MetricEngine:
    def __init__(self, path: Path | None = None):
        self.path = (path or database_path()).resolve()
        self.catalog = metric_catalog()

    def definition(self, metric_id: str) -> dict[str, Any]:
        if metric_id not in self.catalog:
            raise KeyError(f"Unknown metric: {metric_id}")
        return {"metric_id": metric_id, **self.catalog[metric_id]}

    def list_definitions(self) -> list[dict[str, Any]]:
        return [self.definition(metric_id) for metric_id in self.catalog]

    def compute(
        self,
        metric_id: str,
        *,
        filters: dict[str, Any] | None = None,
        group_by: list[str] | None = None,
    ) -> list[MetricValue]:
        definition = self.definition(metric_id)
        filters = filters or {}
        group_by = group_by or []
        if len(group_by) != len(set(group_by)) or any(item not in DIMENSIONS for item in group_by):
            raise ValueError(f"group_by must use unique supported dimensions: {sorted(DIMENSIONS)}")

        if definition["kind"] == "duplicate_signature_rate":
            return self._compute_duplicate_rate(metric_id, definition, filters, group_by)
        return self._compute_user_metric(metric_id, definition, filters, group_by)

    def _compute_user_metric(
        self,
        metric_id: str,
        definition: dict[str, Any],
        filters: dict[str, Any],
        group_by: list[str],
    ) -> list[MetricValue]:
        filter_params: list[Any] = []
        where = _filters_sql(filters, filter_params)
        dimension_columns = [f"{DIMENSIONS[item]} AS {item}" for item in group_by]
        dimension_select = ", ".join(dimension_columns)
        flag_group = ", ".join(["u.user_id", *[DIMENSIONS[item] for item in group_by]])
        output_group = ", ".join(group_by)
        prefix = f"{dimension_select}, " if dimension_select else ""
        output_prefix = f"{output_group}, " if output_group else ""

        kind = definition["kind"]
        condition_params: list[Any] = []
        if kind == "retention":
            day_offset = int(definition["day_offset"])
            numerator_expression = (
                "MAX(CASE WHEN e.event_name = 'session_start' "
                f"AND CAST(julianday(e.event_date) - julianday(u.install_date) AS INTEGER) = {day_offset} "
                "THEN 1 ELSE 0 END)"
            )
            denominator_expression = "1"
        else:
            numerator_condition = _condition("e", definition["numerator"], condition_params)
            denominator_condition = _condition("e", definition["denominator"], condition_params)
            if kind == "event_count_per_user":
                numerator_expression = f"SUM(CASE WHEN {numerator_condition} THEN 1 ELSE 0 END)"
            else:
                numerator_expression = f"MAX(CASE WHEN {numerator_condition} THEN 1 ELSE 0 END)"
            denominator_expression = f"MAX(CASE WHEN {denominator_condition} THEN 1 ELSE 0 END)"

        sql = f"""
        WITH player_flags AS (
            SELECT {prefix}u.user_id,
                   {numerator_expression} AS numerator_value,
                   {denominator_expression} AS denominator_value
            FROM users u
            LEFT JOIN events e ON e.user_id = u.user_id
            WHERE {where}
            GROUP BY {flag_group}
        )
        SELECT {output_prefix}
               COALESCE(SUM(numerator_value), 0) AS numerator,
               COALESCE(SUM(denominator_value), 0) AS denominator
        FROM player_flags
        {f'GROUP BY {output_group}' if output_group else ''}
        {f'ORDER BY {output_group}' if output_group else ''}
        """
        return self._run_metric_sql(metric_id, definition["unit"], group_by, sql, [*condition_params, *filter_params])

    def _compute_duplicate_rate(
        self,
        metric_id: str,
        definition: dict[str, Any],
        filters: dict[str, Any],
        group_by: list[str],
    ) -> list[MetricValue]:
        params: list[Any] = []
        where = _filters_sql(filters, params)
        dim_exprs = [f"{DIMENSIONS[item]} AS {item}" for item in group_by]
        dims = ", ".join(dim_exprs)
        dim_names = ", ".join(group_by)
        source_dim_names = ", ".join(DIMENSIONS[item] for item in group_by)
        scoped_prefix = f"{dims}, " if dims else ""
        grouped_prefix = f"{dim_names}, " if dim_names else ""
        grouped_clause = f"{source_dim_names}, " if source_dim_names else ""
        sql = f"""
        WITH signatures AS (
            SELECT {scoped_prefix}
                   e.user_id, e.event_name, e.event_time, e.session_id,
                   COALESCE(e.action, '') AS action,
                   COALESCE(e.result, '') AS result,
                   COALESCE(e.product_type, '') AS product_type,
                   COUNT(*) AS copies
            FROM events e
            JOIN users u ON u.user_id = e.user_id
            WHERE {where}
            GROUP BY {grouped_clause}e.user_id, e.event_name, e.event_time, e.session_id,
                     COALESCE(e.action, ''), COALESCE(e.result, ''), COALESCE(e.product_type, '')
        )
        SELECT {grouped_prefix}
               COALESCE(SUM(CASE WHEN copies > 1 THEN copies - 1 ELSE 0 END), 0) AS numerator,
               COALESCE(SUM(copies), 0) AS denominator
        FROM signatures
        {f'GROUP BY {dim_names}' if dim_names else ''}
        {f'ORDER BY {dim_names}' if dim_names else ''}
        """
        return self._run_metric_sql(metric_id, definition["unit"], group_by, sql, params)

    def _run_metric_sql(
        self,
        metric_id: str,
        unit: str,
        group_by: list[str],
        sql: str,
        params: list[Any],
    ) -> list[MetricValue]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(sql, params).fetchall()
        finally:
            connection.close()
        values: list[MetricValue] = []
        for row in rows:
            numerator = float(row["numerator"] or 0)
            denominator = float(row["denominator"] or 0)
            raw_value = None if denominator == 0 else numerator / denominator
            value = raw_value * 100 if raw_value is not None and unit == "percent" else raw_value
            values.append(
                MetricValue(
                    metric_id=metric_id,
                    numerator=numerator,
                    denominator=denominator,
                    value=value,
                    unit=unit,
                    dimensions={item: row[item] for item in group_by},
                )
            )
        return values


def two_proportion_z(current: MetricValue, baseline: MetricValue) -> float | None:
    if current.denominator <= 0 or baseline.denominator <= 0:
        return None
    p1 = current.numerator / current.denominator
    p0 = baseline.numerator / baseline.denominator
    pooled = (current.numerator + baseline.numerator) / (current.denominator + baseline.denominator)
    standard_error = math.sqrt(max(0.0, pooled * (1 - pooled) * (1 / current.denominator + 1 / baseline.denominator)))
    return None if standard_error == 0 else (p1 - p0) / standard_error


def log_rate_z(current: MetricValue, baseline: MetricValue) -> float | None:
    if min(current.numerator, current.denominator, baseline.numerator, baseline.denominator) <= 0:
        return None
    rate_ratio = (current.numerator / current.denominator) / (baseline.numerator / baseline.denominator)
    standard_error = math.sqrt(1 / current.numerator + 1 / baseline.numerator)
    return math.log(rate_ratio) / standard_error if standard_error else None
