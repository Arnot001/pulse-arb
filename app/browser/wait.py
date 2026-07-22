from __future__ import annotations

from dataclasses import dataclass
from re import Pattern
from time import perf_counter, sleep
from typing import Callable

from playwright.sync_api import Locator, Page

from app.browser.finder import BrowserFinder
from app.browser.models import SearchMatch, WaitResult


@dataclass(slots=True)
class BrowserWaitConfig:
    """
    Controls BrowserWait timeouts and polling behaviour.
    """

    default_timeout_ms: int = 10_000
    short_timeout_ms: int = 3_000
    long_timeout_ms: int = 30_000

    poll_interval_ms: int = 100
    navigation_settle_ms: int = 350

    wait_for_network_idle: bool = False
    network_idle_timeout_ms: int = 5_000

    minimum_search_score: float | None = None


class BrowserWait:
    """
    Shared waiting engine for the Pulse browser intelligence layer.

    BrowserWait exposes structured waits for locators, text, URLs,
    navigation, page load states and BrowserFinder matches.
    """

    def __init__(
        self,
        page: Page,
        finder: BrowserFinder,
        config: BrowserWaitConfig | None = None,
    ) -> None:
        self.page = page
        self.finder = finder
        self.config = config or BrowserWaitConfig()

    # -----------------------------------------------------
    # Generic condition waits
    # -----------------------------------------------------

    def until(
        self,
        condition: Callable[[], bool],
        *,
        description: str,
        timeout_ms: int | None = None,
        poll_interval_ms: int | None = None,
    ) -> WaitResult:
        started = perf_counter()

        timeout = self._timeout(timeout_ms)
        poll = self._poll_interval(poll_interval_ms)

        deadline = started + timeout / 1_000
        last_error: str | None = None

        while perf_counter() <= deadline:
            try:
                if condition():
                    return WaitResult(
                        successful=True,
                        condition=description,
                        elapsed_ms=self._elapsed_ms(started),
                        message="Condition satisfied.",
                    )
            except Exception as exc:
                last_error = str(exc)

            sleep(poll / 1_000)

        return WaitResult(
            successful=False,
            condition=description,
            elapsed_ms=self._elapsed_ms(started),
            message="Timed out waiting for condition.",
            error=last_error,
            metadata={
                "timeout_ms": timeout,
                "poll_interval_ms": poll,
            },
        )

    # -----------------------------------------------------
    # Locator waits
    # -----------------------------------------------------

    def for_attached(
        self,
        locator: Locator,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self._wait_for_locator_state(
            locator=locator,
            state="attached",
            timeout_ms=timeout_ms,
        )

    def for_detached(
        self,
        locator: Locator,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self._wait_for_locator_state(
            locator=locator,
            state="detached",
            timeout_ms=timeout_ms,
        )

    def for_visible(
        self,
        locator: Locator,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self._wait_for_locator_state(
            locator=locator,
            state="visible",
            timeout_ms=timeout_ms,
        )

    def for_hidden(
        self,
        locator: Locator,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self._wait_for_locator_state(
            locator=locator,
            state="hidden",
            timeout_ms=timeout_ms,
        )

    def for_enabled(
        self,
        locator: Locator,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        target = locator.first

        return self.until(
            lambda: (
                target.count() > 0
                and target.is_enabled()
            ),
            description="locator enabled",
            timeout_ms=timeout_ms,
        )

    def for_disabled(
        self,
        locator: Locator,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        target = locator.first

        return self.until(
            lambda: (
                target.count() > 0
                and not target.is_enabled()
            ),
            description="locator disabled",
            timeout_ms=timeout_ms,
        )

    def for_clickable(
        self,
        locator: Locator,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        target = locator.first

        return self.until(
            lambda: (
                target.count() > 0
                and target.is_visible()
                and target.is_enabled()
            ),
            description="locator clickable",
            timeout_ms=timeout_ms,
        )

    def for_count(
        self,
        locator: Locator,
        expected_count: int,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.until(
            lambda: locator.count() == expected_count,
            description=(
                f"locator count equals {expected_count}"
            ),
            timeout_ms=timeout_ms,
        )

    # -----------------------------------------------------
    # Finder waits
    # -----------------------------------------------------

    def for_match(
        self,
        query: str,
        *,
        clickable: bool = False,
        enabled: bool = False,
        confident: bool = False,
        secondary_query: str | None = None,
        role: str | tuple[str, ...] | None = None,
        tag: str | tuple[str, ...] | None = None,
        near: SearchMatch | None = None,
        minimum_score: float | None = None,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        last_match: SearchMatch | None = None

        def condition() -> bool:
            nonlocal last_match

            result = self.finder.find(
                query=query,
                secondary_query=secondary_query,
                prefer_clickable=clickable,
                require_clickable=clickable,
                require_enabled=enabled,
                role=role,
                tag=tag,
                near=near,
                minimum_score=(
                    minimum_score
                    if minimum_score is not None
                    else self.config.minimum_search_score
                ),
                maximum_results=1,
                refresh=True,
            )

            last_match = result.best_match

            if last_match is None:
                return False

            if confident and not last_match.confident:
                return False

            return True

        result = self.until(
            condition,
            description=f"finder match for {query!r}",
            timeout_ms=timeout_ms,
        )

        if last_match is not None:
            result.metadata["match"] = (
                last_match.to_dict()
            )

        return result

    def for_text(
        self,
        text: str,
        *,
        case_sensitive: bool = False,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.until(
            lambda: self.finder.explorer.page_contains_text(
                text=text,
                case_sensitive=case_sensitive,
            ),
            description=f"page contains text {text!r}",
            timeout_ms=timeout_ms,
        )

    def for_text_to_disappear(
        self,
        text: str,
        *,
        case_sensitive: bool = False,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.until(
            lambda: not self.finder.explorer.page_contains_text(
                text=text,
                case_sensitive=case_sensitive,
            ),
            description=f"text disappears {text!r}",
            timeout_ms=timeout_ms,
        )

    # -----------------------------------------------------
    # URL and navigation waits
    # -----------------------------------------------------

    def for_url(
        self,
        expected: str | Pattern[str],
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(timeout_ms)

        try:
            self.page.wait_for_url(
                expected,
                timeout=timeout,
            )

            return WaitResult(
                successful=True,
                condition=f"url matches {expected!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="URL condition satisfied.",
                metadata={
                    "url": self._safe_url(),
                },
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition=f"url matches {expected!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Timed out waiting for URL.",
                error=str(exc),
                metadata={
                    "url": self._safe_url(),
                    "timeout_ms": timeout,
                },
            )

    def for_url_change(
        self,
        previous_url: str,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.until(
            lambda: self._safe_url() != previous_url,
            description="url changed",
            timeout_ms=timeout_ms,
        )

    def for_navigation(
        self,
        *,
        previous_url: str | None = None,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        before = (
            previous_url
            if previous_url is not None
            else self._safe_url()
        )

        if before is None:
            return WaitResult(
                successful=False,
                condition="navigation",
                message="Unable to read current URL.",
            )

        result = self.for_url_change(
            before,
            timeout_ms=timeout_ms,
        )

        if (
            result.successful
            and self.config.navigation_settle_ms > 0
        ):
            self.page.wait_for_timeout(
                self.config.navigation_settle_ms
            )

        result.metadata["url_before"] = before
        result.metadata["url_after"] = (
            self._safe_url()
        )

        return result

    # -----------------------------------------------------
    # Page load waits
    # -----------------------------------------------------

    def for_load_state(
        self,
        state: str = "domcontentloaded",
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(timeout_ms)

        try:
            self.page.wait_for_load_state(
                state=state,
                timeout=timeout,
            )

            return WaitResult(
                successful=True,
                condition=f"load state {state}",
                elapsed_ms=self._elapsed_ms(started),
                message="Load state reached.",
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition=f"load state {state}",
                elapsed_ms=self._elapsed_ms(started),
                message="Timed out waiting for load state.",
                error=str(exc),
                metadata={
                    "timeout_ms": timeout,
                },
            )

    def for_dom_ready(
        self,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.for_load_state(
            "domcontentloaded",
            timeout_ms=timeout_ms,
        )

    def for_network_idle(
        self,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.for_load_state(
            "networkidle",
            timeout_ms=(
                timeout_ms
                if timeout_ms is not None
                else self.config.network_idle_timeout_ms
            ),
        )

    def for_page_ready(
        self,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(timeout_ms)

        dom_result = self.for_dom_ready(
            timeout_ms=timeout
        )

        if not dom_result.successful:
            return dom_result

        if self.config.wait_for_network_idle:
            network_result = self.for_network_idle(
                timeout_ms=min(
                    timeout,
                    self.config.network_idle_timeout_ms,
                )
            )

            if not network_result.successful:
                network_result.message = (
                    "DOM became ready, but network idle "
                    "was not reached."
                )
                return network_result

        return WaitResult(
            successful=True,
            condition="page ready",
            elapsed_ms=self._elapsed_ms(started),
            message="Page is ready.",
            metadata={
                "url": self._safe_url(),
            },
        )

    # -----------------------------------------------------
    # Private helpers
    # -----------------------------------------------------

    def _wait_for_locator_state(
        self,
        *,
        locator: Locator,
        state: str,
        timeout_ms: int | None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(timeout_ms)

        try:
            locator.first.wait_for(
                state=state,
                timeout=timeout,
            )

            return WaitResult(
                successful=True,
                condition=f"locator {state}",
                elapsed_ms=self._elapsed_ms(started),
                message=f"Locator became {state}.",
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition=f"locator {state}",
                elapsed_ms=self._elapsed_ms(started),
                message=(
                    f"Timed out waiting for locator to become {state}."
                ),
                error=str(exc),
                metadata={
                    "timeout_ms": timeout,
                },
            )

    def _timeout(
        self,
        value: int | None,
    ) -> int:
        if value is None:
            return max(
                0,
                self.config.default_timeout_ms,
            )

        return max(
            0,
            int(value),
        )

    def _poll_interval(
        self,
        value: int | None,
    ) -> int:
        if value is None:
            return max(
                10,
                self.config.poll_interval_ms,
            )

        return max(
            10,
            int(value),
        )

    def _safe_url(
        self,
    ) -> str | None:
        try:
            return self.page.url
        except Exception:
            return None

    @staticmethod
    def _elapsed_ms(
        started: float,
    ) -> float:
        return round(
            (perf_counter() - started) * 1_000,
            3,
        )