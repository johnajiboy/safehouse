"""Joins the parts together: what happens when a report arrives or an officer acts."""
from __future__ import annotations

import json
import zlib
from datetime import datetime
from functools import lru_cache

from . import config, intake, messages, patterns, planner, repairs, rules, store
from .hazards import EMERGENCY, STAGES, VULNERABILITY_TYPES
from .models import Case


class NotFound(Exception):
    pass


class NotAllowed(Exception):
    pass


@lru_cache
def load_areas() -> dict:
    with open(config.DATA_DIR / "areas.json", encoding="utf-8") as f:
        return json.load(f)


def locate(address: str, area: str) -> tuple[float | None, float | None]:
    """Approximate map position: the area centre, nudged per building so pins don't overlap.

    Exact homes are deliberately not shown, to protect tenants' privacy.
    """
    centre = load_areas().get(area)
    if not centre:
        return None, None
    seed = zlib.crc32(patterns.building_of(address).encode())
    return (
        round(centre["lat"] + ((seed % 9) - 4) * 0.0012, 5),
        round(centre["lng"] + (((seed >> 4) % 9) - 4) * 0.0018, 5),
    )


def require_case(ref: str) -> Case:
    case = store.get_case(ref)
    if case is None:
        raise NotFound(f"No case {ref}")
    return case


# --- A report arrives ---------------------------------------------------------

def submit_report(text: str, address: str, area: str, contact: str = "", reported_at: datetime | None = None,
                  extraction=None, needs: list[str] | None = None) -> Case:
    extraction = extraction or intake.extract(text)
    needs = [n for n in VULNERABILITY_TYPES if n in (needs or [])]
    if needs:
        extraction.vulnerability = [n for n in VULNERABILITY_TYPES if n in needs or n in extraction.vulnerability]
        # The tenant has already told us about their household, so don't ask again.
        extraction.questions = [q for q in extraction.questions if not intake.asks_about_household(q)]
    decision = rules.decide_level(extraction, text)
    lat, lng = locate(address, area)
    case = Case(
        ref=store.next_ref(),
        text=text,
        address=address,
        area=area,
        reported_at=reported_at or datetime.now(),
        extraction=extraction,
        level=decision.level,
        level_reasons=decision.reasons,
        lat=lat,
        lng=lng,
        contact=contact,
        stated_needs=needs,
    )
    store.save_case(case)
    store.log("Intake Agent", f"Read the report: {case.hazard} ({case.level}), using {extraction.source}", case.ref)

    safety = messages.safety_message(case)
    if safety:
        store.add_message(case.ref, "Safety advice", safety, "sent")
        store.log("Intake Agent", "Sent the pre-approved emergency safety message", case.ref)
    recommend(case, case.reported_at)
    return case


# --- Repair Agent ---------------------------------------------------------------

def booking_counts(exclude: str | None = None) -> dict[str, int]:
    """Jobs already booked with each repairer, leaving out one case if given."""
    counts: dict[str, int] = {}
    for other in store.all_cases():
        if other.booking and other.ref != exclude:
            counts[other.booking["repairer_id"]] = counts.get(other.booking["repairer_id"], 0) + 1
    return counts


def recommend(case: Case, now: datetime, bookings: dict[str, int] | None = None) -> None:
    """Save the Repair Agent's top repairer on the case. It only suggests: an officer must approve the booking."""
    if case.booking:
        return
    options = repairs.shortlist(case, booking_counts(case.ref) if bookings is None else bookings, now, limit=1)
    new = None
    if options:
        top = options[0]
        new = {
            "repairer_id": top["repairer"]["id"],
            "repairer_name": top["repairer"]["name"],
            "match": top["match"],
            "reasons": repairs.reasons_for(top, case),
            "made_at": now.isoformat(timespec="minutes"),
        }
    old = case.recommendation
    if (old and new and (old["repairer_id"], old["match"]) == (new["repairer_id"], new["match"])) or old == new:
        return
    case.recommendation = new
    store.save_case(case)
    if new:
        store.log("Repair Agent", f"Recommended {new['repairer_name']} ({new['match']}% match): "
                  f"{'; '.join(new['reasons'])}. Waiting for officer approval", case.ref)
    else:
        store.log("Repair Agent", "No approved repairer is available to recommend", case.ref)


