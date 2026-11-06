from safehome import intake


def test_evidence_points_at_the_real_words():
    text = "Mould in my son's bedroom again. I reported this before."
    result = intake.extract_with_keywords(text)
    assert result.hazard == "Damp and mould"
    assert "Young child" in result.vulnerability
    assert result.repeat
    for evidence in result.evidence:
        assert text[evidence.start:evidence.end] == evidence.quote


def test_made_up_quotes_are_dropped():
    findings = {
        "hazard": "Damp and mould",
        "hazard_evidence": ["black mould", "water pouring through the roof"],
        "hazard_confidence": "High",
        "emergency_signals": [],
        "vulnerability": [],
        "vulnerability_evidence": [],
        "repeat": False,
        "repeat_evidence": [],
        "missing_information": [],
    }
    result = intake.build_extraction("There is black mould on the wall", findings, source="claude")
    assert [e.quote for e in result.evidence] == ["black mould"]


def test_a_hazard_with_no_evidence_is_low_confidence():
    findings = {
        "hazard": "Falls",
        "hazard_evidence": ["the stairs are dangerous"],
        "hazard_confidence": "High",
        "emergency_signals": [],
        "vulnerability": [],
        "vulnerability_evidence": [],
        "repeat": False,
        "repeat_evidence": [],
        "missing_information": [],
    }
    result = intake.build_extraction("My flat has a problem", findings, source="claude")
    assert result.hazard_confidence == "Low"


def test_claude_answer_is_read_from_the_tool_call(monkeypatch):
    """Uses a fake client, so no API call is made."""
    import types

    import anthropic

    from safehome import config

    answer = {
        "hazard": "Fire and explosions",
        "hazard_evidence": ["smell of gas"],
        "hazard_confidence": "High",
        "emergency_signals": ["smell of gas"],
        "vulnerability": ["Young child"],
        "vulnerability_evidence": ["my baby"],
        "repeat": False,
        "repeat_evidence": [],
        "missing_information": [],
    }

    class FakeMessages:
        def create(self, **kwargs):
            assert [t["name"] for t in kwargs["tools"]] == ["record_findings"]
            block = types.SimpleNamespace(type="tool_use", input=answer)
            return types.SimpleNamespace(content=[block])

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    result = intake.extract("There is a smell of gas and my baby is here")
    assert result.source == "claude"
    assert result.hazard == "Fire and explosions"
    assert result.emergency_signals == ["smell of gas"]
