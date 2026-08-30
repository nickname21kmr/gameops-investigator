# Three-minute demo script

## 0:00–0:30 — Positioning

Open the Streamlit home page. Point out the synthetic-data disclosure and the boundary: Claude plans and explains; code calculates.

## 0:30–1:20 — Incident investigation

Select `tutorial_failure`. Show baseline/current D1, the channel anomaly, and the top candidate. Open the generated report and highlight that the wording says “candidate,” not “proven cause.”

## 1:20–1:55 — Evidence and safety

Open `Evidence & SQL`. Show the tool trace and evidence digests. Run a safe grouped query, then try `DELETE FROM events` to demonstrate rejection.

## 1:55–2:25 — Generality

Switch to `segment_churn` to show a significant segment hidden by a low-confidence aggregate. Switch to `duplicate_tracking` to contrast event intensity with player-level adoption and duplicate signatures.

## 2:25–3:00 — Evaluation and Claude Code

Open `Evaluation` and show the 40 fixed cases, measured p95, Top-3 hit rate, and citation accuracy. End on `.mcp.json` and `CLAUDE.md`: an authenticated Claude Code session uses exactly the same five read-only tools.

