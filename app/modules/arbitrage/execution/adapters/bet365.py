from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from playwright.sync_api import Locator

from app.browser import BrowserActionResult, WaitResult
from app.modules.arbitrage.execution.adapter import (
    AdapterStepResult,
    ExecutionLeg,
    ExecutionStage,
)
from app.modules.arbitrage.execution.generic_adapter import (
    GenericSportsbookAdapter,
    SportsbookSelectors,
)
from app.modules.arbitrage.execution.registry import register_adapter


@dataclass(slots=True)
class Bet365Selectors(SportsbookSelectors):
    """Bet365-specific wording and structural selector fallbacks."""

    logged_in_markers: tuple[str, ...] = (
        "Deposit",
        "My Bets",
        "Cash Out",
        "Balance",
    )
    logged_out_markers: tuple[str, ...] = (
        "Log In",
        "Join",
        "Register",
    )
    cookie_buttons: tuple[str, ...] = (
        "Accept All Cookies",
        "Accept All",
        "Accept",
        "I Accept",
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
        "Bet",
    )
    logged_in_css: tuple[str, ...] = (
        '[data-testid*="balance" i]',
        '[aria-label*="balance" i]',
        '[class*="balance" i]',
    )
    betslip_css: tuple[str, ...] = (
        '[data-testid*="betslip" i]',
        '[aria-label*="bet slip" i]',
        '[class*="betslip" i]',
        '[class*="bet-slip" i]',
        '[class*="slip" i]',
    )
    stake_input_css: tuple[str, ...] = (
        'input[placeholder*="stake" i]',
        'input[aria-label*="stake" i]',
        'input[name*="stake" i]',
        '[data-testid*="stake" i] input',
        '[class*="betslip" i] input[inputmode="decimal"]',
        '[class*="betslip" i] input[type="number"]',
        '[class*="slip" i] input[inputmode="decimal"]',
        'input[inputmode="decimal"]',
    )


