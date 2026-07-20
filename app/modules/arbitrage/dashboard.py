from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from app.modules.arbitrage.store import (
    CURRENT_STATE_FILE,
    clean,
    current_records,
    dashboard_stats,
    expire_stale_opportunities,
    safe_float,
    safe_int,
)


STATUS_ORDER = {
    "VERIFIED": 0,
    "REVIEW": 1,
    "OBSERVED": 2,
    "INCOMPLETE": 3,
    "INVALID": 4,
    "EXPIRED": 5,
}


def parse_iso_datetime(value) -> Optional[datetime]:
    text = clean(value)

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def format_timestamp(value) -> str:
    parsed = parse_iso_datetime(
        value
    )

    if parsed is None:
        return ""

    return parsed.strftime(
        "%H:%M:%S"
    )


def opportunity_status(record: dict) -> str:
    status = clean(
        record.get("status")
    ).upper()

    if record.get("expired") is True:
        return "EXPIRED"

    return status or "OBSERVED"


def normalize_leg(leg: dict) -> dict:
    bookmaker = (
        clean(leg.get("bookmaker"))
        or clean(leg.get("source"))
        or "Unknown"
    )

    horse = (
        clean(leg.get("horse"))
        or clean(leg.get("runner"))
        or clean(leg.get("selection"))
        or "Runner"
    )

    return {
        **leg,
        "horse": horse,
        "runner": horse,
        "selection": horse,
        "bookmaker": bookmaker,
        "source": bookmaker,
        "decimal_odds": safe_float(
            leg.get("decimal_odds")
            or leg.get("odds")
        ),
        "stake": safe_float(
            leg.get("stake")
        ),
        "return": safe_float(
            leg.get("return")
        ),
    }


def normalize_record(record: dict) -> dict:
    status = opportunity_status(
        record
    )

    raw_legs = record.get(
        "legs",
        [],
    )

    if not isinstance(
        raw_legs,
        list,
    ):
        raw_legs = []

    legs = [
        normalize_leg(leg)
        for leg in raw_legs
        if isinstance(
            leg,
            dict,
        )
    ]

    race = (
        clean(record.get("race"))
        or "Unknown race"
    )

    course = (
        clean(record.get("course"))
        or "Unknown"
    )

    race_time = clean(
        record.get("race_time")
    )

    total_stake = safe_float(
        record.get("total_stake")
    )

    guaranteed_return = safe_float(
        record.get(
            "guaranteed_return"
        )
    )

    profit = safe_float(
        record.get("profit")
    )

    roi = safe_float(
        record.get("roi_percent")
    )

    market_percentage = record.get(
        "market_percentage"
    )

    if market_percentage is not None:
        market_percentage = safe_float(
            market_percentage
        )

    warnings = record.get(
        "warnings",
        [],
    )

    if not isinstance(
        warnings,
        list,
    ):
        warnings = []

    failures = record.get(
        "failures",
        [],
    )

    if not isinstance(
        failures,
        list,
    ):
        failures = []

    first_seen = clean(
        record.get("first_seen")
    )

    last_seen = clean(
        record.get("last_seen")
    )

    display = {
        "race_name": race,
        "course": course,
        "race_time": race_time,
        "race_date": "",
        "status": status,
        "roi_percent": round(
            roi,
            2,
        ),
        "guaranteed_profit": round(
            profit,
            2,
        ),
        "guaranteed_return": round(
            guaranteed_return,
            2,
        ),
        "total_stake": round(
            total_stake,
            2,
        ),
        "confidence_percent": round(
            safe_float(
                record.get(
                    "validation_score"
                )
            ),
            1,
        ),
        "discovery_score": round(
            safe_float(
                record.get(
                    "validation_score"
                )
            ),
            1,
        ),
        "bookmaker_count": safe_int(
            record.get(
                "bookmaker_count"
            )
        ),
        "market_percentage": (
            round(
                market_percentage,
                2,
            )
            if market_percentage
            is not None
            else None
        ),
        "arb_margin_percent": (
            round(
                safe_float(
                    record.get(
                        "arb_margin_percent"
                    )
                ),
                2,
            )
            if record.get(
                "arb_margin_percent"
            )
            is not None
            else None
        ),
        "stable_seconds": 0,
        "seen_count": safe_int(
            record.get(
                "seen_count"
            )
        ),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "last_seen_time": format_timestamp(
            last_seen
        ),
        "active": (
            record.get("active")
            is not False
        ),
        "expired": (
            record.get("expired")
            is True
        ),
    }

    opportunity = {
        "opportunity_id": clean(
            record.get(
                "opportunity_id"
            )
        ),
        "race_id": clean(
            record.get(
                "opportunity_id"
            )
        ),
        "course": course,
        "race_time": race_time,
        "race_date": "",
        "total_stake": total_stake,
        "guaranteed_return": (
            guaranteed_return
        ),
        "guaranteed_profit": profit,
        "roi_percent": roi,
        "pulse_score": None,
        "stable_seconds": 0,
        "seen_count": safe_int(
            record.get(
                "seen_count"
            )
        ),
        "detected_at": first_seen,
        "last_seen_at": last_seen,
        "legs": legs,
        "metadata": {
            "race_name": race,
            "market_percentage": (
                market_percentage
            ),
            "arb_margin_percent": (
                record.get(
                    "arb_margin_percent"
                )
            ),
        },
    }

    execution_label = {
        "VERIFIED": "EXECUTE",
        "REVIEW": "REVIEW",
        "OBSERVED": "WATCH",
        "INCOMPLETE": "WATCH",
        "INVALID": "REJECT",
        "EXPIRED": "EXPIRED",
    }.get(
        status,
        "WATCH",
    )

    return {
        **record,
        "status": status,
        "execution_label": execution_label,
        "discovery_score": safe_float(
            record.get(
                "validation_score"
            )
        ),
        "confidence_percent": safe_float(
            record.get(
                "validation_score"
            )
        ),
        "bookmaker_count": safe_int(
            record.get(
                "bookmaker_count"
            )
        ),
        "warnings": [
            clean(item)
            for item in warnings
            if clean(item)
        ],
        "failures": [
            clean(item)
            for item in failures
            if clean(item)
        ],
        "opportunity": opportunity,
        "display": display,
    }


