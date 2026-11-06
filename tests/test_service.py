from datetime import datetime, timedelta

import pytest

from safehome import patterns, planner, service, store

NOW = datetime(2026, 11, 6, 10, 0)


def add(text, address="1 Test Street", area="Linthorpe", hours_ago=1):
    return service.submit_report(text, address, area, reported_at=NOW - timedelta(hours=hours_ago))


def test_emergencies_come_first_in_the_plan():
    add("Damp patch on the wall")
    add("Strong smell of gas in the hall")
    plan = planner.build_plan(store.all_cases(), inspectors=1, now=NOW)
    assert plan.today[0].hazard == "Fire and explosions"


def test_capacity_limits_today():
    for i in range(5):
        add(f"Mould on the wall in room {i}", address=f"{i} Test Street")
    plan = planner.build_plan(store.all_cases(), inspectors=1, now=NOW)
    assert len(plan.today) == 3
    assert len(plan.later) == 2


def test_emergency_sends_a_safety_message_straight_away():
    case = add("I can smell gas near the boiler")
    sent = [m for m in store.messages_for(case.ref) if m["status"] == "sent"]
    assert sent and "0800 111 999" in sent[0]["body"]


def test_other_messages_wait_for_approval():
    case = add("Mould in the bathroom")
    service.confirm_visit(case.ref)
    drafts = [m for m in store.messages_for(case.ref) if m["status"] == "draft"]
    assert len(drafts) == 1


def test_overrides_need_a_reason():
    case = add("Mould in the bathroom")
    with pytest.raises(service.NotAllowed):
        service.move(case.ref, "later", reason="")
    service.move(case.ref, "later", reason="Tenant not available today")
    assert "Tenant not available" in store.get_case(case.ref).override_reason


def test_investigated_cases_leave_the_inspection_plan():
    case = add("Mould in the bathroom")
    service.record_stage(case.ref, NOW)
    plan = planner.build_plan(store.all_cases(), inspectors=2, now=NOW)
    assert case.ref not in [c.ref for c in plan.today + plan.later]


def test_three_damp_reports_in_one_building_are_linked():
    add("Black mould in the bedroom", address="Flat 1, Elm House", area="Berwick Hills")
    add("Damp walls in the lounge", address="Flat 5, Elm House", area="Berwick Hills")
    add("Flat is freezing, the radiators are cold", address="Flat 8, Elm House", area="Berwick Hills")
    clusters = patterns.find_clusters(store.all_cases(), NOW)
    assert len(clusters) == 1 and clusters[0].building == "Elm House"


def test_grouped_survey_uses_one_visit():
    for flat in (1, 5, 8):
        add("Black mould in the bedroom", address=f"Flat {flat}, Elm House", area="Berwick Hills")
    groups = [c.refs for c in patterns.find_clusters(store.all_cases(), NOW)]
    plan = planner.build_plan(store.all_cases(), inspectors=1, now=NOW, survey_groups=groups)
    assert len(plan.today) == 3
    assert plan.visits_used == 1


def test_gas_jobs_go_to_a_gas_engineer():
    case = add("Smell of gas in the kitchen", area="Newport")
    options = service.repairer_options(case.ref, NOW)
    assert options and all("gas" in o["repairer"]["trades"] for o in options)


def test_a_case_cannot_be_booked_twice():
    case = add("Smell of gas in the kitchen", area="Newport")
    service.book(case.ref, "northline", NOW)
    with pytest.raises(service.NotAllowed):
        service.book(case.ref, "southfield", NOW)
