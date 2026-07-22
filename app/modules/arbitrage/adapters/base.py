from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from playwright.sync_api import Page

from app.modules.arbitrage.bookmakers import Bookmaker


class PreparationStatus(str, Enum):
    """
    Final state of a bookmaker preparation attempt.
    """

    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


class PreparationStage(str, Enum):
    """
    Furthest stage reached while preparing a bookmaker.
    """

    SESSION_OPEN = "SESSION_OPEN"
    HOMEPAGE_OPEN = "HOMEPAGE_OPEN"
    SEARCH_OPEN = "SEARCH_OPEN"
    SEARCH_SUBMITTED = "SEARCH_SUBMITTED"
    EVENT_FOUND = "EVENT_FOUND"
    EVENT_OPEN = "EVENT_OPEN"
    MARKET_OPEN = "MARKET_OPEN"
    SELECTION_CHOSEN = "SELECTION_CHOSEN"
    STAKE_ENTERED = "STAKE_ENTERED"


@dataclass(slots=True)
class ArbEvent:
    """
    Bookmaker-neutral description of a sporting event.

    The adapter converts this neutral event into the bookmaker's
    own navigation and interaction flow.
    """

    sport: str
    venue: str
    start_time: str

    event_name: Optional[str] = None
    competition: Optional[str] = None
    country: Optional[str] = None
    race_number: Optional[int] = None
    source_url: Optional[str] = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def search_text(self) -> str:
        """
        Basic search phrase suitable for bookmaker search boxes.
        """

        parts = [
            self.venue.strip(),
            self.start_time.strip(),
        ]

        return " ".join(
            part
            for part in parts
            if part
        )


@dataclass(slots=True)
class ArbSelection:
    """
    Bookmaker-neutral description of the required selection.
    """

    name: str
    market: str = "Win"
    requested_odds: Optional[float] = None
    requested_stake: Optional[float] = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(slots=True)
class PreparationRequest:
    """
    Complete request sent to a bookmaker adapter.
    """

    bookmaker_id: str
    event: ArbEvent
    selection: ArbSelection

    navigate_home_first: bool = False
    select_market: bool = True
    select_runner: bool = True
    enter_stake: bool = False

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(slots=True)
class PreparationResult:
    """
    Standard result returned by every bookmaker adapter.
    """

    bookmaker_id: str
    bookmaker_name: str
    status: PreparationStatus

    stage: Optional[PreparationStage] = None
    message: Optional[str] = None
    current_url: Optional[str] = None

    expected_selection: Optional[str] = None
    expected_odds: Optional[float] = None
    observed_odds: Optional[float] = None
    requested_stake: Optional[float] = None

    started_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )
    completed_at: Optional[datetime] = None

    warnings: list[str] = field(
        default_factory=list
    )
    errors: list[str] = field(
        default_factory=list
    )
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def successful(self) -> bool:
        return self.status in {
            PreparationStatus.READY,
            PreparationStatus.PARTIAL,
        }

    def complete(
        self,
        status: PreparationStatus,
        stage: Optional[PreparationStage] = None,
        message: Optional[str] = None,
    ) -> PreparationResult:
        self.status = status

        if stage is not None:
            self.stage = stage

        if message is not None:
            self.message = message

        self.completed_at = datetime.now(
            timezone.utc
        )

        return self

    def add_warning(
        self,
        message: str,
    ) -> None:
        cleaned = str(
            message or ""
        ).strip()

        if cleaned:
            self.warnings.append(
                cleaned
            )

    def add_error(
        self,
        message: str,
    ) -> None:
        cleaned = str(
            message or ""
        ).strip()

        if cleaned:
            self.errors.append(
                cleaned
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bookmaker_id": self.bookmaker_id,
            "bookmaker_name": self.bookmaker_name,
            "status": self.status.value,
            "successful": self.successful,
            "stage": (
                self.stage.value
                if self.stage
                else None
            ),
            "message": self.message,
            "current_url": self.current_url,
            "expected_selection": (
                self.expected_selection
            ),
            "expected_odds": (
                self.expected_odds
            ),
            "observed_odds": (
                self.observed_odds
            ),
            "requested_stake": (
                self.requested_stake
            ),
            "started_at": (
                self.started_at.isoformat()
            ),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at
                else None
            ),
            "warnings": list(
                self.warnings
            ),
            "errors": list(
                self.errors
            ),
            "metadata": dict(
                self.metadata
            ),
        }


class BookmakerAdapter(ABC):
    """
    Base class for bookmaker-specific browser automation.

    Each adapter is responsible only for the behaviour of one
    bookmaker website.

    The Navigator decides which adapter to use.
    The Session Centre owns the browser tabs.
    """

    bookmaker_id: str

    def __init__(
        self,
        bookmaker: Bookmaker,
    ) -> None:
        if bookmaker.id != self.bookmaker_id:
            raise ValueError(
                "Adapter bookmaker mismatch: "
                f"expected {self.bookmaker_id}, "
                f"received {bookmaker.id}"
            )

        self.bookmaker = bookmaker

    def create_result(
        self,
        request: PreparationRequest,
    ) -> PreparationResult:
        return PreparationResult(
            bookmaker_id=self.bookmaker.id,
            bookmaker_name=(
                self.bookmaker.display_name
            ),
            status=PreparationStatus.FAILED,
            expected_selection=(
                request.selection.name
            ),
            expected_odds=(
                request.selection.requested_odds
            ),
            requested_stake=(
                request.selection.requested_stake
            ),
        )

    def page_url(
        self,
        page: Page,
    ) -> Optional[str]:
        try:
            return page.url
        except Exception:
            return None

    def ensure_page(
        self,
        page: Optional[Page],
    ) -> Page:
        if page is None:
            raise RuntimeError(
                "Bookmaker page is unavailable."
            )

        if page.is_closed():
            raise RuntimeError(
                "Bookmaker page is closed."
            )

        return page

    def prepare(
        self,
        page: Page,
        request: PreparationRequest,
    ) -> PreparationResult:
        """
        Run the adapter safely and always return a structured result.
        """

        result = self.create_result(
            request
        )

        try:
            active_page = self.ensure_page(
                page
            )

            result.current_url = self.page_url(
                active_page
            )
            result.stage = (
                PreparationStage.SESSION_OPEN
            )

            prepared = self.prepare_event(
                active_page,
                request,
                result,
            )

            prepared.current_url = self.page_url(
                active_page
            )

            if prepared.completed_at is None:
                prepared.completed_at = datetime.now(
                    timezone.utc
                )

            return prepared

        except Exception as exc:
            result.add_error(
                str(exc)
            )

            result.current_url = self.page_url(
                page
            )

            return result.complete(
                status=PreparationStatus.FAILED,
                stage=result.stage,
                message=(
                    f"{self.bookmaker.display_name} "
                    "preparation failed."
                ),
            )

    @abstractmethod
    def prepare_event(
        self,
        page: Page,
        request: PreparationRequest,
        result: PreparationResult,
    ) -> PreparationResult:
        """
        Perform bookmaker-specific event preparation.

        Concrete adapters should progressively update result.stage
        as each step succeeds.
        """

        raise NotImplementedError