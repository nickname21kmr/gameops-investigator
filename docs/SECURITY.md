# Safety and governance

## Query controls

- A query must begin with `SELECT` or `WITH`.
- Semicolons, SQL comments, mutations, DDL, `PRAGMA`, attach/detach, and extension loading in executable SQL are rejected. Quoted text and identifiers are excluded from keyword scanning.
- SQLite is opened with `mode=ro` and `PRAGMA query_only=ON`.
- A SQLite authorizer restricts reads to `users`, `events`, `dataset_manifest`, and `incident_catalog`.
- The maximum returned row count is 500; the default is 200. The executor fetches at most `row_limit + 1` result rows and returns only the first `row_limit`; the extra row determines `truncated` and is never returned. SQL text, including every `LIMIT` and `OFFSET`, is left unchanged.
- The maximum timeout is 10 seconds; the default is 2 seconds.
- A progress handler interrupts queries that exceed the deadline.

The hidden `incident_ground_truth` table is deliberately unavailable through MCP. Evaluation knows expected answers, but the investigator must recover them from public evidence.

## Query semantics and result limits

A response limit must not change which records participate in an analysis. For example:

```sql
SELECT COUNT(*) AS sampled_users
FROM (SELECT user_id FROM users ORDER BY user_id LIMIT 100)
```

With `row_limit=5`, this returns one row with `sampled_users=100` on the demo dataset and `truncated=false`. The inner `LIMIT 100` defines the sample and is not reduced to the response limit. The same rule applies to CTEs, aggregates, limit expressions, and bound parameters in the Python executor.

`truncated=true` means the original query produced more than the allowed number of result rows. Empty results, exactly-full results, and explicit SQL limits at or below the response limit are not marked truncated. `executed_sql` is the validated input with only leading/trailing whitespace removed. `validate_readonly_sql` validates the policy and row-limit range; it does not add a SQL limit. Call `execute_readonly` (or `query_metrics`) to enforce the response cap.

This uses the bounded cursor-fetch approach found in [Datasette's query executor](https://github.com/simonw/datasette/blob/main/datasette/database.py), while keeping this project's table allowlist and read-only policy. Cursors and connections are closed after fetching or on error. The response cap does not bound the number of rows SQLite scans or its working memory: sorting and aggregation may process additional rows, and the progress-handler timeout remains the execution-time control.

## Operational controls

- Reports are always `human_review_required`.
- The agent cannot write to the analytics database.
- No tool can roll back a version, message a player, edit an economy, or deploy code.
- Evidence IDs are SHA-256 digests of tool outputs; the report validator rejects unknown references.
- Synthetic-data disclosure and causal uncertainty are tested behaviors.

## Evaluation exports

`evals/run_evals.py` builds an allowlisted summary for `claude_code` before returning, printing, or saving the evaluation report. It retains boolean installation/login status and whether the authentication check reported an error. Executable paths, authentication diagnostics, provider details, and unknown runtime fields are omitted. Runtime discovery itself is unchanged.

The optional `--claude` run exports only a typed outcome, finite non-negative elapsed time, an integer exit code when available, and `output_omitted: true`. Raw model payloads and subprocess errors are not included. This outcome is not a scored model evaluation: the deterministic metrics and `claude_agent_metrics: null` remain separate. The default run does not invoke the model, although it checks local CLI availability and authentication status.

SQL-policy cases record `error: null` on success or `query_rejected_or_unavailable` on failure, rather than copying tool error text into the artifact. Re-run the corresponding tool locally for detailed diagnostics. These export rules apply to runtime diagnostics, not arbitrary custom case definitions or other project reports; review those separately before publishing.

## Production hardening checklist

Before a real deployment, add identity-aware warehouse credentials, row/column-level access, query cost estimation, central audit logs, PII masking, rate limits, result-cache policy, incident-owner routing, and an approval workflow separate from the LLM.
