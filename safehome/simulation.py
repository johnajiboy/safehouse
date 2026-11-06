"""Planner evaluation: compare SafeHome's ordering with simpler methods.

Every method gets the same simulated reports, so differences come from the
ordering alone. Results are averaged over many runs.

Assumptions (state these in the report):
- 5 to 7 new reports per working day, 3 extra per day during a 5-day cold snap
- 12% of reports are emergencies, 30% come from vulnerable households
- deadlines of 0 days (same day) for emergencies and 10 working days otherwise
- each inspector makes 3 visits a day
"""
from __future__ import annotations

import random
from dataclasses import dataclass

DAYS = 20
RUNS = 100


@dataclass
class SimCase:
    arrived: int
    emergency: bool
    vulnerable: bool
    deadline: int
    order: int


def workload(seed: int, cold_snap: bool) -> list[SimCase]:
    rng = random.Random(seed)
    cases = []
    for day in range(DAYS):
        count = rng.randint(5, 7) + (3 if cold_snap and 8 <= day <= 12 else 0)
        for _ in range(count):
            emergency = rng.random() < 0.12
            vulnerable = rng.random() < 0.30
            cases.append(SimCase(day, emergency, vulnerable, day + (0 if emergency else 10), len(cases)))
    return cases


def first_come_first_served(case: SimCase, day: int):
    return (case.arrived, case.order)


def emergencies_then_oldest(case: SimCase, day: int):
    return (not case.emergency, case.arrived, case.order)


def safehome(case: SimCase, day: int):
    due_soon = case.deadline - day <= 1
    return (not case.emergency, not due_soon, not case.vulnerable, case.arrived, case.order)


METHODS = {
    "First come, first served": first_come_first_served,
    "Emergencies first, then oldest": emergencies_then_oldest,
    "SafeHome plan": safehome,
}


def run_once(method, capacity: int, seed: int, cold_snap: bool) -> dict:
    cases = workload(seed, cold_snap)
    waiting: list[SimCase] = []
    missed = missed_emergencies = 0
    high_risk_waits = []

    for day in range(DAYS):
        waiting += [c for c in cases if c.arrived == day]
        waiting.sort(key=lambda c: method(c, day))
        visited, waiting = waiting[:capacity], waiting[capacity:]
        for case in visited:
            if day > case.deadline:
                missed += 1
                missed_emergencies += case.emergency
            if case.emergency or case.vulnerable:
                high_risk_waits.append(day - case.arrived)

    for case in waiting:  # still waiting when the period ends
        if case.deadline < DAYS:
            missed += 1
            missed_emergencies += case.emergency
        if case.emergency or case.vulnerable:
            high_risk_waits.append(DAYS - case.arrived)

    return {
        "deadlines_missed": missed,
        "emergencies_missed": missed_emergencies,
        "high_risk_wait_days": sum(high_risk_waits) / len(high_risk_waits) if high_risk_waits else 0,
    }


def compare(inspectors: int, cold_snap: bool = False) -> list[dict]:
    capacity = inspectors * 3
    results = []
    for name, method in METHODS.items():
        runs = [run_once(method, capacity, seed * 7919, cold_snap) for seed in range(1, RUNS + 1)]
        results.append({
            "method": name,
            **{key: round(sum(r[key] for r in runs) / RUNS, 1) for key in runs[0]},
        })
    return results


if __name__ == "__main__":
    for inspectors in (1, 2, 3):
        print(f"\n{inspectors} inspector(s)")
        for row in compare(inspectors):
            print(f"  {row['method']:32} missed {row['deadlines_missed']:5}  "
                  f"emergencies missed {row['emergencies_missed']:5}  high-risk wait {row['high_risk_wait_days']:4} days")
