from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterable

from app.modules.arbitrage.adapters import (
    PreparationRequest,
    PreparationResult,
    PreparationStage,
    PreparationStatus,
    get_adapter,
)
from app.modules.arbitrage.bookmakers import (
    get_bookmaker,
)
from app.modules.arbitrage.session import (
    SessionCentre,
    get_session_centre,
)


@dataclass(slots=True)
class NavigationBatchResult:
    started_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    completed_at: datetime | None = None

    results: list[
        PreparationResult
    ] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def total(self) -> int:
        return len(
            self.results
        )

    @property
    def ready(self) -> int:
        return sum(
            result.status
            == PreparationStatus.READY
            for result in self.results
        )

    @property
    def partial(self) -> int:
        return sum(
            result.status
            == PreparationStatus.PARTIAL
            for result in self.results
        )

    @property
    def failed(self) -> int:
        return sum(
            result.status
            == PreparationStatus.FAILED
            for result in self.results
        )

    @property
    def unsupported(self) -> int:
        return sum(
            result.status
            == PreparationStatus.UNSUPPORTED
            for result in self.results
        )

    @property
    def successful(self) -> bool:
        return (
            self.total > 0
            and self.failed == 0
            and self.unsupported == 0
        )

    def complete(
        self,
    ) -> NavigationBatchResult:
        self.completed_at = datetime.now(
            timezone.utc
        )

        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": (
                self.started_at.isoformat()
            ),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at
                else None
            ),
            "total": self.total,
            "ready": self.ready,
            "partial": self.partial,
            "failed": self.failed,
            "unsupported": self.unsupported,
            "successful": self.successful,
            "results": [
                result.to_dict()
                for result in self.results
            ],
            "metadata": dict(
                self.metadata
            ),
        }


class ArbNavigator:
    """
    Coordinates preparation requests.

    Responsibilities:

    - Get or create the bookmaker session.
    - Resolve the correct bookmaker adapter.
    - Pass the bookmaker page to the adapter.
    - Return standard preparation results.

    It contains no bookmaker-specific selectors.
    """

    def __init__(
        self,
        session_centre: SessionCentre | None = None,
    ) -> None:
        self._lock = RLock()

        self.session_centre = (
            session_centre
            or get_session_centre()
        )

    def prepare(
        self,
        request: PreparationRequest,
    ) -> PreparationResult:
        with self._lock:
            bookmaker = get_bookmaker(
                request.bookmaker_id
            )

            if bookmaker is None:
                return PreparationResult(
                    bookmaker_id=(
                        request.bookmaker_id
                    ),
                    bookmaker_name=(
                        request.bookmaker_id
                    ),
                    status=(
                        PreparationStatus.FAILED
                    ),
                    stage=None,
                    message=(
                        "Unknown bookmaker."
                    ),
                    expected_selection=(
                        request.selection.name
                    ),
                    expected_odds=(
                        request.selection
                        .requested_odds
                    ),
                    requested_stake=(
                        request.selection
                        .requested_stake
                    ),
                    errors=[
                        (
                            "No bookmaker exists with ID "
                            f"{request.bookmaker_id}."
                        )
                    ],
                ).complete(
                    status=PreparationStatus.FAILED,
                    message="Unknown bookmaker.",
                )

            adapter = get_adapter(
                bookmaker.id
            )

            if adapter is None:
                return PreparationResult(
                    bookmaker_id=bookmaker.id,
                    bookmaker_name=(
                        bookmaker.display_name
                    ),
                    status=(
                        PreparationStatus.UNSUPPORTED
                    ),
                    stage=None,
                    message=(
                        f"{bookmaker.display_name} does not "
                        "have an execution adapter yet."
                    ),
                    expected_selection=(
                        request.selection.name
                    ),
                    expected_odds=(
                        request.selection
                        .requested_odds
                    ),
                    requested_stake=(
                        request.selection
                        .requested_stake
                    ),
                    warnings=[
                        (
                            "The bookmaker session can still "
                            "be opened manually."
                        )
                    ],
                ).complete(
                    status=(
                        PreparationStatus.UNSUPPORTED
                    ),
                    message=(
                        f"{bookmaker.display_name} does not "
                        "have an execution adapter yet."
                    ),
                )

            try:
                session = (
                    self.session_centre.open(
                        bookmaker.id
                    )
                )

            except Exception as exc:
                return PreparationResult(
                    bookmaker_id=bookmaker.id,
                    bookmaker_name=(
                        bookmaker.display_name
                    ),
                    status=(
                        PreparationStatus.FAILED
                    ),
                    stage=None,
                    message=(
                        "Bookmaker session could not be opened."
                    ),
                    expected_selection=(
                        request.selection.name
                    ),
                    expected_odds=(
                        request.selection
                        .requested_odds
                    ),
                    requested_stake=(
                        request.selection
                        .requested_stake
                    ),
                    errors=[
                        str(exc)
                    ],
                ).complete(
                    status=PreparationStatus.FAILED,
                    message=(
                        "Bookmaker session could not be opened."
                    ),
                )

            if not session.page:
                return PreparationResult(
                    bookmaker_id=bookmaker.id,
                    bookmaker_name=(
                        bookmaker.display_name
                    ),
                    status=(
                        PreparationStatus.FAILED
                    ),
                    stage=(
                        PreparationStage.SESSION_OPEN
                    ),
                    message=(
                        "Bookmaker page is unavailable."
                    ),
                    expected_selection=(
                        request.selection.name
                    ),
                    expected_odds=(
                        request.selection
                        .requested_odds
                    ),
                    requested_stake=(
                        request.selection
                        .requested_stake
                    ),
                    errors=[
                        "Session Centre returned no page."
                    ],
                ).complete(
                    status=PreparationStatus.FAILED,
                    stage=PreparationStage.SESSION_OPEN,
                    message=(
                        "Bookmaker page is unavailable."
                    ),
                )

            result = adapter.prepare(
                page=session.page,
                request=request,
            )

            self.session_centre.refresh_state(
                bookmaker.id
            )

            return result

    def prepare_many(
        self,
        requests: Iterable[
            PreparationRequest
        ],
    ) -> NavigationBatchResult:
        batch = NavigationBatchResult()

        for request in requests:
            batch.results.append(
                self.prepare(
                    request
                )
            )

        return batch.complete()


_navigator = ArbNavigator()


def get_arb_navigator() -> ArbNavigator:
    return _navigator