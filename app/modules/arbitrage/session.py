from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Optional

from playwright.sync_api import Page

from app.browser_manager import get_browser_manager
from app.modules.arbitrage.bookmakers import (
    Bookmaker,
    all_bookmakers,
    get_bookmaker,
)


# ---------------------------------------------------------
# Models
# ---------------------------------------------------------


@dataclass(slots=True)
class BookmakerSession:
    bookmaker: Bookmaker
    page: Optional[Page] = None
    logged_in: bool = False
    healthy: bool = False
    current_url: Optional[str] = None
    last_activity: Optional[datetime] = None
    last_error: Optional[str] = None

    def touch(self) -> None:
        self.last_activity = datetime.now(
            timezone.utc
        )

    @property
    def is_open(self) -> bool:
        try:
            return (
                self.page is not None
                and not self.page.is_closed()
            )
        except Exception:
            return False

    def to_dict(self) -> dict:
        return {
            "bookmaker_id": self.bookmaker.id,
            "bookmaker": self.bookmaker.display_name,
            "open": self.is_open,
            "healthy": self.healthy,
            "logged_in": self.logged_in,
            "url": self.current_url,
            "last_activity": (
                self.last_activity.isoformat()
                if self.last_activity
                else None
            ),
            "last_error": self.last_error,
        }


# ---------------------------------------------------------
# Session Centre
# ---------------------------------------------------------


class SessionCentre:
    """
    Owns persistent bookmaker tabs inside the shared Playwright
    browser context.

    The browser manager owns Playwright and the browser lifecycle.
    Session Centre owns which page belongs to each bookmaker.
    """

    def __init__(self) -> None:
        self._lock = RLock()

        self._sessions = {
            bookmaker.id: BookmakerSession(
                bookmaker=bookmaker
            )
            for bookmaker in all_bookmakers()
        }

    # -----------------------------------------------------

    def session(
        self,
        bookmaker_id: str,
    ) -> BookmakerSession:
        bookmaker = get_bookmaker(
            bookmaker_id
        )

        if bookmaker is None:
            raise KeyError(
                f"Unknown bookmaker: {bookmaker_id}"
            )

        return self._sessions[
            bookmaker.id
        ]

    # -----------------------------------------------------

    def open(
        self,
        bookmaker_id: str,
    ) -> BookmakerSession:
        """
        Create or reuse a bookmaker tab.

        This method deliberately does not navigate anywhere.
        Navigation is handled separately by navigate().
        """

        with self._lock:
            session = self.session(
                bookmaker_id
            )

            if session.is_open:
                return session

            try:
                page = (
                    get_browser_manager()
                    .new_page()
                )

                session.page = page
                session.current_url = (
                    page.url
                    if page.url != "about:blank"
                    else None
                )
                session.healthy = True
                session.last_error = None
                session.touch()

            except Exception as exc:
                session.page = None
                session.current_url = None
                session.healthy = False
                session.last_error = str(exc)
                session.touch()
                raise

            return session

    # -----------------------------------------------------

    def navigate(
        self,
        bookmaker_id: str,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout_ms: int = 30_000,
    ) -> BookmakerSession:
        """
        Navigate an existing bookmaker tab, creating it first
        when necessary.
        """

        cleaned_url = str(
            url or ""
        ).strip()

        if not cleaned_url:
            raise ValueError(
                "Navigation URL cannot be empty."
            )

        with self._lock:
            session = self.open(
                bookmaker_id
            )

            if not session.page:
                raise RuntimeError(
                    "Bookmaker page is unavailable."
                )

            if (
                session.is_open
                and session.current_url == cleaned_url
            ):
                session.touch()
                return session

            try:
                session.page.goto(
                    cleaned_url,
                    wait_until=wait_until,
                    timeout=timeout_ms,
                )

                session.current_url = (
                    session.page.url
                )
                session.healthy = True
                session.last_error = None
                session.touch()

            except Exception as exc:
                try:
                    session.current_url = (
                        session.page.url
                    )
                except Exception:
                    session.current_url = None

                session.healthy = False
                session.last_error = str(exc)
                session.touch()
                raise

            return session

    # -----------------------------------------------------

    def navigate_home(
        self,
        bookmaker_id: str,
        wait_until: str = "domcontentloaded",
        timeout_ms: int = 30_000,
    ) -> BookmakerSession:
        session = self.session(
            bookmaker_id
        )

        return self.navigate(
            bookmaker_id=bookmaker_id,
            url=session.bookmaker.homepage,
            wait_until=wait_until,
            timeout_ms=timeout_ms,
        )

    # -----------------------------------------------------

    def close(
        self,
        bookmaker_id: str,
    ) -> None:
        with self._lock:
            session = self.session(
                bookmaker_id
            )

            if session.page:
                get_browser_manager().close_page(
                    session.page
                )

            session.page = None
            session.logged_in = False
            session.healthy = False
            session.current_url = None
            session.last_error = None
            session.touch()

    # -----------------------------------------------------

    def open_all(
        self,
    ) -> list[BookmakerSession]:
        opened: list[BookmakerSession] = []

        for bookmaker in all_bookmakers():
            if not bookmaker.enabled:
                continue

            try:
                opened.append(
                    self.open(
                        bookmaker.id
                    )
                )
            except Exception:
                continue

        return opened

    # -----------------------------------------------------

    def navigate_all_home(
        self,
    ) -> list[BookmakerSession]:
        navigated: list[BookmakerSession] = []

        for bookmaker in all_bookmakers():
            if not bookmaker.enabled:
                continue

            try:
                navigated.append(
                    self.navigate_home(
                        bookmaker.id
                    )
                )
            except Exception:
                continue

        return navigated

    # -----------------------------------------------------

    def close_all(
        self,
    ) -> None:
        for bookmaker in all_bookmakers():
            self.close(
                bookmaker.id
            )

    # -----------------------------------------------------

    def mark_logged_in(
        self,
        bookmaker_id: str,
        logged_in: bool = True,
    ) -> BookmakerSession:
        with self._lock:
            session = self.session(
                bookmaker_id
            )

            session.logged_in = bool(
                logged_in
            )
            session.touch()

            return session

    # -----------------------------------------------------

    def refresh_state(
        self,
        bookmaker_id: str,
    ) -> BookmakerSession:
        """
        Refresh basic page state without navigating.
        """

        with self._lock:
            session = self.session(
                bookmaker_id
            )

            if not session.is_open:
                session.healthy = False
                session.current_url = None
                return session

            try:
                if not session.page:
                    raise RuntimeError(
                        "Page object is unavailable."
                    )

                session.current_url = (
                    session.page.url
                )
                session.healthy = True
                session.last_error = None

            except Exception as exc:
                session.healthy = False
                session.last_error = str(exc)

            session.touch()

            return session

    # -----------------------------------------------------

    def health(
        self,
    ) -> list[dict]:
        with self._lock:
            results: list[dict] = []

            for bookmaker in all_bookmakers():
                session = self._sessions[
                    bookmaker.id
                ]

                if session.is_open:
                    try:
                        if session.page:
                            session.current_url = (
                                session.page.url
                            )
                    except Exception as exc:
                        session.healthy = False
                        session.last_error = str(exc)

                else:
                    session.healthy = False

                results.append(
                    session.to_dict()
                )

            return results


# ---------------------------------------------------------
# Singleton
# ---------------------------------------------------------


_session_centre = SessionCentre()


def get_session_centre() -> SessionCentre:
    return _session_centre