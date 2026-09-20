# 教程关键步失败率升高，D1 留存同步下降

- Report ID: `IR-2989C12F29`
- Generated at: `2026-09-20T14:44:03+00:00`
- Decision status: `human_review_required`
- Investigation status: `supported`
- Investigation outcome: 焦点异常与必需证据满足固定排查规则；候选仍需人工复核，不代表因果证明。
- Dataset: synthetic NewtonMarket demo data; not production player behavior

## Alert summary

`D1 留存率` changed from **36.57%** to **22.94%** (-13.64 pp).
The detector used `two_proportion_z` with a z-threshold of `1.96`.

## Ranked cause candidates

### 1. 教程关键步完成下降是 D1 留存下滑的首要上游候选

- Confidence: `high`
- Status: `supported_candidate`
- Evidence: `E03`, `E04`, `E07`
- Reasoning: campus_demo 的教程完成率变化为 -62.345117，并与同 cohort 的留存方向一致；这仍是关联证据而非因果证明。

### 2. 交易环节或后续回合体验退化

- Confidence: `low`
- Status: `secondary`
- Evidence: `E05`, `E06`
- Reasoning: 下游指标受上游样本选择影响，必须先处理教程漏斗变化。

### 3. 渠道用户结构变化

- Confidence: `low`
- Status: `alternative`
- Evidence: `E03`
- Reasoning: 需要额外的渠道获客与设备属性才能进一步确认。

## Evidence ledger

### E01 — get_metric_definition

Result digest: `153260e503bc18f1`

### E02 — compare_cohorts

Result digest: `ac74434f5c17dbc0`

### E03 — detect_anomalies

Result digest: `15fbbef982a3bbbe`

### E04 — compare_cohorts

Result digest: `b0e42cf4a5555d6a`

### E05 — compare_cohorts

Result digest: `99e02538c4940307`

### E06 — compare_cohorts

Result digest: `4fd5735f01c40174`

### E07 — query_metrics

```sql
SELECT u.install_date, u.channel, COUNT(DISTINCT u.user_id) AS installs, COUNT(DISTINCT CASE WHEN e.event_name = 'opening_item_selected' THEN u.user_id END) AS tutorial_completed FROM users u LEFT JOIN events e ON e.user_id = u.user_id WHERE u.app_version = '0.9.3' AND u.install_date BETWEEN '2026-08-07' AND '2026-08-14' GROUP BY u.install_date, u.channel ORDER BY u.install_date, u.channel LIMIT 100
```

Result digest: `c84f373736a9649e`

## Recommended next actions

1. Have the owning analyst reproduce the top candidate against a clean instrumentation sample.
2. Check release notes, client logs, and tracking delivery records for the affected cohort only.
3. Do not roll back or rebalance solely from this report; use the linked evidence and owner sign-off.

## Limitations and uncertainty

- The analysis establishes association and data-quality signals, not causal proof.
- This repository uses deterministic synthetic data with deliberately injected incidents.
- LLM wording must not override metric definitions, SQL results, or statistical thresholds.
- The deterministic coordinator follows a fixed investigation playbook; open-ended planning is delegated to Claude Code.
