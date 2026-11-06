"""Planner: ranks open cases and fits them to today's inspection capacity."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import config
from .hazards import EMERGENCY, ROUTINE
from .models import Case
from .rules import add_working_days, investigation_deadline


def score_breakdown(case: Case, now: datetime) -> list[tuple[str, int]]:
    """The points behind a case's priority, so officers can see why it ranks where it does."""
    parts = []
    if case.level == EMERGENCY:
        parts.append(("Possible emergency", 1000))

    deadline = investigation_deadline(case)
    if deadline and deadline <= add_working_days(now, 1):
        parts.append(("Investigation due within a working day", 500))
    elif deadline and deadline <= add_working_days(now, 3):
        parts.append(("Investigation due within 3 working days", 150))

    for need in case.extraction.vulnerability:
        parts.append((f"Vulnerable household: {need.lower()}", 60))
    if case.extraction.repeat:
        parts.append(("Reported before", 30))

    waiting_days = min(10, (now - case.reported_at).days)
    if waiting_days:
        parts.append((f"Waiting {waiting_days} day{'s' if waiting_days != 1 else ''}", 5 * waiting_days))
    return parts


def priority(case: Case, now: datetime) -> int:
    return sum(points for _, points in score_breakdown(case, now))


@dataclass
class Plan:
    today: list[Case] = field(default_factory=list)
    later: list[Case] = field(default_factory=list)
    investigated: list[Case] = field(default_factory=list)
    routine: list[Case] = field(default_factory=list)
    at_risk: list[Case] = field(default_factory=list)
    visits_used: int = 0
    capacity: int = 0


def build_plan(cases: list[Case], inspectors: int, now: datetime, survey_groups: list[list[str]] | None = None) -> Plan:
    """Fill today's visits in priority order. A grouped building survey uses one visit."""
    plan = Plan(capacity=inspectors * config.VISITS_PER_INSPECTOR)
    plan.investigated = [c for c in cases if c.stage >= 1]
    plan.routine = [c for c in cases if c.stage == 0 and c.level == ROUTINE]
    waiting = [c for c in cases if c.stage == 0 and c.level != ROUTINE]

    # Officer overrides go first or last; everything else by score, then oldest first.
    waiting.sort(key=lambda c: (
        0 if c.pinned == "today" else 2 if c.pinned == "later" else 1,
        -priority(c, now),
        c.reported_at,
    ))

    group_of = {}
    for group in survey_groups or []:
        for ref in group:
            group_of[ref] = tuple(group)
    groups_counted = set()

    for case in waiting:
        group = group_of.get(case.ref)
        costs_a_visit = not (group and group in groups_counted)
        if not costs_a_visit or plan.visits_used < plan.capacity:
            plan.today.append(case)
            if costs_a_visit:
                plan.visits_used += 1
            if group:
                groups_counted.add(group)
        else:
            plan.later.append(case)

    plan.at_risk = [c for c in plan.later if may_miss_deadline(c, now)]
    return plan


def may_miss_deadline(case: Case, now: datetime) -> bool:
    """A case left for later is at risk if its investigation is due by the end of the next working day."""
    if case.level == EMERGENCY:
        return True
    deadline = investigation_deadline(case)
    return deadline is not None and deadline <= add_working_days(now, 1)
