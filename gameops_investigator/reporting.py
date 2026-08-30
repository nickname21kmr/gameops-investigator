from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _format_value(value: float | None, unit: str) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%" if unit == "percent" else f"{value:.3f}"


def draft_report(
    *,
    title: str,
    alert_metric: dict[str, Any],
    overall_comparison: dict[str, Any],
    anomaly_result: dict[str, Any],
    candidates: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    limitations = limitations or []
    first = overall_comparison["rows"][0] if overall_comparison.get("rows") else None
    unit = alert_metric.get("unit", "percent")
    report_seed = json.dumps(
        {"title": title, "metric": alert_metric.get("metric_id"), "candidates": candidates, "evidence": evidence},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    report_id = f"IR-{hashlib.sha256(report_seed.encode('utf-8')).hexdigest()[:10].upper()}"
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if first:
        baseline_text = _format_value(first["baseline"]["value"], unit)
        current_text = _format_value(first["current"]["value"], unit)
        delta = first.get("delta")
        delta_text = "N/A" if delta is None else (f"{delta:+.2f} pp" if unit == "percent" else f"{delta:+.3f}")
    else:
        baseline_text = current_text = delta_text = "N/A"

    lines = [
        f"# {title}",
        "",
        f"- Report ID: `{report_id}`",
        f"- Generated at: `{generated_at}`",
        "- Decision status: `human_review_required`",
        "- Dataset: synthetic NewtonMarket demo data; not production player behavior",
        "",
        "## Alert summary",
        "",
        f"`{alert_metric.get('display_name', alert_metric.get('metric_id'))}` changed from **{baseline_text}** to **{current_text}** ({delta_text}).",
        f"The detector used `{anomaly_result.get('method')}` with a z-threshold of `{anomaly_result.get('threshold', {}).get('z_score')}`.",
        "",
        "## Ranked cause candidates",
        "",
    ]
    for index, candidate in enumerate(candidates, start=1):
        refs = ", ".join(f"`{item}`" for item in candidate.get("evidence_refs", [])) or "none"
        lines.extend(
            [
                f"### {index}. {candidate['title']}",
                "",
                f"- Confidence: `{candidate.get('confidence', 'unknown')}`",
                f"- Status: `{candidate.get('status', 'candidate')}`",
                f"- Evidence: {refs}",
                f"- Reasoning: {candidate.get('reasoning', '')}",
                "",
            ]
        )

    lines.extend(["## Evidence ledger", ""])
    for item in evidence:
        lines.append(f"### {item['evidence_id']} — {item['title']}")
        lines.append("")
        if item.get("sql"):
            lines.extend(["```sql", item["sql"], "```", ""])
        lines.append(f"Result digest: `{item.get('digest', 'not recorded')}`")
        lines.append("")

    lines.extend(
        [
            "## Recommended next actions",
            "",
            "1. Have the owning analyst reproduce the top candidate against a clean instrumentation sample.",
            "2. Check release notes, client logs, and tracking delivery records for the affected cohort only.",
            "3. Do not roll back or rebalance solely from this report; use the linked evidence and owner sign-off.",
            "",
            "## Limitations and uncertainty",
            "",
        ]
    )
    default_limitations = [
        "The analysis establishes association and data-quality signals, not causal proof.",
        "This repository uses deterministic synthetic data with deliberately injected incidents.",
        "LLM wording must not override metric definitions, SQL results, or statistical thresholds.",
    ]
    for item in [*default_limitations, *limitations]:
        lines.append(f"- {item}")

    markdown = "\n".join(lines).strip() + "\n"
    cited = {ref for candidate in candidates for ref in candidate.get("evidence_refs", [])}
    available = {item["evidence_id"] for item in evidence}
    return {
        "report_id": report_id,
        "generated_at": generated_at,
        "review_status": "human_review_required",
        "markdown": markdown,
        "citation_check": {
            "valid": cited <= available,
            "cited_evidence_ids": sorted(cited),
            "available_evidence_ids": sorted(available),
            "unknown_references": sorted(cited - available),
        },
    }

