# Safety and governance

## Query controls

- A query must begin with `SELECT` or `WITH`.
- Semicolons, SQL comments, mutations, DDL, `PRAGMA`, attach/detach, and extension loading in executable SQL are rejected. Quoted text and identifiers are excluded from keyword scanning.
- SQLite is opened with `mode=ro` and `PRAGMA query_only=ON`.
- A SQLite authorizer restricts reads to `users`, `events`, `dataset_manifest`, and `incident_catalog`.
- The maximum row limit is 500; the default is 200. Both SQLite `LIMIT count OFFSET offset` and `LIMIT offset, count` forms are capped.
- The maximum timeout is 10 seconds; the default is 2 seconds.
- A progress handler interrupts queries that exceed the deadline.

The hidden `incident_ground_truth` table is deliberately unavailable through MCP. Evaluation knows expected answers, but the investigator must recover them from public evidence.

## Operational controls

- Reports are always `human_review_required`.
- The agent cannot write to the analytics database.
- No tool can roll back a version, message a player, edit an economy, or deploy code.
- Evidence IDs are SHA-256 digests of tool outputs; the report validator rejects unknown references.
- Synthetic-data disclosure and causal uncertainty are tested behaviors.

## Production hardening checklist

Before a real deployment, add identity-aware warehouse credentials, row/column-level access, query cost estimation, central audit logs, PII masking, rate limits, result-cache policy, incident-owner routing, and an approval workflow separate from the LLM.
