# 埋点重复上报导致高级系统参与强度虚高

- Report ID: `IR-EACDFC1B30`
- Generated at: `2026-09-20T14:44:04+00:00`
- Decision status: `human_review_required`
- Investigation status: `supported`
- Investigation outcome: 焦点异常与必需证据满足固定排查规则；候选仍需人工复核，不代表因果证明。
- Dataset: synthetic NewtonMarket demo data; not production player behavior

## Alert summary

`人均高级系统打开事件数` changed from **1.330** to **2.112** (+0.782).
The detector used `log_rate_ratio_z` with a z-threshold of `1.96`.

## Ranked cause candidates

### 1. 重复埋点上报放大事件级参与强度

- Confidence: `high`
- Status: `supported_candidate`
- Evidence: `E03`, `E05`, `E04`, `E06`
- Reasoning: 重复签名率变化为 6.245614; 玩家级采用率变化为 1.976035。事件强度与重复率显著上升，未检出玩家采用率显著上升；未检出不等于证明采用率不变，仍需人工核对埋点。

### 2. 玩家真实提高了高级系统使用频次

- Confidence: `low`
- Status: `not_supported_yet`
- Evidence: `E04`
- Reasoning: 需要玩家级采用率、会话深度或游戏内状态同步上升；当前证据不足。

### 3. 渠道结构变化造成聚合指标偏移

- Confidence: `low`
- Status: `alternative`
- Evidence: `E03`
- Reasoning: 渠道下钻已定位异常，但仍需校验总体用户构成变化。

## Evidence ledger

### E01 — get_metric_definition

Result digest: `fcf26eeb5ab29fc4`

### E02 — compare_cohorts

Result digest: `43dd4b4168a051d8`

### E03 — detect_anomalies

Result digest: `e4bb3064642c1e38`

### E04 — compare_cohorts

Result digest: `018ee833a4517ec7`

### E05 — compare_cohorts

Result digest: `830e34cdc2ebe927`

### E06 — query_metrics

```sql
SELECT u.install_date, u.channel, e.user_id, e.event_time, e.session_id, e.product_type, COUNT(*) AS copies FROM events e JOIN users u ON u.user_id = e.user_id WHERE e.event_name = 'system_opened' AND u.app_version = '0.9.2' AND u.install_date BETWEEN '2026-08-04' AND '2026-08-10' GROUP BY u.install_date, u.channel, e.user_id, e.event_time, e.session_id, e.product_type HAVING COUNT(*) > 1 ORDER BY copies DESC LIMIT 50
```

Result digest: `6fcca047ca99384a`

## Recommended next actions

1. Have the owning analyst reproduce the top candidate against a clean instrumentation sample.
2. Check release notes, client logs, and tracking delivery records for the affected cohort only.
3. Do not roll back or rebalance solely from this report; use the linked evidence and owner sign-off.

## Limitations and uncertainty

- The analysis establishes association and data-quality signals, not causal proof.
- This repository uses deterministic synthetic data with deliberately injected incidents.
- LLM wording must not override metric definitions, SQL results, or statistical thresholds.
- The deterministic coordinator follows a fixed investigation playbook; open-ended planning is delegated to Claude Code.
