from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Any, Iterable

from playwright.sync_api import Locator

from app.browser import BrowserActionResult, WaitResult
from app.modules.arbitrage.execution.adapter import (
    AdapterStepResult,
    BrowserAdapter,
    ExecutionLeg,
    ExecutionStage,
)


@dataclass(slots=True)
class SportsbookSelectors:
    """Shared sportsbook selector and text fallbacks."""

    logged_in_markers: tuple[str, ...] = (
        "Deposit",
        "My Bets",
        "Cash Out",
        "Balance",
    )
    logged_out_markers: tuple[str, ...] = (
        "Log In",
        "Login",
        "Join",
        "Register",
    )
    cookie_buttons: tuple[str, ...] = (
        "Accept All Cookies",
        "Accept All",
        "Accept",
        "I Accept",
        "Allow All",
    )
    horse_racing_links: tuple[str, ...] = (
        "Horse Racing",
        "Racing",
    )
    win_market_names: tuple[str, ...] = (
        "Win",
        "Race Winner",
        "To Win",
    )
    stake_labels: tuple[str, ...] = (
        "Stake",
        "Enter Stake",
        "Stake Amount",
    )
    final_confirmation_markers: tuple[str, ...] = (
        "Place Bet",
        "Confirm Bet",
    )
    logged_in_css: tuple[str, ...] = (
        '[data-testid*="balance" i]',
        '[aria-label*="balance" i]',
        '[class*="balance" i]',
        '[data-test*="account" i]',
    )
    betslip_css: tuple[str, ...] = (
        '[data-testid*="betslip" i]',
        '[aria-label*="bet slip" i]',
        '[class*="betslip" i]',
        '[class*="bet-slip" i]',
    )
    stake_input_css: tuple[str, ...] = (
        'input[placeholder*="stake" i]',
        'input[aria-label*="stake" i]',
        'input[name*="stake" i]',
        '[data-testid*="stake" i] input',
        '[class*="betslip" i] input[inputmode="decimal"]',
        '[class*="betslip" i] input[type="number"]',
        'input[inputmode="decimal"]',
    )
    selection_container_xpath: str = (
        'xpath=ancestor-or-self::*['
        'self::button or self::a or @role="button" '
        'or @role="option"][1]'
    )
    selection_fallback_xpath: str = (
        'xpath=ancestor::*['
        'contains(@class, "participant") '
        'or contains(@class, "selection") '
        'or contains(@class, "runner")][1]'
    )


