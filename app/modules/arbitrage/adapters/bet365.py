from __future__ import annotations

from typing import Iterable

from playwright.sync_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from app.modules.arbitrage.adapters.base import (
    BookmakerAdapter,
    PreparationRequest,
    PreparationResult,
    PreparationStage,
    PreparationStatus,
)


class Bet365Adapter(BookmakerAdapter):
    """
    Browser preparation adapter for Bet365.

    Initial responsibilities:

    - Ensure the Bet365 homepage is open.
    - Detect security-verification pages.
    - Attempt to open Bet365 search.
    - Search for the requested race.
    - Attempt to open the matching event.

    Selection clicking and stake entry are deliberately left disabled
    until the event-navigation flow has been tested reliably.
    """

    bookmaker_id = "bet365"

    SEARCH_BUTTON_SELECTORS = (
        '[aria-label*="Search" i]',
        'button[title*="Search" i]',
        '[data-testid*="search" i]',
        '.hm-MainHeaderRHSLoggedOutWide_Search',
        '.hm-MainHeaderRHSLoggedInWide_Search',
        'text=/^Search$/i',
    )

    SEARCH_INPUT_SELECTORS = (
        'input[type="search"]',
        'input[placeholder*="Search" i]',
        'input[aria-label*="Search" i]',
        '[data-testid*="search"] input',
        '.scc-SearchInput_Input',
    )

    SECURITY_TEXT = (
        "verify you are human",
        "security verification",
        "checking your browser",
        "performing security verification",
        "cloudflare",
        "please wait while we verify",
    )

    def prepare_event(
        self,
        page: Page,
        request: PreparationRequest,
        result: PreparationResult,
    ) -> PreparationResult:
        self._ensure_homepage(
            page=page,
            request=request,
            result=result,
        )

        if self._security_challenge_detected(
            page
        ):
            result.add_warning(
                "Bet365 security verification is active. "
                "Complete the challenge manually in the open browser."
            )

            return result.complete(
                status=PreparationStatus.PARTIAL,
                stage=PreparationStage.HOMEPAGE_OPEN,
                message=(
                    "Bet365 opened, but manual security "
                    "verification is required."
                ),
            )

        search_button = self._first_visible(
            page=page,
            selectors=self.SEARCH_BUTTON_SELECTORS,
            timeout_ms=1_500,
        )

        search_input = self._first_visible(
            page=page,
            selectors=self.SEARCH_INPUT_SELECTORS,
            timeout_ms=750,
        )

        if search_input is None:
            if search_button is None:
                result.add_warning(
                    "Bet365 search control was not found."
                )

                return result.complete(
                    status=PreparationStatus.PARTIAL,
                    stage=PreparationStage.HOMEPAGE_OPEN,
                    message=(
                        "Bet365 is open, but Pulse could not "
                        "locate the search control."
                    ),
                )

            try:
                search_button.click(
                    timeout=5_000
                )

                result.stage = (
                    PreparationStage.SEARCH_OPEN
                )

            except Exception as exc:
                result.add_warning(
                    f"Could not open Bet365 search: {exc}"
                )

                return result.complete(
                    status=PreparationStatus.PARTIAL,
                    stage=PreparationStage.HOMEPAGE_OPEN,
                    message=(
                        "Bet365 opened, but search could not "
                        "be activated."
                    ),
                )

            search_input = self._first_visible(
                page=page,
                selectors=self.SEARCH_INPUT_SELECTORS,
                timeout_ms=5_000,
            )

        else:
            result.stage = (
                PreparationStage.SEARCH_OPEN
            )

        if search_input is None:
            result.add_warning(
                "Bet365 search opened, but no search input appeared."
            )

            return result.complete(
                status=PreparationStatus.PARTIAL,
                stage=PreparationStage.SEARCH_OPEN,
                message=(
                    "Bet365 search opened, but Pulse could not "
                    "locate the input field."
                ),
            )

        search_text = (
            request.event.search_text
        ).strip()

        try:
            search_input.fill(
                search_text,
                timeout=5_000,
            )

            search_input.press(
                "Enter",
                timeout=5_000,
            )

            result.stage = (
                PreparationStage.SEARCH_SUBMITTED
            )

        except Exception as exc:
            result.add_warning(
                f"Bet365 search submission failed: {exc}"
            )

            return result.complete(
                status=PreparationStatus.PARTIAL,
                stage=PreparationStage.SEARCH_OPEN,
                message=(
                    "Bet365 search opened, but the event query "
                    "could not be submitted."
                ),
            )

        matching_event = self._find_event_result(
            page=page,
            venue=request.event.venue,
            start_time=request.event.start_time,
        )

        if matching_event is None:
            result.add_warning(
                "No confident matching race result was found."
            )

            return result.complete(
                status=PreparationStatus.PARTIAL,
                stage=PreparationStage.SEARCH_SUBMITTED,
                message=(
                    f"Bet365 search submitted for "
                    f"{request.event.search_text}. "
                    "Manual event selection may be required."
                ),
            )

        result.stage = (
            PreparationStage.EVENT_FOUND
        )

        try:
            matching_event.click(
                timeout=5_000
            )

            page.wait_for_timeout(
                1_000
            )

            result.stage = (
                PreparationStage.EVENT_OPEN
            )

        except Exception as exc:
            result.add_warning(
                f"Matching Bet365 event could not be opened: {exc}"
            )

            return result.complete(
                status=PreparationStatus.PARTIAL,
                stage=PreparationStage.EVENT_FOUND,
                message=(
                    "The matching Bet365 race was found, but "
                    "Pulse could not open it automatically."
                ),
            )

        if request.select_market:
            result.add_warning(
                "Automatic Win market selection is not enabled yet."
            )

        if request.select_runner:
            result.add_warning(
                "Automatic runner selection is not enabled yet."
            )

        if request.enter_stake:
            result.add_warning(
                "Automatic stake entry is not enabled yet."
            )

        return result.complete(
            status=PreparationStatus.PARTIAL,
            stage=PreparationStage.EVENT_OPEN,
            message=(
                f"Bet365 prepared the event for "
                f"{request.selection.name}. "
                "Runner selection remains manual."
            ),
        )

    def _ensure_homepage(
        self,
        page: Page,
        request: PreparationRequest,
        result: PreparationResult,
    ) -> None:
        current_url = (
            page.url or ""
        ).strip()

        must_navigate = (
            request.navigate_home_first
            or not current_url
            or current_url == "about:blank"
            or "bet365" not in current_url.lower()
        )

        if must_navigate:
            page.goto(
                self.bookmaker.homepage,
                wait_until="domcontentloaded",
                timeout=30_000,
            )

        result.stage = (
            PreparationStage.HOMEPAGE_OPEN
        )
        result.current_url = page.url

    def _security_challenge_detected(
        self,
        page: Page,
    ) -> bool:
        try:
            title = (
                page.title() or ""
            ).lower()
        except Exception:
            title = ""

        try:
            body_text = (
                page.locator("body")
                .inner_text(timeout=2_000)
                .lower()
            )
        except Exception:
            body_text = ""

        combined = (
            f"{title}\n{body_text}"
        )

        return any(
            phrase in combined
            for phrase in self.SECURITY_TEXT
        )

    def _first_visible(
        self,
        page: Page,
        selectors: Iterable[str],
        timeout_ms: int,
    ) -> Locator | None:
        for selector in selectors:
            try:
                locator = (
                    page.locator(selector)
                    .first
                )

                locator.wait_for(
                    state="visible",
                    timeout=timeout_ms,
                )

                return locator

            except (
                PlaywrightTimeoutError,
                Exception,
            ):
                continue

        return None

    def _find_event_result(
        self,
        page: Page,
        venue: str,
        start_time: str,
    ) -> Locator | None:
        venue_clean = (
            venue or ""
        ).strip()

        start_clean = (
            start_time or ""
        ).strip()

        candidate_selectors: list[str] = []

        if venue_clean and start_clean:
            candidate_selectors.extend(
                [
                    (
                        f"text=/{self._regex_escape(venue_clean)}"
                        f".*{self._regex_escape(start_clean)}/i"
                    ),
                    (
                        f"text=/{self._regex_escape(start_clean)}"
                        f".*{self._regex_escape(venue_clean)}/i"
                    ),
                ]
            )

        if venue_clean:
            candidate_selectors.append(
                f"text=/{self._regex_escape(venue_clean)}/i"
            )

        for selector in candidate_selectors:
            try:
                locator = (
                    page.locator(selector)
                    .first
                )

                locator.wait_for(
                    state="visible",
                    timeout=3_000,
                )

                return locator

            except Exception:
                continue

        return None

    @staticmethod
    def _regex_escape(
        value: str,
    ) -> str:
        escaped = value

        for character in (
            "\\",
            ".",
            "+",
            "*",
            "?",
            "^",
            "$",
            "(",
            ")",
            "[",
            "]",
            "{",
            "}",
            "|",
            "/",
        ):
            escaped = escaped.replace(
                character,
                f"\\{character}",
            )

        return escaped