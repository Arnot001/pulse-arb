from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Sequence

from playwright.sync_api import Locator, Page, Response

from app.browser.clicker import (
    BrowserClicker,
    BrowserClickerConfig,
)
from app.browser.dom import (
    DOMExplorer,
    DOMExplorerConfig,
)
from app.browser.finder import (
    BrowserFinder,
    BrowserFinderConfig,
)
from app.browser.models import (
    ClickResult,
    SearchMatch,
    SearchResult,
    WaitResult,
)
from app.browser.wait import (
    BrowserWait,
    BrowserWaitConfig,
)


@dataclass(slots=True)
class BrowserPageConfig:
    """
    Configuration for the BrowserPage orchestration layer.

    Each lower-level browser component keeps its own dedicated config,
    while BrowserPage controls navigation and high-level input behaviour.
    """

    navigation_timeout_ms: int = 30_000
    action_timeout_ms: int = 10_000
    page_ready_timeout_ms: int = 15_000
    post_navigation_settle_ms: int = 350

    wait_until: str = "domcontentloaded"
    wait_after_navigation: bool = True
    clear_before_fill: bool = True
    press_delay_ms: int = 0

    dom: DOMExplorerConfig = field(
        default_factory=DOMExplorerConfig
    )
    finder: BrowserFinderConfig = field(
        default_factory=BrowserFinderConfig
    )
    clicker: BrowserClickerConfig = field(
        default_factory=BrowserClickerConfig
    )
    wait: BrowserWaitConfig = field(
        default_factory=BrowserWaitConfig
    )