@register_adapter(
    aliases=(
        "bet 365",
        "Bet365",
        "bet365 sportsbook",
    )
)
class Bet365Adapter(GenericSportsbookAdapter):
    """
    Bet365 execution adapter.

    Pulse may navigate, choose a runner and fill a stake, but it never
    presses the final Bet / Place Bet / Confirm control.
    """

    BOOKMAKER = "bet365"
    DISPLAY_NAME = "Bet365"
    HOME_URL = "https://www.bet365.com/"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.selectors = Bet365Selectors()

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
            if navigation.successful and self._race_page_ready(leg):
                return self.success_step(
                    stage=ExecutionStage.OPEN_EVENT,
                    started=started,
                    message="Bet365 race opened from its direct URL.",
                    metadata={
                        "event_url": leg.event_url,
                        "url": self.browser.url,
                    },
                )

        self.open_horse_racing()
        page = self.browser.page
        page.wait_for_timeout(700)

        for label in self._race_labels(leg):
            candidate = page.get_by_text(label, exact=False)

            for index in range(min(candidate.count(), 12)):
                text_locator = candidate.nth(index)
                if not self._visible_locator(text_locator):
                    continue

                clickable = self._nearest_clickable(text_locator)
                if clickable is None:
                    continue

                result = self.browser.click_locator(
                    clickable,
                    description=f"Bet365 race {label}",
                )
                if not result.successful:
                    continue

                page.wait_for_timeout(900)

                if self._race_page_ready(leg):
                    return self.success_step(
                        stage=ExecutionStage.OPEN_EVENT,
                        started=started,
                        message=f"Opened Bet365 race using {label!r}.",
                        metadata={
                            "race_label": label,
                            "url": self.browser.url,
                        },
                    )

        return super().open_event(leg)

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

        if self.betslip_contains(selection):
            return self.success_step(
                stage=ExecutionStage.SELECT_RUNNER,
                started=started,
                message=f"Bet365 runner {selection!r} is already in the bet slip.",
                metadata={"selection": selection},
            )

        page = self.browser.page
        runner_names = page.get_by_text(selection, exact=True)

        if runner_names.count() == 0:
            runner_names = page.get_by_text(selection, exact=False)

        for index in range(min(runner_names.count(), 12)):
            runner_name = runner_names.nth(index)
            if not self._visible_locator(runner_name):
                continue

            for odds_button in self._runner_odds_candidates(runner_name):
                result = self.browser.click_locator(
                    odds_button,
                    description=f"Bet365 odds for {selection}",
                )
                if not result.successful:
                    continue

                page.wait_for_timeout(600)

                if self.betslip_contains(selection):
                    return self.success_step(
                        stage=ExecutionStage.SELECT_RUNNER,
                        started=started,
                        message=f"Selected Bet365 runner {selection!r}.",
                        metadata={
                            "selection": selection,
                            "expected_odds": leg.decimal_odds,
                            "click": result.to_dict(),
                        },
                    )

        return self.failure_step(
            stage=ExecutionStage.SELECT_RUNNER,
            started=started,
            message=f"Bet365 runner {selection!r} could not be added.",
            error=(
                "The runner name was found, but no odds control produced "
                "a verified bet-slip selection."
            ),
            metadata={
                "selection": selection,
                "expected_odds": leg.decimal_odds,
                "url": self.browser.url,
            },
        )

    def _race_page_ready(self, leg: ExecutionLeg) -> bool:
        return (
            self.runner_visible(leg.selection_name)
            or (
                bool(leg.course)
                and self.browser.exists(
                    leg.course,
                    minimum_score=42.0,
                    refresh=True,
                )
                and not self._looks_like_racing_hub()
            )
        )

    def _looks_like_racing_hub(self) -> bool:
        page = self.browser.page
        return (
            self._visible_locator(page.get_by_text("UK & Ireland Races", exact=False))
            or self._visible_locator(page.get_by_text("Place Boost Races", exact=False))
        )

    def _race_labels(self, leg: ExecutionLeg) -> tuple[str, ...]:
        course = (leg.course or "").strip()
        values: list[str] = []

        for race_time in self._time_variants(leg.race_time):
            if course:
                values.extend(
                    (
                        f"{race_time} {course}",
                        f"{course} {race_time}",
                    )
                )
            else:
                values.append(race_time)

        if leg.event_name:
            values.append(leg.event_name)

        return self.unique(values)

    @staticmethod
    def _time_variants(race_time: str | None) -> tuple[str, ...]:
        if not race_time:
            return ()

        raw = race_time.strip()
        values = [raw, raw.replace(":", ".")]

        try:
            hour_text, minute = raw.replace(".", ":").split(":", 1)
            hour = int(hour_text)
            hour_12 = hour % 12 or 12

            values.extend(
                (
                    f"{hour_12}:{minute}",
                    f"{hour_12}.{minute}",
                    f"{hour_12:02d}:{minute}",
                    f"{hour_12:02d}.{minute}",
                )
            )
        except (TypeError, ValueError):
            pass

        output: list[str] = []
        seen: set[str] = set()

        for value in values:
            key = value.casefold()
            if value and key not in seen:
                output.append(value)
                seen.add(key)

        return tuple(output)

    def _nearest_clickable(self, locator: Locator) -> Locator | None:
        direct = locator.locator(
            'xpath=ancestor-or-self::*['
            'self::button or self::a or @role="button"][1]'
        )
        if direct.count() > 0 and self._visible_enabled_locator(direct.first):
            return direct.first

        for level in range(1, 6):
            ancestor = locator.locator(f"xpath=ancestor::*[{level}]")
            if ancestor.count() == 0:
                continue

            candidate = ancestor.first
            if not self._visible_enabled_locator(candidate):
                continue

            text = self._safe_text(candidate)
            if 0 < len(text) <= 180:
                return candidate

        return None

    def _runner_odds_candidates(
        self,
        runner_name: Locator,
    ) -> list[Locator]:
        candidates: list[Locator] = []
        runner_text = self._safe_text(runner_name).casefold()

        for level in range(1, 8):
            row = runner_name.locator(f"xpath=ancestor::*[{level}]")
            if row.count() == 0:
                continue

            row = row.first
            if not self._visible_locator(row):
                continue

            text = self._safe_text(row)
            if not text or len(text) > 260:
                continue

            controls = row.locator(
                'button, [role="button"], [tabindex="0"], '
                '[class*="price" i], [class*="odds" i]'
            )
            visible: list[Locator] = []

            for index in range(min(controls.count(), 12)):
                control = controls.nth(index)
                if not self._visible_enabled_locator(control):
                    continue

                control_text = self._safe_text(control).strip()

                if control_text.casefold() == runner_text:
                    continue

                if self._looks_like_odds(control_text):
                    visible.append(control)

            if visible:
                candidates.extend(reversed(visible))
                break

        return candidates

    @staticmethod
    def _looks_like_odds(text: str) -> bool:
        cleaned = text.strip().replace(" ", "")
        if not cleaned:
            return False

        if "/" in cleaned:
            left, _, right = cleaned.partition("/")
            return left.isdigit() and right.isdigit()

        try:
            value = float(cleaned)
        except ValueError:
            return False

        return 1.01 <= value <= 1000