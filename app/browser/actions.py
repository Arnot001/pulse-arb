from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Sequence

from app.browser.models import (
    ClickResult,
    SearchMatch,
    WaitResult,
)
from app.browser.page import BrowserPage


@dataclass(slots=True)
class BrowserActionsConfig:
    """
    Configuration for reusable high-level browser action sequences.
    """

    default_timeout_ms: int = 10_000
    navigation_timeout_ms: int = 20_000
    retry_delay_ms: int = 250
    maximum_attempts: int = 3
    human_delay_ms: int = 0
    wait_after_click_ms: int = 150


@dataclass(slots=True)
class BrowserActionStep:
    """
    One recorded step in a high-level browser action.
    """

    name: str
    successful: bool
    elapsed_ms: float = 0.0
    message: str = ""
    error: str | None = None
    metadata: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "successful": self.successful,
            "elapsed_ms": self.elapsed_ms,
            "message": self.message,
            "error": self.error,
            "metadata": self.metadata or {},
        }


@dataclass(slots=True)
class BrowserActionResult:
    """
    Structured result for a multi-step browser action.
    """

    successful: bool
    action: str
    elapsed_ms: float = 0.0
    message: str = ""
    error: str | None = None
    steps: list[BrowserActionStep] | None = None
    metadata: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "successful": self.successful,
            "action": self.action,
            "elapsed_ms": self.elapsed_ms,
            "message": self.message,
            "error": self.error,
            "steps": [
                step.to_dict()
                for step in (self.steps or [])
            ],
            "metadata": self.metadata or {},
        }


