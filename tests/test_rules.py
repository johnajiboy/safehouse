from datetime import datetime

from safehome import intake, rules
from safehome.hazards import EMERGENCY, OFFICER_REVIEW, ROUTINE, SIGNIFICANT


def level_of(text):
    return rules.decide_level(intake.extract_with_keywords(text), text).level


def test_gas_smell_is_always_an_emergency():
    assert level_of("There is a strong smell of gas in the kitchen") == EMERGENCY


def test_sparks_are_an_emergency():
    assert level_of("Sparks came out of the socket") == EMERGENCY


def test_mould_is_significant():
    assert level_of("Black mould is spreading on the bedroom wall") == SIGNIFICANT


def test_dripping_tap_is_routine():
    assert level_of("The kitchen tap is dripping") == ROUTINE


def test_vague_report_goes_to_an_officer():
    assert level_of("Something feels wrong in the flat") == OFFICER_REVIEW


def test_rules_raise_a_level_even_when_the_model_does_not():
    extraction = intake.extract_with_keywords("The radiator is cold")
    extraction.emergency_signals = []
    text = "The radiator is cold and I can smell gas"
    assert rules.decide_level(extraction, text).level == EMERGENCY


def test_working_days_skip_the_weekend():
    friday = datetime(2026, 11, 6, 9, 0)
    assert rules.add_working_days(friday, 1) == datetime(2026, 11, 9, 9, 0)  # Monday
    assert rules.add_working_days(friday, 10).weekday() == 4  # a Friday two weeks on


def test_describe_due():
    now = datetime(2026, 11, 6, 9, 0)
    assert rules.describe_due(datetime(2026, 11, 6, 15, 0), now) == "6 hours"
    assert rules.describe_due(datetime(2026, 11, 5, 9, 0), now) == "Overdue"
    assert rules.describe_due(None, now) == "No legal deadline"


def rule_level(text):
    """The fixed rules alone: the extraction carries no emergency signals."""
    return rules.decide_level(intake.extract_with_keywords("Black mould on the wall"), text).level


def test_a_hole_in_the_landing_floorboards_is_an_emergency():
    assert rule_level("The hole in the landing floorboards is getting bigger") == EMERGENCY
    assert level_of("The hole in the landing floorboards is getting bigger") == EMERGENCY


def test_bare_wires_are_an_emergency():
    assert rule_level("The smoke alarm came off and there's just a bare wire") == EMERGENCY
    assert rule_level("bare wires sticking out of the ceiling") == EMERGENCY
    assert level_of("bare wires sticking out of the ceiling") == EMERGENCY


def test_falling_plaster_or_a_missing_smoke_alarm_alone_is_not_an_emergency():
    assert level_of("A crack across the ceiling and small bits of plaster falling") != EMERGENCY
    assert level_of("The smoke alarm is missing from the hallway ceiling") != EMERGENCY


def test_wires_with_no_sign_they_are_live_go_to_an_officer():
    text = "There are wires near the light in the hall"
    assert intake.extract_with_keywords(text).hazard_confidence == "Low"
    assert level_of(text) == OFFICER_REVIEW


def test_live_wires_stay_an_emergency():
    assert level_of("There are live wires near the light in the hall") == EMERGENCY


def test_a_report_too_short_to_judge_goes_to_an_officer():
    assert level_of("Mould again.") == OFFICER_REVIEW