def refresh_recommendations(now: datetime) -> None:
    """Re-run the Repair Agent for every unbooked case, because bookings change who is free."""
    bookings = booking_counts()
    for case in store.all_cases():
        recommend(case, now, bookings)


# --- Views for the dashboard ----------------------------------------------------

def survey_groups(now: datetime) -> list[list[str]]:
    chosen = set(store.get_setting("surveys", []))
    return [c.refs for c in patterns.find_clusters(store.all_cases(), now) if c.key in chosen]


def current_plan(now: datetime, cases: list[Case] | None = None) -> planner.Plan:
    inspectors = store.get_setting("inspectors", config.DEFAULT_INSPECTORS)
    cases = store.all_cases() if cases is None else cases
    return planner.build_plan(cases, inspectors, now, survey_groups(now))


def summary(case: Case, now: datetime) -> dict:
    deadline = rules.investigation_deadline(case)
    if case.stage >= 1:
        due_text = "All steps recorded" if case.stage >= len(STAGES) - 1 else f"Next: {STAGES[case.stage + 1].lower()}"
    else:
        due_text = rules.describe_due(deadline, now)

    if case.level == EMERGENCY:
        urgency = 1.0
    elif deadline:
        total = (deadline - case.reported_at).total_seconds()
        urgency = min(1.0, max(0.06, 1 - (deadline - now).total_seconds() / total))
    else:
        urgency = 0.05

    return {
        "ref": case.ref,
        "address": case.address,
        "area": case.area,
        "hazard": case.hazard,
        "level": case.level,
        "due_text": due_text,
        "due_at": deadline.isoformat() if deadline else None,
        "due_soon": bool(deadline and deadline <= rules.add_working_days(now, 1)),
        "urgency": round(urgency, 2),
        "vulnerability": case.extraction.vulnerability,
        "repeat": case.extraction.repeat,
        "stage": case.stage,
        "visit_confirmed": case.visit_confirmed,
        "booked": bool(case.booking),
        "suggested": None if case.booking or not case.recommendation else {
            "name": case.recommendation["repairer_name"], "match": case.recommendation["match"]},
        "overridden": bool(case.pinned),
        "needs_review": case.extraction.hazard_confidence == "Low" or case.hazard == "Unclear",
        "lat": case.lat,
        "lng": case.lng,
    }


def plan_view(now: datetime) -> dict:
    plan = current_plan(now)
    cases = store.all_cases()
    clusters = patterns.find_clusters(cases, now)
    chosen = set(store.get_setting("surveys", []))
    open_cases = plan.today + plan.later
    return {
        "now": now.isoformat(timespec="minutes"),
        "inspectors": store.get_setting("inspectors", config.DEFAULT_INSPECTORS),
        "capacity": plan.capacity,
        "visits_used": plan.visits_used,
        "today": [summary(c, now) for c in plan.today],
        "later": [summary(c, now) for c in plan.later],
        "routine": [summary(c, now) for c in plan.routine],
        "investigated": [summary(c, now) for c in plan.investigated],
        "at_risk": [c.ref for c in plan.at_risk],
        "clusters": [{**vars(c), "grouped": c.key in chosen} for c in clusters],
        # One definition everywhere: open cases are those waiting for an investigation visit.
        # Routine repairs have no Awaab's Law deadline, so they are counted separately.
        "counts": {
            "open": len(open_cases),
            "today": len(plan.today),
            "routine": len(plan.routine),
            "emergencies": sum(c.level == EMERGENCY for c in open_cases),
            "booked_today": sum(bool(c.booking) for c in plan.today),
        },
    }