class BrowserActions:
    """
    Reusable browser interaction sequences for bookmaker adapters.

    This layer combines BrowserPage operations into common workflows,
    while preserving structured diagnostics for every step.
    """

    def __init__(
        self,
        browser: BrowserPage,
        config: BrowserActionsConfig | None = None,
    ) -> None:
        self.browser = browser
        self.config = config or BrowserActionsConfig()

    # -----------------------------------------------------
    # Search and click
    # -----------------------------------------------------

    def search_and_click(
        self,
        query: str,
        *,
        secondary_query: str | None = None,
        role: str | tuple[str, ...] | None = None,
        tag: str | tuple[str, ...] | None = None,
        near: SearchMatch | None = None,
        confident: bool = False,
        minimum_score: float | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserActionResult:
        started = perf_counter()
        steps: list[BrowserActionStep] = []
        timeout = self._timeout(timeout_ms)

        wait_result = self.browser.wait_for(
            query=query,
            clickable=True,
            enabled=True,
            confident=confident,
            secondary_query=secondary_query,
            role=role,
            tag=tag,
            near=near,
            minimum_score=minimum_score,
            timeout_ms=timeout,
        )

        steps.append(
            self._step_from_wait(
                "wait_for_clickable",
                wait_result,
            )
        )

        if not wait_result.successful:
            return self._failure(
                action="search_and_click",
                started=started,
                steps=steps,
                message=f"Clickable target {query!r} was not found.",
                error=wait_result.error,
            )

        click_result = self.browser.click(
            query=query,
            secondary_query=secondary_query,
            role=role,
            tag=tag,
            near=near,
            require_confident=confident,
            minimum_score=minimum_score,
            refresh=True,
        )

        steps.append(
            self._step_from_click(
                "click",
                click_result,
            )
        )

        if not click_result.successful:
            return self._failure(
                action="search_and_click",
                started=started,
                steps=steps,
                message=f"Failed to click {query!r}.",
                error=click_result.error,
            )

        self._post_action_delay()

        return self._success(
            action="search_and_click",
            started=started,
            steps=steps,
            message=f"Clicked {query!r}.",
            metadata={
                "query": query,
                "url": self.browser.url,
            },
        )

    # -----------------------------------------------------
    # Find and fill
    # -----------------------------------------------------

    def find_and_fill(
        self,
        query: str,
        value: str,
        *,
        secondary_query: str | None = None,
        near: SearchMatch | None = None,
        minimum_score: float | None = None,
        clear_first: bool = True,
        timeout_ms: int | None = None,
    ) -> BrowserActionResult:
        started = perf_counter()
        steps: list[BrowserActionStep] = []
        timeout = self._timeout(timeout_ms)

        wait_result = self.browser.wait_for(
            query=query,
            enabled=True,
            secondary_query=secondary_query,
            near=near,
            minimum_score=minimum_score,
            timeout_ms=timeout,
        )

        steps.append(
            self._step_from_wait(
                "wait_for_input",
                wait_result,
            )
        )

        if not wait_result.successful:
            return self._failure(
                action="find_and_fill",
                started=started,
                steps=steps,
                message=f"Input {query!r} was not found.",
                error=wait_result.error,
            )

        fill_result = self.browser.fill(
            query=query,
            value=value,
            secondary_query=secondary_query,
            near=near,
            minimum_score=minimum_score,
            clear_first=clear_first,
            timeout_ms=timeout,
        )

        steps.append(
            self._step_from_wait(
                "fill",
                fill_result,
            )
        )

        if not fill_result.successful:
            return self._failure(
                action="find_and_fill",
                started=started,
                steps=steps,
                message=f"Failed to fill {query!r}.",
                error=fill_result.error,
            )

        return self._success(
            action="find_and_fill",
            started=started,
            steps=steps,
            message=f"Filled {query!r}.",
            metadata={
                "query": query,
                "value_length": len(value),
            },
        )

    def fill_and_press(
        self,
        query: str,
        value: str,
        *,
        key: str = "Enter",
        secondary_query: str | None = None,
        minimum_score: float | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserActionResult:
        started = perf_counter()
        steps: list[BrowserActionStep] = []

        fill_result = self.find_and_fill(
            query=query,
            value=value,
            secondary_query=secondary_query,
            minimum_score=minimum_score,
            timeout_ms=timeout_ms,
        )

        steps.extend(fill_result.steps or [])

        if not fill_result.successful:
            return self._failure(
                action="fill_and_press",
                started=started,
                steps=steps,
                message=fill_result.message,
                error=fill_result.error,
            )

        press_result = self.browser.press(
            key=key,
            query=query,
            timeout_ms=self._timeout(timeout_ms),
        )

        steps.append(
            self._step_from_wait(
                "press",
                press_result,
            )
        )

        if not press_result.successful:
            return self._failure(
                action="fill_and_press",
                started=started,
                steps=steps,
                message=f"Filled {query!r}, but failed to press {key!r}.",
                error=press_result.error,
            )

        return self._success(
            action="fill_and_press",
            started=started,
            steps=steps,
            message=f"Filled {query!r} and pressed {key!r}.",
        )

    # -----------------------------------------------------
    # Click with waits
    # -----------------------------------------------------

    def click_then_wait_for_text(
        self,
        query: str,
        expected_text: str,
        *,
        timeout_ms: int | None = None,
        minimum_score: float | None = None,
    ) -> BrowserActionResult:
        started = perf_counter()
        steps: list[BrowserActionStep] = []

        click_result = self.search_and_click(
            query=query,
            timeout_ms=timeout_ms,
            minimum_score=minimum_score,
        )

        steps.extend(click_result.steps or [])

        if not click_result.successful:
            return self._failure(
                action="click_then_wait_for_text",
                started=started,
                steps=steps,
                message=click_result.message,
                error=click_result.error,
            )

        wait_result = self.browser.wait_for_text(
            expected_text,
            timeout_ms=self._timeout(timeout_ms),
        )

        steps.append(
            self._step_from_wait(
                "wait_for_text",
                wait_result,
            )
        )

        if not wait_result.successful:
            return self._failure(
                action="click_then_wait_for_text",
                started=started,
                steps=steps,
                message=(
                    f"Clicked {query!r}, but text "
                    f"{expected_text!r} did not appear."
                ),
                error=wait_result.error,
            )

        return self._success(
            action="click_then_wait_for_text",
            started=started,
            steps=steps,
            message=(
                f"Clicked {query!r} and found "
                f"{expected_text!r}."
            ),
        )

    def click_then_wait_for_url(
        self,
        query: str,
        expected_url: object,
        *,
        timeout_ms: int | None = None,
        minimum_score: float | None = None,
    ) -> BrowserActionResult:
        started = perf_counter()
        steps: list[BrowserActionStep] = []

        click_result = self.search_and_click(
            query=query,
            timeout_ms=timeout_ms,
            minimum_score=minimum_score,
        )

        steps.extend(click_result.steps or [])

        if not click_result.successful:
            return self._failure(
                action="click_then_wait_for_url",
                started=started,
                steps=steps,
                message=click_result.message,
                error=click_result.error,
            )

        wait_result = self.browser.wait_for_url(
            expected=expected_url,
            timeout_ms=(
                timeout_ms
                if timeout_ms is not None
                else self.config.navigation_timeout_ms
            ),
        )

        steps.append(
            self._step_from_wait(
                "wait_for_url",
                wait_result,
            )
        )

        if not wait_result.successful:
            return self._failure(
                action="click_then_wait_for_url",
                started=started,
                steps=steps,
                message=(
                    f"Clicked {query!r}, but URL did not "
                    "reach the expected state."
                ),
                error=wait_result.error,
            )

        return self._success(
            action="click_then_wait_for_url",
            started=started,
            steps=steps,
            message=f"Clicked {query!r} and URL matched.",
            metadata={
                "url": self.browser.url,
            },
        )

    # -----------------------------------------------------
    # Retry and fallback
    # -----------------------------------------------------

    def retry(
        self,
        action_name: str,
        action: Callable[[], BrowserActionResult],
        *,
        maximum_attempts: int | None = None,
        retry_delay_ms: int | None = None,
    ) -> BrowserActionResult:
        started = perf_counter()
        all_steps: list[BrowserActionStep] = []
        attempts = max(
            1,
            maximum_attempts
            if maximum_attempts is not None
            else self.config.maximum_attempts,
        )
        delay = max(
            0,
            retry_delay_ms
            if retry_delay_ms is not None
            else self.config.retry_delay_ms,
        )
        last_result: BrowserActionResult | None = None

        for attempt_number in range(1, attempts + 1):
            attempt_started = perf_counter()

            try:
                result = action()
                last_result = result

                all_steps.append(
                    BrowserActionStep(
                        name=f"attempt_{attempt_number}",
                        successful=result.successful,
                        elapsed_ms=self._elapsed_ms(
                            attempt_started
                        ),
                        message=result.message,
                        error=result.error,
                        metadata={
                            "attempt": attempt_number,
                            "action": result.action,
                        },
                    )
                )

                all_steps.extend(result.steps or [])

                if result.successful:
                    return self._success(
                        action=action_name,
                        started=started,
                        steps=all_steps,
                        message=(
                            f"{action_name} succeeded on "
                            f"attempt {attempt_number}."
                        ),
                        metadata={
                            "attempts": attempt_number,
                        },
                    )

            except Exception as exc:
                all_steps.append(
                    BrowserActionStep(
                        name=f"attempt_{attempt_number}",
                        successful=False,
                        elapsed_ms=self._elapsed_ms(
                            attempt_started
                        ),
                        message="Action raised an exception.",
                        error=str(exc),
                        metadata={
                            "attempt": attempt_number,
                        },
                    )
                )

            if attempt_number < attempts and delay > 0:
                self.browser.page.wait_for_timeout(delay)

        return self._failure(
            action=action_name,
            started=started,
            steps=all_steps,
            message=f"{action_name} failed after {attempts} attempts.",
            error=(
                last_result.error
                if last_result is not None
                else None
            ),
            metadata={
                "attempts": attempts,
            },
        )

    def click_with_fallbacks(
        self,
        queries: Sequence[str],
        *,
        timeout_ms: int | None = None,
        minimum_score: float | None = None,
    ) -> BrowserActionResult:
        started = perf_counter()
        steps: list[BrowserActionStep] = []

        for query in queries:
            result = self.search_and_click(
                query=query,
                timeout_ms=timeout_ms,
                minimum_score=minimum_score,
            )

            steps.append(
                BrowserActionStep(
                    name=f"fallback:{query}",
                    successful=result.successful,
                    elapsed_ms=result.elapsed_ms,
                    message=result.message,
                    error=result.error,
                    metadata={
                        "query": query,
                    },
                )
            )

            steps.extend(result.steps or [])

            if result.successful:
                return self._success(
                    action="click_with_fallbacks",
                    started=started,
                    steps=steps,
                    message=f"Clicked fallback target {query!r}.",
                    metadata={
                        "matched_query": query,
                    },
                )

        return self._failure(
            action="click_with_fallbacks",
            started=started,
            steps=steps,
            message="No fallback click target succeeded.",
            metadata={
                "queries": list(queries),
            },
        )

    # -----------------------------------------------------
    # Common bookmaker-style sequences
    # -----------------------------------------------------

    def open_selection(
        self,
        *,
        event_query: str,
        selection_query: str,
        market_query: str | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserActionResult:
        started = perf_counter()
        steps: list[BrowserActionStep] = []

        for step_name, query in (
            ("event", event_query),
            ("market", market_query),
            ("selection", selection_query),
        ):
            if not query:
                continue

            result = self.search_and_click(
                query=query,
                timeout_ms=timeout_ms,
            )

            steps.extend(result.steps or [])

            if not result.successful:
                return self._failure(
                    action="open_selection",
                    started=started,
                    steps=steps,
                    message=(
                        f"Failed during {step_name} step "
                        f"for {query!r}."
                    ),
                    error=result.error,
                    metadata={
                        "failed_step": step_name,
                        "query": query,
                    },
                )

        return self._success(
            action="open_selection",
            started=started,
            steps=steps,
            message="Selection opened.",
            metadata={
                "event_query": event_query,
                "market_query": market_query,
                "selection_query": selection_query,
            },
        )

    def enter_stake(
        self,
        stake: str | int | float,
        *,
        input_queries: Sequence[str] = (
            "Stake",
            "Enter stake",
            "Stake amount",
        ),
        timeout_ms: int | None = None,
    ) -> BrowserActionResult:
        value = str(stake)
        started = perf_counter()
        steps: list[BrowserActionStep] = []

        for query in input_queries:
            result = self.find_and_fill(
                query=query,
                value=value,
                timeout_ms=timeout_ms,
            )

            steps.append(
                BrowserActionStep(
                    name=f"stake_input:{query}",
                    successful=result.successful,
                    elapsed_ms=result.elapsed_ms,
                    message=result.message,
                    error=result.error,
                    metadata={
                        "query": query,
                    },
                )
            )

            steps.extend(result.steps or [])

            if result.successful:
                return self._success(
                    action="enter_stake",
                    started=started,
                    steps=steps,
                    message=f"Stake entered using {query!r}.",
                    metadata={
                        "input_query": query,
                        "stake": value,
                    },
                )

        return self._failure(
            action="enter_stake",
            started=started,
            steps=steps,
            message="No stake input could be filled.",
            metadata={
                "stake": value,
                "input_queries": list(input_queries),
            },
        )

    # -----------------------------------------------------
    # Private helpers
    # -----------------------------------------------------

    def _post_action_delay(self) -> None:
        delay = max(
            self.config.wait_after_click_ms,
            self.config.human_delay_ms,
        )

        if delay > 0:
            self.browser.page.wait_for_timeout(delay)

    def _timeout(
        self,
        timeout_ms: int | None,
    ) -> int:
        if timeout_ms is None:
            return max(
                0,
                self.config.default_timeout_ms,
            )

        return max(
            0,
            int(timeout_ms),
        )

    def _success(
        self,
        *,
        action: str,
        started: float,
        steps: list[BrowserActionStep],
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> BrowserActionResult:
        return BrowserActionResult(
            successful=True,
            action=action,
            elapsed_ms=self._elapsed_ms(started),
            message=message,
            steps=steps,
            metadata=metadata or {},
        )

    def _failure(
        self,
        *,
        action: str,
        started: float,
        steps: list[BrowserActionStep],
        message: str,
        error: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> BrowserActionResult:
        return BrowserActionResult(
            successful=False,
            action=action,
            elapsed_ms=self._elapsed_ms(started),
            message=message,
            error=error,
            steps=steps,
            metadata=metadata or {},
        )

    @staticmethod
    def _step_from_wait(
        name: str,
        result: WaitResult,
    ) -> BrowserActionStep:
        return BrowserActionStep(
            name=name,
            successful=result.successful,
            elapsed_ms=result.elapsed_ms,
            message=result.message,
            error=result.error,
            metadata=result.metadata,
        )

    @staticmethod
    def _step_from_click(
        name: str,
        result: ClickResult,
    ) -> BrowserActionStep:
        return BrowserActionStep(
            name=name,
            successful=result.successful,
            elapsed_ms=result.elapsed_ms,
            message=result.message,
            error=result.error,
            metadata=result.to_dict(),
        )

    @staticmethod
    def _elapsed_ms(
        started: float,
    ) -> float:
        return round(
            (perf_counter() - started) * 1_000,
            3,
        )