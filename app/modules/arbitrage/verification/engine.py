from __future__ import annotations

from typing import Iterable

from app.modules.arbitrage.verification.models import (
    VerificationCheck,
    VerificationResult,
    utc_now_string,
)


# ---------------------------------------------------------
# Status bands
# ---------------------------------------------------------

def verification_status(
    trust_score: int,
) -> tuple[str, bool]:

    if trust_score >= 95:
        return "VERIFIED", True

    if trust_score >= 85:
        return "STRONG", True

    if trust_score >= 70:
        return "REVIEW", False

    if trust_score >= 50:
        return "WEAK", False

    return "REJECT", False


# ---------------------------------------------------------
# Engine
# ---------------------------------------------------------

def build_verification_result(
    checks: Iterable[VerificationCheck],
) -> VerificationResult:

    checks = list(checks)

    total_score = sum(
        check.score
        for check in checks
    )

    maximum_score = max(
        1,
        sum(
            check.max_score
            for check in checks
        ),
    )

    trust_score = round(
        total_score
        / maximum_score
        * 100
    )

    status, verified = verification_status(
        trust_score
    )

    warnings = [
        check.message
        for check in checks
        if not check.passed
    ]

    reasons = [
        check.message
        for check in checks
        if check.passed
    ]

    confidence = trust_score

    return VerificationResult(
        verified=verified,
        status=status,
        trust_score=trust_score,
        total_score=total_score,
        maximum_score=maximum_score,
        confidence=confidence,
        checks=checks,
        warnings=warnings,
        reasons=reasons,
        verified_at=utc_now_string(),
    )