class GenericSportsbookAdapter(BrowserAdapter):
    """
    Reusable execution adapter for sportsbook websites.

    Concrete bookmaker adapters usually only define BOOKMAKER,
    DISPLAY_NAME, HOME_URL and selectors. Bookmaker-specific behaviour can
    override any hook. This class never presses the final bet button.
    """

    selectors: SportsbookSelectors

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not hasattr(self, "selectors"):
            self.selectors = SportsbookSelectors()

    def is_logged_in(self) -> bool:
        if self.browser.is_closed:
            return False

        self.dismiss_cookie_banner()
        page = self.browser.page

        for selector in self.selectors.logged_in_css:
            if self._visible_locator(page.locator(selector)):
                return True

        logged_in_score = sum(
            1
            for marker in self.selectors.logged_in_markers
            if self.browser.exists(marker, minimum_score=50.0, refresh=True)
        )
        logged_out_score = sum(
            1
            for marker in self.selectors.logged_out_markers
            if self.browser.exists(
                marker,
                clickable=True,
                minimum_score=55.0,
                refresh=True,
            )
        )
        return logged_in_score >= 1 and logged_out_score == 0

    def open_event(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        started = perf_counter()
        self.dismiss_cookie_banner()

        if leg.event_url:
            navigation = self.browser.goto(
                leg.event_url,
                timeout_ms=self.config.navigation_timeout_ms,
            )
            if not navigation.successful:
                return self.wait_step(
                    stage=ExecutionStage.OPEN_EVENT,
                    result=navigation,
                )
            if self.event_visible(leg):
                return self.success_step(
                    stage=ExecutionStage.OPEN_EVENT,
                    started=started,
                    message=f"{self.display_name} event opened from its direct URL.",
                    metadata={"event_url": leg.event_url, "url": self.browser.url},
                )

        racing_opened = self.open_horse_racing()
        event_queries = self.event_queries(leg)

        for query in event_queries:
            result = self.actions.search_and_click(
                query=query,
                secondary_query=leg.course,
                timeout_ms=self.config.default_timeout_ms,
                minimum_score=42.0,
            )
            if result.successful:
                self.browser.page.wait_for_timeout(350)
                return self.success_step(
                    stage=ExecutionStage.OPEN_EVENT,
                    started=started,
                    message=f"Opened {self.display_name} event using {query!r}.",
                    metadata={
                        "query": query,
                        "racing_navigation": (
                            racing_opened.to_dict()
                            if racing_opened is not None
                            else None
                        ),
                        "url": self.browser.url,
                    },
                )

        return self.failure_step(
            stage=ExecutionStage.OPEN_EVENT,
            started=started,
            message=f"{self.display_name} event could not be located.",
            error=(
                f"No event matched: {', '.join(event_queries)}"
                if event_queries
                else "Execution leg contained no usable event query."
            ),
            metadata={"event_queries": event_queries, "url": self.browser.url},
        )

    def select_market(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        started = perf_counter()
        requested = (leg.market_name or "Win").strip()

        if self.market_already_visible(requested):
            return self.success_step(
                stage=ExecutionStage.SELECT_MARKET,
                started=started,
                message=f"{self.display_name} market {requested!r} is already visible.",
                metadata={"market": requested, "url": self.browser.url},
            )

        result = self.actions.click_with_fallbacks(
            self.market_queries(requested),
            timeout_ms=self.config.default_timeout_ms,
            minimum_score=45.0,
        )
        if result.successful:
            return self.action_step(stage=ExecutionStage.SELECT_MARKET, result=result)

        if (
            requested.casefold()
            in {name.casefold() for name in self.selectors.win_market_names}
            and self.runner_visible(leg.selection_name)
        ):
            return self.success_step(
                stage=ExecutionStage.SELECT_MARKET,
                started=started,
                message="Runner list is visible; the default Win market is being used.",
                metadata={"requested_market": requested, "url": self.browser.url},
            )

        return self.failure_step(
            stage=ExecutionStage.SELECT_MARKET,
            started=started,
            message=f"{self.display_name} market {requested!r} could not be selected.",
            error=result.error,
            metadata=result.to_dict(),
        )

    def select_runner(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        started = perf_counter()
        selection = leg.selection_name.strip()
        if not selection:
            return self.failure_step(
                stage=ExecutionStage.SELECT_RUNNER,
                started=started,
                message="Execution leg has no runner name.",
                error="selection_name is empty.",
            )

        direct = self.click_runner_structurally(
            selection=selection,
            expected_odds=leg.decimal_odds,
        )
        if direct is not None and direct.successful:
            return self.action_step(stage=ExecutionStage.SELECT_RUNNER, result=direct)

        result = self.actions.search_and_click(
            query=selection,
            secondary_query=(
                self.format_decimal_odds(leg.decimal_odds)
                if leg.decimal_odds is not None
                else None
            ),
            timeout_ms=self.config.default_timeout_ms,
            minimum_score=48.0,
        )
        if result.successful:
            self.browser.page.wait_for_timeout(300)
            return self.action_step(stage=ExecutionStage.SELECT_RUNNER, result=result)

        return self.failure_step(
            stage=ExecutionStage.SELECT_RUNNER,
            started=started,
            message=f"{self.display_name} runner {selection!r} could not be selected.",
            error=result.error,
            metadata={
                "selection": selection,
                "expected_odds": leg.decimal_odds,
                "action": result.to_dict(),
            },
        )

    def enter_stake(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        started = perf_counter()
        try:
            stake = Decimal(str(leg.stake))
        except InvalidOperation:
            stake = Decimal("-1")

        if stake <= 0:
            return self.failure_step(
                stage=ExecutionStage.ENTER_STAKE,
                started=started,
                message="Execution leg contains an invalid stake.",
                error=f"Invalid stake: {leg.stake!r}",
            )

        stake_text = self.format_stake(stake)
        structural = self.fill_stake_structurally(stake_text)
        if structural is not None and structural.successful:
            return self.wait_step(stage=ExecutionStage.ENTER_STAKE, result=structural)

        for label in self.selectors.stake_labels:
            result = self.actions.find_and_fill(
                query=label,
                value=stake_text,
                secondary_query=leg.selection_name,
                timeout_ms=self.config.default_timeout_ms,
                minimum_score=35.0,
            )
            if result.successful:
                return self.action_step(stage=ExecutionStage.ENTER_STAKE, result=result)

        return self.failure_step(
            stage=ExecutionStage.ENTER_STAKE,
            started=started,
            message=f"{self.display_name} stake input could not be filled.",
            error="No visible enabled bet-slip stake input was found.",
            metadata={
                "stake": stake_text,
                "selection": leg.selection_name,
                "url": self.browser.url,
            },
        )

    def verify_ready(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        started = perf_counter()
        selection_visible = self.betslip_contains(leg.selection_name)
        stake_matches = self.stake_matches(leg.stake)
        final_button_visible = any(
            self.browser.exists(
                marker,
                clickable=True,
                minimum_score=45.0,
                refresh=True,
            )
            for marker in self.selectors.final_confirmation_markers
        )

        if self.config.verify_odds_when_available and leg.decimal_odds is not None:
            actual_odds = self.betslip_decimal_odds(leg.selection_name)
            odds_ok: bool | None = (
                actual_odds is None
                or abs(actual_odds - leg.decimal_odds) <= self.config.odds_tolerance
            )
        else:
            actual_odds = None
            odds_ok = None

        successful = selection_visible and stake_matches and odds_ok is not False
        metadata = {
            "selection_visible": selection_visible,
            "stake_matches": stake_matches,
            "final_confirmation_visible": final_button_visible,
            "expected_stake": leg.stake,
            "expected_odds": leg.decimal_odds,
            "actual_odds": actual_odds,
            "odds_ok": odds_ok,
            "url": self.browser.url,
        }

        if successful:
            return self.success_step(
                stage=ExecutionStage.VERIFY_READY,
                started=started,
                message=(
                    f"{self.display_name} bet slip is prepared for manual review "
                    "and confirmation."
                ),
                metadata=metadata,
            )

        failed_checks = [
            name
            for name, passed in (
                ("selection", selection_visible),
                ("stake", stake_matches),
                ("odds", odds_ok is not False),
            )
            if not passed
        ]
        return self.failure_step(
            stage=ExecutionStage.VERIFY_READY,
            started=started,
            message=f"{self.display_name} bet slip verification failed.",
            error=f"Failed checks: {', '.join(failed_checks)}.",
            metadata=metadata,
        )

    def dismiss_cookie_banner(self) -> BrowserActionResult | None:
        for text in self.selectors.cookie_buttons:
            if not self.browser.exists(
                text,
                clickable=True,
                minimum_score=55.0,
                refresh=True,
            ):
                continue
            result = self.actions.search_and_click(
                query=text,
                timeout_ms=2_500,
                minimum_score=55.0,
            )
            if result.successful:
                return result
        return None

    def open_horse_racing(self) -> BrowserActionResult | None:
        if any(
            token in self.browser.url.casefold()
            for token in ("horse-racing", "horseracing", "racing")
        ):
            return None
        for query in self.selectors.horse_racing_links:
            result = self.actions.search_and_click(
                query=query,
                timeout_ms=5_000,
                minimum_score=50.0,
            )
            if result.successful:
                self.browser.page.wait_for_timeout(300)
                return result
        return None

    def event_queries(self, leg: ExecutionLeg) -> tuple[str, ...]:
        values: list[str] = []
        if leg.event_name.strip():
            values.append(leg.event_name.strip())
        if leg.race_time and leg.course:
            values.extend((
                f"{leg.race_time} {leg.course}",
                f"{leg.course} {leg.race_time}",
            ))
        if leg.course:
            values.append(leg.course.strip())
        return self.unique(values)

    def market_queries(self, market: str) -> tuple[str, ...]:
        values = [market]
        if market.casefold() in {"win", "race winner", "to win"}:
            values.extend(self.selectors.win_market_names)
        return self.unique(values)

    def event_visible(self, leg: ExecutionLeg) -> bool:
        return any(
            self.browser.exists(query, minimum_score=42.0, refresh=True)
            for query in self.event_queries(leg)
        )

    def market_already_visible(self, market: str) -> bool:
        return any(
            self.browser.exists(query, minimum_score=50.0, refresh=True)
            for query in self.market_queries(market)
        )

    def runner_visible(self, selection: str) -> bool:
        return self.browser.exists(selection, minimum_score=48.0, refresh=True)

    def click_runner_structurally(
        self,
        *,
        selection: str,
        expected_odds: float | None,
    ) -> BrowserActionResult | None:
        page = self.browser.page
        escaped_selection = selection.replace('"', '\\"')
        candidate = page.get_by_text(selection, exact=True)
        if candidate.count() == 0:
            candidate = page.get_by_text(selection, exact=False)
        if candidate.count() == 0:
            candidate = page.locator(
                f'[aria-label*="{escaped_selection}" i], '
                f'[title*="{escaped_selection}" i]'
            )

        for index in range(min(candidate.count(), 10)):
            text_locator = candidate.nth(index)
            if not self._visible_locator(text_locator):
                continue
            clickable = text_locator.locator(self.selectors.selection_container_xpath)
            if clickable.count() == 0:
                clickable = text_locator.locator(
                    self.selectors.selection_fallback_xpath
                )
            if clickable.count() == 0:
                continue

            click_result = self.browser.click_locator(
                clickable.first,
                description=f"{self.display_name} runner {selection}",
            )
            return BrowserActionResult(
                successful=click_result.successful,
                action=f"{self.BOOKMAKER}_select_runner",
                elapsed_ms=click_result.elapsed_ms,
                message=click_result.message,
                error=click_result.error,
                steps=[],
                metadata={
                    "selection": selection,
                    "expected_odds": expected_odds,
                    "click": click_result.to_dict(),
                },
            )
        return None

    def fill_stake_structurally(self, stake_text: str) -> WaitResult | None:
        page = self.browser.page
        for selector in self.selectors.stake_input_css:
            locator = page.locator(selector)
            for index in range(min(locator.count(), 20)):
                candidate = locator.nth(index)
                if not self._visible_enabled_locator(candidate):
                    continue
                try:
                    candidate.fill("", timeout=self.config.default_timeout_ms)
                    candidate.fill(stake_text, timeout=self.config.default_timeout_ms)
                    return WaitResult(
                        successful=True,
                        condition=f"fill {self.display_name} stake input",
                        message=f"{self.display_name} stake input filled.",
                        metadata={"selector": selector, "stake": stake_text},
                    )
                except Exception:
                    continue
        return None

    def betslip_contains(self, text: str) -> bool:
        page = self.browser.page
        for selector in self.selectors.betslip_css:
            betslip = page.locator(selector)
            for index in range(min(betslip.count(), 5)):
                candidate = betslip.nth(index)
                if (
                    self._visible_locator(candidate)
                    and text.casefold() in self._safe_text(candidate).casefold()
                ):
                    return True
        return self.browser.exists(text, minimum_score=48.0, refresh=True)

    def stake_matches(self, stake: float) -> bool:
        expected = self.format_stake(Decimal(str(stake)))
        for selector in self.selectors.stake_input_css:
            locator = self.browser.page.locator(selector)
            for index in range(min(locator.count(), 20)):
                candidate = locator.nth(index)
                if not self._visible_locator(candidate):
                    continue
                try:
                    value = candidate.input_value().strip()
                except Exception:
                    continue
                if self.numeric_equal(value, expected):
                    return True

        for label in self.selectors.stake_labels:
            value = self.browser.value(label, minimum_score=35.0)
            if value is not None and self.numeric_equal(value, expected):
                return True
        return False

    def betslip_decimal_odds(self, selection: str) -> float | None:
        selection_locator = self.browser.page.get_by_text(selection, exact=False)
        for index in range(min(selection_locator.count(), 10)):
            candidate = selection_locator.nth(index)
            if not self._visible_locator(candidate):
                continue
            container = candidate.locator(
                'xpath=ancestor::*['
                'contains(@class, "betslip") '
                'or contains(@class, "selection")][1]'
            )
            if container.count() == 0:
                continue
            text = self._safe_text(container.first)
            for token in text.replace("\n", " ").split():
                try:
                    value = float(token)
                except ValueError:
                    continue
                if 1.01 <= value <= 1000:
                    return value
        return None

    @staticmethod
    def format_stake(stake: Decimal) -> str:
        quantized = stake.quantize(Decimal("0.01"))
        text = format(quantized, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    @staticmethod
    def format_decimal_odds(odds: float | None) -> str | None:
        if odds is None:
            return None
        return f"{odds:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def numeric_equal(left: str, right: str) -> bool:
        try:
            return Decimal(
                left.replace("£", "").replace(",", "").strip()
            ) == Decimal(
                right.replace("£", "").replace(",", "").strip()
            )
        except InvalidOperation:
            return False

    @staticmethod
    def unique(values: Iterable[str]) -> tuple[str, ...]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip()
            key = cleaned.casefold()
            if cleaned and key not in seen:
                output.append(cleaned)
                seen.add(key)
        return tuple(output)

    @staticmethod
    def _safe_text(locator: Locator) -> str:
        try:
            return locator.inner_text(timeout=1_000).strip()
        except Exception:
            return ""

    @staticmethod
    def _visible_locator(locator: Locator) -> bool:
        try:
            return locator.count() > 0 and locator.first.is_visible()
        except Exception:
            return False

    @staticmethod
    def _visible_enabled_locator(locator: Locator) -> bool:
        try:
            return (
                locator.count() > 0
                and locator.first.is_visible()
                and locator.first.is_enabled()
            )
        except Exception:
            return False
