"""Deterministic management summary: a fixed template filled from metrics, no LLM involved."""

from __future__ import annotations

import math

import pandas as pd

from . import metrics


def _pct(x: float) -> str:
    return "n/a" if x is None or math.isnan(x) else f"{x:.0%}"


def build_summary(findings: pd.DataFrame, as_of) -> str:
    """Return a short markdown summary of follow-up status for the given findings."""
    as_of = pd.Timestamp(as_of)
    k = metrics.compute_kpis(findings, as_of)
    if k["total"] == 0:
        return "No findings match the current selection."

    prepared = metrics.prepare(findings, as_of)
    lines = [f"**Follow-up status as of {as_of:%d %B %Y}**", ""]

    if k["open"] == 0:
        lines.append(f"All {k['total']} findings in scope are resolved.")
    else:
        lines.append(
            f"- {k['open']} of {k['total']} findings are open; {k['overdue']} "
            f"({_pct(k['overdue_rate'])}) are past their current due date, "
            f"by {k['avg_days_overdue']:.0f} days on average."
        )
    crit_high = prepared[
        prepared["is_overdue"] & prepared["risk_rating"].isin(["Critical", "High"])
    ]
    if len(crit_high):
        n_crit = int((crit_high["risk_rating"] == "Critical").sum())
        lines.append(
            f"- {len(crit_high)} Critical/High findings are overdue ({n_crit} Critical). "
            "These need escalation to the owning executive."
        )
    score = metrics.function_scorecard(findings, as_of)
    score = score[score["overdue"] > 0]
    if len(score):
        top = score.sort_values(["overdue", "avg_days_overdue"], ascending=False).iloc[0]
        lines.append(
            f"- {top['owner_function']} holds the most overdue items ({int(top['overdue'])}, "
            f"{_pct(top['overdue_pct'])} of its open findings)."
        )
    lines.append(
        f"- Only {_pct(k['on_time_rate'])} of findings were implemented by their original "
        f"due date; due dates have been revised {k['avg_revisions']:.1f} times per finding "
        "on average."
    )
    lines.append(f"- Repeat findings make up {_pct(k['repeat_rate'])} of all findings.")
    pareto = metrics.root_cause_pareto(findings, as_of)
    if len(pareto):
        r = pareto.iloc[0]
        lines.append(
            f'- The most frequent root cause is "{r["root_cause"]}" '
            f"({int(r['count'])} findings, {r['count'] / pareto['count'].sum():.0%})."
        )
    due = metrics.due_within(findings, as_of, 30)
    lines.append(f"- {len(due)} findings fall due in the next 30 days.")

    lines += ["", "**Suggested attention**", ""]
    if k["open"] and k["overdue_rate"] >= 0.25:
        lines.append("- Overdue share is high: agree recovery dates with the owners concerned.")
    elif k["open"]:
        lines.append("- Overdue share is moderate: keep the regular follow-up cadence.")
    if not math.isnan(k["on_time_rate"]) and k["on_time_rate"] < 0.6:
        lines.append("- Low on-time delivery: challenge whether original due dates are realistic.")
    if k["avg_revisions"] >= 0.5:
        lines.append("- Frequent due-date extensions: require approval and rationale for each.")
    if not math.isnan(k["repeat_rate"]) and k["repeat_rate"] >= 0.1:
        lines.append("- Repeat findings suggest earlier actions did not fix the root cause.")
    lines.append("")
    lines.append("_Generated from a fixed template; thresholds are illustrative._")
    return "\n".join(lines)
