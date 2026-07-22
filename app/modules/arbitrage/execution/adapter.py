from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from time import perf_counter
from typing import Any, Mapping

from app.browser import (
    BrowserActionResult,
    BrowserActions,
    BrowserPage,
    WaitResult,
)


class AdapterStatus(str, Enum):
    """
    Current lifecycle state of a bookmaker browser adapter.
    """

    CREATED = "CREATED"
    OPEN = "OPEN"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    READY = "READY"
    BUSY = "BUSY"
    ERROR = "ERROR"
    CLOSED = "CLOSED"


class ExecutionStage(str, Enum):
    """
    High-level bookmaker preparation stages.
    """

    OPEN_HOME = "OPEN_HOME"
    LOGIN_CHECK = "LOGIN_CHECK"
    OPEN_EVENT = "OPEN_EVENT"
    SELECT_MARKET = "SELECT_MARKET"
    SELECT_RUNNER = "SELECT_RUNNER"
    ENTER_STAKE = "ENTER_STAKE"
    VERIFY_READY = "VERIFY_READY"


@dataclass(slots=True, frozen=True)
class ExecutionLeg:
    """
    One bookmaker leg prepared by the execution engine.

    Pulse prepares the page and stake only. The user remains responsible
    for reviewing the bet slip and manually pressing the bookmaker's
    final bet/confirm control.
    """

    bookmaker: str
    event_name: str
    selection_name: str
    stake: float

    market_name: str = "Win"
    event_url: str | None = None
    decimal_odds: float | None = None
    race_time: str | None = None
    course: str | None = None
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bookmaker": self.bookmaker,
            "event_name": self.event_name,
            "selection_name": self.selection_name,
            "stake": self.stake,
            "market_name": self.market_name,
            "event_url": self.event_url,
            "decimal_odds": self.decimal_odds,
            "race_time": self.race_time,
            "course": self.course,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AdapterStepResult:
    """
    Structured result for one execution preparation stage.
    """

    stage: ExecutionStage
    successful: bool
    elapsed_ms: float = 0.0
    message: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "successful": self.successful,
            "elapsed_ms": self.elapsed_ms,
            "message": self.message,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class AdapterExecutionResult:
    """
    Final result after preparing one bookmaker bet slip.
    """

    bookmaker: str
    successful: bool
    ready_for_manual_confirmation: bool
    elapsed_ms: float = 0.0
    message: str = ""
    error: str | None = None
    leg: ExecutionLeg | None = None
    steps: list[AdapterStepResult] = field(
        default_factory=list
    )
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bookmaker": self.bookmaker,
            "successful": self.successful,
            "ready_for_manual_confirmation": (
                self.ready_for_manual_confirmation
            ),
            "elapsed_ms": self.elapsed_ms,
            "message": self.message,
            "error": self.error,
            "leg": (
                self.leg.to_dict()
                if self.leg is not None
                else None
            ),
            "steps": [
                step.to_dict()
                for step in self.steps
            ],
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class BrowserAdapterConfig:
    """
    Shared adapter behaviour.

    Bookmaker-specific selectors, URLs and text variants belong in each
    concrete adapter rather than this base config.
    """

    default_timeout_ms: int = 10_000
    navigation_timeout_ms: int = 30_000
    require_login_before_prepare: bool = True
    verify_odds_when_available: bool = True
    odds_tolerance: float = 0.05
    stop_on_first_failure: bool = True


