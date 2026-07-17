from typing import Any


def _as_float(value: Any):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number <= 1:
        return None

    return number


def _round(value, digits=4):
    if value is None:
        return None

    return round(value, digits)


def _runner_price_analytics(runner):
    sportsbook_prices = []

    for price in runner.get("prices", []):
        if price.get("market_type") != "sportsbook":
            continue

        decimal_odds = _as_float(
            price.get("decimal")
        )

        if decimal_odds is None:
            continue

        sportsbook_prices.append(
            {
                "bookmaker": price.get("bookmaker"),
                "bookmaker_code": price.get("bookmaker_code"),
                "odds": price.get("odds"),
                "decimal": decimal_odds,
            }
        )

    if not sportsbook_prices:
        return {
            "sportsbook_price_count": 0,
            "best_decimal": None,
            "worst_decimal": None,
            "price_spread": None,
            "spread_percent": None,
            "best_bookmaker": None,
            "worst_bookmaker": None,
        }

    best = max(
        sportsbook_prices,
        key=lambda price: price["decimal"],
    )

    worst = min(
        sportsbook_prices,
        key=lambda price: price["decimal"],
    )

    price_spread = (
        best["decimal"]
        - worst["decimal"]
    )

    spread_percent = (
        price_spread
        / worst["decimal"]
        * 100
    )

    return {
        "sportsbook_price_count": len(
            sportsbook_prices
        ),
        "best_decimal": _round(
            best["decimal"]
        ),
        "worst_decimal": _round(
            worst["decimal"]
        ),
        "price_spread": _round(
            price_spread
        ),
        "spread_percent": _round(
            spread_percent,
            2,
        ),
        "best_bookmaker": best.get(
            "bookmaker"
        ),
        "best_bookmaker_code": best.get(
            "bookmaker_code"
        ),
        "worst_bookmaker": worst.get(
            "bookmaker"
        ),
        "worst_bookmaker_code": worst.get(
            "bookmaker_code"
        ),
    }


def analyse_market(runners):
    """
    Build race-level market intelligence from the best available
    sportsbook price for each runner.

    Exchanges remain available on each runner, but they are excluded
    from the sportsbook overround and arbitrage calculation.
    """

    runners = runners or []

    valid_runners = []
    bookmaker_codes = set()
    sportsbook_price_total = 0

    for runner in runners:
        analytics = _runner_price_analytics(
            runner
        )

        runner["market_analytics"] = analytics

        sportsbook_price_total += (
            analytics[
                "sportsbook_price_count"
            ]
        )

        for price in runner.get(
            "prices",
            [],
        ):
            if (
                price.get("market_type")
                == "sportsbook"
                and price.get(
                    "bookmaker_code"
                )
            ):
                bookmaker_codes.add(
                    price[
                        "bookmaker_code"
                    ]
                )

        best_decimal = _as_float(
            analytics.get(
                "best_decimal"
            )
        )

        if best_decimal is None:
            continue

        valid_runners.append(
            {
                "runner": runner,
                "best_decimal": best_decimal,
                "analytics": analytics,
            }
        )

    market_percentage = sum(
        1 / item["best_decimal"]
        for item in valid_runners
    ) * 100

    overround = (
        market_percentage - 100
        if valid_runners
        else None
    )

    favourite = None

    if valid_runners:
        favourite_item = min(
            valid_runners,
            key=lambda item: item[
                "best_decimal"
            ],
        )

        favourite = {
            "horse": favourite_item[
                "runner"
            ].get("horse"),
            "market_rank": favourite_item[
                "runner"
            ].get("market_rank"),
            "best_bookmaker": favourite_item[
                "analytics"
            ].get("best_bookmaker"),
            "best_odds": favourite_item[
                "runner"
            ].get("best_odds"),
            "best_decimal": _round(
                favourite_item[
                    "best_decimal"
                ]
            ),
            "implied_probability": _round(
                100
                / favourite_item[
                    "best_decimal"
                ],
                2,
            ),
        }

    widest_price_spread = None

    spread_candidates = [
        item
        for item in valid_runners
        if item["analytics"].get(
            "spread_percent"
        ) is not None
    ]

    if spread_candidates:
        widest = max(
            spread_candidates,
            key=lambda item: item[
                "analytics"
            ]["spread_percent"],
        )

        widest_price_spread = {
            "horse": widest[
                "runner"
            ].get("horse"),
            "best_bookmaker": widest[
                "analytics"
            ].get("best_bookmaker"),
            "worst_bookmaker": widest[
                "analytics"
            ].get("worst_bookmaker"),
            "lowest_decimal": widest[
                "analytics"
            ].get("worst_decimal"),
            "highest_decimal": widest[
                "analytics"
            ].get("best_decimal"),
            "spread": widest[
                "analytics"
            ].get("price_spread"),
            "spread_percent": widest[
                "analytics"
            ].get("spread_percent"),
        }

    average_bookmakers_per_runner = (
        sportsbook_price_total
        / len(runners)
        if runners
        else 0
    )

    complete_market = (
        len(valid_runners)
        == len(runners)
        and len(runners) > 1
    )

    is_arbitrage = bool(
        complete_market
        and market_percentage < 100
    )

    return {
        "calculation_version": (
            "best_sportsbook_market_v1"
        ),
        "runner_count": len(runners),
        "priced_runner_count": len(
            valid_runners
        ),
        "complete_market": (
            complete_market
        ),
        "market_percentage": (
            _round(
                market_percentage,
                2,
            )
            if valid_runners
            else None
        ),
        "overround": (
            _round(
                overround,
                2,
            )
            if overround is not None
            else None
        ),
        "is_arbitrage": is_arbitrage,
        "arbitrage_margin": (
            _round(
                100
                - market_percentage,
                2,
            )
            if is_arbitrage
            else 0.0
        ),
        "sportsbook_count": len(
            bookmaker_codes
        ),
        "sportsbook_price_count": (
            sportsbook_price_total
        ),
        "average_bookmakers_per_runner": (
            _round(
                average_bookmakers_per_runner,
                2,
            )
        ),
        "favourite": favourite,
        "widest_price_spread": (
            widest_price_spread
        ),
    }