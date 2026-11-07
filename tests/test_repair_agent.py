from datetime import datetime, timedelta

import pytest

from safehome import repairs, service, store

NOW = datetime(2026, 11, 6, 10, 0)


def add(text, address="1 Test Street", area="Newport"):
    return service.submit_report(text, address, area, reported_at=NOW - timedelta(hours=1))


def agent_log(ref):
    return [e["action"] for e in store.read_log() if e["case_ref"] == ref and e["actor"] == "Repair Agent"]


def test_repair_agent_suggests_when_a_report_arrives_but_never_books():
    case = store.get_case(add("Smell of gas in the kitchen").ref)
    rec = case.recommendation
    assert rec and rec["match"] > 0 and rec["reasons"]
    assert case.booking is None
    assert any(rec["repairer_name"] in a and "Waiting for officer approval" in a for a in agent_log(case.ref))


def test_suggestion_shows_on_the_case_row_until_booked():
    case = add("Smell of gas in the kitchen")
    row = next(c for c in service.plan_view(NOW)["today"] if c["ref"] == case.ref)
    assert row["suggested"] == {"name": case.recommendation["repairer_name"], "match": case.recommendation["match"]}
    service.book(case.ref, case.recommendation["repairer_id"], NOW)
    row = next(c for c in service.plan_view(NOW)["today"] if c["ref"] == case.ref)
    assert row["suggested"] is None and row["booked"]


def test_approving_the_suggestion_needs_no_reason():
    case = add("Smell of gas in the kitchen")
    assert service.book(case.ref, case.recommendation["repairer_id"], NOW) == case.recommendation["repairer_name"]


def test_choosing_a_different_repairer_needs_a_reason():
    case = add("Smell of gas in the kitchen")
    other = next(r["id"] for r in repairs.load_repairers()
                 if "gas" in r["trades"] and r["id"] != case.recommendation["repairer_id"])
    with pytest.raises(service.NotAllowed, match="reason"):
        service.book(case.ref, other, NOW)
    assert store.get_case(case.ref).booking is None
    service.book(case.ref, other, NOW, reason="Tenant asked for this repairer")
    assert store.get_case(case.ref).booking["repairer_id"] == other
    assert any("instead of the suggested" in e["action"] and "Tenant asked" in e["action"] for e in store.read_log())


def test_suggestions_refresh_when_bookings_change(monkeypatch):
    monkeypatch.setattr(repairs, "HOURS_PER_BOOKING", 1000)  # one booking makes a repairer too late
    first = add("Smell of gas in the kitchen", address="1 Test Street")
    second = add("Smell of gas in the hall", address="2 Test Street")
    favourite = second.recommendation["repairer_id"]
    service.book(first.ref, first.recommendation["repairer_id"], NOW)
    assert first.recommendation["repairer_id"] == favourite
    changed = store.get_case(second.ref).recommendation
    assert changed["repairer_id"] != favourite
    assert any(changed["repairer_name"] in a for a in agent_log(second.ref))

    service.cancel_booking(first.ref, reason="Repairer unavailable", now=NOW)
    assert store.get_case(second.ref).recommendation["repairer_id"] == favourite


def test_no_suggestion_without_a_trade():
    case = add("Something is wrong but I'm not sure what it is")
    assert store.get_case(case.ref).recommendation is None
