# Offline agent trajectory audit

Use `audit-trace` to check a recorded GameOps investigation before reviewing its report:

```powershell
.\.venv\Scripts\python.exe -m gameops_investigator.cli audit-trace reports/tutorial_failure.trace.json
```

No model credentials are needed. The auditor only reads JSON: it never runs SQL, executes a tool, or replays a prompt found in the file. It prints a summary with stable violation codes and one-based step numbers. It does not print tool arguments, report text, raw errors, or the input path. CLI exit codes are `0` for pass, `1` for an audit/input failure, and `2` for invalid command-line syntax.

## Audit a fresh investigation

Run the deterministic investigation once and immediately audit the result in memory:

```powershell
.\.venv\Scripts\python.exe -m gameops_investigator.cli investigate tutorial_failure --audit
```

Unlike `audit-trace`, this command executes the synthetic-data investigation's read-only tools. It does not call Claude, read an old trace, or write report files. It preserves the complete investigation JSON, including SQL arguments and report text, and adds `trajectory_audit` and top-level `ok`. The summary-only privacy behavior of `audit-trace` does **not** apply to the complete investigation output; review it before publishing.

An audit violation, or an explicitly failed investigation, produces `ok: false` and exit code `1`. A passing audit does not erase an existing investigation failure. Investigation exceptions still follow the existing behavior; this option does not add exception recovery. The report remains available for diagnosis and human review, even when the audit fails.

`--max-tool-calls` requires `--audit` for this command and defaults to `20`. Out-of-range budgets (outside `1–10000`) and incompatible flags are rejected with exit code `2` **before** running an investigation. The threshold is checked after the run; it does not interrupt tools or limit their runtime. Omitting `--audit` preserves the original output and exit behavior. Standalone `audit-trace` keeps its existing input-error exit codes.

## Input and rules

Input is either a list of calls or an investigation object containing that list under `trace`. Each call needs `tool` (string), `arguments` (object), and `ok` (boolean). Other fields are ignored. Files must be UTF-8 JSON, optionally with a BOM, and at most 2 MiB.

This is a **complete successful investigation** policy, not a universal policy for all agents:

- Only the five GameOps tools are allowed.
- A successful `get_metric_definition` must precede every analysis call.
- Successful `compare_cohorts`, `detect_anomalies`, and `query_metrics` must precede the report, alongside the definition lookup. Analysis calls may repeat or appear in different orders.
- `draft_incident_report` must be last. Each of the five required tools must succeed at least once.
- Every failed call is flagged, even if a later retry succeeds. This policy deliberately rejects traces containing recoverable failures as well as unrecovered ones.
- The default budget is 20 recorded calls, configurable with `--max-tool-calls`. This is a post-run check, not a runtime limit, and is distinct from Claude's turn limit.

Violations include `invalid_trace`, `invalid_step`, `unknown_tool`, `tool_call_failed`, `definition_required`, `report_prerequisites_missing`, `report_not_last`, `tool_budget_exceeded`, and `missing_<required_tool>`. A `step` of `null` means a file-level or whole-trajectory issue. Invalid budgets return `invalid_budget`; unreadable, oversized, or malformed files return `trace_file_unreadable`, `trace_file_too_large`, or `invalid_json`.

## What a pass does not prove

The audit trusts recorded tool names and `ok` flags. It does **not** authenticate a trace, inspect SQL policy, validate metric arguments, link evidence to claims, detect prompt injection, grade the answer, or prove causal reasoning. A fabricated well-formed trace could pass. Runtime read-only controls and analyst review remain necessary.

The committed examples come from the deterministic replay coordinator. The current Claude runner returns its final payload, not this normalized tool-call log; this command does not automatically capture or convert live Claude/MCP traffic. Normalize and independently verify an actual tool-call log before auditing it. Synthetic replay checks are not model-quality measurements.

## Design references

[LangChain AgentEvals](https://github.com/langchain-ai/agentevals) provides deterministic matching and model-based evaluators for agent trajectories. [Anthropic's agent evaluation guide](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) discusses examining agent transcripts alongside outcomes. These informed the decision to check intermediate steps here. This module is an independent, standard-library implementation of GameOps-specific workflow rules; it does not copy code, depend on either framework, or implement AgentEvals compatibility.
