"""Findings metrics. Pure pandas, no UI code.

All functions take an ``as_of`` date and derive status from dates rather than trusting the
stored status, so the same data can be viewed at any point in time.

Expected ``findings`` columns (dates are datetime64):
    finding_id, audit_id, risk_rating, root_cause, owner_function, created_date,
    original_due_date, due_date (current, after revisions), resolved_date (NaT while open),
    status, revised_due_count, repeat_flag
"""

from __future__ import annotations

import pandas as pd

from .palette import RISK_ORDER

CLOSED_STATUSES = ("Implemented", "Validated")
RISK_ACCEPTED = "Risk accepted"

# (label, min age in days, max age in days or None)
AGEING_BUCKETS = [
    ("0-30 days", 0, 30),
    ("31-90 days", 31, 90),
    ("91-180 days", 91, 180),
    ("181-365 days", 181, 365),
    ("> 365 days", 366, None),
]


def prepare(findings: pd.DataFrame, as_of) -> pd.DataFrame:
    """Return findings that exist at ``as_of`` with derived columns.

    Adds: is_open, is_overdue, days_overdue, age_days, effective_status.
    A finding is open until its resolved_date (implementation, validation or risk acceptance).
    It is overdue when open and the current (revised) due date is before ``as_of``.
    """
    as_of = pd.Timestamp(as_of)
    df = findings[findings["created_date"] <= as_of].copy()
    resolved = df["resolved_date"].notna() & (df["resolved_date"] <= as_of)
    df["is_open"] = ~resolved
    df["is_overdue"] = df["is_open"] & (df["due_date"] < as_of)
    df["days_overdue"] = (as_of - df["due_date"]).dt.days.where(df["is_overdue"], 0)
    df["age_days"] = (as_of - df["created_date"]).dt.days

    stored = df["status"]
    open_status = stored.where(stored.isin(["Open", "In progress"]), "Open")
    resolved_status = stored.where(stored.isin([*CLOSED_STATUSES, RISK_ACCEPTED]), "Implemented")
    df["effective_status"] = open_status.where(df["is_open"], resolved_status)
    df.loc[df["is_overdue"], "effective_status"] = "Overdue"
    return df


def open_findings(findings: pd.DataFrame, as_of) -> pd.DataFrame:
    df = prepare(findings, as_of)
    return df[df["is_open"]]


def overdue_rate(findings: pd.DataFrame, as_of) -> float:
    """Overdue findings as a share of open findings (NaN when nothing is open)."""
    df = prepare(findings, as_of)
    n_open = int(df["is_open"].sum())
    return float(df["is_overdue"].sum() / n_open) if n_open else float("nan")


def avg_days_overdue(findings: pd.DataFrame, as_of) -> float:
    """Mean days past the current due date across overdue findings (0 when none)."""
    df = prepare(findings, as_of)
    od = df[df["is_overdue"]]
    return float(od["days_overdue"].mean()) if len(od) else 0.0


def implementation_within_due_rate(findings: pd.DataFrame, as_of) -> float:
    """Share of findings implemented on or before their ORIGINAL due date.

    Denominator: findings that are implemented/validated by ``as_of`` plus findings still
    unresolved whose original due date has already passed. Risk-accepted findings and
    findings not yet due are excluded so recent findings do not flatter the rate.
    """
    as_of = pd.Timestamp(as_of)
    df = findings[findings["created_date"] <= as_of]
    df = df[df["status"] != RISK_ACCEPTED]
    resolved = df["resolved_date"].notna() & (df["resolved_date"] <= as_of)
    eligible = resolved | (df["original_due_date"] < as_of)
    if not eligible.any():
        return float("nan")
    on_time = resolved & (df["resolved_date"] <= df["original_due_date"])
    return float(on_time[eligible].sum() / eligible.sum())


def repeat_rate(findings: pd.DataFrame, as_of=None) -> float:
    """Share of findings flagged as repeat findings (NaN for an empty set)."""
    df = findings
    if as_of is not None:
        df = df[df["created_date"] <= pd.Timestamp(as_of)]
    return float(df["repeat_flag"].astype(bool).mean()) if len(df) else float("nan")


def ageing_buckets(findings: pd.DataFrame, as_of) -> pd.DataFrame:
    """Open findings by age since creation, split by risk rating.

    Returns long format: bucket, risk_rating, count (all bucket/risk cells present).
    """
    df = open_findings(findings, as_of)
    rows = []
    for label, lo, hi in AGEING_BUCKETS:
        in_bucket = df["age_days"] >= lo
        if hi is not None:
            in_bucket &= df["age_days"] <= hi
        for risk in RISK_ORDER:
            rows.append(
                {
                    "bucket": label,
                    "risk_rating": risk,
                    "count": int((in_bucket & (df["risk_rating"] == risk)).sum()),
                }
            )
    return pd.DataFrame(rows)


