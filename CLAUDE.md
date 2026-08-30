# GameOps Investigator — Claude Code operating contract

## Mission

Investigate game-operations metric alerts with an auditable chain:

`alert -> plan -> metric contract -> deterministic tools -> evidence SQL -> ranked candidates -> human-review report`

Claude is the planning and interpretation layer. It must never replace metric code, SQL execution, anomaly calculation, or citation validation with intuition.

## Required investigation order

1. Call `get_metric_definition` before interpreting a metric.
2. Call `detect_anomalies` to establish whether a change crosses the configured statistical threshold.
3. Use `compare_cohorts` for version, channel, activity, or player-segment contribution analysis.
4. Use `query_metrics` only for evidence that is not already returned by a deterministic tool.
5. Rank no more than three cause candidates. Distinguish `supported_candidate`, `alternative`, and `not_supported_yet`.
6. Call `draft_incident_report` with evidence IDs, SQL, confidence, and limitations.

## Data and safety boundaries

- The bundled NewtonMarket dataset is synthetic: 5,000 players and an immutable 136,164-event source snapshot.
- Three incidents are injected only into `data/gameops_demo.db` by `scripts/bootstrap_demo.py`.
- Do not query database files directly. Use the `gameops` MCP server.
- `query_metrics` permits one `SELECT` or `WITH` statement, public tables only, up to 500 rows and 10 seconds.
- The hidden ground-truth table exists only for evaluation and is blocked by the MCP query authorizer.
- Association is not causation. A report can recommend checks; it cannot autonomously roll back a release, compensate users, or rebalance the game.
- Never describe this synthetic dataset as commercial or live production data.

## Repository map

- `gameops_investigator/`: metric engine, query guard, detector, MCP tools, coordinator, reporting.
- `config/metrics.json`: metric formulas and ownership.
- `config/schema_contract.json`: portable warehouse adapter contract.
- `config/scenarios.json`: public alert windows and investigation playbooks; no injected answer is exposed here at runtime.
- `prompts/`: production-style prompt templates.
- `evals/`: 40 fixed cases and the scoring harness.
- `reports/`: three reproducible reports plus complete tool traces.
- `data/source/`: immutable source snapshot.
- `data/gameops_demo.db`: generated demo database; safe to rebuild.
- `docs/architecture.png`: review-ready architecture diagram.

## Commands

```powershell
.\setup.ps1
.\run.ps1

.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe evals\run_evals.py
.\.venv\Scripts\python.exe scripts\generate_reports.py
.\.venv\Scripts\python.exe -m gameops_investigator.cli investigate tutorial_failure
```

For an authenticated Claude Code session:

```powershell
.\claude-local.ps1 mcp list
.\claude-local.ps1 -p "Investigate the tutorial failure alert and return a cited report." `
  --mcp-config .mcp.json `
  --allowedTools "mcp__gameops__get_metric_definition,mcp__gameops__query_metrics,mcp__gameops__compare_cohorts,mcp__gameops__detect_anomalies,mcp__gameops__draft_incident_report"
```

## Definition of done

- Source snapshot count and checksum preserved.
- All tests pass.
- 40 fixed evals run with actual outputs saved under `artifacts/`.
- Each incident's expected cause appears in Top-3 and every cited evidence ID exists.
- Streamlit health endpoint responds.
- Claude-specific latency and cost remain `N/A` until measured from an authenticated run; never invent them.
