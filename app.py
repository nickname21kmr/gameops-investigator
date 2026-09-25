from __future__ import annotations

import html
import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gameops_investigator.config import PROJECT_ROOT, metric_catalog, scenario_catalog
from gameops_investigator.orchestrator import ClaudeCodeRunner, DeterministicInvestigator
from gameops_investigator.tools import query_metrics


st.set_page_config(
    page_title="GameOps Investigator",
    page_icon=":material/troubleshoot:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Design tokens. One accent (evidence blue), status colours reserved for
# meaning (flagged / failed / passed), warm paper surface, ink text.
# ---------------------------------------------------------------------------
INK = "#16181D"
INK_2 = "#4B4F58"
INK_3 = "#7C808A"
LINE = "#E3E1DA"
PAPER = "#F6F5F1"
CARD = "#FFFFFF"
ACCENT = "#2A78D6"
FLAG = "#D4453F"
NEUTRAL = "#9A9DA4"
FONT_STACK = "'IBM Plex Sans', 'Noto Sans SC', system-ui, sans-serif"
MONO_STACK = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Consolas, monospace"

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap');

    :root {
      --ink:#16181D; --ink-2:#4B4F58; --ink-3:#7C808A; --line:#E3E1DA; --line-2:#EDEBE5;
      --paper:#F6F5F1; --card:#FFFFFF; --accent:#2A78D6; --accent-ink:#1C5CAB; --accent-soft:#EAF2FC;
      --flag:#C0392F; --flag-soft:#FBECEA; --ok:#1E7A46; --ok-soft:#E7F4EC; --warn:#9A5B00; --warn-soft:#FBF1DF;
      --sans:'IBM Plex Sans','Noto Sans SC',system-ui,sans-serif;
      --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Consolas,monospace;
      --radius:10px;
    }
    html, body, .stApp, .stMarkdown, button, input, textarea, select { font-family: var(--sans); }
    .stApp { background: var(--paper); color: var(--ink); }
    header[data-testid="stHeader"] { background: transparent; }
    .stAppDeployButton, #MainMenu, footer { display: none !important; }
    .block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1320px; }
    h1, h2, h3, h4 { font-family: var(--sans); color: var(--ink); letter-spacing: -0.01em; }
    code, pre, .mono { font-family: var(--mono) !important; }

    /* Sidebar ---------------------------------------------------------- */
    section[data-testid="stSidebar"] { background: #EFEDE7; border-right: 1px solid var(--line); }
    section[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
    .brand { display:flex; align-items:center; gap:.65rem; margin:.1rem 0 1.4rem; }
    .brand-mark { width:32px; height:32px; border-radius:8px; background:var(--ink); display:grid; place-items:center; }
    .brand-name { font-weight:700; font-size:.98rem; line-height:1.1; color:var(--ink); }
    .brand-sub { font-size:.72rem; color:var(--ink-3); letter-spacing:.02em; }
    .side-label { font-size:.68rem; font-weight:600; letter-spacing:.12em; text-transform:uppercase; color:var(--ink-3); margin:1.1rem 0 .35rem; }
    .engine { display:flex; gap:.55rem; align-items:flex-start; font-size:.8rem; color:var(--ink-2); padding:.6rem .7rem; border:1px solid var(--line); border-radius:8px; background:rgba(255,255,255,.55); }
    .dot { width:8px; height:8px; border-radius:50%; margin-top:.35rem; flex:none; }
    .dot--ok { background:var(--ok); } .dot--warn { background:#C98500; }
    .facts { display:grid; grid-template-columns:1fr 1fr; gap:.5rem; }
    .fact { background:rgba(255,255,255,.6); border:1px solid var(--line); border-radius:8px; padding:.55rem .65rem; }
    .fact b { display:block; font-size:1.02rem; color:var(--ink); font-variant-numeric: tabular-nums; }
    .fact span { font-size:.7rem; color:var(--ink-3); }
    .side-note { font-size:.74rem; color:var(--ink-3); line-height:1.5; margin-top:.6rem; }

    /* Dossier header --------------------------------------------------- */
    .topline { display:flex; justify-content:space-between; align-items:center; gap:1rem; font-size:.78rem; color:var(--ink-3); margin-bottom:1.1rem; }
    .crumbs b { color:var(--ink-2); font-weight:500; }
    .synthetic { display:inline-flex; align-items:center; gap:.4rem; padding:.22rem .6rem; border:1px dashed #B9B5AA; border-radius:999px; color:var(--ink-2); background:rgba(255,255,255,.5); }
    .dossier { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:1.4rem 1.6rem 1.3rem; margin-bottom:1rem; position:relative; overflow:hidden; }
    .dossier::before { content:""; position:absolute; left:0; top:0; bottom:0; width:4px; background:var(--accent); }
    .dossier-head { display:flex; justify-content:space-between; gap:1.5rem; align-items:flex-start; }
    .eyebrow { font-family:var(--mono); font-size:.72rem; letter-spacing:.06em; color:var(--accent-ink); text-transform:uppercase; }
    .dossier h1 { font-size:1.72rem; font-weight:700; line-height:1.25; margin:.35rem 0 .5rem; padding:0; }
    .dossier p.lede { color:var(--ink-2); font-size:.9rem; margin:0; max-width:860px; }
    .meta { display:flex; flex-wrap:wrap; gap:.4rem 1.6rem; margin-top:1.05rem; padding-top:.95rem; border-top:1px solid var(--line-2); }
    .meta div { font-size:.78rem; color:var(--ink-3); }
    .meta b { display:block; font-weight:500; color:var(--ink); font-size:.86rem; margin-top:.1rem; }
    .meta .arrow { color:var(--ink-3); padding:0 .25rem; }

    .status { display:inline-flex; align-items:center; gap:.45rem; white-space:nowrap; font-size:.8rem; font-weight:600; padding:.38rem .75rem; border-radius:999px; }
    .status svg { flex:none; }
    .status--supported { background:var(--ok-soft); color:var(--ok); }
    .status--insufficient_evidence, .status--no_supported_candidate { background:var(--warn-soft); color:var(--warn); }
    .status--tool_failure { background:var(--flag-soft); color:var(--flag); }

    /* KPI tiles (native st.metric, restyled) --------------------------- */
    div[data-testid="stMetric"] { background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:.95rem 1.1rem .9rem; }
    div[data-testid="stMetricLabel"] p { font-size:.74rem !important; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3) !important; }
    div[data-testid="stMetricValue"] { font-size:1.85rem; font-weight:600; color:var(--ink); font-variant-numeric: tabular-nums; letter-spacing:-.02em; }
    div[data-testid="stMetricDelta"] { font-size:.8rem; font-weight:500; }

    /* Tabs -------------------------------------------------------------- */
    .stTabs [data-baseweb="tab-list"] { gap:1.6rem; border-bottom:1px solid var(--line); }
    .stTabs [data-baseweb="tab"] { padding:.7rem 0; font-weight:500; color:var(--ink-3); background:transparent; }
    .stTabs [aria-selected="true"] { color:var(--ink) !important; }
    .stTabs [data-baseweb="tab-highlight"] { background:var(--ink); height:2px; }
    .stTabs [data-baseweb="tab-border"] { display:none; }
    .stTabs [data-baseweb="tab-panel"] { padding-top:1.4rem; }

    .section-title { display:flex; align-items:baseline; justify-content:space-between; margin:0 0 .75rem; }
    .section-title h3 { font-size:1.02rem; font-weight:600; margin:0; padding:0; }
    .section-title span { font-size:.76rem; color:var(--ink-3); }

    /* Candidate cards --------------------------------------------------- */
    .cand { display:grid; grid-template-columns:44px 1fr; gap:.2rem 1rem; background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:1.05rem 1.2rem 1rem; margin-bottom:.7rem; }
    .cand--lead { border-color:#BCD3EF; box-shadow:0 1px 0 rgba(22,24,29,.03), 0 8px 24px -18px rgba(42,120,214,.55); }
    .cand-rank { font-family:var(--mono); font-size:1.35rem; font-weight:500; color:var(--ink-3); line-height:1.2; }
    .cand--lead .cand-rank { color:var(--accent); }
    .cand h4 { font-size:1rem; font-weight:600; line-height:1.4; margin:.35rem 0 .3rem; padding:0; }
    .cand p { font-size:.86rem; color:var(--ink-2); line-height:1.6; margin:0 0 .7rem; }
    .cand-meta { display:flex; flex-wrap:wrap; align-items:center; gap:.5rem; }
    .conf { display:inline-flex; align-items:center; gap:.45rem; font-size:.74rem; font-weight:600; color:var(--ink-2); }
    .conf i { display:inline-block; width:14px; height:5px; border-radius:2px; background:var(--line); margin-right:2px; }
    .conf i.on { background:var(--accent); }
    .tag { font-size:.72rem; font-weight:500; color:var(--ink-2); background:#F1EFEA; border-radius:6px; padding:.15rem .5rem; }
    .chips { display:flex; flex-wrap:wrap; gap:.35rem; align-items:center; font-size:.72rem; color:var(--ink-3); }
    .chip { font-family:var(--mono); font-size:.72rem; color:var(--accent-ink); background:var(--accent-soft); border-radius:5px; padding:.1rem .42rem; }

    /* Plan stepper ------------------------------------------------------ */
    .steps { list-style:none; margin:0 0 1.2rem; padding:0; }
    .steps li { position:relative; display:flex; gap:.8rem; padding:0 0 .95rem; }
    .steps li:not(:last-child)::after { content:""; position:absolute; left:11px; top:25px; bottom:2px; width:2px; background:var(--line); }
    .steps .n { flex:none; width:24px; height:24px; border-radius:50%; border:2px solid var(--accent); color:var(--accent-ink); background:var(--card); font-family:var(--mono); font-size:.68rem; font-weight:500; display:grid; place-items:center; }
    .steps .t { font-size:.86rem; color:var(--ink); padding-top:.15rem; }

    .callout { border:1px solid var(--line); border-left:3px solid var(--ink); background:var(--card); border-radius:8px; padding:.85rem 1rem; font-size:.84rem; color:var(--ink-2); line-height:1.6; }
    .callout b { color:var(--ink); display:block; margin-bottom:.2rem; font-size:.8rem; letter-spacing:.04em; text-transform:uppercase; }

    /* Trace timeline ---------------------------------------------------- */
    .trace { background:var(--card); border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; margin-bottom:1rem; }
    .trace-row { display:grid; grid-template-columns:56px 210px 1fr 88px 22px; gap:1rem; align-items:center; padding:.7rem 1.1rem; border-top:1px solid var(--line-2); font-size:.82rem; }
    .trace-row:first-child { border-top:none; }
    .trace-row.head { background:#FAF9F6; font-size:.68rem; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3); }
    .trace-tool { font-family:var(--mono); color:var(--ink); font-size:.8rem; }
    .trace-args { color:var(--ink-3); font-family:var(--mono); font-size:.72rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .trace-ms { font-family:var(--mono); font-size:.76rem; color:var(--ink-2); text-align:right; font-variant-numeric: tabular-nums; }

    .panel { background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:1.1rem 1.25rem; height:100%; }
    .panel h4 { font-size:.95rem; font-weight:600; margin:0 0 .6rem; padding:0; }
    .panel ul { margin:0; padding-left:1.1rem; } .panel li { font-size:.85rem; color:var(--ink-2); margin:.3rem 0; }
    .panel p { font-size:.85rem; color:var(--ink-2); line-height:1.65; }

    /* Native widgets ---------------------------------------------------- */
    div[data-testid="stExpander"] details { background:var(--card); border:1px solid var(--line); border-radius:var(--radius); }
    div[data-testid="stExpander"] summary p { font-size:.86rem; }
    div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; }
    .stButton > button, .stDownloadButton > button { border-radius:8px; font-weight:500; }
    .stButton > button[kind="primary"] { background:var(--ink); border-color:var(--ink); }
    .stButton > button[kind="primary"]:hover { background:#2B2F37; border-color:#2B2F37; }
    div[data-testid="stAlert"] { border-radius:8px; }
    .foot { margin-top:2.5rem; padding-top:1rem; border-top:1px solid var(--line); font-size:.74rem; color:var(--ink-3); display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap; }
    </style>
    """,
    unsafe_allow_html=True,
)


SCENARIOS = scenario_catalog()

STATUS_LABELS = {
    "supported": "Supported by evidence",
    "insufficient_evidence": "Insufficient evidence",
    "no_supported_candidate": "No supported candidate",
    "tool_failure": "Tool failure",
}
STATUS_ICONS = {
    "supported": '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.6"/><path d="M5 8.2l2 2 4-4.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "tool_failure": '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.6"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
}
STATUS_ICON_WARN = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.6"/><path d="M8 4.6v4.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="11.2" r="1" fill="currentColor"/></svg>'
CANDIDATE_STATUS = {
    "supported_candidate": "Supported candidate",
    "secondary": "Secondary",
    "alternative": "Alternative explanation",
    "not_supported_yet": "Not supported yet",
}
CONFIDENCE_LEVEL = {"high": 3, "medium": 2, "low": 1}


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


def esc(value: Any) -> str:
    return html.escape(str(value))


def section(title: str, note: str = "") -> None:
    st.markdown(
        f'<div class="section-title"><h3>{esc(title)}</h3><span>{esc(note)}</span></div>',
        unsafe_allow_html=True,
    )


def window_text(filters: dict[str, Any]) -> str:
    start, end = filters.get("start_date"), filters.get("end_date")
    if not start:
        return "—"
    return f"{start[5:]} → {end[5:]}" if end else start


def args_text(arguments: dict[str, Any]) -> str:
    parts = []
    for key, value in arguments.items():
        if isinstance(value, dict):
            value = ",".join(f"{k}={v}" for k, v in value.items())
        elif isinstance(value, list):
            value = ",".join(map(str, value)) or "[]"
        parts.append(f"{key}={value}")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div class="brand">
          <div class="brand-mark">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <circle cx="7.5" cy="7.5" r="5" stroke="#F6F5F1" stroke-width="1.8"/>
              <path d="M11.3 11.3L15.5 15.5" stroke="#2A78D6" stroke-width="2" stroke-linecap="round"/>
              <path d="M5 8.6l1.6-1.8 1.4 1.2 2-2.4" stroke="#F6F5F1" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div><div class="brand-name">GameOps Investigator</div><div class="brand-sub">Evidence-first incident review</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="side-label">Incident</div>', unsafe_allow_html=True)
    scenario_id = st.selectbox(
        "Reproducible incident",
        options=list(SCENARIOS),
        format_func=lambda item: SCENARIOS[item]["title"],
        label_visibility="collapsed",
    )
    st.markdown('<div class="side-label">Coordinator</div>', unsafe_allow_html=True)
    mode = st.radio(
        "Coordinator",
        ["Deterministic replay", "Claude Code + MCP"],
        label_visibility="collapsed",
    )
    availability = ClaudeCodeRunner.availability()
    if availability["installed"] and availability.get("logged_in"):
        engine = f'<span class="dot dot--ok"></span><span>Claude Code ready · {esc(availability.get("auth_method"))}</span>'
    elif availability["installed"]:
        engine = '<span class="dot dot--warn"></span><span>Claude Code installed · sign-in pending</span>'
    else:
        engine = '<span class="dot dot--warn"></span><span>Claude Code not detected — deterministic replay stays fully functional</span>'
    st.markdown(f'<div class="engine">{engine}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="side-note">确定性回放用于无密钥演示与评测；Claude Code 用于开放式规划和解释。两者调用同一组只读工具。</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    run_button = st.button("Run investigation", type="primary", width="stretch", icon=":material/play_arrow:")
    st.markdown('<div class="side-label">Data boundary</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="facts">
          <div class="fact"><b>5,000</b><span>synthetic players</span></div>
          <div class="fact"><b>136,164</b><span>source events</span></div>
          <div class="fact"><b>3</b><span>injected incidents</span></div>
          <div class="fact"><b>0</b><span>write paths</span></div>
        </div>
        <div class="side-note">固定种子生成的合成数据，仅用于展示方法、工具边界与评测，不代表商业游戏结果。</div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Investigation data
# ---------------------------------------------------------------------------
scenario = SCENARIOS[scenario_id]
result = run_replay(scenario_id)
overall_rows = result["overall_comparison"].get("rows", [])
overall = overall_rows[0] if overall_rows else {}
alert_metric = result["alert_metric"]
unit = alert_metric.get("unit", "percent")
baseline_value = overall.get("baseline", {}).get("value")
current_value = overall.get("current", {}).get("value")
delta = overall.get("delta")
status = result["investigation_status"]


# ---------------------------------------------------------------------------
# Dossier header
# ---------------------------------------------------------------------------
status_icon = STATUS_ICONS.get(status, STATUS_ICON_WARN)
st.markdown(
    f"""
    <div class="topline">
      <div class="crumbs">Incident review&nbsp;&nbsp;/&nbsp;&nbsp;<b>{esc(scenario_id)}</b></div>
      <div class="synthetic">Synthetic demo data · fixed seed</div>
    </div>
    <div class="dossier">
      <div class="dossier-head">
        <div>
          <div class="eyebrow">Alert · {esc(alert_metric.get("metric_id", ""))}</div>
          <h1>{esc(scenario["title"])}</h1>
          <p class="lede">Claude 负责计划、工具选择与解释；指标口径、SQL、分群比较、异常检验和引用校验由确定性程序完成。结论是人工复核草稿，不代表因果证明。</p>
        </div>
        <span class="status status--{esc(status)}">{status_icon}{esc(STATUS_LABELS.get(status, status))}</span>
      </div>
      <div class="meta">
        <div>Alert metric<b>{esc(alert_metric.get("display_name", alert_metric.get("metric_id", "—")))}</b></div>
        <div>Baseline → current window<b>{esc(window_text(scenario.get("baseline", {})))}<span class="arrow">vs</span>{esc(window_text(scenario.get("current", {})))}</b></div>
        <div>App version<b>{esc(scenario.get("current", {}).get("app_version", "—"))}</b></div>
        <div>Breakdown<b>{esc(scenario.get("breakdown_dimension", "—"))}</b></div>
        <div>Owner<b>{esc(alert_metric.get("owner", "—"))}</b></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if mode == "Claude Code + MCP":
    question = st.text_area(
        "Open-ended investigation question",
        value=f"Investigate {scenario['title']}. Use metric definitions first and return a cited, uncertainty-aware report.",
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
            st.info("请按上方错误提示排查后手动重试；下方仍展示同工具链的确定性回放，并非本次 Claude 调查结果。")

metric_cols = st.columns(4)
metric_cols[0].metric("Baseline", metric_text(baseline_value, unit))
delta_label = None if delta is None else (f"{delta:+.2f} pp" if unit == "percent" else f"{delta:+.3f}")
# Higher retention is good; for event-intensity metrics a rise is not automatically good.
delta_color = "normal" if alert_metric.get("kind") == "retention" else "off"
metric_cols[1].metric("Current", metric_text(current_value, unit), delta_label, delta_color=delta_color)
metric_cols[2].metric("Detected slices", result["anomaly_result"].get("anomaly_count", "N/A"))
metric_cols[3].metric("Tool calls", len(result["trace"]), f"{result['elapsed_ms']:.0f} ms replay", delta_color="off")

st.write("")
tab_conclusion, tab_evidence, tab_monitor, tab_eval, tab_governance = st.tabs(
    ["Investigation", "Evidence & SQL", "Monitoring", "Evaluation", "Governance"]
)

# ---------------------------------------------------------------------------
# Investigation
# ---------------------------------------------------------------------------
with tab_conclusion:
    left, right = st.columns([1.55, 1], gap="large")
    with left:
        section("Ranked cause candidates", f"{len(result['candidates'])} of max 3 · human review required")
        if not result["candidates"]:
            message = result["investigation_reason"]
            if status == "tool_failure":
                st.error(message)
            else:
                st.info(message)
        for index, candidate in enumerate(result["candidates"], start=1):
            level = CONFIDENCE_LEVEL.get(candidate["confidence"], 1)
            bars = "".join(f'<i class="{"on" if n < level else ""}"></i>' for n in range(3))
            chips = "".join(f'<span class="chip">{esc(ref)}</span>' for ref in candidate["evidence_refs"])
            st.markdown(
                f"""
                <div class="cand{' cand--lead' if index == 1 else ''}">
                  <div class="cand-rank">{index:02d}</div>
                  <div>
                    <div class="cand-meta">
                      <span class="conf">{bars}{esc(candidate['confidence'].capitalize())} confidence</span>
                      <span class="tag">{esc(CANDIDATE_STATUS.get(candidate['status'], candidate['status']))}</span>
                    </div>
                    <h4>{esc(candidate['title'])}</h4>
                    <p>{esc(candidate['reasoning'])}</p>
                    <div class="chips">Evidence {chips}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with right:
        section("Investigation plan", f"{len(result['plan'])} steps")
        steps = "".join(
            f'<li><span class="n">{number:02d}</span><span class="t">{esc(step)}</span></li>'
            for number, step in enumerate(result["plan"], start=1)
        )
        st.markdown(f'<ol class="steps">{steps}</ol>', unsafe_allow_html=True)
        st.markdown(
            '<div class="callout"><b>Decision boundary</b>报告是人工复核草稿。统计关联、埋点异常和候选原因不能自动触发回滚、补偿或数值调整。</div>',
            unsafe_allow_html=True,
        )

    st.write("")
    section("Human-review report", "Markdown · evidence IDs + SHA-256 digests")
    with st.expander("Open generated report", expanded=False, icon=":material/description:"):
        st.markdown(result["report"]["markdown"])
    st.download_button(
        "Download report (.md)",
        data=result["report"]["markdown"],
        file_name=f"{scenario_id}.md",
        mime="text/markdown",
        icon=":material/download:",
    )

# ---------------------------------------------------------------------------
# Evidence & SQL
# ---------------------------------------------------------------------------
with tab_evidence:
    section("Auditable tool trace", f"{len(result['trace'])} read-only calls · {result['elapsed_ms']:.0f} ms total")
    rows_html = "".join(
        f"""<div class="trace-row">
              <span class="chip">{esc(item.get('evidence_id', '—'))}</span>
              <span class="trace-tool">{esc(item.get('tool', ''))}</span>
              <span class="trace-args" title="{esc(args_text(item.get('arguments', {})))}">{esc(args_text(item.get('arguments', {})))}</span>
              <span class="trace-ms">{item.get('elapsed_ms', 0):.1f} ms</span>
              <span title="{'ok' if item.get('ok') else 'failed'}">{STATUS_ICONS['supported'] if item.get('ok') else STATUS_ICONS['tool_failure']}</span>
            </div>"""
        for item in result["trace"]
    )
    st.markdown(
        f'<div class="trace"><div class="trace-row head"><span>ID</span><span>Tool</span><span>Arguments</span><span style="text-align:right">Latency</span><span></span></div>{rows_html}</div>',
        unsafe_allow_html=True,
    )
    with st.expander("Raw trace table", icon=":material/table:"):
        st.dataframe(pd.DataFrame(result["trace"]), width="stretch", hide_index=True)

    st.write("")
    section("Evidence ledger", "click to inspect SQL and result")
    for item in result["evidence"]:
        with st.expander(f"{item['evidence_id']} · {item['title']} · {item['digest']}"):
            if item.get("sql"):
                st.code(item["sql"], language="sql")
            st.json(item["result"], expanded=False)

    st.write("")
    section("Read-only SQL workbench", "SELECT / WITH only · allowlisted tables · 100-row cap")
    default_sql = "SELECT app_version, channel, COUNT(*) AS players FROM users GROUP BY app_version, channel ORDER BY app_version, players DESC LIMIT 50"
    sql = st.text_area("SQL", value=default_sql, height=120, label_visibility="collapsed")
    if st.button("Execute guarded SQL", icon=":material/play_arrow:"):
        sql_result = query_metrics(sql, row_limit=100, timeout_ms=2000)
        if sql_result["ok"]:
            st.caption(f"{sql_result['row_count']} rows · {sql_result['elapsed_ms']:.2f} ms · policy={sql_result['policy']}")
            st.dataframe(pd.DataFrame(sql_result["rows"]), width="stretch", hide_index=True)
        else:
            st.error(sql_result["error"])

# ---------------------------------------------------------------------------
# Monitoring — dumbbell: baseline → current per slice, flagged slices marked.
# ---------------------------------------------------------------------------
with tab_monitor:
    rows = result["anomaly_result"].get("all_comparisons", [])
    dimensions = result["anomaly_result"].get("dimensions", [])
    if not rows or not dimensions:
        st.info("No cohort comparisons are available for monitoring. Check the investigation status and data windows.")
    else:
        dimension = dimensions[0]
        threshold = result["anomaly_result"].get("threshold")
        z_gate = threshold.get("z_score", 1.96) if isinstance(threshold, dict) else (threshold or 1.96)
        ordered = sorted(rows, key=lambda row: row["delta"] or 0)
        labels = [str(row["dimensions"].get(dimension, "ALL")) for row in ordered]
        base = [row["baseline"]["value"] for row in ordered]
        cur = [row["current"]["value"] for row in ordered]
        flagged = [abs(row.get("z_score") or 0) >= z_gate for row in ordered]
        fmt = ".2f" if unit == "percent" else ".3f"
        suffix = "%" if unit == "percent" else ""

        section(
            f"{alert_metric.get('display_name', 'Metric')} by {dimension}",
            f"baseline → current · flagged when |z| ≥ {z_gate:g}",
        )
        chart = go.Figure()
        connector_x, connector_y = [], []
        for label, b, c in zip(labels, base, cur):
            connector_x += [b, c, None]
            connector_y += [label, label, None]
        chart.add_scatter(
            x=connector_x, y=connector_y, mode="lines", line=dict(color="#CFCCC3", width=2),
            hoverinfo="skip", showlegend=False,
        )
        custom = [
            [row["baseline"]["denominator"], row["current"]["denominator"], row["delta"], row.get("z_score") or 0]
            for row in ordered
        ]
        chart.add_scatter(
            x=base, y=labels, mode="markers", name="Baseline",
            marker=dict(size=13, color=CARD, line=dict(color=NEUTRAL, width=2.5)),
            customdata=custom,
            hovertemplate=f"<b>%{{y}}</b><br>Baseline %{{x:{fmt}}}{suffix}<br>n = %{{customdata[0]:,.0f}}<extra></extra>",
        )
        chart.add_scatter(
            x=cur, y=labels, mode="markers", name="Current", showlegend=False,
            marker=dict(size=14, color=[FLAG if f else ACCENT for f in flagged], line=dict(color=CARD, width=2)),
            customdata=custom,
            hovertemplate=(
                f"<b>%{{y}}</b><br>Current %{{x:{fmt}}}{suffix}<br>n = %{{customdata[1]:,.0f}}"
                f"<br>Δ %{{customdata[2]:+{fmt}}} · z = %{{customdata[3]:.2f}}<extra></extra>"
            ),
        )
        # Legend entries use fixed colours; per-point colours would make the legend take the first slice's state.
        # Identity is never colour-alone: flagged slices are also annotated.
        chart.add_scatter(x=[None], y=[None], mode="markers", name="Current",
                          marker=dict(size=14, color=ACCENT, line=dict(color=CARD, width=2)))
        chart.add_scatter(x=[None], y=[None], mode="markers", name="Current · flagged",
                          marker=dict(size=14, color=FLAG, line=dict(color=CARD, width=2)))
        for label, c, row, flag in zip(labels, cur, ordered, flagged):
            if flag:
                chart.add_annotation(
                    x=c, y=label, text=f"<b>flagged</b> · z = {row['z_score']:.2f}", showarrow=False,
                    xanchor="left" if row["delta"] >= 0 else "right", xshift=14 if row["delta"] >= 0 else -14,
                    yshift=16, font=dict(size=11.5, color=INK),
                )
        chart.update_layout(
            height=150 + 70 * len(labels),
            margin=dict(l=8, r=24, t=8, b=8),
            paper_bgcolor=CARD,
            plot_bgcolor=CARD,
            font=dict(family=FONT_STACK, size=12.5, color=INK_2),
            legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=12)),
            hoverlabel=dict(bgcolor=INK, bordercolor=INK, font=dict(family=FONT_STACK, color="#FFFFFF", size=12)),
            xaxis=dict(
                title=dict(text="Percent" if unit == "percent" else "Ratio", font=dict(size=11.5, color=INK_3)),
                gridcolor="#EFEDE7", zeroline=False, ticksuffix=suffix, tickfont=dict(color=INK_3),
            ),
            yaxis=dict(tickfont=dict(family=MONO_STACK, size=12.5, color=INK), automargin=True),
        )
        with st.container(border=True):
            st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})

        monitor_rows = [
            {
                dimension: row["dimensions"].get(dimension),
                "baseline": row["baseline"]["value"],
                "current": row["current"]["value"],
                "delta": row["delta"],
                "z_score": row["z_score"],
                "confidence": row["confidence"],
            }
            for row in ordered
        ]
        st.dataframe(
            pd.DataFrame(monitor_rows),
            width="stretch",
            hide_index=True,
            column_config={
                "baseline": st.column_config.NumberColumn(format=f"%.2f{suffix}" if suffix else "%.3f"),
                "current": st.column_config.NumberColumn(format=f"%.2f{suffix}" if suffix else "%.3f"),
                "delta": st.column_config.NumberColumn(format="%+.2f" if suffix else "%+.3f"),
                "z_score": st.column_config.NumberColumn("z score", format="%.2f"),
            },
        )

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
with tab_eval:
    evaluation = eval_results()
    if not evaluation:
        st.warning("Run `python evals/run_evals.py` to generate evaluation results.")
    else:
        metrics = evaluation["metrics"]
        section(
            f"Deterministic baseline · {evaluation['case_count']} fixed cases",
            f"{evaluation.get('passed', '—')} passed · {evaluation.get('failed', '—')} failed",
        )
        cols = st.columns(5)
        cols[0].metric("Tool selection", f"{metrics['tool_selection_accuracy']:.1%}")
        cols[1].metric("SQL execution", f"{metrics['sql_execution_success_rate']:.1%}")
        cols[2].metric("SQL policy", f"{metrics['sql_policy_expected_outcome_rate']:.1%}")
        cols[3].metric("Root cause top-3", f"{metrics['root_cause_top3_hit_rate']:.1%}")
        cols[4].metric("Report citations", f"{metrics['report_citation_accuracy']:.1%}")
        st.markdown(
            f'<div class="callout" style="margin:1rem 0 1.2rem"><b>What these numbers mean</b>'
            f"p95 case latency {metrics['p95_case_latency_ms']:.2f} ms · local deterministic cost $0. "
            "The 100% values validate the harness and tool contracts, not Claude — model scores and cost stay N/A until an authenticated run is measured.</div>",
            unsafe_allow_html=True,
        )
        st.dataframe(
            pd.DataFrame(evaluation["details"]),
            width="stretch",
            hide_index=True,
            column_config={"passed": st.column_config.CheckboxColumn("passed")},
        )

# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------
with tab_governance:
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(
            """
            <div class="panel"><h4>Control plane</h4><ul>
              <li><code>SELECT</code> / <code>WITH</code> only; semicolons and comments rejected</li>
              <li>Public-table allowlist plus SQLite authorizer</li>
              <li>Maximum 500 rows and 10-second hard ceiling</li>
              <li>Ground-truth injection table inaccessible to MCP queries</li>
              <li>Evidence IDs and SHA-256 digests in every report</li>
              <li>Human review required before operational action</li>
            </ul></div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            """
            <div class="panel"><h4>Generalization contract</h4>
            <p>Onboard another game by mapping its warehouse to <code>users</code> and <code>events</code>, then adding metric
            entries in <code>config/metrics.json</code>. The planner, query guard, cohort comparison, anomaly detector, report
            ledger and eval harness do not depend on Newton-specific UI or player identity.</p></div>
            """,
            unsafe_allow_html=True,
        )
    st.write("")
    with st.expander("Metric catalog", icon=":material/menu_book:"):
        st.json(metric_catalog(), expanded=False)

st.markdown(
    '<div class="foot"><span>GameOps Investigator · read-only MCP tools · deterministic replay</span>'
    "<span>Synthetic data only — not commercial game metrics</span></div>",
    unsafe_allow_html=True,
)