def findings(case: Case) -> list[dict]:
    ex = case.extraction
    unclear = rules.unclear_wording(case.text) if case.level != EMERGENCY else []
    vulnerability_quotes = ex.quotes("household")
    repeat_quotes = ex.quotes("repeat")
    return [
        {"field": "Hazard", "value": ex.hazard, "evidence": ex.quotes("hazard"), "confidence": ex.hazard_confidence,
         "note": "No clear hazard words" if not ex.quotes("hazard") else ""},
        {"field": "Level", "value": case.level, "evidence": ex.quotes("emergency"),
         "confidence": "Low" if unclear else "Set by rules",
         "note": "; ".join(unclear) if unclear else "Set by the legal rules"},
        {"field": "Household", "value": ", ".join(ex.vulnerability) or "No vulnerability stated",
         "evidence": vulnerability_quotes,
         "confidence": "High" if vulnerability_quotes or case.stated_needs
         else ("Low" if ex.vulnerability else "Medium"),
         "note": "Stated by the tenant on the report form" if case.stated_needs
         else ("" if vulnerability_quotes else "Nothing in the report")},
        {"field": "Repeat", "value": "Reported before" if ex.repeat else "Not stated", "evidence": repeat_quotes,
         "confidence": "High" if repeat_quotes else ("Low" if ex.repeat else "Medium"),
         "note": "" if repeat_quotes else "Nothing in the report"},
    ]


def case_view(ref: str, now: datetime) -> dict:
    case = require_case(ref)
    plan = current_plan(now)
    view = summary(case, now)
    view.update({
        "text": case.text,
        "contact": case.contact,
        "reported_at": case.reported_at.isoformat(timespec="minutes"),
        "source": case.extraction.source,
        "evidence": [vars(e) for e in case.extraction.evidence],
        "findings": findings(case),
        "level_reasons": case.level_reasons,
        "score": [{"reason": r, "points": p} for r, p in planner.score_breakdown(case, now)],
        "questions": case.extraction.questions,
        "stages": rules.stage_plan(case),
        "in_today": any(c.ref == ref for c in plan.today),
        "override_reason": case.override_reason,
        "booking": case.booking,
        "recommendation": case.recommendation,
        "messages": store.messages_for(ref),
        "trade_needed": repairs.trade_for(case) is not None,
    })
    return view


def repairer_options(ref: str, now: datetime) -> list[dict]:
    case = require_case(ref)
    return repairs.shortlist(case, booking_counts(ref), now)


def repairers_view() -> list[dict]:
    jobs = {}
    for case in store.all_cases():
        if case.booking:
            jobs.setdefault(case.booking["repairer_id"], []).append(
                {"ref": case.ref, "lat": case.lat, "lng": case.lng, "address": case.address}
            )
    return [{**r, "jobs": jobs.get(r["id"], [])} for r in repairs.load_repairers()]


# --- Officer actions --------------------------------------------------------------

def confirm_visit(ref: str) -> None:
    case = require_case(ref)
    case.visit_confirmed = True
    store.save_case(case)
    store.add_message(ref, "Visit confirmation", messages.visit_draft(case), "draft")
    store.log("Officer", "Confirmed today's inspection visit", ref)


def move(ref: str, to: str, reason: str, note: str = "", now: datetime | None = None) -> None:
    if to not in ("today", "later"):
        raise NotAllowed("Cases can only be moved to today or later")
    if not reason:
        raise NotAllowed("A reason is required for every override")
    case = require_case(ref)
    if to == "today":
        check_no_emergency_bumped(case, now or datetime.now())
    case.pinned = to
    case.override_reason = reason + (f" ({note})" if note else "")
    if to == "later":
        case.visit_confirmed = False
    store.save_case(case)
    store.log("Officer", f"Override: moved to {to}. Reason: {case.override_reason}", ref)