def sort_records(
    records: Iterable[dict],
) -> list[dict]:
    items = [
        normalize_record(record)
        for record in records
        if isinstance(
            record,
            dict,
        )
    ]

    items.sort(
        key=lambda item: (
            STATUS_ORDER.get(
                opportunity_status(
                    item
                ),
                99,
            ),
            -safe_float(
                item.get(
                    "roi_percent"
                )
            ),
            clean(
                item.get(
                    "last_seen"
                )
            ),
        )
    )

    return items


def filter_status(
    records: Iterable[dict],
    *statuses: str,
) -> list[dict]:
    allowed = {
        clean(status).upper()
        for status in statuses
    }

    return [
        record
        for record in records
        if opportunity_status(
            record
        ) in allowed
    ]


def calculate_stats(
    records: Iterable[dict],
) -> dict:
    items = list(
        records
    )

    active = [
        item
        for item in items
        if item.get(
            "expired"
        ) is not True
    ]

    verified = filter_status(
        active,
        "VERIFIED",
    )

    review = filter_status(
        active,
        "REVIEW",
    )

    observed = filter_status(
        active,
        "OBSERVED",
    )

    incomplete = filter_status(
        active,
        "INCOMPLETE",
    )

    invalid = filter_status(
        active,
        "INVALID",
    )

    actionable = (
        verified
        + review
    )

    bookmakers = {
        clean(bookmaker)
        for item in active
        for bookmaker in (
            item.get(
                "bookmakers"
            )
            or []
        )
        if clean(bookmaker)
    }

    highest_roi = max(
        (
            safe_float(
                item.get(
                    "roi_percent"
                )
            )
            for item in actionable
        ),
        default=0.0,
    )

    average_roi = (
        sum(
            safe_float(
                item.get(
                    "roi_percent"
                )
            )
            for item in actionable
        )
        / len(actionable)
        if actionable
        else 0.0
    )

    total_profit = sum(
        safe_float(
            item.get("profit")
        )
        for item in verified
    )

    return {
        "markets": len(active),
        "opportunities": len(
            actionable
        ),
        "verified": len(verified),
        "execute": len(verified),
        "strong": 0,
        "review": len(review),
        "watch": len(observed),
        "observed": len(observed),
        "incomplete": len(incomplete),
        "invalid": len(invalid),
        "diagnostics": (
            len(incomplete)
            + len(invalid)
        ),
        "highest_roi": round(
            highest_roi,
            2,
        ),
        "average_roi": round(
            average_roi,
            2,
        ),
        "total_guaranteed_profit": round(
            total_profit,
            2,
        ),
        "average_confidence": round(
            (
                sum(
                    safe_float(
                        item.get(
                            "validation_score"
                        )
                    )
                    for item in active
                )
                / len(active)
            )
            if active
            else 0.0,
            2,
        ),
        "average_discovery_score": round(
            (
                sum(
                    safe_float(
                        item.get(
                            "validation_score"
                        )
                    )
                    for item in active
                )
                / len(active)
            )
            if active
            else 0.0,
            2,
        ),
        "bookmakers": len(
            bookmakers
        ),
    }


