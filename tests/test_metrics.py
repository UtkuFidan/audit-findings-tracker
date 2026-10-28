import pandas as pd
import pytest

from findings_tracker import metrics
from findings_tracker.generate import generate
from findings_tracker.summary import build_summary

AS_OF = pd.Timestamp("2026-06-30")


def make(rows):
    base = {
        "audit_id": "AUD-001",
        "risk_rating": "Medium",
        "root_cause": "Data quality",
        "owner_function": "IT",
        "created_date": "2026-01-01",
        "original_due_date": "2026-03-31",
        "due_date": "2026-03-31",
        "resolved_date": None,
        "status": "Open",
        "revised_due_count": 0,
        "repeat_flag": False,
    }
    df = pd.DataFrame([{**base, "finding_id": f"F-{i}", **r} for i, r in enumerate(rows)])
    for c in ["created_date", "original_due_date", "due_date", "resolved_date"]:
        df[c] = pd.to_datetime(df[c])
    return df


def test_overdue_uses_revised_due_date():
    df = make(
        [
            {},  # due 31 Mar, still open -> overdue by 91 days
            {"due_date": "2026-09-30", "revised_due_count": 1},  # extended -> not overdue
            {"resolved_date": "2026-03-01", "status": "Implemented"},  # closed
        ]
    )
    p = metrics.prepare(df, AS_OF)
    assert list(p["is_overdue"]) == [True, False, False]
    assert p.loc[0, "days_overdue"] == 91
    assert metrics.overdue_rate(df, AS_OF) == pytest.approx(0.5)
    assert metrics.avg_days_overdue(df, AS_OF) == 91
    assert p.loc[0, "effective_status"] == "Overdue"


def test_resolution_after_as_of_counts_as_open():
    df = make([{"resolved_date": "2026-08-01", "status": "Implemented"}])
    assert metrics.prepare(df, AS_OF)["is_open"].all()


def test_ageing_buckets():
    df = make(
        [
            {"created_date": "2026-06-20"},  # 10 days
            {"created_date": "2026-05-01", "risk_rating": "High"},  # 60 days
            {"created_date": "2025-01-01", "risk_rating": "High"},  # > 365
            {"created_date": "2026-01-01", "resolved_date": "2026-02-01", "status": "Validated"},
        ]
    )
    a = metrics.ageing_buckets(df, AS_OF)
    cell = lambda b, r: int(a[(a.bucket == b) & (a.risk_rating == r)]["count"].iloc[0])  # noqa: E731
    assert cell("0-30 days", "Medium") == 1
    assert cell("31-90 days", "High") == 1
    assert cell("> 365 days", "High") == 1
    assert a["count"].sum() == 3


def test_repeat_rate():
    df = make([{"repeat_flag": True}, {}, {}, {"repeat_flag": True}])
    assert metrics.repeat_rate(df, AS_OF) == 0.5
    assert pd.isna(metrics.repeat_rate(df.iloc[0:0]))


def test_implementation_within_original_due_date():
    df = make(
        [
            {"resolved_date": "2026-03-15", "status": "Implemented"},  # on time
            {"resolved_date": "2026-04-30", "status": "Validated"},  # late
            {"due_date": "2026-09-30", "original_due_date": "2026-03-31", "revised_due_count": 1},
            # unresolved, original date passed -> counts as miss even though extended
            {"original_due_date": "2026-12-31", "due_date": "2026-12-31"},  # not yet due: excluded
            {"status": "Risk accepted", "resolved_date": "2026-02-01"},  # excluded
        ]
    )
    assert metrics.implementation_within_due_rate(df, AS_OF) == pytest.approx(1 / 3)


def test_overdue_trend_rebuilds_due_dates_from_log():
    df = make([{"due_date": "2026-05-31", "revised_due_count": 1}])
    log = pd.DataFrame(
        [
            {
                "finding_id": "F-0",
                "update_date": pd.Timestamp("2026-03-20"),
                "update_type": "Due date revised",
                "new_due_date": pd.Timestamp("2026-05-31"),
            }
        ]
    )
    t = metrics.overdue_trend(df, log, AS_OF).set_index("date")["overdue"]
    assert t[pd.Timestamp("2026-03-31")] == 0  # extension already agreed
    assert t[pd.Timestamp("2026-06-30")] == 1


def test_due_within_and_pareto():
    df = make(
        [
            {"due_date": "2026-07-10"},
            {"due_date": "2026-09-01"},
            {"root_cause": "Data quality"},
            {"root_cause": "Process design gap"},
        ]
    )
    assert list(metrics.due_within(df, AS_OF, 30)["finding_id"]) == ["F-0"]
    p = metrics.root_cause_pareto(df)
    assert p.iloc[0]["root_cause"] == "Data quality"
    assert p["cumulative_pct"].iloc[-1] == pytest.approx(1.0)


def test_generator_is_deterministic_and_consistent():
    a1, f1, u1, _ = generate(7)
    _, f2, _, _ = generate(7)
    assert f1.equals(f2)
    assert 350 <= len(f1) <= 450
    assert set(f1["risk_rating"]) == {"Critical", "High", "Medium", "Low"}
    assert (pd.to_datetime(f1["due_date"]) >= pd.to_datetime(f1["original_due_date"])).all()
    assert (
        f1["revised_due_count"]
        == (u1["update_type"] == "Due date revised")
        .groupby(u1["finding_id"])
        .sum()
        .reindex(f1["finding_id"])
        .fillna(0)
        .values
    ).all()


def test_summary_is_deterministic_text():
    _, f, _, as_of = generate(7)
    for c in ["created_date", "original_due_date", "due_date", "resolved_date"]:
        f[c] = pd.to_datetime(f[c].replace("", None))
    text = build_summary(f, pd.Timestamp(as_of["as_of"]))
    assert text == build_summary(f, pd.Timestamp(as_of["as_of"]))
    assert "overdue" in text
