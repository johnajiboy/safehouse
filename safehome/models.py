from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Evidence:
    """A phrase in the report that supports a finding, with its position."""

    kind: str  # "hazard", "emergency", "household" or "repeat"
    quote: str
    start: int
    end: int


@dataclass
class Extraction:
    """What the Intake Agent found in a tenant's report."""

    hazard: str
    hazard_confidence: str
    emergency_signals: list[str]
    vulnerability: list[str]
    repeat: bool
    evidence: list[Evidence]
    questions: list[str]
    source: str  # "claude" or "keywords"

    def quotes(self, kind: str) -> list[str]:
        return [e.quote for e in self.evidence if e.kind == kind]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Extraction:
        data = dict(data)
        data["evidence"] = [Evidence(**e) for e in data["evidence"]]
        return cls(**data)


@dataclass
class Case:
    ref: str
    text: str
    address: str
    area: str
    reported_at: datetime
    extraction: Extraction
    level: str
    level_reasons: list[str]
    lat: float | None = None
    lng: float | None = None
    contact: str = ""
    stated_needs: list[str] = field(default_factory=list)  # ticked by the tenant on the report form
    # Times each legal step was recorded, in the order of hazards.STAGES after "Reported".
    stage_times: list[datetime] = field(default_factory=list)
    visit_confirmed: bool = False
    pinned: str | None = None  # "today" or "later" when an officer overrides the plan
    override_reason: str = ""
    booking: dict | None = None  # {"repairer_id", "repairer_name", "booked_at"}

    @property
    def stage(self) -> int:
        """0 = reported only, 1 = investigated, and so on."""
        return len(self.stage_times)

    @property
    def hazard(self) -> str:
        return self.extraction.hazard

    @property
    def investigated_at(self) -> datetime | None:
        return self.stage_times[0] if self.stage_times else None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["reported_at"] = self.reported_at.isoformat()
        data["stage_times"] = [t.isoformat() for t in self.stage_times]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Case:
        data = dict(data)
        data["reported_at"] = datetime.fromisoformat(data["reported_at"])
        data["stage_times"] = [datetime.fromisoformat(t) for t in data["stage_times"]]
        data["extraction"] = Extraction.from_dict(data["extraction"])
        return cls(**data)
