"""Pattern Agent: links reports from the same building that may share a cause."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import config
from .hazards import RELATED_HAZARDS
from .models import Case


@dataclass
class Cluster:
    key: str
    building: str
    refs: list[str]
    hazards: list[str]
    explanation: str


def building_of(address: str) -> str:
    """'Flat 9, Elm House' -> 'Elm House'; '22 Oak Terrace' -> 'Oak Terrace'."""
    address = re.sub(r"^\s*flat\s+\w+\s*,\s*", "", address, flags=re.IGNORECASE)
    address = re.sub(r"^\s*\d+\w?\s+", "", address)
    return address.strip()


def shared_building(address: str) -> str | None:
    """'Flat 9, Elm House' -> 'Elm House'. Houses return None: sharing a street is not sharing a building."""
    match = re.match(r"^\s*flat\s+\w+\s*,\s*(.+)$", address, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def find_clusters(cases: list[Case], now: datetime) -> list[Cluster]:
    since = now - timedelta(days=config.PATTERN_WINDOW_DAYS)
    by_building: dict[str, list[Case]] = {}
    for case in cases:
        building = shared_building(case.address)
        if not building or case.reported_at < since or case.hazard not in RELATED_HAZARDS:
            continue
        by_building.setdefault(building, []).append(case)

    clusters = []
    for building, group in by_building.items():
        flats = {c.address for c in group}
        if len(group) < config.PATTERN_MIN_REPORTS or len(flats) < 2:
            continue
        hazards = sorted({c.hazard for c in group})
        clusters.append(Cluster(
            key=re.sub(r"[^a-z0-9]+", "-", building.lower()).strip("-"),
            building=building,
            refs=[c.ref for c in sorted(group, key=lambda c: c.reported_at)],
            hazards=hazards,
            explanation=(
                f"{len(group)} {' and '.join(h.lower() for h in hazards)} reports from "
                f"{len(flats)} homes in {building} within {config.PATTERN_WINDOW_DAYS} days. "
                "Ventilation or insulation could be a shared cause. A surveyor must confirm this."
            ),
        ))
    return clusters
