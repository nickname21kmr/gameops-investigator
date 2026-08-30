from __future__ import annotations

from typing import Any

try:
    from mcp.server import MCPServer
except ImportError:  # MCP Python SDK 1.x compatibility
    from mcp.server.fastmcp import FastMCP as MCPServer

from .tools import (
    compare_cohorts as compare_cohorts_impl,
    detect_anomalies as detect_anomalies_impl,
    draft_incident_report as draft_incident_report_impl,
    get_metric_definition as get_metric_definition_impl,
    query_metrics as query_metrics_impl,
)


mcp = MCPServer(
    "GameOps Investigator",
    instructions=(
        "Read-only game operations analytics. Read metric definitions before querying. "
        "Use deterministic anomaly and cohort tools for calculations. Treat all results as synthetic demo evidence."
    ),
)


@mcp.tool()
def get_metric_definition(metric_name: str | None = None) -> dict[str, Any]:
    """Read metric formulas, ownership, event sources, and data-quality notes."""
    return get_metric_definition_impl(metric_name)


@mcp.tool()
def query_metrics(sql: str, row_limit: int = 200, timeout_ms: int = 2000) -> dict[str, Any]:
    """Run one validated SELECT/CTE query against allowlisted public analytics tables."""
    return query_metrics_impl(sql, row_limit, timeout_ms)


@mcp.tool()
def compare_cohorts(
    metric_name: str,
    current_filters: dict[str, Any],
    baseline_filters: dict[str, Any],
    group_by: list[str] | None = None,
) -> dict[str, Any]:
    """Compare current and baseline cohorts with deterministic metric code and significance."""
    return compare_cohorts_impl(metric_name, current_filters, baseline_filters, group_by)


@mcp.tool()
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
    """Detect statistically supported changes; the LLM is not allowed to invent anomaly scores."""
    return detect_anomalies_impl(
        metric_name,
        current_start,
        current_end,
        baseline_start,
        baseline_end,
        dimensions,
        filters,
        min_denominator,
        z_threshold,
    )


@mcp.tool()
def draft_incident_report(
    title: str,
    alert_metric: dict[str, Any],
    overall_comparison: dict[str, Any],
    anomaly_result: dict[str, Any],
    candidates: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Draft a human-review report and validate that every evidence reference exists."""
    return draft_incident_report_impl(
        title,
        alert_metric,
        overall_comparison,
        anomaly_result,
        candidates,
        evidence,
        limitations,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
