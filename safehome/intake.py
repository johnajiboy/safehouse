"""Intake Agent: reads a tenant's report and records what it says.

It uses the Claude API when an API key is set. Without one it falls back to
keyword matching, so the app still runs offline for demos and tests.

The agent only extracts facts. It never sets the legal level or deadline;
that is done by the fixed rules in rules.py.
"""
from __future__ import annotations

import re

from . import config
from .hazards import HAZARD_TYPES, VULNERABILITY_TYPES
from .models import Evidence, Extraction

SYSTEM_PROMPT = """You help a social housing repairs team in England read tenant reports.
Record what the report says using the record_findings tool.
Always answer by calling record_findings, never with plain text.

Rules:
- Only use what the tenant wrote. Do not guess or add facts.
- Every evidence item must be an exact phrase copied from the report, word for word.
- Choose "Routine repair" for minor problems with no risk to health or safety.
- Choose "Unclear" when the report does not say enough to identify a hazard.
- Emergency signals are phrases suggesting an imminent risk of serious harm, such as
  a gas smell, sparks, exposed wires, a collapsed ceiling or a total loss of heating
  in cold weather. Leave the list empty if there are none.
- Missing information: up to three short questions an officer should ask the tenant
  because a safety detail is missing. Do not ask for details already given."""

FINDINGS_TOOL = {
    "name": "record_findings",
    "description": "Record the hazard, household and history described in a tenant's report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "hazard": {"type": "string", "enum": HAZARD_TYPES},
            "hazard_evidence": {"type": "array", "items": {"type": "string"}},
            "hazard_confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
            "emergency_signals": {"type": "array", "items": {"type": "string"}},
            "vulnerability": {"type": "array", "items": {"type": "string", "enum": VULNERABILITY_TYPES}},
            "vulnerability_evidence": {"type": "array", "items": {"type": "string"}},
            "repeat": {"type": "boolean", "description": "True if the tenant says they reported this before."},
            "repeat_evidence": {"type": "array", "items": {"type": "string"}},
            "missing_information": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "hazard", "hazard_evidence", "hazard_confidence", "emergency_signals",
            "vulnerability", "vulnerability_evidence", "repeat", "repeat_evidence",
            "missing_information",
        ],
    },
}


def extract(text: str) -> Extraction:
    """Read a report with Claude if possible, otherwise with keywords."""
    if config.ANTHROPIC_API_KEY:
        try:
            return extract_with_claude(text)
        except Exception as error:  # network or API problems should not lose the report
            print(f"Claude extraction failed, using keywords instead: {error}")
    return extract_with_keywords(text)


# --- Claude -----------------------------------------------------------------

def extract_with_claude(text: str) -> Extraction:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.MODEL,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        tools=[FINDINGS_TOOL],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": f"Tenant report:\n\n{text}"}],
    )
    findings = next(block.input for block in response.content if block.type == "tool_use")
    return build_extraction(text, findings, source="claude")


def build_extraction(text: str, findings: dict, source: str) -> Extraction:
    """Turn the model's answer into an Extraction, keeping only evidence that is really in the text."""
    evidence = (
        locate(text, findings.get("hazard_evidence", []), "hazard")
        + locate(text, findings.get("emergency_signals", []), "emergency")
        + locate(text, findings.get("vulnerability_evidence", []), "household")
        + locate(text, findings.get("repeat_evidence", []), "repeat")
    )
    hazard = findings.get("hazard", "Unclear")
    if hazard not in HAZARD_TYPES:
        hazard = "Unclear"

    confidence = findings.get("hazard_confidence", "Low")
    has_hazard_evidence = any(e.kind == "hazard" for e in evidence)
    if hazard not in ("Unclear", "Routine repair") and not has_hazard_evidence:
        confidence = "Low"  # a claim with no words to back it up is not trusted

    return Extraction(
        hazard=hazard,
        hazard_confidence=confidence,
        emergency_signals=[e.quote for e in evidence if e.kind == "emergency"],
        vulnerability=[v for v in findings.get("vulnerability", []) if v in VULNERABILITY_TYPES],
        repeat=bool(findings.get("repeat", False)),
        evidence=evidence,
        questions=list(findings.get("missing_information", []))[:3],
        source=source,
    )