class BrowserPage:
    """
    High-level browser API used by bookmaker adapters.

    BrowserPage owns and coordinates:

    - DOMExplorer
    - BrowserFinder
    - BrowserClicker
    - BrowserWait

    It intentionally keeps Playwright available through ``page`` and
    ``locator()`` for edge cases while providing a clean common API for
    normal bookmaker automation.
    """

    def __init__(
        self,
        page: Page,
        config: BrowserPageConfig | None = None,
        *,
        explorer: DOMExplorer | None = None,
        finder: BrowserFinder | None = None,
        clicker: BrowserClicker | None = None,
        waiter: BrowserWait | None = None,
    ) -> None:
        self.page = page
        self.config = config or BrowserPageConfig()

        self.explorer = (
            explorer
            or DOMExplorer(
                page=self.page,
                config=self.config.dom,
            )
        )

        self.finder = (
            finder
            or BrowserFinder(
                explorer=self.explorer,
                config=self.config.finder,
            )
        )

        self.clicker = (
            clicker
            or BrowserClicker(
                page=self.page,
                explorer=self.explorer,
                finder=self.finder,
                config=self.config.clicker,
            )
        )

        self.wait = (
            waiter
            or BrowserWait(
                page=self.page,
                finder=self.finder,
                config=self.config.wait,
            )
        )

    # -----------------------------------------------------
    # Basic page state
    # -----------------------------------------------------

    @property
    def url(self) -> str:
        try:
            return self.page.url
        except Exception:
            return ""

    @property
    def title(self) -> str:
        try:
            return self.page.title()
        except Exception:
            return ""

    @property
    def is_closed(self) -> bool:
        try:
            return self.page.is_closed()
        except Exception:
            return True

    def locator(
        self,
        selector: str,
    ) -> Locator:
        return self.page.locator(selector)

    # -----------------------------------------------------
    # Navigation
    # -----------------------------------------------------

    def goto(
        self,
        url: str,
        *,
        timeout_ms: int | None = None,
        wait_until: str | None = None,
        wait_for_ready: bool | None = None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(
            timeout_ms,
            self.config.navigation_timeout_ms,
        )
        ready = (
            self.config.wait_after_navigation
            if wait_for_ready is None
            else wait_for_ready
        )

        response: Response | None = None

        try:
            response = self.page.goto(
                url,
                timeout=timeout,
                wait_until=(
                    wait_until
                    or self.config.wait_until
                ),
            )

            if ready:
                page_ready = self.wait.for_page_ready(
                    timeout_ms=min(
                        timeout,
                        self.config.page_ready_timeout_ms,
                    )
                )

                if not page_ready.successful:
                    page_ready.condition = (
                        f"navigate to {url!r}"
                    )
                    page_ready.metadata.update(
                        self._navigation_metadata(
                            requested_url=url,
                            response=response,
                        )
                    )
                    return page_ready

            if self.config.post_navigation_settle_ms > 0:
                self.page.wait_for_timeout(
                    self.config.post_navigation_settle_ms
                )

            return WaitResult(
                successful=True,
                condition=f"navigate to {url!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Navigation completed.",
                metadata=self._navigation_metadata(
                    requested_url=url,
                    response=response,
                ),
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition=f"navigate to {url!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Navigation failed.",
                error=str(exc),
                metadata=self._navigation_metadata(
                    requested_url=url,
                    response=response,
                ),
            )

    def reload(
        self,
        *,
        timeout_ms: int | None = None,
        wait_until: str | None = None,
        wait_for_ready: bool | None = None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(
            timeout_ms,
            self.config.navigation_timeout_ms,
        )
        ready = (
            self.config.wait_after_navigation
            if wait_for_ready is None
            else wait_for_ready
        )

        response: Response | None = None

        try:
            response = self.page.reload(
                timeout=timeout,
                wait_until=(
                    wait_until
                    or self.config.wait_until
                ),
            )

            if ready:
                page_ready = self.wait.for_page_ready(
                    timeout_ms=min(
                        timeout,
                        self.config.page_ready_timeout_ms,
                    )
                )

                if not page_ready.successful:
                    page_ready.condition = "reload page"
                    page_ready.metadata.update(
                        self._navigation_metadata(
                            requested_url=self.url,
                            response=response,
                        )
                    )
                    return page_ready

            if self.config.post_navigation_settle_ms > 0:
                self.page.wait_for_timeout(
                    self.config.post_navigation_settle_ms
                )

            return WaitResult(
                successful=True,
                condition="reload page",
                elapsed_ms=self._elapsed_ms(started),
                message="Page reloaded.",
                metadata=self._navigation_metadata(
                    requested_url=self.url,
                    response=response,
                ),
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition="reload page",
                elapsed_ms=self._elapsed_ms(started),
                message="Page reload failed.",
                error=str(exc),
                metadata={
                    "url": self.url,
                },
            )

    def back(
        self,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self._history_navigation(
            direction="back",
            action=self.page.go_back,
            timeout_ms=timeout_ms,
        )

    def forward(
        self,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self._history_navigation(
            direction="forward",
            action=self.page.go_forward,
            timeout_ms=timeout_ms,
        )

    # -----------------------------------------------------
    # Search
    # -----------------------------------------------------

    def search(
        self,
        query: str,
        *,
        secondary_query: str | None = None,
        prefer_clickable: bool | None = None,
        require_clickable: bool = False,
        require_enabled: bool = False,
        role: str | Sequence[str] | None = None,
        tag: str | Sequence[str] | None = None,
        near: SearchMatch | None = None,
        maximum_results: int | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> SearchResult:
        return self.finder.find(
            query=query,
            secondary_query=secondary_query,
            prefer_clickable=prefer_clickable,
            require_clickable=require_clickable,
            require_enabled=require_enabled,
            role=role,
            tag=tag,
            near=near,
            maximum_results=maximum_results,
            minimum_score=minimum_score,
            refresh=refresh,
        )

    def search_all(
        self,
        query: str,
        **kwargs: Any,
    ) -> list[SearchMatch]:
        return self.finder.find_all(
            query,
            **kwargs,
        )

    def search_clickable(
        self,
        query: str,
        *,
        secondary_query: str | None = None,
        role: str | Sequence[str] | None = None,
        tag: str | Sequence[str] | None = None,
        near: SearchMatch | None = None,
        maximum_results: int | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> SearchResult:
        return self.finder.find_clickable(
            query=query,
            secondary_query=secondary_query,
            role=role,
            tag=tag,
            near=near,
            maximum_results=maximum_results,
            minimum_score=minimum_score,
            refresh=refresh,
        )

    def search_input(
        self,
        query: str,
        *,
        secondary_query: str | None = None,
        near: SearchMatch | None = None,
        maximum_results: int | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> SearchResult:
        return self.finder.find_input(
            query=query,
            secondary_query=secondary_query,
            near=near,
            maximum_results=maximum_results,
            minimum_score=minimum_score,
            refresh=refresh,
        )

    def exists(
        self,
        query: str,
        *,
        clickable: bool = False,
        enabled: bool = False,
        role: str | Sequence[str] | None = None,
        tag: str | Sequence[str] | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> bool:
        result = self.finder.find(
            query=query,
            prefer_clickable=clickable,
            require_clickable=clickable,
            require_enabled=enabled,
            role=role,
            tag=tag,
            minimum_score=minimum_score,
            maximum_results=1,
            refresh=refresh,
        )

        return result.found

    # -----------------------------------------------------
    # Clicking
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
        return self.clicker.click(
            query=query,
            secondary_query=secondary_query,
            role=role,
            tag=tag,
            near=near,
            require_confident=require_confident,
            minimum_score=minimum_score,
            refresh=refresh,
        )

    def click_match(
        self,
        match: SearchMatch,
        *,
        require_confident: bool | None = None,
    ) -> ClickResult:
        return self.clicker.click_match(
            match=match,
            require_confident=require_confident,
        )

    def click_locator(
        self,
        locator: Locator,
        *,
        description: str = "locator",
    ) -> ClickResult:
        return self.clicker.click_locator(
            locator=locator,
            description=description,
        )

    # -----------------------------------------------------
    # Text and input
    # -----------------------------------------------------

    def fill(
        self,
        query: str,
        value: str,
        *,
        secondary_query: str | None = None,
        near: SearchMatch | None = None,
        minimum_score: float | None = None,
        clear_first: bool | None = None,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(
            timeout_ms,
            self.config.action_timeout_ms,
        )

        result = self.search_input(
            query=query,
            secondary_query=secondary_query,
            near=near,
            minimum_score=minimum_score,
            maximum_results=1,
            refresh=True,
        )

        match = result.best_match

        if match is None:
            return WaitResult(
                successful=False,
                condition=f"fill input {query!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Input was not found.",
                metadata={
                    "query": query,
                    "value_length": len(value),
                    "search": result.to_dict(),
                },
            )

        locator = match.locator.first
        ready = self.wait.for_clickable(
            locator,
            timeout_ms=timeout,
        )

        if not ready.successful:
            ready.condition = f"fill input {query!r}"
            ready.metadata.update(
                {
                    "query": query,
                    "match": match.to_dict(),
                }
            )
            return ready

        should_clear = (
            self.config.clear_before_fill
            if clear_first is None
            else clear_first
        )

        try:
            if should_clear:
                locator.fill(
                    "",
                    timeout=timeout,
                )

            locator.fill(
                str(value),
                timeout=timeout,
            )

            return WaitResult(
                successful=True,
                condition=f"fill input {query!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Input filled.",
                metadata={
                    "query": query,
                    "value_length": len(value),
                    "match": match.to_dict(),
                },
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition=f"fill input {query!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Failed to fill input.",
                error=str(exc),
                metadata={
                    "query": query,
                    "value_length": len(value),
                    "match": match.to_dict(),
                },
            )

    def type_text(
        self,
        query: str,
        value: str,
        *,
        secondary_query: str | None = None,
        near: SearchMatch | None = None,
        minimum_score: float | None = None,
        clear_first: bool | None = None,
        delay_ms: int = 0,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(
            timeout_ms,
            self.config.action_timeout_ms,
        )

        result = self.search_input(
            query=query,
            secondary_query=secondary_query,
            near=near,
            minimum_score=minimum_score,
            maximum_results=1,
            refresh=True,
        )

        match = result.best_match

        if match is None:
            return WaitResult(
                successful=False,
                condition=f"type into input {query!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Input was not found.",
                metadata={
                    "query": query,
                    "value_length": len(value),
                    "search": result.to_dict(),
                },
            )

        locator = match.locator.first
        ready = self.wait.for_clickable(
            locator,
            timeout_ms=timeout,
        )

        if not ready.successful:
            ready.condition = f"type into input {query!r}"
            ready.metadata.update(
                {
                    "query": query,
                    "match": match.to_dict(),
                }
            )
            return ready

        should_clear = (
            self.config.clear_before_fill
            if clear_first is None
            else clear_first
        )

        try:
            locator.click(
                timeout=timeout,
            )

            if should_clear:
                locator.fill(
                    "",
                    timeout=timeout,
                )

            locator.press_sequentially(
                str(value),
                delay=max(
                    0,
                    int(delay_ms),
                ),
                timeout=timeout,
            )

            return WaitResult(
                successful=True,
                condition=f"type into input {query!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Text typed.",
                metadata={
                    "query": query,
                    "value_length": len(value),
                    "delay_ms": max(0, int(delay_ms)),
                    "match": match.to_dict(),
                },
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition=f"type into input {query!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Failed to type text.",
                error=str(exc),
                metadata={
                    "query": query,
                    "value_length": len(value),
                    "match": match.to_dict(),
                },
            )

    def press(
        self,
        key: str,
        *,
        query: str | None = None,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(
            timeout_ms,
            self.config.action_timeout_ms,
        )

        try:
            if query is None:
                self.page.keyboard.press(
                    key,
                    delay=max(
                        0,
                        self.config.press_delay_ms,
                    ),
                )

                return WaitResult(
                    successful=True,
                    condition=f"press key {key!r}",
                    elapsed_ms=self._elapsed_ms(started),
                    message="Key pressed.",
                    metadata={
                        "key": key,
                        "target": "page",
                    },
                )

            result = self.search_input(
                query=query,
                maximum_results=1,
                refresh=True,
            )

            match = result.best_match

            if match is None:
                return WaitResult(
                    successful=False,
                    condition=f"press {key!r} on {query!r}",
                    elapsed_ms=self._elapsed_ms(started),
                    message="Input was not found.",
                    metadata={
                        "key": key,
                        "query": query,
                        "search": result.to_dict(),
                    },
                )

            match.locator.first.press(
                key,
                timeout=timeout,
            )

            return WaitResult(
                successful=True,
                condition=f"press {key!r} on {query!r}",
                elapsed_ms=self._elapsed_ms(started),
                message="Key pressed.",
                metadata={
                    "key": key,
                    "query": query,
                    "match": match.to_dict(),
                },
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition=(
                    f"press key {key!r}"
                    if query is None
                    else f"press {key!r} on {query!r}"
                ),
                elapsed_ms=self._elapsed_ms(started),
                message="Failed to press key.",
                error=str(exc),
                metadata={
                    "key": key,
                    "query": query,
                },
            )

    def value(
        self,
        query: str,
        *,
        minimum_score: float | None = None,
    ) -> str | None:
        result = self.search_input(
            query=query,
            minimum_score=minimum_score,
            maximum_results=1,
            refresh=True,
        )

        match = result.best_match

        if match is None:
            return None

        try:
            return match.locator.first.input_value()
        except Exception:
            return None

    # -----------------------------------------------------
    # Waiting shortcuts
    # -----------------------------------------------------

    def wait_for(
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
        return self.wait.for_match(
            query=query,
            clickable=clickable,
            enabled=enabled,
            confident=confident,
            secondary_query=secondary_query,
            role=role,
            tag=tag,
            near=near,
            minimum_score=minimum_score,
            timeout_ms=timeout_ms,
        )

    def wait_for_text(
        self,
        text: str,
        *,
        case_sensitive: bool = False,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.wait.for_text(
            text=text,
            case_sensitive=case_sensitive,
            timeout_ms=timeout_ms,
        )

    def wait_for_text_to_disappear(
        self,
        text: str,
        *,
        case_sensitive: bool = False,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.wait.for_text_to_disappear(
            text=text,
            case_sensitive=case_sensitive,
            timeout_ms=timeout_ms,
        )

    def wait_for_url(
        self,
        expected: Any,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.wait.for_url(
            expected=expected,
            timeout_ms=timeout_ms,
        )

    def wait_for_page_ready(
        self,
        *,
        timeout_ms: int | None = None,
    ) -> WaitResult:
        return self.wait.for_page_ready(
            timeout_ms=timeout_ms,
        )

    def wait_until(
        self,
        condition: Callable[[], bool],
        *,
        description: str,
        timeout_ms: int | None = None,
        poll_interval_ms: int | None = None,
    ) -> WaitResult:
        return self.wait.until(
            condition=condition,
            description=description,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
        )

    # -----------------------------------------------------
    # Inspection and diagnostics
    # -----------------------------------------------------

    def page_text(
        self,
        *,
        refresh: bool = True,
    ) -> str:
        return self.explorer.page_text(
            refresh=refresh,
        )

    def contains_text(
        self,
        text: str,
        *,
        case_sensitive: bool = False,
    ) -> bool:
        return self.explorer.page_contains_text(
            text=text,
            case_sensitive=case_sensitive,
        )

    def summary(
        self,
        *,
        refresh: bool = True,
    ) -> dict[str, Any]:
        result = self.explorer.summary(
            refresh=refresh,
        )

        result["browser_page"] = {
            "url": self.url,
            "title": self.title,
            "closed": self.is_closed,
        }

        return result

    def screenshot(
        self,
        path: str,
        *,
        full_page: bool = True,
    ) -> str:
        self.page.screenshot(
            path=path,
            full_page=full_page,
        )

        return path

    # -----------------------------------------------------
    # Private helpers
    # -----------------------------------------------------

    def _history_navigation(
        self,
        *,
        direction: str,
        action: Callable[..., Response | None],
        timeout_ms: int | None,
    ) -> WaitResult:
        started = perf_counter()
        timeout = self._timeout(
            timeout_ms,
            self.config.navigation_timeout_ms,
        )
        before = self.url

        try:
            response = action(
                timeout=timeout,
                wait_until=self.config.wait_until,
            )

            ready = self.wait.for_page_ready(
                timeout_ms=min(
                    timeout,
                    self.config.page_ready_timeout_ms,
                )
            )

            if not ready.successful:
                ready.condition = f"go {direction}"
                ready.metadata.update(
                    {
                        "url_before": before,
                        "url_after": self.url,
                    }
                )
                return ready

            return WaitResult(
                successful=True,
                condition=f"go {direction}",
                elapsed_ms=self._elapsed_ms(started),
                message=f"History navigation {direction} completed.",
                metadata={
                    "url_before": before,
                    "url_after": self.url,
                    "status": (
                        response.status
                        if response is not None
                        else None
                    ),
                },
            )

        except Exception as exc:
            return WaitResult(
                successful=False,
                condition=f"go {direction}",
                elapsed_ms=self._elapsed_ms(started),
                message=f"History navigation {direction} failed.",
                error=str(exc),
                metadata={
                    "url_before": before,
                    "url_after": self.url,
                },
            )

    def _navigation_metadata(
        self,
        *,
        requested_url: str,
        response: Response | None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "requested_url": requested_url,
            "final_url": self.url,
            "title": self.title,
        }

        if response is not None:
            try:
                metadata["status"] = response.status
            except Exception:
                metadata["status"] = None

            try:
                metadata["ok"] = response.ok
            except Exception:
                metadata["ok"] = None

        return metadata

    @staticmethod
    def _timeout(
        value: int | None,
        default: int,
    ) -> int:
        if value is None:
            return max(
                0,
                int(default),
            )

        return max(
            0,
            int(value),
        )

    @staticmethod
    def _elapsed_ms(
        started: float,
    ) -> float:
        return round(
            (perf_counter() - started) * 1_000,
            3,
        )