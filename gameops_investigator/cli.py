from __future__ import annotations

import argparse
import json

from .orchestrator import ClaudeCodeRunner, DeterministicInvestigator
from .tools import query_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="GameOps Investigator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    investigate = subparsers.add_parser("investigate", help="Run a reproducible incident investigation")
    investigate.add_argument("scenario", choices=["tutorial_failure", "segment_churn", "duplicate_tracking"])
    sql = subparsers.add_parser("query", help="Run validated read-only SQL")
    sql.add_argument("sql")
    sql.add_argument("--row-limit", type=int, default=200, help="Maximum rows to return (1-500)")
    sql.add_argument("--timeout-ms", type=int, default=2000, help="Query timeout in milliseconds (50-10000)")
    claude = subparsers.add_parser("claude", help="Run an open-ended investigation through Claude Code + MCP")
    claude.add_argument("question")
    args = parser.parse_args()

    if args.command == "investigate":
        result = DeterministicInvestigator().investigate(args.scenario)
    elif args.command == "query":
        result = query_metrics(args.sql, row_limit=args.row_limit, timeout_ms=args.timeout_ms)
    else:
        result = ClaudeCodeRunner().run(args.question)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
