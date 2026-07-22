from __future__ import annotations

from app.modules.arbitrage.execution.models import (
    ExecutionPlan,
    ExecutionStep,
)


# ---------------------------------------------------------
# Lifetime Estimate
# ---------------------------------------------------------

def estimate_lifetime(
    roi: float,
) -> int:

    if roi >= 5:
        return 10

    if roi >= 3:
        return 20

    if roi >= 2:
        return 30

    if roi >= 1:
        return 45

    return 60


# ---------------------------------------------------------
# Confidence
# ---------------------------------------------------------

def confidence_score(
    roi: float,
    market_percentage: float,
    natural_score: float,
) -> int:

    score = 60

    score += min(
        roi * 4,
        20,
    )

    score += max(
        0,
        100 - market_percentage,
    )

    score += natural_score * 10

    return max(
        0,
        min(
            100,
            round(score),
        ),
    )


# ---------------------------------------------------------
# Priority
# ---------------------------------------------------------

def execution_priority(
    roi: float,
) -> str:

    if roi >= 5:
        return "CRITICAL"

    if roi >= 3:
        return "HIGH"

    if roi >= 2:
        return "MEDIUM"

    return "LOW"


# ---------------------------------------------------------
# Planner
# ---------------------------------------------------------

def build_execution_plan(
    optimized_plan,
) -> ExecutionPlan:

    steps = []

    sorted_stakes = sorted(
        optimized_plan.stakes,
        key=lambda x: x.recommended_stake,
        reverse=True,
    )

    for index, stake in enumerate(
        sorted_stakes,
        start=1,
    ):

        steps.append(
            ExecutionStep(
                step_number=index,

                bookmaker=stake.bookmaker,

                selection=stake.selection,

                odds=stake.odds,

                stake=stake.recommended_stake,

                expected_return=stake.outcome_return,

                expected_profit=stake.outcome_profit,

                priority=index,

                event_url=stake.event_url,

                notes=[],
            )
        )

    confidence = confidence_score(
        optimized_plan.roi,
        optimized_plan.market_percentage,
        optimized_plan.natural_stake_score,
    )

    lifetime = estimate_lifetime(
        optimized_plan.roi,
    )

    priority = execution_priority(
        optimized_plan.roi,
    )

    warnings = []

    if optimized_plan.roi < 1:
        warnings.append(
            "Low ROI opportunity."
        )

    if optimized_plan.total_stake_difference != 0:
        warnings.append(
            "Rounded stake differs from requested bankroll."
        )

    return ExecutionPlan(

        priority=priority,

        confidence=confidence,

        execution_score=confidence,

        estimated_lifetime_seconds=lifetime,

        recommended_action="PREPARE",

        total_stake=optimized_plan.total_stake,

        guaranteed_profit=optimized_plan.guaranteed_profit,

        roi=optimized_plan.roi,

        steps=steps,

        warnings=warnings,

        notes=[
            "Execution order generated automatically."
        ],
    )