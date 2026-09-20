from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from gameops_investigator.config import scenario_catalog  # noqa: E402
from gameops_investigator.orchestrator import DeterministicInvestigator  # noqa: E402


REPORTS = PROJECT_ROOT / "reports"


def generate() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    summary = {}
    for scenario_id in scenario_catalog():
        result = DeterministicInvestigator().investigate(scenario_id)
        markdown_path = REPORTS / f"{scenario_id}.md"
        trace_path = REPORTS / f"{scenario_id}.trace.json"
        markdown_path.write_text(result["report"]["markdown"], encoding="utf-8")
        trace_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        summary[scenario_id] = {
            "report": str(markdown_path.relative_to(PROJECT_ROOT)),
            "trace": str(trace_path.relative_to(PROJECT_ROOT)),
            "top_candidate": result["candidates"][0]["id"] if result["candidates"] else None,
            "investigation_status": result["investigation_status"],
            "investigation_reason": result["investigation_reason"],
            "ok": result["ok"],
            "elapsed_ms": result["elapsed_ms"],
            "citation_valid": result["report"].get("citation_check", {}).get("valid", False),
        }
    (REPORTS / "index.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
