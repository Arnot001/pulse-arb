from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from playwright.sync_api import Locator


# ---------------------------------------------------------
# Enums
# ---------------------------------------------------------


class MatchQuality(str, Enum):
    """
    Human-readable confidence band for a browser search match.
    """

    EXACT = "EXACT"
    STRONG = "STRONG"
    POSSIBLE = "POSSIBLE"
    WEAK = "WEAK"
    NONE = "NONE"


class ClickStatus(str, Enum):
    """
    Final state of a browser click attempt.
    """

    CLICKED = "CLICKED"
    RETRIED = "RETRIED"
    FAILED = "FAILED"
    NOT_FOUND = "NOT_FOUND"
    NOT_VISIBLE = "NOT_VISIBLE"
    NOT_ENABLED = "NOT_ENABLED"


# ---------------------------------------------------------
# Geometry
# ---------------------------------------------------------


@dataclass(slots=True)
class ElementBounds:
    """
    Screen-space position and dimensions for an element.
    """

    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def centre_x(self) -> float:
        return self.x + (
            self.width / 2
        )

    @property
    def centre_y(self) -> float:
        return self.y + (
            self.height / 2
        )
        
    @property
    def centre(self) -> tuple[float, float]:
        return (
            self.centre_x,
            self.centre_y,
        )

    @property
    def area(self) -> float:
        return max(
            0.0,
            self.width,
        ) * max(
            0.0,
            self.height,
        )

    def distance_to(
        self,
        other: ElementBounds,
    ) -> float:
        """
        Euclidean distance between the centres of two elements.
        """

        delta_x = (
            self.centre_x
            - other.centre_x
        )

        delta_y = (
            self.centre_y
            - other.centre_y
        )

        return (
            (
                delta_x ** 2
                + delta_y ** 2
            )
            ** 0.5
        )

    def overlaps(
        self,
        other: ElementBounds,
    ) -> bool:
        return not (
            self.right < other.left
            or self.left > other.right
            or self.bottom < other.top
            or self.top > other.bottom
        )

    def to_dict(
        self,
    ) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "centre_x": self.centre_x,
            "centre_y": self.centre_y,
            "area": self.area,
        }


# ---------------------------------------------------------
# DOM element model
# ---------------------------------------------------------


