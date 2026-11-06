"""Step 1: create the answer key (labels) for the SafeHome test set.

Every row is one tenant report that will be written later. The columns are the
correct answers the Intake Agent should find. Your group should check these
labels against the Awaab's Law hazard guidance and change any you disagree with.

Run:  python make_labels.py
Output: data/labels.csv
"""
import csv
import random
from pathlib import Path

random.seed(42)  # same dataset every time

# Hazard -> list of (correct level, facts the tenant will describe)
SCENARIOS = {
    "Damp and mould": [
        ("Significant", "black mould spreading across the bedroom wall and ceiling"),
        ("Significant", "a damp patch growing on the living room wall, and the walls feel wet"),
        ("Significant", "mould around the bathroom window that keeps coming back after cleaning"),
    ],
    "Excess cold": [
        ("Emergency", "the boiler has completely failed in winter, with no heating or hot water and a very cold home"),
        ("Significant", "the radiators only warm up in one room, so the flat stays very cold"),
        ("Significant", "the windows don't seal and cold air comes in all the time"),
    ],
    "Excess heat": [
        ("Significant", "the bedroom gets dangerously hot and the windows won't open"),
        ("Significant", "the heating is stuck on full and can't be turned off"),
        ("Significant", "the top-floor flat overheats badly and there is no ventilation"),
    ],
    "Falls": [
        ("Significant", "the stair handrail has come away from the wall"),
        ("Significant", "the back step outside the door has broken"),
        ("Emergency", "there is a large hole in the floorboards on the landing"),
    ],
    "Structural collapse": [
        ("Emergency", "part of the bedroom ceiling has fallen in"),
        ("Significant", "a big crack has appeared across the ceiling and plaster is dropping"),
        ("Significant", "the garden wall is leaning and looks like it could fall"),
    ],
    "Fire and explosions": [
        ("Emergency", "a strong smell of gas near the boiler"),
        ("Significant", "the smoke alarm is missing and has not been replaced"),
        ("Significant", "the fire door to the flat no longer closes properly"),
    ],
    "Electrical hazards": [
        ("Emergency", "sparks came from a socket and the wall around it feels hot"),
        ("Emergency", "live wires are hanging out of the ceiling light fitting"),
        ("Significant", "a light switch buzzes and the lights flicker"),
    ],
    "Hygiene and food safety": [
        ("Significant", "mice droppings in the kitchen near the food cupboards"),
        ("Significant", "the bath won't drain and the water smells bad"),
        ("Significant", "a sewage smell keeps coming from the kitchen drain"),
    ],
}
ROUTINE = [
    "a dripping kitchen tap",
    "a kitchen cupboard door hanging loose",
    "a small cracked tile in the bathroom",
    "the front door lock is stiff",
    "the garden gate squeaks",
    "a toilet seat is loose",
]
UNCLEAR = [
    "something is wrong with the loft hatch and they are worried",
    "a strange noise from inside the walls at night",
    "the flat hasn't felt right since workmen visited last week",
]
VULNERABILITY = ["None", "Young child", "Older person", "Pregnancy", "Mobility need", "Long-term health condition"]
VULN_WEIGHTS = [50, 14, 12, 8, 8, 8]
STYLES = ["formal", "casual", "simple English", "angry", "short"]
AREAS = ["Newport", "North Ormesby", "Linthorpe", "Berwick Hills", "Acklam", "Marton", "Hemlington", "Park End"]
STREETS = ["Ash Court", "Mill Row", "Station Walk", "Oak Terrace", "Chapel Lane", "Quarry Road", "Cedar Grove", "Willow Close"]

rows = []


def add(hazard, level, facts, *, vuln=None, repeat=None, style=None, address=None,
        area=None, set_name="core", group_id="", cluster_id=""):
    rid = f"T{len(rows) + 1:03d}"
    rows.append({
        "id": rid,
        "set": set_name,
        "hazard": hazard,
        "level": level,
        "vulnerability": vuln or random.choices(VULNERABILITY, VULN_WEIGHTS)[0],
        "repeat": repeat if repeat is not None else random.choice(["yes", "no", "no"]),
        "style": style or random.choice(STYLES),
        "address": address or f"{random.randint(1, 60)} {random.choice(STREETS)}",
        "area": area or random.choice(AREAS),
        "facts": facts,
        "group_id": group_id,
        "cluster_id": cluster_id,
    })


# 1. Core set: every scenario written 4 times with different households and styles (96 reports)
for hazard, scenarios in SCENARIOS.items():
    for level, facts in scenarios:
        for _ in range(4):
            add(hazard, level, facts)

# 2. Fairness set: the same facts in three styles. Priority should not change (30 reports)
fair_pool = [(h, lvl, f) for h, sc in SCENARIOS.items() for lvl, f in sc]
for g, (hazard, level, facts) in enumerate(random.sample(fair_pool, 10), start=1):
    vuln = random.choices(VULNERABILITY, VULN_WEIGHTS)[0]
    address = f"{random.randint(1, 60)} {random.choice(STREETS)}"
    area = random.choice(AREAS)
    for style in ["formal", "casual", "simple English"]:
        add(hazard, level, facts, vuln=vuln, repeat="no", style=style, address=address,
            area=area, set_name="fairness", group_id=f"F{g:02d}")

# 3. Cluster set: related reports from the same building (8 reports)
clusters = [
    ("C1", "Elm House", "Berwick Hills", [("Damp and mould", SCENARIOS["Damp and mould"][0][1]),
                                          ("Damp and mould", SCENARIOS["Damp and mould"][1][1]),
                                          ("Excess cold", SCENARIOS["Excess cold"][1][1]),
                                          ("Excess cold", SCENARIOS["Excess cold"][2][1])]),
    ("C2", "Birch Court", "Park End", [("Damp and mould", SCENARIOS["Damp and mould"][2][1]),
                                       ("Damp and mould", SCENARIOS["Damp and mould"][0][1]),
                                       ("Damp and mould", SCENARIOS["Damp and mould"][1][1]),
                                       ("Excess cold", SCENARIOS["Excess cold"][2][1])]),
]
for cid, building, area, items in clusters:
    for hazard, facts in items:
        add(hazard, "Significant", facts, address=f"Flat {random.randint(1, 30)}, {building}",
            area=area, set_name="cluster", cluster_id=cid)

# 4. Routine repairs, below the significant level (12 reports)
for facts in ROUTINE:
    for _ in range(2):
        add("Routine repair", "Routine", facts, set_name="routine")

# 5. Unclear reports that should be flagged for an officer (6 reports)
for facts in UNCLEAR:
    for _ in range(2):
        add("Unclear", "Officer review", facts, set_name="unclear")

Path("data").mkdir(exist_ok=True)
with open("data/labels.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print(f"Wrote {len(rows)} labels to data/labels.csv")
for s in ["core", "fairness", "cluster", "routine", "unclear"]:
    print(f"  {s:9} {sum(r['set'] == s for r in rows)}")
print(f"  emergencies {sum(r['level'] == 'Emergency' for r in rows)}")