def risk_function_matrix(findings: pd.DataFrame, as_of) -> pd.DataFrame:
    """Open findings: rows = owner function, columns = risk rating (Critical..Low)."""
    df = open_findings(findings, as_of)
    pivot = pd.crosstab(df["owner_function"], df["risk_rating"])
    pivot = pivot.reindex(columns=RISK_ORDER, fill_value=0)
    return pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]


def root_cause_pareto(findings: pd.DataFrame, as_of=None) -> pd.DataFrame:
    """Findings per root cause, descending, with cumulative share."""
    df = findings if as_of is None else findings[findings["created_date"] <= pd.Timestamp(as_of)]
    counts = df["root_cause"].value_counts().rename_axis("root_cause").reset_index(name="count")
    total = counts["count"].sum()
    counts["cumulative_pct"] = counts["count"].cumsum() / total if total else 0.0
    return counts


def due_within(findings: pd.DataFrame, as_of, days: int = 30) -> pd.DataFrame:
    """Open findings whose current due date falls in [as_of, as_of + days]."""
    as_of = pd.Timestamp(as_of)
    df = open_findings(findings, as_of)
    mask = (df["due_date"] >= as_of) & (df["due_date"] <= as_of + pd.Timedelta(days=days))
    return df[mask].sort_values("due_date")


def function_scorecard(findings: pd.DataFrame, as_of) -> pd.DataFrame:
    """Per owner function: open, overdue, overdue %, average days overdue, avg revisions."""
    df = prepare(findings, as_of)
    rows = []
    for func, g in df.groupby("owner_function"):
        o = g[g["is_open"]]
        od = g[g["is_overdue"]]
        rows.append(
            {
                "owner_function": func,
                "open": len(o),
                "overdue": len(od),
                "overdue_pct": len(od) / len(o) if len(o) else float("nan"),
                "avg_days_overdue": float(od["days_overdue"].mean()) if len(od) else 0.0,
                "avg_revisions": float(g["revised_due_count"].mean()),
            }
        )
    cols = ["owner_function", "open", "overdue", "overdue_pct", "avg_days_overdue", "avg_revisions"]
    return pd.DataFrame(rows, columns=cols).sort_values("overdue", ascending=False)


def overdue_trend(findings: pd.DataFrame, updates: pd.DataFrame, as_of) -> pd.DataFrame:
    """Month-end history of open and overdue findings.

    The due date in force at each point is rebuilt from the updates log (original due date,
    then the latest "Due date revised" event on or before that date), so later extensions
    do not rewrite history.
    """
    as_of = pd.Timestamp(as_of)
    if findings.empty:
        return pd.DataFrame(columns=["date", "open", "overdue", "overdue_pct"])
    points = list(pd.date_range(findings["created_date"].min(), as_of, freq="ME"))
    if not points or points[-1] != as_of:
        points.append(as_of)
    revs = updates[updates["update_type"] == "Due date revised"].sort_values("update_date")
    rows = []
    for t in points:
        latest = revs[revs["update_date"] <= t].groupby("finding_id")["new_due_date"].last()
        due = findings["original_due_date"].where(
            ~findings["finding_id"].isin(latest.index), findings["finding_id"].map(latest.to_dict())
        )
        is_open = (findings["created_date"] <= t) & ~(
            findings["resolved_date"].notna() & (findings["resolved_date"] <= t)
        )
        n_open = int(is_open.sum())
        n_over = int((is_open & (due < t)).sum())
        rows.append(
            {
                "date": t,
                "open": n_open,
                "overdue": n_over,
                "overdue_pct": n_over / n_open if n_open else 0.0,
            }
        )
    return pd.DataFrame(rows)


def compute_kpis(findings: pd.DataFrame, as_of) -> dict:
    """Headline KPIs for a (possibly filtered) set of findings."""
    df = prepare(findings, as_of)
    return {
        "open": int(df["is_open"].sum()),
        "overdue": int(df["is_overdue"].sum()),
        "overdue_rate": overdue_rate(findings, as_of),
        "avg_days_overdue": avg_days_overdue(findings, as_of),
        "on_time_rate": implementation_within_due_rate(findings, as_of),
        "repeat_rate": repeat_rate(findings, as_of),
        "avg_revisions": float(df["revised_due_count"].mean()) if len(df) else 0.0,
        "total": len(df),
    }
