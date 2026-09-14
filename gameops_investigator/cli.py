from __future__ import annotations

import argparse
import json

from .orchestrator import ClaudeCodeRunner, DeterministicInvestigator
from .tools import query_metrics
from .trace_audit import audit_trace, audit_trace_file


def main() -> int:
    parser = argparse.ArgumentParser(description="GameOps Investigator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    investigate = subparsers.add_parser("investigate", help="Run a reproducible incident investigation")
    investigate.add_argument("scenario", choices=["tutorial_failure", "segment_churn", "duplicate_tracking"])
    investigate.add_argument("--audit", action="store_true", help="Audit this run's tool trajectory before returning its status")
    investigate.add_argument("--max-tool-calls", type=int, default=None, help="Post-run audit budget (1-10000, default 20; requires --audit)")
    sql = subparsers.add_parser("query", help="Run validated read-only SQL")
    sql.add_argument("sql")
    sql.add_argument("--row-limit", type=int, default=200, help="Maximum rows to return (1-500)")
    sql.add_argument("--timeout-ms", type=int, default=2000, help="Query timeout in milliseconds (50-10000)")
    claude = subparsers.add_parser("claude", help="Run an open-ended investigation through Claude Code + MCP")
    claude.add_argument("question")
    audit = subparsers.add_parser("audit-trace", help="Check a recorded investigation without running tools or a model")
    audit.add_argument("path", help="UTF-8 JSON trace file (up to 2 MiB)")
    audit.add_argument("--max-tool-calls", type=int, default=20, help="Allowed recorded calls (1-10000; default 20)")
    args = parser.parse_args()

    if args.command == "investigate":
        if args.max_tool_calls is not None and not args.audit:
            parser.error("investigate --max-tool-calls requires --audit")
        budget = 20 if args.max_tool_calls is None else args.max_tool_calls
        if not 1 <= budget <= 10000:
            parser.error("investigate --max-tool-calls must be between 1 and 10000")
        result = DeterministicInvestigator().investigate(args.scenario)
        if args.audit:
            audit_result = audit_trace(result, max_tool_calls=budget)
            result = {
                **result,
                "trajectory_audit": audit_result,
                "ok": audit_result["ok"] is True and result.get("ok") is not False,
            }
    elif args.command == "query":
        result = query_metrics(args.sql, row_limit=args.row_limit, timeout_ms=args.timeout_ms)
    elif args.command == "audit-trace":
        result = audit_trace_file(args.path, max_tool_calls=args.max_tool_calls)
    else:
        result = ClaudeCodeRunner().run(args.question)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("ok") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
