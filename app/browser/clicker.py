from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter, sleep
from typing import Any

from playwright.sync_api import Locator, Page

from app.browser.dom import DOMExplorer
from app.browser.finder import BrowserFinder
from app.browser.models import (
    ClickAttempt,
    ClickResult,
    ClickStatus,
    SearchMatch,
)


@dataclass(slots=True)
class BrowserClickerConfig:
    """
    Controls BrowserClicker retry behaviour and fallback strategies.
    """

    click_timeout_ms: int = 5_000
    actionability_timeout_ms: int = 3_000
    navigation_settle_ms: int = 350
    retry_delay_ms: int = 250

    maximum_attempts: int = 4

    scroll_before_click: bool = True
    use_clickable_ancestor: bool = True
    use_force_click: bool = True
    use_javascript_click: bool = True

    wait_for_visible: bool = True
    wait_for_enabled: bool = True

    require_confident_match: bool = False
    minimum_match_score: float | None = None


class BrowserClicker:
    """
    Reliable click execution for the Pulse browser intelligence layer.

    BrowserClicker searches through BrowserFinder, upgrades text-only
    matches to clickable ancestors where possible, and escalates through
    safe click strategies while returning structured diagnostics.
    """

    def __init__(
        self,
        page: Page,
        explorer: DOMExplorer,
        finder: BrowserFinder,
        config: BrowserClickerConfig | None = None,
    ) -> None:
        self.page = page
        self.explorer = explorer
        self.finder = finder
        self.config = config or BrowserClickerConfig()

    # -----------------------------------------------------
    # Public API
    # -----------------------------------------------------

    def click(
        self,
        query: str,
        *,
        secondary_query: str | None = None,
        role: str | tuple[str, ...] | None = None,
        tag: str | tuple[str, ...] | None = None,
        near: SearchMatch | None = None,
        require_confident: bool | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> ClickResult:
        """
        Find a clickable element by text and click it.
        """

        result = self.finder.find_clickable(
            query=query,
            secondary_query=secondary_query,
            role=role,
            tag=tag,
            near=near,
            minimum_score=(
                minimum_score
                if minimum_score is not None
                else self.config.minimum_match_score
            ),
            refresh=refresh,
        )

        if not result.found:
            return ClickResult(
                status=ClickStatus.NOT_FOUND,
                message=f"No clickable element found for {query!r}.",
                metadata={
                    "query": query,
                    "search": result.to_dict(),
                },
            )

        match = result.best_match

        if match is None:
            return ClickResult(
                status=ClickStatus.NOT_FOUND,
                message=f"No clickable element found for {query!r}.",
                metadata={
                    "query": query,
                    "search": result.to_dict(),
                },
            )

        confidence_required = (
            self.config.require_confident_match
            if require_confident is None
            else require_confident
        )

        if confidence_required and not match.confident:
            return ClickResult(
                status=ClickStatus.NOT_FOUND,
                message=(
                    f"Best match for {query!r} was not confident "
                    f"({match.quality.value}, score {match.score:.1f})."
                ),
                match=match,
                metadata={
                    "query": query,
                    "search": result.to_dict(),
                },
            )

        click_result = self.click_match(match)
        click_result.metadata.setdefault(
            "search",
            result.to_dict(),
        )

        return click_result

    def click_match(
        self,
        match: SearchMatch,
    ) -> ClickResult:
        """
        Click an existing BrowserFinder match.
        """

        locator = match.locator
        effective_match = match

        if (
            self.config.use_clickable_ancestor
            and not match.element.clickable
        ):
            ancestor = self.explorer.nearest_clickable_ancestor(
                locator
            )

            if ancestor is not None:
                locator = ancestor.locator
                effective_match = SearchMatch(
                    element=ancestor,
                    query=match.query,
                    score=match.score,
                    quality=match.quality,
                    text_score=match.text_score,
                    exact_score=match.exact_score,
                    token_score=match.token_score,
                    secondary_score=match.secondary_score,
                    clickable_score=match.clickable_score,
                    proximity_score=match.proximity_score,
                    matched_text=match.matched_text,
                    reasons=list(match.reasons),
                    metadata={
                        **match.metadata,
                        "used_clickable_ancestor": True,
                    },
                )

        result = self.click_locator(
            locator=locator,
            match=effective_match,
        )

        return result

    def click_locator(
        self,
        locator: Locator,
        *,
        match: SearchMatch | None = None,
    ) -> ClickResult:
        """
        Click an arbitrary Playwright locator using escalating strategies.
        """

        target = locator.first

        if not self._locator_exists(target):
            return ClickResult(
                status=ClickStatus.NOT_FOUND,
                message="Locator did not resolve to an element.",
                match=match,
                final_url=self._safe_url(),
            )

        if self.config.wait_for_visible:
            if not self._wait_until_visible(target):
                return ClickResult(
                    status=ClickStatus.NOT_VISIBLE,
                    message="Element did not become visible before timeout.",
                    match=match,
                    final_url=self._safe_url(),
                )

        if self.config.wait_for_enabled:
            if not self._wait_until_enabled(target):
                return ClickResult(
                    status=ClickStatus.NOT_ENABLED,
                    message="Element did not become enabled before timeout.",
                    match=match,
                    final_url=self._safe_url(),
                )

        if self.config.scroll_before_click:
            self._scroll_into_view(target)

        attempts: list[ClickAttempt] = []

        strategies = self._strategies()

        for attempt_number, strategy in enumerate(
            strategies,
            start=1,
        ):
            if attempt_number > self.config.maximum_attempts:
                break

            attempt = self._perform_attempt(
                locator=target,
                method=strategy,
                attempt_number=attempt_number,
            )

            attempts.append(attempt)

            if attempt.successful:
                status = (
                    ClickStatus.CLICKED
                    if attempt_number == 1
                    else ClickStatus.RETRIED
                )

                result = ClickResult(
                    status=status,
                    message=(
                        "Element clicked successfully."
                        if attempt_number == 1
                        else (
                            "Element clicked successfully after "
                            f"{attempt_number} attempts."
                        )
                    ),
                    match=match,
                    attempts=attempts,
                    final_url=self._safe_url(),
                    metadata={
                        "successful_method": strategy,
                    },
                )

                return result

            if attempt_number < min(
                len(strategies),
                self.config.maximum_attempts,
            ):
                sleep(
                    max(
                        0,
                        self.config.retry_delay_ms,
                    )
                    / 1_000
                )

                if self.config.scroll_before_click:
                    self._scroll_into_view(target)

        return ClickResult(
            status=ClickStatus.FAILED,
            message="All configured click strategies failed.",
            match=match,
            attempts=attempts,
            final_url=self._safe_url(),
            metadata={
                "attempted_methods": [
                    attempt.method
                    for attempt in attempts
                ],
            },
        )

    # -----------------------------------------------------
    # Attempt execution
    # -----------------------------------------------------

    def _perform_attempt(
        self,
        *,
        locator: Locator,
        method: str,
        attempt_number: int,
    ) -> ClickAttempt:
        url_before = self._safe_url()
        started = perf_counter()

        attempt = ClickAttempt(
            attempt_number=attempt_number,
            method=method,
            url_before=url_before,
        )

        try:
            if method == "playwright":
                locator.click(
                    timeout=self.config.click_timeout_ms,
                )

            elif method == "playwright_force":
                locator.click(
                    timeout=self.config.click_timeout_ms,
                    force=True,
                )

            elif method == "javascript":
                locator.evaluate(
                    """
                    (element) => {
                        element.scrollIntoView({
                            block: "center",
                            inline: "center"
                        });
                        element.click();
                    }
                    """
                )

            elif method == "dispatch_event":
                locator.dispatch_event("click")

            else:
                raise ValueError(
                    f"Unknown click strategy: {method}"
                )

            if self.config.navigation_settle_ms > 0:
                self.page.wait_for_timeout(
                    self.config.navigation_settle_ms
                )

            attempt.successful = True
            attempt.url_after = self._safe_url()
            attempt.metadata["duration_ms"] = round(
                (perf_counter() - started) * 1_000,
                3,
            )

            return attempt

        except Exception as exc:
            attempt.successful = False
            attempt.error = str(exc)
            attempt.url_after = self._safe_url()
            attempt.metadata["duration_ms"] = round(
                (perf_counter() - started) * 1_000,
                3,
            )

            return attempt

    def _strategies(
        self,
    ) -> list[str]:
        strategies = ["playwright"]

        if self.config.use_force_click:
            strategies.append("playwright_force")

        if self.config.use_javascript_click:
            strategies.append("javascript")
            strategies.append("dispatch_event")

        return strategies

    # -----------------------------------------------------
    # Actionability helpers
    # -----------------------------------------------------

    def _wait_until_visible(
        self,
        locator: Locator,
    ) -> bool:
        try:
            locator.wait_for(
                state="visible",
                timeout=self.config.actionability_timeout_ms,
            )
            return True
        except Exception:
            try:
                return locator.is_visible()
            except Exception:
                return False

    def _wait_until_enabled(
        self,
        locator: Locator,
    ) -> bool:
        deadline = (
            perf_counter()
            + max(
                0,
                self.config.actionability_timeout_ms,
            )
            / 1_000
        )

        while perf_counter() <= deadline:
            try:
                if locator.is_enabled():
                    return True
            except Exception:
                return False

            sleep(0.05)

        return False

    @staticmethod
    def _scroll_into_view(
        locator: Locator,
    ) -> bool:
        try:
            locator.scroll_into_view_if_needed(
                timeout=2_000
            )
            return True
        except Exception:
            try:
                locator.evaluate(
                    """
                    (element) => element.scrollIntoView({
                        block: "center",
                        inline: "center",
                        behavior: "instant"
                    })
                    """
                )
                return True
            except Exception:
                return False

    @staticmethod
    def _locator_exists(
        locator: Locator,
    ) -> bool:
        try:
            return locator.count() > 0
        except Exception:
            return False

    def _safe_url(
        self,
    ) -> str | None:
        try:
            return self.page.url
        except Exception:
            return None