def check_no_emergency_bumped(case: Case, now: datetime) -> None:
    """Refuse a "today" override that would push an emergency out of today's visits."""
    cases = store.all_cases()
    waiting_before = {c.ref for c in current_plan(now, cases).later}
    for c in cases:
        if c.ref == case.ref:
            c.pinned = "today"
    bumped = [c for c in current_plan(now, cases).later if c.level == EMERGENCY and c.ref not in waiting_before]
    if bumped:
        names = ", ".join(f"{c.address} ({c.ref})" for c in bumped)
        raise NotAllowed(
            f"Moving {case.address} to today would push the emergency at {names} out of today's visits. "
            "Add an inspector or move a non-emergency case to later first."
        )


def record_stage(ref: str, now: datetime) -> str:
    case = require_case(ref)
    if case.stage >= len(STAGES) - 1:
        raise NotAllowed("All legal steps are already recorded")
    case.stage_times.append(now)
    store.save_case(case)
    step = STAGES[case.stage]
    store.log("Officer", f"Recorded: {step.lower()}", ref)
    if step == "Investigated":
        store.add_message(ref, "Written summary", messages.written_summary_draft(case), "draft")
        store.log("Intake Agent", "Drafted the written summary for officer approval", ref)
    return step


def book(ref: str, repairer_id: str, now: datetime, reason: str = "", note: str = "") -> str:
    """An officer approves a booking. Choosing someone other than the Repair Agent's suggestion needs a reason."""
    case = require_case(ref)
    if case.booking:
        raise NotAllowed("This case already has a booking")
    repairer = next((r for r in repairs.load_repairers() if r["id"] == repairer_id), None)
    if repairer is None:
        raise NotFound(f"No repairer {repairer_id}")
    suggested = case.recommendation
    differs = suggested is not None and suggested["repairer_id"] != repairer_id
    if differs and not reason:
        raise NotAllowed(f"The Repair Agent suggested {suggested['repairer_name']}. "
                         "Give a reason for choosing a different repairer.")
    case.booking = {"repairer_id": repairer_id, "repairer_name": repairer["name"],
                    "booked_at": now.isoformat(timespec="minutes")}
    store.save_case(case)
    store.add_message(ref, "Repair booking", messages.booking_draft(case, repairer["name"]), "draft")
    if differs:
        store.log("Officer", f"Approved and booked {repairer['name']} instead of the suggested "
                  f"{suggested['repairer_name']}. Reason: {reason}" + (f" ({note})" if note else ""), ref)
    else:
        store.log("Officer", f"Approved and booked {repairer['name']}", ref)
    refresh_recommendations(now)
    return repairer["name"]


def cancel_booking(ref: str, reason: str, note: str = "", now: datetime | None = None) -> None:
    if not reason:
        raise NotAllowed("A reason is required to cancel a booking")
    case = require_case(ref)
    if not case.booking:
        raise NotAllowed("This case has no booking")
    name = case.booking["repairer_name"]
    case.booking = None
    store.save_case(case)
    store.log("Officer", f"Cancelled the booking with {name}. Reason: {reason}" + (f" ({note})" if note else ""), ref)
    refresh_recommendations(now or datetime.now())


def approve_message(message_id: int, body: str | None = None) -> None:
    message = store.get_message(message_id)
    if message is None:
        raise NotFound(f"No message {message_id}")
    if message["status"] == "sent":
        raise NotAllowed("This message has already been sent")
    store.mark_sent(message_id, body)
    store.log("Officer", f"Approved and sent: {message['kind'].lower()}", message["case_ref"])


def set_inspectors(count: int) -> None:
    if not 1 <= count <= 20:
        raise NotAllowed("Inspectors must be between 1 and 20")
    store.set_setting("inspectors", count)
    store.log("Officer", f"Set inspectors on shift to {count}")


def toggle_survey(key: str, now: datetime) -> bool:
    clusters = {c.key: c for c in patterns.find_clusters(store.all_cases(), now)}
    if key not in clusters:
        raise NotFound("No such building pattern")
    chosen = set(store.get_setting("surveys", []))
    grouped = key not in chosen
    chosen.symmetric_difference_update({key})
    store.set_setting("surveys", sorted(chosen))
    store.log("Officer", f"{'Grouped' if grouped else 'Ungrouped'} the {clusters[key].building} reports into one survey")
    return grouped