def locate(text: str, quotes: list[str], kind: str) -> list[Evidence]:
    """Find each quote in the text. Quotes that are not in the text are dropped."""
    found = []
    lowered = text.lower()
    for quote in quotes:
        quote = quote.strip().strip('"')
        if not quote:
            continue
        start = lowered.find(quote.lower())
        if start >= 0:
            found.append(Evidence(kind, text[start:start + len(quote)], start, start + len(quote)))
    return found


# --- Keyword fallback ---------------------------------------------------------

HAZARD_KEYWORDS = [  # checked in order, first match wins
    ("Fire and explosions", r"\bgas\b|smoke alarm|fire door|\bsmoke\b|burning smell"),
    ("Electrical hazards", r"spark\w*|live wires?|exposed wires?|wires? hanging|socket|light switch|buzz\w*|flicker\w*"),
    ("Structural collapse", r"ceiling (has )?(fallen|collapsed|came down)|crack\w*|plaster|wall is leaning|leaning"),
    ("Damp and mould", r"mould|mold|damp|walls? feels? wet|condensation"),
    ("Excess cold", r"no heating|heating is off|boiler|freezing|\bcold\b|radiators?|can't get warm"),
    ("Excess heat", r"dangerously hot|too hot|overheat\w*|stuck on full|no ventilation"),
    ("Falls", r"handrail|stairs?|\bstep\b|floorboards?|hole in the floor"),
    ("Hygiene and food safety", r"mice|mouse|\brats?\b|droppings|sewage|won't drain|smells bad"),
    ("Routine repair", r"\btap\b|cupboard|tile|\block\b|\bgate\b|toilet seat|squeak\w*"),
]
EMERGENCY_KEYWORDS = r"\bgas\b|spark\w*|live wires?|exposed wires?|wires? hanging|ceiling (has )?(fallen|collapsed|came down)|hole in the floor"
VULNERABILITY_KEYWORDS = [
    ("Young child", r"\bbaby\b|newborn|toddler|\bchild\w*|\bson\b|son's|daughter|\bkids?\b"),
    ("Older person", r"elderly|older|pensioner|(dad|mum|mother|father|nan|grandad) is \d+"),
    ("Pregnancy", r"pregnan\w*"),
    ("Mobility need", r"wheelchair|walking frame|mobility"),
    ("Long-term health condition", r"asthma|breathing|\bcopd\b|\blungs?\b"),
]
REPEAT_KEYWORDS = r"reported (this|it) (before|twice|already)|again|third time|second time|still (not|isn't|hasn't)|is back|keeps"


def extract_with_keywords(text: str) -> Extraction:
    lowered = text.lower()
    findings = {
        "hazard": "Unclear",
        "hazard_evidence": [],
        "hazard_confidence": "Low",
        "emergency_signals": [m.group(0) for m in re.finditer(EMERGENCY_KEYWORDS, lowered)],
        "vulnerability": [],
        "vulnerability_evidence": [],
        "repeat": False,
        "repeat_evidence": [m.group(0) for m in re.finditer(REPEAT_KEYWORDS, lowered)],
        "missing_information": [],
    }
    for hazard, pattern in HAZARD_KEYWORDS:
        matches = [m.group(0) for m in re.finditer(pattern, lowered)]
        if matches:
            findings["hazard"] = hazard
            findings["hazard_evidence"] = matches
            findings["hazard_confidence"] = "High" if len(set(matches)) > 1 else "Medium"
            break

    for need, pattern in VULNERABILITY_KEYWORDS:
        matches = [m.group(0) for m in re.finditer(pattern, lowered)]
        if matches:
            findings["vulnerability"].append(need)
            findings["vulnerability_evidence"] += matches

    findings["repeat"] = bool(findings["repeat_evidence"])
    findings["missing_information"] = suggest_questions(findings)
    if findings["hazard"] == "Routine repair":
        findings["hazard_confidence"] = "Medium"
    return build_extraction(text, findings, source="keywords")


def suggest_questions(findings: dict) -> list[str]:
    questions = []
    if findings["hazard"] == "Unclear":
        questions.append("What exactly has happened, and is anyone at risk right now?")
    if findings["hazard"] == "Excess cold":
        questions.append("Do you have another safe way to heat your home?")
    if not findings["vulnerability"] and findings["hazard"] not in ("Routine repair",):
        questions.append("Does anyone at home have a health or mobility need, or is anyone very young, older or pregnant?")
    return questions[:3]