def get_recent(
    limit: int = 20,
) -> list[dict]:
    limit = max(
        0,
        safe_int(
            limit,
            20,
        ),
    )

    records = sort_records(
        current_records(
            include_expired=False
        )
    )

    records.sort(
        key=lambda item: (
            parse_iso_datetime(
                item.get(
                    "last_seen"
                )
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True,
    )

    return records[:limit]


def get_opportunity(
    opportunity_id: str,
) -> Optional[dict]:
    expected = clean(
        opportunity_id
    )

    if not expected:
        return None

    for record in current_records(
        include_expired=True
    ):
        if clean(
            record.get(
                "opportunity_id"
            )
        ) == expected:
            return normalize_record(
                record
            )

    return None


def get_stats() -> dict:
    records = current_records(
        include_expired=False
    )

    return calculate_stats(
        records
    )


def get_dashboard() -> dict:
    try:
        raw_records = current_records(
            include_expired=True
        )

        records = sort_records(
            raw_records
        )

        active = records

        verified = filter_status(
            active,
            "VERIFIED",
        )

        review = filter_status(
            active,
            "REVIEW",
        )

        observed = filter_status(
            active,
            "OBSERVED",
        )

        incomplete = filter_status(
            active,
            "INCOMPLETE",
        )

        invalid = filter_status(
            active,
            "INVALID",
        )

        expired = [
            record
            for record in records
            if record.get(
                "expired"
            ) is True
        ]

        recent = get_recent(
            limit=20
        )

        stats = calculate_stats(
            records
        )

        best_market = (
            max(
                verified + review,
                key=lambda item: (
                    safe_float(
                        item.get(
                            "roi_percent"
                        )
                    ),
                    safe_float(
                        item.get(
                            "profit"
                        )
                    ),
                ),
            )
            if verified or review
            else None
        )

        market_summary = {
            "markets": stats[
                "markets"
            ],
            "guaranteed_arbs": stats[
                "verified"
            ],
            "almost_there": stats[
                "review"
            ],
            "best_value": stats[
                "observed"
            ],
            "worth_watching": stats[
                "incomplete"
            ],
            "best_market": best_market,
            "market_labels": {
                "VERIFIED": stats[
                    "verified"
                ],
                "REVIEW": stats[
                    "review"
                ],
                "OBSERVED": stats[
                    "observed"
                ],
                "INCOMPLETE": stats[
                    "incomplete"
                ],
                "INVALID": stats[
                    "invalid"
                ],
            },
        }

        return {
            "status": (
                "LIVE"
                if active
                else "WAITING"
            ),
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "source_path": str(
                CURRENT_STATE_FILE
            ),
            "error": None,
            "stats": stats,
            "market_summary": (
                market_summary
            ),
            "verified": verified,
            "review": review,
            "observed": observed,
            "recent": recent,
            "diagnostics": {
                "incomplete": (
                    incomplete
                ),
                "invalid": invalid,
            },
            "incomplete": incomplete,
            "invalid": invalid,
            "expired": expired,
            "execute": verified,
            "strong": [],
            "watch": observed,
            "all": active,
            "discoveries": active,
            "guaranteed_arbs": verified,
            "almost_there": review,
            "best_value": observed,
            "worth_watching": incomplete,
            "top_roi": (
                best_market
            ),
            "top_profit": (
                max(
                    verified,
                    key=lambda item: (
                        safe_float(
                            item.get(
                                "profit"
                            )
                        ),
                        safe_float(
                            item.get(
                                "roi_percent"
                            )
                        ),
                    ),
                )
                if verified
                else None
            ),
        }

    except Exception as exc:
        return {
            "status": "ERROR",
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "source_path": str(
                CURRENT_STATE_FILE
            ),
            "error": str(exc),
            "stats": {
                "markets": 0,
                "opportunities": 0,
                "verified": 0,
                "execute": 0,
                "strong": 0,
                "review": 0,
                "watch": 0,
                "observed": 0,
                "incomplete": 0,
                "invalid": 0,
                "diagnostics": 0,
                "highest_roi": 0.0,
                "average_roi": 0.0,
                "total_guaranteed_profit": 0.0,
                "average_confidence": 0.0,
                "average_discovery_score": 0.0,
                "bookmakers": 0,
            },
            "market_summary": {
                "markets": 0,
                "guaranteed_arbs": 0,
                "almost_there": 0,
                "best_value": 0,
                "worth_watching": 0,
                "best_market": None,
                "market_labels": {},
            },
            "verified": [],
            "review": [],
            "observed": [],
            "recent": [],
            "diagnostics": {
                "incomplete": [],
                "invalid": [],
            },
            "incomplete": [],
            "invalid": [],
            "expired": [],
            "execute": [],
            "strong": [],
            "watch": [],
            "all": [],
            "discoveries": [],
            "guaranteed_arbs": [],
            "almost_there": [],
            "best_value": [],
            "worth_watching": [],
            "top_roi": None,
            "top_profit": None,
        }