class BrowserAdapter(ABC):
    """
    Base class for every bookmaker execution adapter.

    Concrete adapters implement bookmaker-specific navigation and page
    behaviour while this class controls the common preparation pipeline.

    Important:
        This layer never clicks the final Bet / Place Bet / Confirm Bet
        button. It prepares the bookmaker bet slip for manual review and
        confirmation by the user.
    """

    BOOKMAKER: str = ""
    DISPLAY_NAME: str = ""
    HOME_URL: str = ""

    def __init__(
        self,
        browser: BrowserPage,
        actions: BrowserActions | None = None,
        config: BrowserAdapterConfig | None = None,
    ) -> None:
        if not self.BOOKMAKER.strip():
            raise ValueError(
                "Concrete adapter must define BOOKMAKER."
            )

        if not self.HOME_URL.strip():
            raise ValueError(
                "Concrete adapter must define HOME_URL."
            )

        self.browser = browser
        self.actions = (
            actions
            if actions is not None
            else BrowserActions(browser)
        )
        self.config = config or BrowserAdapterConfig()

        self.status = AdapterStatus.CREATED
        self.last_error: str | None = None
        self.current_leg: ExecutionLeg | None = None

    # -----------------------------------------------------
    # Public lifecycle
    # -----------------------------------------------------

    @property
    def bookmaker(self) -> str:
        return self.BOOKMAKER

    @property
    def display_name(self) -> str:
        return (
            self.DISPLAY_NAME.strip()
            or self.BOOKMAKER
        )

    @property
    def is_ready(self) -> bool:
        return self.status == AdapterStatus.READY

    @property
    def is_closed(self) -> bool:
        return (
            self.status == AdapterStatus.CLOSED
            or self.browser.is_closed
        )

    def open_home(
        self,
    ) -> AdapterStepResult:
        started = perf_counter()

        result = self.browser.goto(
            self.HOME_URL,
            timeout_ms=self.config.navigation_timeout_ms,
        )

        if result.successful:
            self.status = AdapterStatus.OPEN
            self.last_error = None
        else:
            self.status = AdapterStatus.ERROR
            self.last_error = result.error

        return self._step_from_wait(
            stage=ExecutionStage.OPEN_HOME,
            started=started,
            result=result,
        )

    def login_check(
        self,
    ) -> AdapterStepResult:
        started = perf_counter()

        try:
            logged_in = self.is_logged_in()

            if logged_in:
                self.status = AdapterStatus.READY
                self.last_error = None

                return AdapterStepResult(
                    stage=ExecutionStage.LOGIN_CHECK,
                    successful=True,
                    elapsed_ms=self._elapsed_ms(started),
                    message="Bookmaker session is logged in.",
                    metadata={
                        "url": self.browser.url,
                    },
                )

            self.status = AdapterStatus.LOGIN_REQUIRED

            return AdapterStepResult(
                stage=ExecutionStage.LOGIN_CHECK,
                successful=False,
                elapsed_ms=self._elapsed_ms(started),
                message="Bookmaker login is required.",
                metadata={
                    "url": self.browser.url,
                },
            )

        except Exception as exc:
            self.status = AdapterStatus.ERROR
            self.last_error = str(exc)

            return AdapterStepResult(
                stage=ExecutionStage.LOGIN_CHECK,
                successful=False,
                elapsed_ms=self._elapsed_ms(started),
                message="Unable to determine login state.",
                error=str(exc),
                metadata={
                    "url": self.browser.url,
                },
            )

    def prepare(
        self,
        leg: ExecutionLeg,
    ) -> AdapterExecutionResult:
        """
        Prepare a bookmaker bet slip for manual confirmation.
        """

        started = perf_counter()
        steps: list[AdapterStepResult] = []

        self.current_leg = leg
        self.status = AdapterStatus.BUSY
        self.last_error = None

        if (
            leg.bookmaker.strip().lower()
            != self.BOOKMAKER.strip().lower()
        ):
            error = (
                f"Execution leg bookmaker {leg.bookmaker!r} does not "
                f"match adapter {self.BOOKMAKER!r}."
            )
            self.status = AdapterStatus.ERROR
            self.last_error = error

            return AdapterExecutionResult(
                bookmaker=self.BOOKMAKER,
                successful=False,
                ready_for_manual_confirmation=False,
                elapsed_ms=self._elapsed_ms(started),
                message="Execution leg was rejected.",
                error=error,
                leg=leg,
            )

        if self.browser.is_closed:
            error = "Browser page is closed."
            self.status = AdapterStatus.CLOSED
            self.last_error = error

            return AdapterExecutionResult(
                bookmaker=self.BOOKMAKER,
                successful=False,
                ready_for_manual_confirmation=False,
                elapsed_ms=self._elapsed_ms(started),
                message="Cannot prepare a closed browser page.",
                error=error,
                leg=leg,
            )

        if self.config.require_login_before_prepare:
            login_step = self.login_check()
            steps.append(login_step)

            if not login_step.successful:
                return self._execution_failure(
                    started=started,
                    leg=leg,
                    steps=steps,
                    message="Login is required before preparation.",
                    error=login_step.error,
                )

        pipeline = (
            (
                ExecutionStage.OPEN_EVENT,
                lambda: self.open_event(leg),
            ),
            (
                ExecutionStage.SELECT_MARKET,
                lambda: self.select_market(leg),
            ),
            (
                ExecutionStage.SELECT_RUNNER,
                lambda: self.select_runner(leg),
            ),
            (
                ExecutionStage.ENTER_STAKE,
                lambda: self.enter_stake(leg),
            ),
            (
                ExecutionStage.VERIFY_READY,
                lambda: self.verify_ready(leg),
            ),
        )

        for stage, operation in pipeline:
            step = self._run_stage(
                stage=stage,
                operation=operation,
            )
            steps.append(step)

            if (
                not step.successful
                and self.config.stop_on_first_failure
            ):
                return self._execution_failure(
                    started=started,
                    leg=leg,
                    steps=steps,
                    message=(
                        f"Preparation failed during "
                        f"{stage.value.lower()}."
                    ),
                    error=step.error,
                )

        successful = all(
            step.successful
            for step in steps
        )

        if successful:
            self.status = AdapterStatus.READY
            self.last_error = None

            return AdapterExecutionResult(
                bookmaker=self.BOOKMAKER,
                successful=True,
                ready_for_manual_confirmation=True,
                elapsed_ms=self._elapsed_ms(started),
                message=(
                    "Bet slip prepared. Review the bookmaker page "
                    "and manually confirm the bet."
                ),
                leg=leg,
                steps=steps,
                metadata={
                    "url": self.browser.url,
                    "status": self.status.value,
                },
            )

        return self._execution_failure(
            started=started,
            leg=leg,
            steps=steps,
            message="Bet slip preparation was incomplete.",
        )

    def health(
        self,
    ) -> dict[str, Any]:
        return {
            "bookmaker": self.BOOKMAKER,
            "display_name": self.display_name,
            "status": self.status.value,
            "ready": self.is_ready,
            "closed": self.is_closed,
            "url": self.browser.url,
            "title": self.browser.title,
            "last_error": self.last_error,
            "current_leg": (
                self.current_leg.to_dict()
                if self.current_leg is not None
                else None
            ),
        }

    def reset(
        self,
    ) -> None:
        self.current_leg = None
        self.last_error = None

        if self.browser.is_closed:
            self.status = AdapterStatus.CLOSED
        else:
            self.status = AdapterStatus.OPEN

    # -----------------------------------------------------
    # Required bookmaker-specific methods
    # -----------------------------------------------------

    @abstractmethod
    def is_logged_in(
        self,
    ) -> bool:
        """
        Return True when the persistent bookmaker session is logged in.
        """

    @abstractmethod
    def open_event(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        """
        Open the requested race or event.
        """

    @abstractmethod
    def select_market(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        """
        Open or confirm the requested market, such as Win.
        """

    @abstractmethod
    def select_runner(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        """
        Add the requested runner or selection to the bet slip.
        """

    @abstractmethod
    def enter_stake(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        """
        Enter the calculated stake without confirming the bet.
        """

    @abstractmethod
    def verify_ready(
        self,
        leg: ExecutionLeg,
    ) -> AdapterStepResult | BrowserActionResult | WaitResult:
        """
        Verify that the correct selection and stake are ready for the user.
        """

    # -----------------------------------------------------
    # Shared helpers for concrete adapters
    # -----------------------------------------------------

    def action_step(
        self,
        *,
        stage: ExecutionStage,
        result: BrowserActionResult,
    ) -> AdapterStepResult:
        return AdapterStepResult(
            stage=stage,
            successful=result.successful,
            elapsed_ms=result.elapsed_ms,
            message=result.message,
            error=result.error,
            metadata=result.to_dict(),
        )

    def wait_step(
        self,
        *,
        stage: ExecutionStage,
        result: WaitResult,
    ) -> AdapterStepResult:
        return AdapterStepResult(
            stage=stage,
            successful=result.successful,
            elapsed_ms=result.elapsed_ms,
            message=result.message,
            error=result.error,
            metadata=result.metadata,
        )

    def success_step(
        self,
        *,
        stage: ExecutionStage,
        message: str,
        started: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdapterStepResult:
        return AdapterStepResult(
            stage=stage,
            successful=True,
            elapsed_ms=(
                self._elapsed_ms(started)
                if started is not None
                else 0.0
            ),
            message=message,
            metadata=metadata or {},
        )

    def failure_step(
        self,
        *,
        stage: ExecutionStage,
        message: str,
        error: str | None = None,
        started: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdapterStepResult:
        return AdapterStepResult(
            stage=stage,
            successful=False,
            elapsed_ms=(
                self._elapsed_ms(started)
                if started is not None
                else 0.0
            ),
            message=message,
            error=error,
            metadata=metadata or {},
        )

    # -----------------------------------------------------
    # Private orchestration
    # -----------------------------------------------------

    def _run_stage(
        self,
        *,
        stage: ExecutionStage,
        operation: Any,
    ) -> AdapterStepResult:
        started = perf_counter()

        try:
            result = operation()

            if isinstance(result, AdapterStepResult):
                if result.stage != stage:
                    result.metadata["reported_stage"] = (
                        result.stage.value
                    )
                    result.stage = stage

                return result

            if isinstance(result, BrowserActionResult):
                return AdapterStepResult(
                    stage=stage,
                    successful=result.successful,
                    elapsed_ms=result.elapsed_ms,
                    message=result.message,
                    error=result.error,
                    metadata=result.to_dict(),
                )

            if isinstance(result, WaitResult):
                return AdapterStepResult(
                    stage=stage,
                    successful=result.successful,
                    elapsed_ms=result.elapsed_ms,
                    message=result.message,
                    error=result.error,
                    metadata=result.metadata,
                )

            error = (
                f"{type(self).__name__}.{stage.value.lower()} "
                "returned an unsupported result type."
            )

            return AdapterStepResult(
                stage=stage,
                successful=False,
                elapsed_ms=self._elapsed_ms(started),
                message="Adapter stage returned an invalid result.",
                error=error,
                metadata={
                    "result_type": type(result).__name__,
                },
            )

        except Exception as exc:
            self.last_error = str(exc)

            return AdapterStepResult(
                stage=stage,
                successful=False,
                elapsed_ms=self._elapsed_ms(started),
                message=(
                    f"Adapter stage {stage.value.lower()} "
                    "raised an exception."
                ),
                error=str(exc),
                metadata={
                    "url": self.browser.url,
                },
            )

    def _execution_failure(
        self,
        *,
        started: float,
        leg: ExecutionLeg,
        steps: list[AdapterStepResult],
        message: str,
        error: str | None = None,
    ) -> AdapterExecutionResult:
        resolved_error = error

        if resolved_error is None:
            for step in reversed(steps):
                if step.error:
                    resolved_error = step.error
                    break

        self.status = AdapterStatus.ERROR
        self.last_error = resolved_error

        return AdapterExecutionResult(
            bookmaker=self.BOOKMAKER,
            successful=False,
            ready_for_manual_confirmation=False,
            elapsed_ms=self._elapsed_ms(started),
            message=message,
            error=resolved_error,
            leg=leg,
            steps=steps,
            metadata={
                "url": self.browser.url,
                "status": self.status.value,
            },
        )

    def _step_from_wait(
        self,
        *,
        stage: ExecutionStage,
        started: float,
        result: WaitResult,
    ) -> AdapterStepResult:
        return AdapterStepResult(
            stage=stage,
            successful=result.successful,
            elapsed_ms=(
                result.elapsed_ms
                if result.elapsed_ms
                else self._elapsed_ms(started)
            ),
            message=result.message,
            error=result.error,
            metadata=result.metadata,
        )

    @staticmethod
    def _elapsed_ms(
        started: float,
    ) -> float:
        return round(
            (perf_counter() - started) * 1_000,
            3,
        )