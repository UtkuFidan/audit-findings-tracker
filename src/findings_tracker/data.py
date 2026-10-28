"""CSV loading."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data"


def load_data(
    data_dir: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Return (audits, findings, updates, as_of) from a directory of generated CSVs."""
    d = Path(data_dir) if data_dir else DEFAULT_DIR
    audits = pd.read_csv(
        d / "audits.csv", parse_dates=["period_start", "period_end", "report_date"]
    )
    findings = pd.read_csv(
        d / "findings.csv",
        parse_dates=["created_date", "original_due_date", "due_date", "resolved_date"],
    )
    findings["repeat_flag"] = findings["repeat_flag"].astype(bool)
    updates = pd.read_csv(d / "updates.csv", parse_dates=["update_date", "new_due_date"])
    as_of = pd.Timestamp(json.loads((d / "meta.json").read_text())["as_of"])
    return audits, findings, updates, as_of
