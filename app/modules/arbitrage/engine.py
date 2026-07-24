from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse

from app.modules.arbitrage.matcher import normalize_runner_name
from app.modules.arbitrage.models import (
    MarketPrice,
    MarketStatus,
    MarketType,
    PriceSide,
    PriceSourceType,
    RaceMarket,
    RunnerMarket,
)
from app.modules.arbitrage.bookmakers import (
    get_bookmaker,
    is_sportsbook,
    is_verified_bookmaker,
    supports_horse_racing,
)

DEFAULT_OUTPUT_PATH = Path(
    "data/arbitrage/horse_opportunities.json"
)


def clean(value) -> str:
    return str(value or "").strip()


def utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def safe_int(
    value,
    default: Optional[int] = None,
) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value

    return clean(value).lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "non-runner",
        "non runner",
        "nr",
    }


def title_case_course(
    value: str,
) -> str:
    value = (
        unquote(
            clean(value)
        )
        .replace(
            "-",
            " ",
        )
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value.title()


def extract_race_metadata(
    snapshot: dict,
) -> dict:
    url = clean(
        snapshot.get("url")
    )

    course = clean(
        snapshot.get("course")
        or snapshot.get("meeting")
        or snapshot.get("track")
    )

    race_time = clean(
        snapshot.get("race_time")
        or snapshot.get("time")
        or snapshot.get("off_time")
    )

    race_date = clean(
        snapshot.get("race_date")
        or snapshot.get("date")
    )

    race_name = clean(
        snapshot.get("race_name")
        or snapshot.get("name")
    )

    collected_at = clean(
        snapshot.get("collected_at")
        or snapshot.get("captured_at")
        or snapshot.get("snapshot_at")
    )

    if url:
        parsed_url = urlparse(
            url
        )

        path = unquote(
            parsed_url.path
        ).rstrip("/")

        match = re.search(
            r"/horse-racing/(?P<course>[^/]+)/"
            r"(?P<race_time>\d{1,2}:\d{2})/winner$",
            path,
            flags=re.IGNORECASE,
        )

        if match:
            if not course:
                course = title_case_course(
                    match.group(
                        "course"
                    )
                )

            if not race_time:
                race_time = clean(
                    match.group(
                        "race_time"
                    )
                )

    if (
        not race_date
        and collected_at
    ):
        try:
            race_date = (
                datetime.fromisoformat(
                    collected_at.replace(
                        "Z",
                        "+00:00",
                    )
                )
                .date()
                .isoformat()
            )

        except ValueError:
            pass

    if (
        not race_name
        and course
        and race_time
    ):
        race_name = (
            f"{course} {race_time}"
        )

    race_id = clean(
        snapshot.get("race_id")
        or snapshot.get("race_key")
        or url
    )

    if not race_id:
        race_id = "|".join(
            value
            for value in (
                race_date,
                course,
                race_time,
            )
            if value
        )

    return {
        "race_id": race_id,
        "course": course,
        "race_time": race_time,
        "race_date": race_date,
        "race_name": (
            race_name or None
        ),
        "url": url or None,
        "collected_at": (
            collected_at
            or utc_now_iso()
        ),
    }


def snapshot_runner_count(
    snapshot: dict,
) -> int:
    explicit = safe_int(
        snapshot.get("runner_count")
        or snapshot.get(
            "expected_runner_count"
        )
        or snapshot.get("field_size")
    )

    if (
        explicit is not None
        and explicit >= 0
    ):
        return explicit

    return len(
        [
            runner
            for runner in snapshot.get(
                "runners",
                [],
            )
            if isinstance(
                runner,
                dict,
            )
        ]
    )


def resolve_market_status(
    snapshot: dict,
) -> MarketStatus:
    raw_status = clean(
        snapshot.get("market_status")
        or snapshot.get("status")
    ).upper()

    for status in MarketStatus:
        if raw_status == status.value:
            return status

    if truthy(
        snapshot.get("suspended")
    ):
        return MarketStatus.SUSPENDED

    if truthy(
        snapshot.get("closed")
    ):
        return MarketStatus.CLOSED

    return MarketStatus.OPEN


class ArbitrageEngine:
    """
    Converts Oddschecker snapshots into RaceMarket objects,
    scans complete markets for horse-racing back/back arbs,
    ranks opportunities, and optionally stores dashboard output.

    Only prices confirmed by the Oddschecker DOM parser are trusted
    for arbitrage calculations. Text-parser fallback prices remain
    available in the raw snapshot but are not loaded into RaceMarket.
    """

    def __init__(self):
        self.races: dict[
            str,
            RaceMarket,
        ] = {}

    def build_market(
        self,
        snapshot: dict,
    ) -> RaceMarket:
        metadata = extract_race_metadata(
            snapshot
        )

        race = RaceMarket(
            race_id=metadata[
                "race_id"
            ],
            course=metadata[
                "course"
            ],
            race_time=metadata[
                "race_time"
            ],
            race_date=metadata[
                "race_date"
            ],
            race_name=metadata[
                "race_name"
            ],
            source_url=metadata[
                "url"
            ],
            market_type=(
                MarketType.WIN
            ),
            status=resolve_market_status(
                snapshot
            ),
            collected_at=metadata[
                "collected_at"
            ],
            expected_runner_count=(
                snapshot_runner_count(
                    snapshot
                )
            ),
            metadata={
                "snapshot_source": (
                    clean(
                        snapshot.get(
                            "source"
                        )
                    )
                    or "oddschecker"
                ),
                "snapshot_id": (
                    clean(
                        snapshot.get(
                            "snapshot_id"
                        )
                    )
                    or None
                ),
                "dom_price_row_count": (
                    safe_int(
                        snapshot.get(
                            "dom_price_row_count"
                        ),
                        0,
                    )
                    or 0
                ),
                "dom_bookmaker_count": (
                    safe_int(
                        snapshot.get(
                            "dom_bookmaker_count"
                        ),
                        0,
                    )
                    or 0
                ),
            },
        )

        for runner_data in snapshot.get(
            "runners",
            [],
        ):
            if not isinstance(
                runner_data,
                dict,
            ):
                continue

            runner_name = clean(
                runner_data.get(
                    "horse"
                )
                or runner_data.get(
                    "runner"
                )
                or runner_data.get(
                    "name"
                )
            )

            if not runner_name:
                continue

            status_text = clean(
                runner_data.get(
                    "status"
                )
            ).upper()

            confirmed_dom_prices = (
                runner_data.get(
                    "confirmed_dom_prices"
                )
                is True
            )

            runner = RunnerMarket(
                runner_name=runner_name,
                runner_key=(
                    normalize_runner_name(
                        runner_name
                    )
                ),
                draw=runner_data.get(
                    "draw"
                ),
                card_number=(
                    runner_data.get(
                        "card_number"
                    )
                    or runner_data.get(
                        "number"
                    )
                ),
                horse_id=(
                    clean(
                        runner_data.get(
                            "horse_id"
                        )
                    )
                    or None
                ),
                is_non_runner=truthy(
                    runner_data.get(
                        "is_non_runner"
                    )
                    or runner_data.get(
                        "non_runner"
                    )
                    or runner_data.get(
                        "withdrawn"
                    )
                    or status_text
                    in {
                        "NR",
                        "NON_RUNNER",
                        "NON-RUNNER",
                        "WITHDRAWN",
                    }
                ),
                market_rank=safe_int(
                    runner_data.get(
                        "market_rank"
                    )
                ),
                metadata={
                    "confirmed_dom_prices": (
                        confirmed_dom_prices
                    ),
                    "raw_runner": {
                        key: value
                        for key, value
                        in runner_data.items()
                        if key != "prices"
                    },
                },
            )

            if confirmed_dom_prices:
                for price_data in runner_data.get(
                    "prices",
                    [],
                ):
                    if not isinstance(
                        price_data,
                        dict,
                    ):
                        continue

                    bookmaker = clean(
                        price_data.get("bookmaker")
                        or price_data.get("source")
                    )

                    book = get_bookmaker(bookmaker)

                    if book is None:
                        continue

                    if not is_verified_bookmaker(bookmaker):
                        continue

                    if not is_sportsbook(bookmaker):
                        continue

                    if not supports_horse_racing(bookmaker):
                        continue

                    raw_odds = clean(
                        price_data.get("odds")
                        or price_data.get("raw_odds")
                )                 

                    decimal_odds = (
                        price_data.get(
                            "decimal"
                        )
                        or price_data.get(
                            "decimal_odds"
                        )
                    )

                    if (
                        not bookmaker
                        or bookmaker
                        .lower()
                        .startswith(
                            "bookmaker "
                        )
                        or decimal_odds
                        is None
                    ):
                        continue

                    try:
                        decimal_odds = float(
                            decimal_odds
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        continue

                    if decimal_odds <= 1:
                        continue

                    captured_at = clean(
                        price_data.get(
                            "captured_at"
                        )
                        or price_data.get(
                            "collected_at"
                        )
                        or metadata[
                            "collected_at"
                        ]
                    )

                    runner.add_price(
                        MarketPrice(
                            source=bookmaker,
                            source_type=(
                                PriceSourceType
                                .BOOKMAKER
                            ),
                            side=(
                                PriceSide.BACK
                            ),
                            decimal_odds=(
                                decimal_odds
                            ),
                            raw_odds=(
                                raw_odds
                                or None
                            ),
                            captured_at=(
                                captured_at
                                or utc_now_iso()
                            ),
                            source_url=(
                                clean(
                                    price_data.get(
                                        "url"
                                    )
                                    or price_data.get(
                                        "source_url"
                                    )
                                    or metadata[
                                        "url"
                                    ]
                                )
                                or None
                            ),
                            market_id=(
                                clean(
                                    price_data.get(
                                        "market_id"
                                    )
                                )
                                or None
                            ),
                            selection_id=(
                                clean(
                                    price_data.get(
                                        "selection_id"
                                    )
                                )
                                or None
                            ),
                            is_active=(
                                not truthy(
                                    price_data.get(
                                        "inactive"
                                    )
                                )
                            ),
                            metadata={
                                "price_captured_at": (
                                    captured_at
                                    or utc_now_iso()
                                ),
                                "confirmed_dom_price": (
                                    True
                                ),
                            },
                        )
                    )

            # Always keep every listed runner.
            #
            # A runner without confirmed DOM prices remains present
            # but has no trusted MarketPrice records. This ensures
            # incomplete DOM markets cannot create false arbitrage.
            race.add_runner(
                runner
            )

        active_runners = (
            race.active_runners()
        )

        active_count = len(
            active_runners
        )

        priced_count = sum(
            1
            for runner in active_runners
            if runner.best_back_price(
                race.market_type
            )
            is not None
        )

        confirmed_runner_count = sum(
            1
            for runner in active_runners
            if runner.metadata.get(
                "confirmed_dom_prices"
            )
            is True
        )

        if (
            race.status
            == MarketStatus.OPEN
        ):
            if active_count == 0:
                race.status = (
                    MarketStatus
                    .INCOMPLETE
                )

            elif priced_count != active_count:
                race.status = (
                    MarketStatus
                    .INCOMPLETE
                )

            elif (
                confirmed_runner_count
                != active_count
            ):
                race.status = (
                    MarketStatus
                    .INCOMPLETE
                )

            elif (
                race.expected_runner_count
                is not None
                and active_count
                != race.expected_runner_count
            ):
                race.status = (
                    MarketStatus
                    .INCOMPLETE
                )

        race.metadata.update(
            {
                "active_runner_count": (
                    active_count
                ),
                "priced_runner_count": (
                    priced_count
                ),
                "confirmed_dom_runner_count": (
                    confirmed_runner_count
                ),
                "all_active_runners_confirmed": (
                    active_count > 0
                    and confirmed_runner_count
                    == active_count
                ),
            }
        )

        return race

    def load_snapshot(
        self,
        snapshot: dict,
    ) -> RaceMarket:
        race = self.build_market(
            snapshot
        )

        self.races[
            race.race_id
        ] = race

        return race

    def load_many(
        self,
        snapshots: Iterable[dict],
    ) -> list[RaceMarket]:
        markets = []

        for snapshot in snapshots:
            if not isinstance(
                snapshot,
                dict,
            ):
                continue

            try:
                markets.append(
                    self.load_snapshot(
                        snapshot
                    )
                )

            except ValueError:
                continue

        return markets

    def scan_market(
        self,
        market: RaceMarket,
        total_stake: float = 100.0,
    ):
        # Local import avoids engine/scanner circular imports.
        from app.modules.arbitrage.scanner import scan_market

        return scan_market(
            market,
            total_stake=total_stake,
        )

    def scan_all(
        self,
        total_stake: float = 100.0,
        include_non_arbs: bool = False,
    ):
        from app.modules.arbitrage.scanner import scan_markets

        return scan_markets(
            self.all_markets(),
            total_stake=total_stake,
            include_non_arbs=(
                include_non_arbs
            ),
        )

    def discover(
        self,
        total_stake: float = 100.0,
        minimum_score: float = 0.0,
        max_price_age_seconds: int = 300,
        target_stable_seconds: int = 120,
    ):
        from app.modules.arbitrage.ranking import (
            rank_opportunities,
        )

        scan_results = self.scan_all(
            total_stake=total_stake,
            include_non_arbs=True,
        )

        from app.modules.arbitrage.discovery import (
            discover_markets,
        )

        discover_markets(
            scan_results,
        )

        opportunities = [
            result.opportunity
            for result in scan_results
            if result.opportunity
            is not None
        ]

        return rank_opportunities(
            opportunities,
            max_price_age_seconds=(
                max_price_age_seconds
            ),
            target_stable_seconds=(
                target_stable_seconds
            ),
            minimum_score=(
                minimum_score
            ),
        )

    def process_snapshots(
        self,
        snapshots: Iterable[dict],
        total_stake: float = 100.0,
        minimum_score: float = 0.0,
        max_price_age_seconds: int = 300,
        target_stable_seconds: int = 120,
    ):
        self.clear()

        self.load_many(
            snapshots
        )

        return self.discover(
            total_stake=total_stake,
            minimum_score=minimum_score,
            max_price_age_seconds=(
                max_price_age_seconds
            ),
            target_stable_seconds=(
                target_stable_seconds
            ),
        )

    def build_dashboard_payload(
        self,
        ranked_opportunities,
    ) -> dict:
        from app.modules.arbitrage.discovery import (
            discover_markets,
            discovery_summary,
        )

        ranked = list(
            ranked_opportunities
        )

        labels = {}

        for result in ranked:
            labels[
                result.execution_label
            ] = (
                labels.get(
                    result.execution_label,
                    0,
                )
                + 1
            )

        scan_results = self.scan_all(
            total_stake=100.0,
            include_non_arbs=True,
        )

        discoveries = discover_markets(
            scan_results,
            include_ignored=False,
            include_incomplete=False,
        )

        market_summary = (
            discovery_summary(
                discoveries
            )
        )

        return {
            "status": "READY",
            "generated_at": (
                utc_now_iso()
            ),
            "summary": {
                **self.summary(),
                "opportunities": len(
                    ranked
                ),
                "profitable": sum(
                    1
                    for result in ranked
                    if (
                        result.opportunity
                        .is_profitable
                    )
                ),
                "verified": sum(
                    1
                    for result in ranked
                    if (
                        result.opportunity
                        .is_verified
                    )
                ),
                "execute": labels.get(
                    "EXECUTE",
                    0,
                ),
                "strong": labels.get(
                    "STRONG",
                    0,
                ),
                "review": labels.get(
                    "REVIEW",
                    0,
                ),
                "watch": labels.get(
                    "WATCH",
                    0,
                ),
                "guaranteed_arbs": (
                    market_summary.get(
                        "guaranteed_arbs",
                        0,
                    )
                ),
                "almost_there": (
                    market_summary.get(
                        "almost_there",
                        0,
                    )
                ),
                "best_value": (
                    market_summary.get(
                        "best_value",
                        0,
                    )
                ),
                "worth_watching": (
                    market_summary.get(
                        "worth_watching",
                        0,
                    )
                ),
                "best_market": (
                    market_summary.get(
                        "best_market"
                    )
                ),
                "labels": labels,
                "market_labels": (
                    market_summary.get(
                        "labels",
                        {},
                    )
                ),
            },
            "opportunities": [
                result.to_dict()
                for result in ranked
            ],
            "discoveries": [
                discovery.to_dict()
                for discovery
                in discoveries
            ],
        }

    def save_dashboard(
        self,
        ranked_opportunities,
        output_path: Path | str = (
            DEFAULT_OUTPUT_PATH
        ),
    ) -> Path:
        path = Path(
            output_path
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = (
            self.build_dashboard_payload(
                ranked_opportunities
            )
        )

        temp_path = path.with_suffix(
            path.suffix + ".tmp"
        )

        temp_path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        temp_path.replace(
            path
        )

        return path

    def run(
        self,
        snapshots: Iterable[dict],
        total_stake: float = 100.0,
        minimum_score: float = 0.0,
        output_path: Path | str = (
            DEFAULT_OUTPUT_PATH
        ),
        max_price_age_seconds: int = 300,
        target_stable_seconds: int = 120,
    ) -> dict:
        ranked = self.process_snapshots(
            snapshots=snapshots,
            total_stake=total_stake,
            minimum_score=minimum_score,
            max_price_age_seconds=(
                max_price_age_seconds
            ),
            target_stable_seconds=(
                target_stable_seconds
            ),
        )

        saved_path = self.save_dashboard(
            ranked,
            output_path=output_path,
        )

        return {
            "ranked": ranked,
            "saved_path": (
                saved_path
            ),
            "payload": (
                self.build_dashboard_payload(
                    ranked
                )
            ),
        }

    def get_market(
        self,
        race_id,
    ):
        return self.races.get(
            race_id
        )

    def all_markets(
        self,
    ) -> list[RaceMarket]:
        return list(
            self.races.values()
        )

    def clear(
        self,
    ) -> None:
        self.races.clear()

    def summary(
        self,
    ) -> dict:
        races = len(
            self.races
        )

        runners = sum(
            market.runner_count
            for market
            in self.races.values()
        )

        prices = sum(
            len(
                runner.prices
            )
            for market
            in self.races.values()
            for runner
            in market.runners
        )

        complete_markets = sum(
            1
            for market
            in self.races.values()
            if market.is_complete
        )

        return {
            "races": races,
            "runners": runners,
            "prices": prices,
            "complete_markets": (
                complete_markets
            ),
            "incomplete_markets": (
                races
                - complete_markets
            ),
        }


engine = ArbitrageEngine()