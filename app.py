from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gameops_investigator.config import PROJECT_ROOT, metric_catalog, scenario_catalog
from gameops_investigator.orchestrator import ClaudeCodeRunner, DeterministicInvestigator
from gameops_investigator.tools import query_metrics


st.set_page_config(page_title="GameOps Investigator", page_icon="🔎", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: radial-gradient(circle at 8% 0%, #102b3a 0, #07111f 34%, #050b14 100%); }
    [data-testid="stSidebar"] { background: #081421; border-right: 1px solid rgba(148,163,184,.16); }
    .hero { padding: 1.2rem 0 .7rem; }
    .eyebrow { color:#5eead4; font-size:.75rem; letter-spacing:.18em; text-transform:uppercase; font-weight:700; }
    .hero h1 { margin:.18rem 0 .35rem; font-size:2.35rem; letter-spacing:-.04em; }
    .hero p { color:#9fb0c6; max-width:850px; margin:0; }
    .notice { border-left:3px solid #2dd4bf; padding:.75rem 1rem; background:rgba(13,148,136,.09); color:#b8c8d9; margin:.4rem 0 1rem; }
    .candidate { padding:1rem 1.05rem; border:1px solid rgba(148,163,184,.16); background:rgba(14,27,43,.72); border-radius:12px; margin:.55rem 0; }
    .candidate strong { color:#ecfeff; }
    .candidate small { color:#7dd3fc; }
    div[data-testid="stMetric"] { background:rgba(14,27,43,.72); border:1px solid rgba(148,163,184,.14); padding:.8rem 1rem; border-radius:12px; }
    .toolstep { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; color:#a7f3d0; }
    code { color:#7dd3fc !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


SCENARIOS = scenario_catalog()


@st.cache_data(show_spinner=False)
def run_replay(scenario_id: str) -> dict[str, Any]:
    return DeterministicInvestigator().investigate(scenario_id)


@st.cache_data(show_spinner=False)
def eval_results() -> dict[str, Any] | None:
    path = PROJECT_ROOT / "artifacts" / "eval_results.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def metric_text(value: float | None, unit: str) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%" if unit == "percent" else f"{value:.3f}"


with st.sidebar:
    st.markdown("### Investigation control")
    scenario_id = st.selectbox(
        "Reproducible incident",
        options=list(SCENARIOS),
        format_func=lambda item: SCENARIOS[item]["title"],
    )
    mode = st.radio("Coordinator", ["Deterministic replay", "Claude Code + MCP"], horizontal=False)
    st.caption("确定性回放用于无密钥演示与评测；Claude Code 用于开放式规划和解释。两者调用同一组只读工具。")
    availability = ClaudeCodeRunner.availability()
    if availability["installed"] and availability.get("logged_in"):
        st.success(f"Claude Code ready · {availability.get('auth_method')}")
    elif availability["installed"]:
        st.warning("Claude Code installed · interactive sign-in pending")
    else:
        st.warning("Claude Code CLI not detected; replay remains fully functional")
    run_button = st.button("Run investigation", type="primary", width="stretch")
    st.divider()
    st.caption("DATA BOUNDARY")
    st.markdown("**5,000 synthetic players**  \n**136,164 source events**  \n3 deterministic incident injections")


st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Evidence-first operations analytics</div>
      <h1>GameOps Investigator</h1>
      <p>Claude 负责计划、工具选择与解释；指标口径、SQL、分群比较、异常检验和引用校验由确定性程序负责。</p>
    </div>
    <div class="notice"><strong>Synthetic demo.</strong> 所有玩家和行为均为固定种子生成；三个事故由脚本注入，仅用于展示方法、工具边界和评测，不代表商业游戏结果。</div>
    """,
    unsafe_allow_html=True,
)

if mode == "Claude Code + MCP":
    question = st.text_area(
        "Open-ended investigation question",
        value=f"Investigate {SCENARIOS[scenario_id]['title']}. Use metric definitions first and return a cited, uncertainty-aware report.",
        height=90,
    )
    if run_button:
        with st.spinner("Claude Code is planning and calling read-only MCP tools…"):
            claude_result = ClaudeCodeRunner().run(question)
        if claude_result["ok"]:
            st.success(f"Claude Code completed in {claude_result['elapsed_ms']:.0f} ms")
            st.json(claude_result["payload"], expanded=True)
        else:
            st.error(claude_result["error"])
            st.info("完成一次交互式 `claude` 登录后即可使用；下方仍展示同工具链的确定性回放。")

result = run_replay(scenario_id)
overall = result["overall_comparison"]["rows"][0]
unit = result["alert_metric"]["unit"]
baseline_value = overall["baseline"]["value"]
current_value = overall["current"]["value"]
delta = overall["delta"]

metric_cols = st.columns(4)
metric_cols[0].metric("Baseline", metric_text(baseline_value, unit))
delta_label = None if delta is None else (f"{delta:+.2f} pp" if unit == "percent" else f"{delta:+.3f}")
metric_cols[1].metric("Current", metric_text(current_value, unit), delta_label)
metric_cols[2].metric("Detected slices", result["anomaly_result"]["anomaly_count"])
metric_cols[3].metric("Tool calls", len(result["trace"]), f"{result['elapsed_ms']:.0f} ms replay")

tab_conclusion, tab_evidence, tab_monitor, tab_eval, tab_governance = st.tabs(
    ["Investigation", "Evidence & SQL", "Monitoring", "Evaluation", "Governance"]
)

with tab_conclusion:
    left, right = st.columns([1.12, .88], gap="large")
    with left:
        st.markdown("### Ranked cause candidates")
        for index, candidate in enumerate(result["candidates"], start=1):
            refs = ", ".join(candidate["evidence_refs"])
            st.markdown(
                f"<div class='candidate'><small>#{index} · {candidate['confidence']} · {candidate['status']}</small><br>"
                f"<strong>{candidate['title']}</strong><br><span>{candidate['reasoning']}</span><br>"
                f"<small>Evidence: {refs}</small></div>",
                unsafe_allow_html=True,
            )
    with right:
        st.markdown("### Investigation plan")
        for number, step in enumerate(result["plan"], start=1):
            st.markdown(f"<div class='toolstep'>{number:02d} / {step}</div>", unsafe_allow_html=True)
        st.markdown("### Decision boundary")
        st.info("报告是人工复核草稿。统计关联、埋点异常和候选原因不能自动触发回滚、补偿或数值调整。")
    st.markdown("### Human-review report")
    with st.expander("Open generated report", expanded=False):
        st.markdown(result["report"]["markdown"])
    st.download_button(
        "Download report (.md)",
        data=result["report"]["markdown"],
        file_name=f"{scenario_id}.md",
        mime="text/markdown",
    )

with tab_evidence:
    st.markdown("### Auditable tool trace")
    trace_frame = pd.DataFrame(result["trace"])
    st.dataframe(trace_frame, width="stretch", hide_index=True)
    for item in result["evidence"]:
        with st.expander(f"{item['evidence_id']} · {item['title']} · {item['digest']}"):
            if item.get("sql"):
                st.code(item["sql"], language="sql")
            st.json(item["result"], expanded=False)

    st.markdown("### Read-only SQL workbench")
    default_sql = "SELECT app_version, channel, COUNT(*) AS players FROM users GROUP BY app_version, channel ORDER BY app_version, players DESC LIMIT 50"
    sql = st.text_area("SQL", value=default_sql, height=120)
    if st.button("Execute guarded SQL"):
        sql_result = query_metrics(sql, row_limit=100, timeout_ms=2000)
        if sql_result["ok"]:
            st.caption(f"{sql_result['row_count']} rows · {sql_result['elapsed_ms']:.2f} ms · policy={sql_result['policy']}")
            st.dataframe(pd.DataFrame(sql_result["rows"]), width="stretch", hide_index=True)
        else:
            st.error(sql_result["error"])

with tab_monitor:
    st.markdown("### Current vs baseline by affected dimension")
    rows = result["anomaly_result"]["all_comparisons"]
    dimension = result["anomaly_result"]["dimensions"][0]
    labels = [row["dimensions"].get(dimension, "ALL") for row in rows]
    baseline_series = [row["baseline"]["value"] for row in rows]
    current_series = [row["current"]["value"] for row in rows]
    chart = go.Figure()
    chart.add_bar(name="Baseline", x=labels, y=baseline_series, marker_color="#64748B")
    chart.add_bar(name="Current", x=labels, y=current_series, marker_color="#2DD4BF")
    chart.update_layout(
        barmode="group",
        height=410,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_orientation="h",
        yaxis_title="Percent" if unit == "percent" else "Ratio",
        xaxis_title=dimension,
    )
    st.plotly_chart(chart, width="stretch")
    monitor_rows = []
    for row in rows:
        monitor_rows.append(
            {
                dimension: row["dimensions"].get(dimension),
                "baseline": row["baseline"]["value"],
                "current": row["current"]["value"],
                "delta": row["delta"],
                "z_score": row["z_score"],
                "confidence": row["confidence"],
            }
        )
    st.dataframe(pd.DataFrame(monitor_rows), width="stretch", hide_index=True)

with tab_eval:
    evaluation = eval_results()
    if not evaluation:
        st.warning("Run `python evals/run_evals.py` to generate evaluation results.")
    else:
        st.markdown(f"### Deterministic baseline · {evaluation['case_count']} fixed cases")
        metrics = evaluation["metrics"]
        cols = st.columns(5)
        cols[0].metric("Tool selection", f"{metrics['tool_selection_accuracy']:.1%}")
        cols[1].metric("SQL execution", f"{metrics['sql_execution_success_rate']:.1%}")
        cols[2].metric("SQL policy outcomes", f"{metrics['sql_policy_expected_outcome_rate']:.1%}")
        cols[3].metric("Root cause Top-3", f"{metrics['root_cause_top3_hit_rate']:.1%}")
        cols[4].metric("Report citations", f"{metrics['report_citation_accuracy']:.1%}")
        st.caption(
            f"p95 case latency: {metrics['p95_case_latency_ms']:.2f} ms · local deterministic cost: $0 · "
            "Claude model scores and cost remain N/A until an authenticated run is measured. These 100% values validate the harness, not Claude."
        )
        st.dataframe(pd.DataFrame(evaluation["details"]), width="stretch", hide_index=True)

with tab_governance:
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("### Control plane")
        st.markdown(
            "- `SELECT` / `WITH` only; semicolons and comments rejected\n"
            "- Public-table allowlist plus SQLite authorizer\n"
            "- Maximum 500 rows and 10-second hard ceiling\n"
            "- Ground-truth injection table inaccessible to MCP queries\n"
            "- Evidence IDs and SHA-256 digests in every report\n"
            "- Human review required before operational action"
        )
    with right:
        st.markdown("### Generalization contract")
        st.markdown(
            "Onboard another game by mapping its warehouse to `users` and `events`, then adding metric entries in "
            "`config/metrics.json`. The planner, query guard, cohort comparison, anomaly detector, report ledger and eval harness do not depend on Newton-specific UI or player identity."
        )
        with st.expander("Metric catalog"):
            st.json(metric_catalog(), expanded=False)
