"""Streamlit dashboard for internal audit findings and action plans (synthetic data)."""

from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from findings_tracker import metrics
from findings_tracker.data import load_data
from findings_tracker.palette import (
    ACCENT,
    HEATMAP_SCALE,
    NEUTRAL,
    RISK_COLOURS,
    RISK_ORDER,
    STATUS_ORDER,
)
from findings_tracker.summary import build_summary

st.set_page_config(page_title="Audit Findings Tracker", layout="wide")


@st.cache_data
def _load(path: str | None):
    return load_data(path)


def _pct(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:.0%}"


def _style(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        font=dict(size=13),
        legend=dict(orientation="h", y=-0.2),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


audits, findings, updates, snapshot = _load(os.environ.get("FINDINGS_DATA_DIR"))

st.sidebar.header("Filters")
as_of = pd.Timestamp(st.sidebar.date_input("As-of date", snapshot.date()))
functions = st.sidebar.multiselect("Owner function", sorted(findings["owner_function"].unique()))
risks = st.sidebar.multiselect("Risk rating", RISK_ORDER)
statuses = st.sidebar.multiselect("Status (at as-of date)", STATUS_ORDER)
audit_opts = audits["audit_id"] + " - " + audits["entity"]
audit_sel = st.sidebar.multiselect("Audit", audit_opts.tolist())
st.sidebar.caption("Synthetic data only. No real organisation, person or record.")

view = findings.copy()
if functions:
    view = view[view["owner_function"].isin(functions)]
if risks:
    view = view[view["risk_rating"].isin(risks)]
if audit_sel:
    view = view[view["audit_id"].isin([a.split(" - ")[0] for a in audit_sel])]
prepared = metrics.prepare(view, as_of)
if statuses:
    keep = prepared.loc[prepared["effective_status"].isin(statuses), "finding_id"]
    view = view[view["finding_id"].isin(keep)]
    prepared = prepared[prepared["finding_id"].isin(keep)]

st.title("Audit Findings Tracker")
st.caption(f"Follow-up of management action plans - data as of {as_of:%d %b %Y} - synthetic data")

tab_dash, tab_drill, tab_sum = st.tabs(["Dashboard", "Drill-down", "Management summary"])

with tab_dash:
    k = metrics.compute_kpis(view, as_of)
    c = st.columns(5)
    c[0].metric("Open findings", k["open"])
    c[1].metric(
        "Overdue (% of open)", _pct(k["overdue_rate"]), help=f"{k['overdue']} overdue findings"
    )
    c[2].metric("Avg days overdue", f"{k['avg_days_overdue']:.0f}")
    c[3].metric(
        "On-time implementation",
        _pct(k["on_time_rate"]),
        help="Implemented on or before the original due date",
    )
    c[4].metric("Repeat-finding rate", _pct(k["repeat_rate"]))

    left, right = st.columns(2)

    ageing = metrics.ageing_buckets(view, as_of)
    fig = go.Figure()
    for risk in RISK_ORDER:
        d = ageing[ageing["risk_rating"] == risk]
        fig.add_bar(x=d["bucket"], y=d["count"], name=risk, marker_color=RISK_COLOURS[risk])
    fig.update_layout(barmode="stack", title="Open findings by age since issue")
    fig.update_yaxes(title="Findings")
    left.plotly_chart(_style(fig), width="stretch")

    matrix = metrics.risk_function_matrix(view, as_of)
    fig = go.Figure(
        go.Heatmap(
            z=matrix.values,
            x=matrix.columns,
            y=matrix.index,
            colorscale=HEATMAP_SCALE,
            text=matrix.values,
            texttemplate="%{text}",
            hovertemplate="%{y} / %{x}: %{z}<extra></extra>",
            showscale=False,
        )
    )
    fig.update_layout(title="Open findings: function x risk")
    fig.update_yaxes(autorange="reversed")
    right.plotly_chart(_style(fig), width="stretch")

    trend = metrics.overdue_trend(view, updates, as_of)
    fig = go.Figure()
    fig.add_scatter(x=trend["date"], y=trend["open"], name="Open", line=dict(color=NEUTRAL))
    fig.add_scatter(
        x=trend["date"],
        y=trend["overdue"],
        name="Overdue",
        line=dict(color=RISK_COLOURS["High"], width=3),
        fill="tozeroy",
    )
    fig.update_layout(title="Open and overdue findings, month-end")
    fig.update_yaxes(title="Findings")
    left.plotly_chart(_style(fig), width="stretch")

    pareto = metrics.root_cause_pareto(view, as_of)
    fig = go.Figure()
    fig.add_bar(x=pareto["root_cause"], y=pareto["count"], name="Findings", marker_color=ACCENT)
    fig.add_scatter(
        x=pareto["root_cause"],
        y=pareto["cumulative_pct"],
        name="Cumulative %",
        yaxis="y2",
        line=dict(color=NEUTRAL),
        mode="lines+markers",
    )
    fig.update_layout(
        title="Root-cause Pareto (all findings)",
        showlegend=False,
        yaxis2=dict(overlaying="y", side="right", range=[0, 1.05], tickformat=".0%"),
    )
    right.plotly_chart(_style(fig), width="stretch")

    st.subheader("Due in the next 30 days")
    due = metrics.due_within(view, as_of, 30)
    due = due.assign(due_date=due["due_date"].dt.strftime("%Y-%m-%d"))
    st.dataframe(
        due[
            [
                "finding_id",
                "title",
                "risk_rating",
                "owner_function",
                "due_date",
                "revised_due_count",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

with tab_drill:
    cols = [
        "finding_id",
        "audit_id",
        "title",
        "risk_rating",
        "root_cause",
        "owner_function",
        "created_date",
        "due_date",
        "effective_status",
        "revised_due_count",
        "days_overdue",
        "repeat_flag",
    ]
    table = (
        prepared[cols]
        .assign(
            created_date=prepared["created_date"].dt.strftime("%Y-%m-%d"),
            due_date=prepared["due_date"].dt.strftime("%Y-%m-%d"),
        )
        .rename(columns={"effective_status": "status"})
    )
    st.caption(f"{len(table)} findings match the sidebar filters.")
    st.dataframe(table, width="stretch", hide_index=True)
    st.download_button(
        "Download CSV", table.to_csv(index=False).encode(), "findings_filtered.csv", "text/csv"
    )

with tab_sum:
    st.markdown(build_summary(view, as_of))
    st.caption("Template-based text; no AI model is involved.")

st.divider()
st.caption("By Utku Fidan - utkufidan.com - synthetic data only")
