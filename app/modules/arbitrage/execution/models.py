from __future__ import annotations

from dataclasses import dataclass, asdict

@dataclass(slots=True)
class ExecutionLeg:
    bookmaker: str
    event_name: str
    selection_name: str
    stake: float
    market_name: str = "Win"
    event_url: str | None = None
    decimal_odds: float | None = None
    race_time: str | None = None
    course: str | None = None
    metadata: dict | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self):
        return asdict(self)


@dataclass(slots=True)
class ExecutionStep:

    step_number: int

    bookmaker: str

    selection: str

    odds: float

    stake: float

    expected_return: float

    expected_profit: float

    priority: int

    must_complete_before_next: bool = True

    event_url: str | None = None

    notes: list[str] | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(slots=True)
class ExecutionPlan:

    priority: str

    confidence: int

    execution_score: float

    estimated_lifetime_seconds: int

    recommended_action: str

    total_stake: float

    guaranteed_profit: float

    roi: float

    steps: list[ExecutionStep]

    warnings: list[str]

    notes: list[str]

    def to_dict(self):
        return {
            "priority": self.priority,
            "confidence": self.confidence,
            "execution_score": self.execution_score,
            "estimated_lifetime_seconds": self.estimated_lifetime_seconds,
            "recommended_action": self.recommended_action,
            "total_stake": self.total_stake,
            "guaranteed_profit": self.guaranteed_profit,
            "roi": self.roi,
            "steps": [
                s.to_dict()
                for s in self.steps
            ],
            "warnings": self.warnings,
            "notes": self.notes,
        }