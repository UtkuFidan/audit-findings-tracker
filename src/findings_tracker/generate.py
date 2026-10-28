"""Seeded synthetic data generator. Everything here is invented."""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

AS_OF = date(2026, 9, 30)
START = date(2023, 10, 1)
LAST_REPORT = date(2026, 9, 12)

# function: (P(on time), lateness scale, P(extension | late), P(stuck | late))
FUNCTIONS = {
    "Finance": (0.80, 0.8, 0.15, 0.08),
    "Procurement": (0.42, 1.4, 0.55, 0.32),  # chronically late
    "IT": (0.38, 1.5, 0.60, 0.35),  # chronically late
    "HR": (0.75, 0.9, 0.20, 0.10),
    "Operations": (0.60, 1.1, 0.35, 0.18),
    "Sales": (0.65, 1.0, 0.30, 0.15),
    "Compliance": (0.85, 0.7, 0.10, 0.06),
    "Legal": (0.70, 0.9, 0.20, 0.10),
}

# entity, owning function, audit type
UNIVERSE = [
    ("Accounts Payable", "Finance", "Financial"),
    ("Payroll", "HR", "Financial"),
    ("Treasury", "Finance", "Financial"),
    ("Financial Close", "Finance", "Financial"),
    ("Expense Management", "Finance", "Financial"),
    ("Vendor Onboarding", "Procurement", "Operational"),
    ("Purchasing", "Procurement", "Operational"),
    ("Third-Party Risk", "Procurement", "Compliance"),
    ("Contract Management", "Legal", "Compliance"),
    ("Records Management", "Legal", "Compliance"),
    ("Identity & Access Management", "IT", "IT"),
    ("Change Management", "IT", "IT"),
    ("Backup & Recovery", "IT", "IT"),
    ("Cloud Security", "IT", "IT"),
    ("Recruitment", "HR", "Operational"),
    ("Warehouse & Inventory", "Operations", "Operational"),
    ("Logistics", "Operations", "Operational"),
    ("Quality Control", "Operations", "Operational"),
    ("Facilities Safety", "Operations", "Compliance"),
    ("Order-to-Cash", "Sales", "Financial"),
    ("Pricing & Discounts", "Sales", "Operational"),
    ("Customer Onboarding", "Compliance", "Compliance"),
    ("Data Privacy", "Compliance", "Compliance"),
    ("Regulatory Reporting", "Compliance", "Compliance"),
]

ROOT_CAUSES = {
    "Process design gap": [
        "Approval workflow does not cover all transaction types",
        "No documented procedure for exception handling",
        "Handover between teams leaves a control gap",
    ],
    "Manual control / human error": [
        "Reconciliations contain unreviewed manual adjustments",
        "Spreadsheet-based calculations lack independent checks",
        "Data entry errors not detected before posting",
    ],
    "Inadequate oversight": [
        "Management review evidence is missing or undated",
        "Key risk indicators are not reported to the owner",
        "Segregation of duties conflicts not monitored",
    ],
    "Policy not followed": [
        "Required approvals obtained after the fact",
        "Policy exceptions granted without documented rationale",
        "Retention and filing rules applied inconsistently",
    ],
    "System / access control": [
        "Periodic user access reviews not performed on schedule",
        "Privileged accounts without timely removal on role change",
        "System changes moved to production without testing evidence",
    ],
    "Training / awareness": [
        "Staff unaware of updated procedures",
        "Mandatory training completion below target",
    ],
    "Third-party management": [
        "Supplier performance not assessed against contract terms",
        "Due diligence refresh overdue for key suppliers",
    ],
    "Data quality": [
        "Master data contains duplicates and stale records",
        "Source-to-report data lineage is undocumented",
    ],
}
CAUSE_WEIGHTS = [20, 18, 14, 14, 16, 6, 6, 6]

RISKS = ["Critical", "High", "Medium", "Low"]
RISK_WEIGHTS = [5, 25, 45, 25]
DUE_OFFSET = {"Critical": (45, 100), "High": (75, 160), "Medium": (110, 240), "Low": (150, 330)}

COMMENTS = {
    "raised": "Finding issued in audit report; action plan agreed with owner.",
    "progress": "Owner has started implementing the agreed action.",
    "revised": "Owner requested a new date; resourcing and dependencies cited.",
    "implemented": "Owner reports the action as implemented; evidence submitted.",
    "validated": "Internal audit reviewed the evidence and validated closure.",
    "accepted": "Risk accepted by management; documented in the risk register.",
}


def _d(d: date, days: float) -> date:
    return d + timedelta(days=int(days))


