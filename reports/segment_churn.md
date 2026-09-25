# 新版本局部玩家分群流失，被整体平均值掩盖

- Report ID: `IR-2B39214944`
- Generated at: `2026-09-20T14:44:04+00:00`
- Decision status: `human_review_required`
- Investigation status: `supported`
- Investigation outcome: 焦点异常与必需证据满足固定排查规则；候选仍需人工复核，不代表因果证明。
- Dataset: synthetic NewtonMarket demo data; not production player behavior

## Alert summary

`D1 留存率` changed from **34.38%** to **28.73%** (-5.65 pp).
The detector used `two_proportion_z` with a z-threshold of `1.96`.

## Ranked cause candidates

### 1. leveraged 分群发生局部留存退化

- Confidence: `high`
- Status: `supported_candidate`
- Evidence: `E03`, `E06`
- Reasoning: 该分群当前窗口相对基线变化 -21.820175，且达到样本量与统计门槛；这定位了退化分群，尚未证明业务根因。

### 2. 版本级普遍留存退化

- Confidence: `low`
- Status: `alternative`
- Evidence: `E02`, `E03`
- Reasoning: 需结合整体与各分群比较，判断是否同时存在版本级普遍退化；局部分群异常不能单独排除该解释。

### 3. 小样本或随机 cohort 波动

- Confidence: `low`
- Status: `alternative`
- Evidence: `E03`
- Reasoning: 统计程序已执行最小样本门槛与 z 检验，但仍需更多日期复核稳定性。

## Evidence ledger

### E01 — get_metric_definition

Result digest: `153260e503bc18f1`

### E02 — compare_cohorts

Result digest: `e36366410829d564`

### E03 — detect_anomalies

Result digest: `ca5763dc023e1679`

### E04 — compare_cohorts

Result digest: `764b882977049fe0`

### E05 — compare_cohorts

Result digest: `67ac065b9cf6f3f1`

### E06 — query_metrics

```sql
SELECT u.install_date, u.strategy_segment, COUNT(DISTINCT u.user_id) AS cohort_users, COUNT(DISTINCT CASE WHEN e.event_name = 'session_start' AND julianday(e.event_date) - julianday(u.install_date) = 1 THEN u.user_id END) AS d1_users FROM users u LEFT JOIN events e ON e.user_id = u.user_id WHERE u.app_version = '0.9.3' AND u.channel <> 'campus_demo' AND u.install_date BETWEEN '2026-08-01' AND '2026-08-14' GROUP BY u.install_date, u.strategy_segment ORDER BY u.install_date, u.strategy_segment LIMIT 100
```

Result digest: `9b3bfb6c20b8ca43`

## Recommended next actions

1. Have the owning analyst reproduce the top candidate against a clean instrumentation sample.
2. Check release notes, client logs, and tracking delivery records for the affected cohort only.
3. Do not roll back or rebalance solely from this report; use the linked evidence and owner sign-off.

## Limitations and uncertainty

- The analysis establishes association and data-quality signals, not causal proof.
- This repository uses deterministic synthetic data with deliberately injected incidents.
- LLM wording must not override metric definitions, SQL results, or statistical thresholds.
- The deterministic coordinator follows a fixed investigation playbook; open-ended planning is delegated to Claude Code.
