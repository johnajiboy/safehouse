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
