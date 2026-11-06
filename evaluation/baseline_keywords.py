"""Step 3 (comparison): a simple keyword-matching baseline.

Your Intake Agent should beat this. It reads data/reports.csv and writes
predictions in the same format your agent must use.

Run:  python baseline_keywords.py
Output: predictions/baseline.csv
"""
import csv
import re
from pathlib import Path

HAZARDS = [  # checked in this order; first match wins
    ("Fire and explosions", r"gas|smoke alarm|fire door|smoke"),
    ("Electrical hazards", r"spark|wire|socket|switch|electric|flicker"),
    ("Structural collapse", r"ceiling.*(fell|fallen|collaps|came down)|crack|plaster|wall.*(lean|fall)"),
    ("Damp and mould", r"mould|mold|damp|wet wall|condensation"),
    ("Excess cold", r"no heating|boiler|freezing|cold|radiator|draught|draft"),
    ("Excess heat", r"too hot|dangerously hot|overheat|stuck on|boiling"),
    ("Falls", r"handrail|stair|step|floorboard|hole in the floor|trip"),
    ("Hygiene and food safety", r"mice|mouse|rat|droppings|sewage|drain|smell"),
    ("Routine repair", r"tap|cupboard|tile|lock|gate|toilet seat|squeak"),
]
EMERGENCY = r"gas|spark|live wire|wires? hanging|ceiling.*(fell|fallen|collaps|came down)|hole in the floor|no heating"
VULN = [
    ("Young child", r"baby|newborn|toddler|child|son|daughter|kids?"),
    ("Older person", r"elderly|older|\b(7[5-9]|8\d|9\d)\b|grand(ma|pa|mother|father)|pension"),
    ("Pregnancy", r"pregnan"),
    ("Mobility need", r"wheelchair|walking frame|mobility|can't walk"),
    ("Long-term health condition", r"asthma|breath|copd|lung|chest"),
]
REPEAT = r"again|before|already reported|still not|still isn't|still hasn't|second time|third time|weeks ago|months ago"

rows = list(csv.DictReader(open("data/reports.csv", encoding="utf-8")))
Path("predictions").mkdir(exist_ok=True)
with open("predictions/baseline.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "hazard", "level", "vulnerability", "repeat", "confidence"])
    for r in rows:
        t = r["text"].lower()
        hazard = next((h for h, p in HAZARDS if re.search(p, t)), "Unclear")
        if hazard == "Unclear":
            level = "Officer review"
        elif hazard == "Routine repair":
            level = "Routine"
        else:
            level = "Emergency" if re.search(EMERGENCY, t) else "Significant"
        vuln = next((v for v, p in VULN if re.search(p, t)), "None")
        repeat = "yes" if re.search(REPEAT, t) else "no"
        confidence = "Low" if hazard == "Unclear" else "Medium"
        w.writerow([r["id"], hazard, level, vuln, repeat, confidence])
print(f"Wrote {len(rows)} baseline predictions to predictions/baseline.csv")
