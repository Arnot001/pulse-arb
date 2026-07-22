from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass(slots=True)
class VerificationCheck:

    name: str

    passed: bool

    score: int

    max_score: int

    message: str

    def to_dict(self):
        return asdict(self)


@dataclass(slots=True)
class VerificationResult:

    verified: bool

    status: str

    trust_score: int

    total_score: int

    maximum_score: int

    confidence: int

    checks: list[VerificationCheck]

    warnings: list[str]

    reasons: list[str]

    verified_at: str

    def to_dict(self):
        return {
            "verified": self.verified,
            "status": self.status,
            "trust_score": self.trust_score,
            "total_score": self.total_score,
            "maximum_score": self.maximum_score,
            "confidence": self.confidence,
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
            "warnings": self.warnings,
            "reasons": self.reasons,
            "verified_at": self.verified_at,
        }


def utc_now_string():
    return (
        datetime.utcnow()
        .replace(microsecond=0)
        .isoformat()
        + "Z"
    )