def generate(seed: int = 7):
    """Return (audits, findings, updates, meta) as DataFrames / dict."""
    rng = random.Random(seed)

    # --- audit schedule: every entity once, then 12 re-audits at least ~6 months later
    span = (LAST_REPORT - START).days
    schedule, first_day = [], {}
    for ent in UNIVERSE:
        first_day[ent[0]] = rng.randint(0, int(span * 0.8))
        schedule.append((first_day[ent[0]], ent, False))
    for ent in rng.sample(UNIVERSE, 12):
        schedule.append(
            (rng.randint(max(first_day[ent[0]] + 180, span - 330), span - 1), ent, True)
        )
    schedule.sort(key=lambda t: t[0])

    audit_rows = []
    findings, updates = [], []
    history: dict[str, list[dict]] = {}
    fid = 0
    for n, (day, (entity, func, atype), is_reaudit) in enumerate(schedule, start=1):
        report = _d(START, day)
        period_end = _d(report, -rng.randint(40, 75))
        audit_id = f"AUD-{n:03d}"
        prior = history.get(entity, [])
        rows = []
        for _ in range(rng.randint(7, 15)):
            fid += 1
            owner = func if rng.random() < 0.8 else rng.choice(list(FUNCTIONS))
            risk = rng.choices(RISKS, RISK_WEIGHTS)[0]
            cause = rng.choices(list(ROOT_CAUSES), CAUSE_WEIGHTS)[0]
            title = rng.choice(ROOT_CAUSES[cause])
            repeat = False
            if prior and rng.random() < 0.40 + (0.10 if owner in ("IT", "Procurement") else 0):
                src = rng.choice(prior)
                title, cause, owner, repeat = src["title"], src["root_cause"], src["owner"], True
            rows.append(
                _simulate_finding(
                    rng,
                    f"F-{fid:04d}",
                    audit_id,
                    title,
                    risk,
                    cause,
                    owner,
                    report,
                    repeat,
                    updates,
                )
            )
        history.setdefault(entity, []).extend(
            {"title": r["title"], "root_cause": r["root_cause"], "owner": r["owner_function"]}
            for r in rows
        )
        findings.extend(rows)
        sev = sum(r["risk_rating"] in ("Critical", "High") for r in rows) / len(rows)
        rating = (
            "Unsatisfactory"
            if sev > 0.42
            else "Needs improvement"
            if sev > 0.22
            else "Satisfactory"
        )
        audit_rows.append(
            {
                "audit_id": audit_id,
                "entity": entity,
                "audit_type": "Follow-up" if is_reaudit and rng.random() < 0.4 else atype,
                "period_start": _d(period_end, -364).isoformat(),
                "period_end": period_end.isoformat(),
                "report_date": report.isoformat(),
                "rating": rating,
            }
        )

    fdf = pd.DataFrame(findings).sort_values("finding_id")
    udf = pd.DataFrame(updates).sort_values(["update_date", "finding_id"], kind="stable")
    udf.insert(0, "update_id", [f"U-{i:05d}" for i in range(1, len(udf) + 1)])
    meta = {"as_of": AS_OF.isoformat(), "seed": seed, "synthetic": True}
    return pd.DataFrame(audit_rows), fdf, udf, meta


def _simulate_finding(rng, fid, audit_id, title, risk, cause, owner, created, repeat, updates):
    p_on, scale, p_ext, p_stuck = FUNCTIONS[owner]
    lo, hi = DUE_OFFSET[risk]
    offset = rng.randint(lo, hi)
    orig_due = _d(created, offset)

    def log(day, kind, comment, old=None, new=None, status=None):
        updates.append(
            {
                "finding_id": fid,
                "update_date": day.isoformat(),
                "update_type": kind,
                "old_due_date": old.isoformat() if old else "",
                "new_due_date": new.isoformat() if new else "",
                "new_status": status or "",
                "comment": comment,
            }
        )

    log(created, "Finding raised", COMMENTS["raised"], new=orig_due, status="Open")

    resolved, status, revisions = None, "Open", 0
    due = orig_due
    if risk != "Critical" and rng.random() < 0.04:
        resolved = _d(created, rng.randint(20, 120))
        status = "Risk accepted"
        log(resolved, "Status change", COMMENTS["accepted"], status=status)
    else:
        if rng.random() < p_on:
            done = _d(orig_due, -rng.uniform(0, 0.2 * offset))
        else:
            done = _d(orig_due, rng.uniform(10, 90) * scale * rng.choice([1, 1, 2, 3]))
            if rng.random() < p_stuck:  # action stalls well beyond the reporting date
                done = _d(orig_due, rng.randint(400, 900))
        late = done > orig_due
        while late and revisions < 3 and rng.random() < (p_ext if revisions == 0 else 0.65):
            rev_day = _d(due, -rng.randint(0, 25))
            if rev_day <= created or rev_day >= done or rev_day > AS_OF or due >= done:
                break
            new_due = _d(due, rng.randint(30, 120))
            log(rev_day, "Due date revised", COMMENTS["revised"], old=due, new=new_due)
            due, revisions = new_due, revisions + 1
        start = _d(created, rng.randint(7, 40))
        if done <= AS_OF:
            resolved = max(done, _d(created, 3))
            if start < resolved:
                log(start, "Status change", COMMENTS["progress"], status="In progress")
            log(resolved, "Status change", COMMENTS["implemented"], status="Implemented")
            status = "Implemented"
            val = _d(resolved, rng.randint(15, 60))
            if rng.random() < 0.7 and val <= AS_OF:
                log(val, "Status change", COMMENTS["validated"], status="Validated")
                status = "Validated"
        else:
            if start <= AS_OF and rng.random() < 0.65:
                log(start, "Status change", COMMENTS["progress"], status="In progress")
                status = "In progress"
            if due < AS_OF:
                status = "Overdue"
    return {
        "finding_id": fid,
        "audit_id": audit_id,
        "title": title,
        "risk_rating": risk,
        "root_cause": cause,
        "owner_function": owner,
        "created_date": created.isoformat(),
        "original_due_date": orig_due.isoformat(),
        "due_date": due.isoformat(),
        "resolved_date": resolved.isoformat() if resolved else "",
        "status": status,
        "revised_due_count": revisions,
        "repeat_flag": repeat,
    }


def write_dataset(out: Path, seed: int = 7) -> dict[str, int]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    audits, findings, updates, meta = generate(seed)
    audits.to_csv(out / "audits.csv", index=False)
    findings.to_csv(out / "findings.csv", index=False)
    updates.to_csv(out / "updates.csv", index=False)
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return {"audits": len(audits), "findings": len(findings), "updates": len(updates)}
