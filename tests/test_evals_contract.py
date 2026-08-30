from __future__ import annotations

import json
from pathlib import Path


def test_fixed_eval_suite_has_expected_breadth():
    path = Path(__file__).resolve().parents[1] / "evals" / "cases.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert 30 <= len(cases) <= 50
    assert {case["type"] for case in cases} == {
        "tool_routing",
        "sql_policy",
        "incident_attribution",
        "metric_contract",
        "governance",
    }

