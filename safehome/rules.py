"""Fixed legal rules: hazard level and Awaab's Law deadlines.

These rules are deliberately simple and readable. An AI model can raise a case
to an emergency, but nothing here lets a model lower a level.

Deadlines follow the Awaab's Law guidance for social landlords in England:
- Emergency: investigate and make safe within 24 hours.
- Significant: investigate within 10 working days, make safe within 5 working
  days of the investigation.
- Written summary within 3 working days of the investigation.
- Further works started within 5 working days of the investigation.
Bank holidays are not counted as non-working days in this version.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .hazards import EMERGENCY, OFFICER_REVIEW, ROUTINE, SIGNIFICANT, STAGES
from .models import Case, Extraction

# Phrases that always make a report an emergency, whatever the model says.
EMERGENCY_TRIGGERS = [
    (r"\bgas\b", "possible gas leak"),
    (r"spark\w*", "sparks from electrics"),
    (r"(live|exposed) wires?|wires? hanging", "exposed wiring"),
    (r"ceiling (has )?(fallen|collapsed|came down|caved in)", "collapsed ceiling"),
    (r"hole in the (floor|floorboards)", "hole in the floor"),
    (r"(boiler|heating).{0,40}(completely )?(failed|broken down|stopped working).{0,60}(no|without) (heating|hot water)", "total loss of heating"),
]


@dataclass
class Decision:
    level: str
    reasons: list[str]


def decide_level(extraction: Extraction, text: str) -> Decision:
    triggers = [label for pattern, label in EMERGENCY_TRIGGERS if re.search(pattern, text, re.IGNORECASE)]

    if triggers or extraction.emergency_signals:
        reasons = []
        if triggers:
            reasons.append(f"Emergency rule matched: {', '.join(triggers)}")
        if extraction.emergency_signals:
            reasons.append("The report describes an imminent risk of harm")
        reasons.append("Investigate and make safe within 24 hours")
        return Decision(EMERGENCY, reasons)

    if extraction.hazard == "Unclear" or extraction.hazard_confidence == "Low":
        return Decision(OFFICER_REVIEW, [
            "The hazard is not clear enough to classify safely",
            "Treated as significant until an officer checks it",
        ])

    if extraction.hazard == "Routine repair":
        return Decision(ROUTINE, ["Minor repair with no health or safety risk described"])

    return Decision(SIGNIFICANT, [
        f"{extraction.hazard} is a significant hazard under Awaab's Law",
        "Investigate within 10 working days",
    ])


def add_working_days(start: datetime, days: int) -> datetime:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def working_days_between(start: datetime, end: datetime) -> int:
    if end <= start:
        return 0
    days = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


def investigation_deadline(case: Case) -> datetime | None:
    if case.level == EMERGENCY:
        return case.reported_at + timedelta(hours=24)
    if case.level in (SIGNIFICANT, OFFICER_REVIEW):
        return add_working_days(case.reported_at, 10)
    return None


def stage_plan(case: Case) -> list[dict]:
    """Each legal step with its rule, deadline and when it was done."""
    investigated = case.investigated_at
    deadlines = {
        "Reported": None,
        "Investigated": investigation_deadline(case),
        "Made safe": None,
        "Written summary sent": add_working_days(investigated, 3) if investigated else None,
        "Further works started": add_working_days(investigated, 5) if investigated else None,
    }
    if case.level == EMERGENCY:
        deadlines["Made safe"] = case.reported_at + timedelta(hours=24)
    elif investigated:
        deadlines["Made safe"] = add_working_days(investigated, 5)

    rules = {
        "Reported": "Logged when the report arrived",
        "Investigated": "Within 24 hours" if case.level == EMERGENCY else "Within 10 working days of the report",
        "Made safe": "As soon as possible, within 24 hours" if case.level == EMERGENCY
        else "Within 5 working days of the investigation",
        "Written summary sent": "Within 3 working days of the investigation, where required",
        "Further works started": "Within 5 working days of the investigation, or as soon as possible within 12 weeks",
    }

    plan = []
    for index, name in enumerate(STAGES):
        done_at = case.reported_at if index == 0 else (
            case.stage_times[index - 1] if index - 1 < len(case.stage_times) else None
        )
        due = deadlines[name]
        plan.append({
            "name": name,
            "rule": rules[name],
            "due_at": due.isoformat() if due else None,
            "done_at": done_at.isoformat() if done_at else None,
            "status": "done" if done_at else ("next" if index == case.stage + 1 else "waiting"),
        })
    return plan


def describe_due(deadline: datetime | None, now: datetime) -> str:
    if deadline is None:
        return "No legal deadline"
    if deadline <= now:
        return "Overdue"
    hours = (deadline - now).total_seconds() / 3600
    if hours < 48:
        whole = max(1, round(hours))
        return f"{whole} hour{'s' if whole != 1 else ''}"
    days = working_days_between(now, deadline)
    return f"{days} working day{'s' if days != 1 else ''}"