@dataclass(slots=True)
class VisibleElement:
    """
    Normalised description of a visible browser element.

    The Playwright Locator remains attached so the element can be
    clicked or inspected after the DOM has been analysed.
    """

    locator: Locator

    text: str = ""
    tag_name: str = ""
    role: str | None = None

    visible: bool = True
    enabled: bool = True
    clickable: bool = False

    bounds: ElementBounds | None = None

    href: str | None = None
    title: str | None = None
    aria_label: str | None = None
    placeholder: str | None = None
    test_id: str | None = None

    css_classes: tuple[str, ...] = ()
    attributes: dict[str, str] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def clean_text(
        self,
    ) -> str:
        return " ".join(
            str(
                self.text or ""
            ).split()
        )

    @property
    def searchable_text(
        self,
    ) -> str:
        """
        Combined text used by the intelligent finder.
        """

        values = (
            self.clean_text,
            self.aria_label or "",
            self.title or "",
            self.placeholder or "",
        )

        return " ".join(
            value.strip()
            for value in values
            if value
        )

    @property
    def has_text(
        self,
    ) -> bool:
        return bool(
            self.searchable_text.strip()
        )

    @property
    def centre(
        self,
    ) -> tuple[float, float] | None:
        if self.bounds is None:
            return None

        return (
            self.bounds.centre_x,
            self.bounds.centre_y,
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Serialisable representation.

        The Playwright Locator is deliberately omitted.
        """

        return {
            "text": self.text,
            "clean_text": self.clean_text,
            "searchable_text": (
                self.searchable_text
            ),
            "tag_name": self.tag_name,
            "role": self.role,
            "visible": self.visible,
            "enabled": self.enabled,
            "clickable": self.clickable,
            "bounds": (
                self.bounds.to_dict()
                if self.bounds
                else None
            ),
            "href": self.href,
            "title": self.title,
            "aria_label": self.aria_label,
            "placeholder": self.placeholder,
            "test_id": self.test_id,
            "css_classes": list(
                self.css_classes
            ),
            "attributes": dict(
                self.attributes
            ),
            "metadata": dict(
                self.metadata
            ),
        }


# ---------------------------------------------------------
# Search models
# ---------------------------------------------------------


@dataclass(slots=True)
class SearchMatch:
    """
    A scored candidate returned by BrowserFinder.
    """

    element: VisibleElement

    query: str
    score: float

    quality: MatchQuality = MatchQuality.NONE

    text_score: float = 0.0
    exact_score: float = 0.0
    token_score: float = 0.0
    secondary_score: float = 0.0
    clickable_score: float = 0.0
    proximity_score: float = 0.0

    matched_text: str | None = None

    reasons: list[str] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def locator(
        self,
    ) -> Locator:
        return self.element.locator

    @property
    def clickable(
        self,
    ) -> bool:
        return self.element.clickable

    @property
    def confident(
        self,
    ) -> bool:
        return self.quality in {
            MatchQuality.EXACT,
            MatchQuality.STRONG,
        }

    def add_reason(
        self,
        reason: str,
    ) -> None:
        cleaned = str(
            reason or ""
        ).strip()

        if (
            cleaned
            and cleaned not in self.reasons
        ):
            self.reasons.append(
                cleaned
            )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "query": self.query,
            "score": self.score,
            "quality": self.quality.value,
            "confident": self.confident,
            "matched_text": self.matched_text,
            "clickable": self.clickable,
            "text_score": self.text_score,
            "exact_score": self.exact_score,
            "token_score": self.token_score,
            "secondary_score": (
                self.secondary_score
            ),
            "clickable_score": (
                self.clickable_score
            ),
            "proximity_score": (
                self.proximity_score
            ),
            "reasons": list(
                self.reasons
            ),
            "element": (
                self.element.to_dict()
            ),
            "metadata": dict(
                self.metadata
            ),
        }


@dataclass(slots=True)
class SearchResult:
    """
    Complete result of a browser element search.
    """

    query: str

    secondary_query: str | None = None

    matches: list[SearchMatch] = field(
        default_factory=list
    )

    scanned_elements: int = 0
    filtered_elements: int = 0

    duration_ms: float = 0.0

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def best_match(
        self,
    ) -> SearchMatch | None:
        if not self.matches:
            return None

        return self.matches[0]

    @property
    def found(
        self,
    ) -> bool:
        return self.best_match is not None

    @property
    def confident(
        self,
    ) -> bool:
        return bool(
            self.best_match
            and self.best_match.confident
        )

    def sort_matches(
        self,
    ) -> None:
        self.matches.sort(
            key=lambda match: match.score,
            reverse=True,
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "query": self.query,
            "secondary_query": (
                self.secondary_query
            ),
            "found": self.found,
            "confident": self.confident,
            "best_match": (
                self.best_match.to_dict()
                if self.best_match
                else None
            ),
            "matches": [
                match.to_dict()
                for match in self.matches
            ],
            "scanned_elements": (
                self.scanned_elements
            ),
            "filtered_elements": (
                self.filtered_elements
            ),
            "duration_ms": self.duration_ms,
            "metadata": dict(
                self.metadata
            ),
        }


# ---------------------------------------------------------
# Click models
# ---------------------------------------------------------


@dataclass(slots=True)
class ClickAttempt:
    """
    Details of one click attempt.
    """

    attempt_number: int
    method: str

    successful: bool = False
    error: str | None = None

    url_before: str | None = None
    url_after: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def navigation_detected(
        self,
    ) -> bool:
        return bool(
            self.url_before
            and self.url_after
            and self.url_before
            != self.url_after
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "attempt_number": (
                self.attempt_number
            ),
            "method": self.method,
            "successful": self.successful,
            "error": self.error,
            "url_before": self.url_before,
            "url_after": self.url_after,
            "navigation_detected": (
                self.navigation_detected
            ),
            "metadata": dict(
                self.metadata
            ),
        }


@dataclass(slots=True)
class ClickResult:
    """
    Structured result returned by BrowserClicker.
    """

    status: ClickStatus

    message: str | None = None

    match: SearchMatch | None = None

    attempts: list[ClickAttempt] = field(
        default_factory=list
    )

    final_url: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def successful(
        self,
    ) -> bool:
        return self.status in {
            ClickStatus.CLICKED,
            ClickStatus.RETRIED,
        }

    @property
    def attempt_count(
        self,
    ) -> int:
        return len(
            self.attempts
        )

    @property
    def navigation_detected(
        self,
    ) -> bool:
        return any(
            attempt.navigation_detected
            for attempt in self.attempts
        )

    def add_attempt(
        self,
        attempt: ClickAttempt,
    ) -> None:
        self.attempts.append(
            attempt
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "successful": self.successful,
            "message": self.message,
            "attempt_count": (
                self.attempt_count
            ),
            "navigation_detected": (
                self.navigation_detected
            ),
            "final_url": self.final_url,
            "match": (
                self.match.to_dict()
                if self.match
                else None
            ),
            "attempts": [
                attempt.to_dict()
                for attempt in self.attempts
            ],
            "metadata": dict(
                self.metadata
            ),
        }


# ---------------------------------------------------------
# Wait models
# ---------------------------------------------------------


@dataclass(slots=True)
class WaitResult:
    """
    Structured result returned by BrowserWait.
    """

    successful: bool
    condition: str

    elapsed_ms: float = 0.0

    message: str | None = None
    error: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "successful": self.successful,
            "condition": self.condition,
            "elapsed_ms": self.elapsed_ms,
            "message": self.message,
            "error": self.error,
            "metadata": dict(
                self.metadata
            ),
        }