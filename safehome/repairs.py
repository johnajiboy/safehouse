"""Repair Agent: shortlists approved repairers for a case.

Repairers are matched on trade first, then ranked on whether they can attend
before the deadline, how close they are and how often they fix a job first time.
An officer approves every booking.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache

from . import config
from .hazards import EMERGENCY, TRADE_FOR_HAZARD, TRADE_NAMES
from .models import Case
from .rules import investigation_deadline

# Each booking already made pushes a repairer's next free slot back by this much.
HOURS_PER_BOOKING = 3


@lru_cache
def load_repairers() -> list[dict]:
    with open(config.DATA_DIR / "repairers.json", encoding="utf-8") as f:
        return json.load(f)


def trade_for(case: Case) -> str | None:
    if case.hazard == "Hygiene and food safety":
        return "drainage" if re.search(r"drain|bath|sink|toilet|sewage", case.text, re.IGNORECASE) else "pest"
    return TRADE_FOR_HAZARD.get(case.hazard)


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def shortlist(case: Case, bookings: dict[str, int], now, limit: int = 3) -> list[dict]:
    """bookings maps repairer id -> number of jobs already booked for other cases."""
    trade = trade_for(case)
    if trade is None:
        return []

    deadline = investigation_deadline(case)
    hours_left = (deadline - now).total_seconds() / 3600 if deadline else 24 * 14

    matches = []
    for repairer in load_repairers():
        if trade not in repairer["trades"]:
            continue
        next_slot = repairer["next_slot_hours"] + HOURS_PER_BOOKING * bookings.get(repairer["id"], 0)
        in_time = next_slot <= hours_left
        km = None
        if case.lat is not None:
            km = distance_km(case.lat, case.lng, repairer["lat"], repairer["lng"])

        score = 42 if in_time else 8
        score += (repairer["first_time_fix"] - 75) * 1.3
        score += 14 if km is None else max(0, 26 - km * 4)
        if case.level == EMERGENCY and repairer["emergency_callouts"]:
            score += 6

        matches.append({
            "repairer": repairer,
            "trade": TRADE_NAMES[trade],
            "next_slot_hours": next_slot,
            "in_time": in_time,
            "distance_km": round(km, 1) if km is not None else None,
            "match": max(30, min(98, round(score))),
        })

    matches.sort(key=lambda m: m["match"], reverse=True)
    return matches[:limit]


def reasons_for(option: dict, case: Case) -> list[str]:
    """Plain-English reasons behind a shortlisted repairer, for the officer and the decision log."""
    repairer = option["repairer"]
    hours = option["next_slot_hours"]
    slot = f"{hours} hours" if hours < 24 else f"{round(hours / 24)} day{'s' if round(hours / 24) != 1 else ''}"
    reasons = [f"{option['trade']}: can attend in {slot}, "
               + ("before the deadline" if option["in_time"] else "after the deadline")]
    if option["distance_km"] is not None:
        reasons.append(f"{option['distance_km']} km away")
    reasons.append(f"{repairer['first_time_fix']}% of jobs fixed first time")
    if case.level == EMERGENCY and repairer["emergency_callouts"]:
        reasons.append("Takes emergency call-outs")
    return reasons
