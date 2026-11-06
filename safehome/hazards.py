"""Shared vocabulary: hazard types, levels, household needs and trades."""

HAZARD_TYPES = [
    "Damp and mould",
    "Excess cold",
    "Excess heat",
    "Falls",
    "Structural collapse",
    "Fire and explosions",
    "Electrical hazards",
    "Hygiene and food safety",
    "Routine repair",
    "Unclear",
]

EMERGENCY = "Emergency"
SIGNIFICANT = "Significant"
ROUTINE = "Routine"
OFFICER_REVIEW = "Officer review"

VULNERABILITY_TYPES = [
    "Young child",
    "Older person",
    "Pregnancy",
    "Mobility need",
    "Long-term health condition",
]

# The trade a repairer needs for each hazard.
TRADE_FOR_HAZARD = {
    "Fire and explosions": "gas",
    "Electrical hazards": "electrical",
    "Damp and mould": "damp",
    "Excess cold": "heating",
    "Excess heat": "ventilation",
    "Falls": "joinery",
    "Structural collapse": "structural",
    "Routine repair": "general",
}

TRADE_NAMES = {
    "gas": "Gas engineer",
    "heating": "Heating engineer",
    "electrical": "Electrician",
    "damp": "Damp specialist",
    "ventilation": "Ventilation contractor",
    "joinery": "Joiner",
    "structural": "Structural repairs",
    "pest": "Pest control",
    "drainage": "Drainage contractor",
    "general": "General repairs",
}

# Hazards that often share a building-wide cause such as poor insulation.
RELATED_HAZARDS = {"Damp and mould", "Excess cold"}

STAGES = [
    "Reported",
    "Investigated",
    "Made safe",
    "Written summary sent",
    "Further works started",
]
