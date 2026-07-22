from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from app.modules.arbitrage.execution.execution_browser import (
    ExecutionBrowserInstance,
    execution_browser_manager,
)
from app.modules.arbitrage.execution.models import ExecutionLeg
from app.modules.arbitrage.execution.worker import (
    execution_browser_worker,
)


# ---------------------------------------------------------
# Bookmaker configuration
# ---------------------------------------------------------

BOOKMAKER_CONFIG: dict[str, dict[str, Any]] = {
    "bet365": {
        "name": "Bet365",
        "home_url": "https://www.bet365.com/",
        "supported": True,
    },
    "skybet": {
        "name": "Sky Bet",
        "home_url": "https://m.skybet.com/",
        "supported": False,
    },
    "coral": {
        "name": "Coral",
        "home_url": "https://sports.coral.co.uk/",
        "supported": False,
    },
    "paddypower": {
        "name": "Paddy Power",
        "home_url": "https://www.paddypower.com/",
        "supported": False,
    },
    "williamhill": {
        "name": "William Hill",
        "home_url": "https://sports.williamhill.com/",
        "supported": False,
    },
    "betvictor": {
        "name": "BetVictor",
        "home_url": "https://www.betvictor.com/",
        "supported": False,
    },
}


# ---------------------------------------------------------
# Session model
# ---------------------------------------------------------

@dataclass(slots=True)
class ExecutionSession:
    bookmaker: str
    browser_instance: ExecutionBrowserInstance
    opened_at: datetime
    last_used_at: datetime

    headless: bool = False
    login_status: str = "UNKNOWN"

    last_url: str | None = None
    last_error: str | None = None

    prepared_leg: dict[str, Any] | None = None
    notes: list[str] = field(
        default_factory=list
    )

    @property
    def page(self) -> Page:
        return self.browser_instance.page

    @property
    def is_open(self) -> bool:
        return self.browser_instance.is_open

    def to_dict(self) -> dict[str, Any]:
        current_url = self.last_url

        if self.is_open:
            try:
                current_url = self.page.url
            except Exception:
                pass

        return {
            "bookmaker": self.bookmaker,
            "is_open": self.is_open,
            "headless": self.headless,
            "login_status": self.login_status,
            "opened_at": self.opened_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "current_url": current_url,
            "last_error": self.last_error,
            "prepared_leg": self.prepared_leg,
            "notes": list(self.notes),
            "browser_channel": (
                self.browser_instance.browser_channel
            ),
            "profile_path": str(
                self.browser_instance.profile_path
            ),
        }


# ---------------------------------------------------------
# Execution service
# ---------------------------------------------------------

class ExecutionService:
    """
    Maintains persistent execution-only bookmaker sessions.

    Every browser operation runs on the dedicated execution worker.

    Each bookmaker has its own persistent Chrome profile, allowing login
    state, cookies, local storage and preferences to survive restarts.

    Pulse never presses the final BET / PLACE BET button.
    """

    def __init__(self):
        self._sessions: dict[
            str,
            ExecutionSession,
        ] = {}

        self._lock = threading.RLock()

    # -----------------------------------------------------
    # Helpers
    # -----------------------------------------------------

    @staticmethod
    def _now() -> datetime:
        return datetime.now(
            timezone.utc
        )

    @staticmethod
    def _normalise_bookmaker(
        bookmaker: str,
    ) -> str:
        return (
            bookmaker
            .strip()
            .lower()
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
        )

    def _bookmaker_key(
        self,
        bookmaker: str,
    ) -> str:
        normalised = (
            self._normalise_bookmaker(
                bookmaker
            )
        )

        aliases = {
            "bet365": "bet365",
            "b365": "bet365",

            "skybet": "skybet",
            "sky": "skybet",

            "coral": "coral",

            "paddypower": "paddypower",
            "pp": "paddypower",

            "williamhill": "williamhill",
            "willhill": "williamhill",
            "wh": "williamhill",

            "betvictor": "betvictor",
            "bv": "betvictor",
        }

        key = aliases.get(
            normalised
        )

        if not key:
            raise KeyError(
                f"Unsupported bookmaker: {bookmaker}"
            )

        return key

    def _get_config(
        self,
        bookmaker: str,
    ) -> tuple[
        str,
        dict[str, Any],
    ]:
        key = self._bookmaker_key(
            bookmaker
        )

        return (
            key,
            BOOKMAKER_CONFIG[key],
        )

    def _get_session(
        self,
        bookmaker: str,
    ) -> ExecutionSession:
        key = self._bookmaker_key(
            bookmaker
        )

        session = self._sessions.get(
            key
        )

        if not session or not session.is_open:
            raise KeyError(
                f"No open execution session for {key}."
            )

        return session

    @staticmethod
    def _bring_to_front(
        page: Page,
    ) -> None:
        try:
            page.bring_to_front()
        except Exception:
            pass

    @staticmethod
    def _safe_title(
        page: Page,
    ) -> str | None:
        try:
            return page.title()
        except Exception:
            return None

    @staticmethod
    def _safe_body_text(
        page: Page,
    ) -> str:
        try:
            return (
                page
                .locator("body")
                .inner_text(
                    timeout=7_000
                )
            )
        except Exception:
            return ""

    # -----------------------------------------------------
    # Health
    # -----------------------------------------------------

    def health(
        self,
    ) -> dict[str, Any]:
        return execution_browser_worker.submit(
            self._health_on_worker,
            timeout=20,
        )

    def _health_on_worker(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            sessions: dict[
                str,
                dict[str, Any],
            ] = {}

            ready_count = 0
            open_count = 0

            for key, session in list(
                self._sessions.items()
            ):
                session_data = (
                    session.to_dict()
                )

                is_open = bool(
                    session_data.get(
                        "is_open"
                    )
                )

                if is_open:
                    open_count += 1

                login_status = str(
                    session_data.get(
                        "login_status",
                        "UNKNOWN",
                    )
                ).upper()

                logged_in = (
                    login_status
                    == "LOGGED_IN"
                )

                if logged_in:
                    ready_count += 1

                if not is_open:
                    status = "CLOSED"

                elif session.last_error:
                    status = "ERROR"

                elif logged_in:
                    status = "READY"

                else:
                    status = "OPEN"

                sessions[key] = {
                    "bookmaker": key,
                    "status": status,
                    "logged_in": logged_in,
                    "login_status": login_status,
                    "browser_closed": (
                        not is_open
                    ),
                    "closed": not is_open,
                    "url": session_data.get(
                        "current_url"
                    ),
                    "last_activity_at": (
                        session_data.get(
                            "last_used_at"
                        )
                    ),
                    "last_checked_at": (
                        session_data.get(
                            "last_used_at"
                        )
                    ),
                    "opened_at": (
                        session_data.get(
                            "opened_at"
                        )
                    ),
                    "last_error": (
                        session_data.get(
                            "last_error"
                        )
                    ),
                    "prepared_leg": (
                        session_data.get(
                            "prepared_leg"
                        )
                    ),
                    "browser_channel": (
                        session_data.get(
                            "browser_channel"
                        )
                    ),
                    "profile_path": (
                        session_data.get(
                            "profile_path"
                        )
                    ),
                }

            return {
                "successful": True,
                "service": "execution",
                "service_running": True,
                "worker_running": (
                    execution_browser_worker
                    .is_running
                ),
                "browser_running": (
                    execution_browser_manager
                    .is_running
                ),
                "manager": {
                    "session_count": open_count,
                    "ready_count": ready_count,
                    "sessions": sessions,
                },
                "browser_manager": (
                    execution_browser_manager
                    .health()
                ),
                "supported_bookmakers": [
                    key
                    for key, config
                    in BOOKMAKER_CONFIG.items()
                    if config["supported"]
                ],
                "timestamp": (
                    self._now()
                    .isoformat()
                ),
            }

    # -----------------------------------------------------
    # Open session
    # -----------------------------------------------------

    def open_session(
        self,
        bookmaker: str,
        *,
        headless: bool = False,
        replace: bool = False,
    ) -> dict[str, Any]:
        return execution_browser_worker.submit(
            self._open_session_on_worker,
            bookmaker,
            headless=headless,
            replace=replace,
            timeout=90,
        )

    def _open_session_on_worker(
        self,
        bookmaker: str,
        *,
        headless: bool = False,
        replace: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            key, config = self._get_config(
                bookmaker
            )

            existing = self._sessions.get(
                key
            )

            if (
                existing
                and existing.is_open
                and not replace
            ):
                self._bring_to_front(
                    existing.page
                )

                existing.last_used_at = (
                    self._now()
                )

                return {
                    "successful": True,
                    "created": False,
                    "status": "SESSION_ALREADY_OPEN",
                    "message": (
                        f"{config['name']} session "
                        "is already open."
                    ),
                    "session": existing.to_dict(),
                }

            if existing:
                execution_browser_manager.close_bookmaker(
                    key
                )

                self._sessions.pop(
                    key,
                    None,
                )

            try:
                browser_result = (
                    execution_browser_manager
                    .open_bookmaker(
                        key,
                        home_url=config[
                            "home_url"
                        ],
                        headless=headless,
                        replace=replace,
                    )
                )

            except BaseException as exc:
                return {
                    "successful": False,
                    "created": False,
                    "status": "BROWSER_START_FAILED",
                    "message": (
                        f"{config['name']} browser "
                        "session could not be started."
                    ),
                    "error": {
                        "type": (
                            type(exc).__name__
                        ),
                        "message": str(exc),
                        "repr": repr(exc),
                    },
                }

            instance = browser_result.get(
                "instance"
            )

            if instance is None:
                return {
                    "successful": False,
                    "created": False,
                    "status": "BROWSER_INSTANCE_MISSING",
                    "message": (
                        "Execution browser opened without "
                        "returning a browser instance."
                    ),
                    "error": browser_result.get(
                        "error"
                    ),
                }

            now = self._now()

            session = ExecutionSession(
                bookmaker=key,
                browser_instance=instance,
                opened_at=now,
                last_used_at=now,
                headless=headless,
                last_url=instance.page.url,
                last_error=None,
                notes=[
                    (
                        "Persistent execution profile "
                        "loaded."
                    ),
                    (
                        "Cookies and login state are "
                        "retained between Pulse sessions."
                    ),
                    (
                        "Pulse will never press the "
                        "final bet button."
                    ),
                ],
            )

            self._sessions[key] = session

            self._bring_to_front(
                session.page
            )

            if not browser_result.get(
                "successful"
            ):
                error = browser_result.get(
                    "error"
                )

                session.last_error = (
                    repr(error)
                )

                return {
                    "successful": False,
                    "created": bool(
                        browser_result.get(
                            "created"
                        )
                    ),
                    "status": (
                        browser_result.get(
                            "status",
                            "BROWSER_OPEN_FAILED",
                        )
                    ),
                    "message": (
                        f"{config['name']} browser "
                        "opened, but the homepage did "
                        "not finish loading."
                    ),
                    "error": error,
                    "session": session.to_dict(),
                }

            return {
                "successful": True,
                "created": bool(
                    browser_result.get(
                        "created"
                    )
                ),
                "status": "SESSION_OPEN",
                "message": (
                    f"{config['name']} persistent "
                    "execution session opened."
                ),
                "session": session.to_dict(),
            }

    # -----------------------------------------------------
    # Login check
    # -----------------------------------------------------

    def login_check(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        return execution_browser_worker.submit(
            self._login_check_on_worker,
            bookmaker,
            timeout=40,
        )

    def _login_check_on_worker(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        with self._lock:
            key, config = self._get_config(
                bookmaker
            )

            session = self._get_session(
                key
            )

            page = session.page

            self._bring_to_front(
                page
            )

            body_text = (
                self._safe_body_text(
                    page
                )
                .lower()
            )

            try:
                current_url = (
                    page.url.lower()
                )
            except Exception:
                current_url = ""

            logged_out_markers = [
                "log in",
                "login",
                "join now",
                "register",
                "create account",
            ]

            logged_in_markers = [
                "my bets",
                "cash out",
                "deposit",
                "balance",
                "account",
                "withdraw",
            ]

            logged_in_matches = [
                marker
                for marker
                in logged_in_markers
                if marker in body_text
            ]

            logged_out_matches = [
                marker
                for marker
                in logged_out_markers
                if marker in body_text
            ]

            if (
                "login" in current_url
                or "signin" in current_url
            ):
                status = "LOGGED_OUT"

            elif logged_in_matches:
                status = "LOGGED_IN"

            elif logged_out_matches:
                status = "LOGGED_OUT"

            else:
                status = "UNKNOWN"

            session.login_status = status
            session.last_used_at = (
                self._now()
            )

            try:
                session.last_url = page.url
            except Exception:
                pass

            session.last_error = None

            return {
                "successful": True,
                "bookmaker": key,
                "bookmaker_name": config[
                    "name"
                ],
                "login_status": status,
                "logged_in": (
                    status == "LOGGED_IN"
                ),
                "current_url": (
                    session.last_url
                ),
                "page_title": (
                    self._safe_title(
                        page
                    )
                ),
                "evidence": {
                    "logged_in_markers": (
                        logged_in_matches
                    ),
                    "logged_out_markers": (
                        logged_out_matches
                    ),
                },
                "session": session.to_dict(),
            }

    # -----------------------------------------------------
    # Prepare execution leg
    # -----------------------------------------------------

    def prepare_leg(
        self,
        leg: ExecutionLeg,
    ) -> dict[str, Any]:
        return execution_browser_worker.submit(
            self._prepare_leg_on_worker,
            leg,
            timeout=90,
        )

    def _prepare_leg_on_worker(
        self,
        leg: ExecutionLeg,
    ) -> dict[str, Any]:
        with self._lock:
            key, _config = self._get_config(
                leg.bookmaker
            )

            session = self._sessions.get(
                key
            )

            if (
                not session
                or not session.is_open
            ):
                open_result = (
                    self._open_session_on_worker(
                        key,
                        headless=False,
                        replace=False,
                    )
                )

                if not open_result.get(
                    "successful"
                ):
                    return {
                        "successful": False,
                        "status": "SESSION_OPEN_FAILED",
                        "bookmaker": key,
                        "error": open_result,
                    }

                session = self._get_session(
                    key
                )

            session.last_used_at = (
                self._now()
            )

            session.last_error = None

            if key == "bet365":
                result = self._prepare_bet365(
                    session,
                    leg,
                )

            else:
                result = self._prepare_generic(
                    session,
                    leg,
                )

            session.prepared_leg = {
                **leg.to_dict(),
                "result_status": result.get(
                    "status"
                ),
                "prepared_at": (
                    self._now()
                    .isoformat()
                ),
            }

            try:
                session.last_url = (
                    session.page.url
                )
            except Exception:
                pass

            return {
                **result,
                "session": session.to_dict(),
            }

    # -----------------------------------------------------
    # Generic preparation
    # -----------------------------------------------------

    def _prepare_generic(
        self,
        session: ExecutionSession,
        leg: ExecutionLeg,
    ) -> dict[str, Any]:
        page = session.page

        key, config = self._get_config(
            leg.bookmaker
        )

        target_url = (
            leg.event_url
            or config["home_url"]
        )

        try:
            page.goto(
                target_url,
                wait_until="domcontentloaded",
                timeout=45_000,
            )

            self._bring_to_front(
                page
            )

        except Exception as exc:
            session.last_error = (
                repr(exc)
            )

            return {
                "successful": False,
                "status": "NAVIGATION_FAILED",
                "bookmaker": key,
                "error": {
                    "type": (
                        type(exc).__name__
                    ),
                    "message": str(exc),
                    "repr": repr(exc),
                },
            }

        return {
            "successful": True,
            "prepared": False,
            "status": "MANUAL_PREPARATION_REQUIRED",
            "bookmaker": key,
            "message": (
                f"{config['name']} event page is open. "
                "Automatic slip preparation is not yet "
                "enabled for this bookmaker."
            ),
            "leg": leg.to_dict(),
            "manual_actions": [
                (
                    f"Select "
                    f"{leg.selection_name}."
                ),
                (
                    f"Enter stake "
                    f"£{leg.stake:.2f}."
                ),
                "Check the live odds.",
                (
                    "Press BET manually only after "
                    "verification."
                ),
            ],
        }

    # -----------------------------------------------------
    # Bet365 preparation
    # -----------------------------------------------------

    def _prepare_bet365(
        self,
        session: ExecutionSession,
        leg: ExecutionLeg,
    ) -> dict[str, Any]:
        page = session.page

        navigation_complete = False
        selection_clicked = False
        stake_filled = False

        warnings: list[str] = []
        actions: list[str] = []

        target_url = (
            leg.event_url
            or BOOKMAKER_CONFIG[
                "bet365"
            ]["home_url"]
        )

        try:
            if leg.event_url:
                page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=45_000,
                )

                actions.append(
                    "Bet365 event page opened."
                )

            else:
                warnings.append(
                    "No event URL was supplied. "
                    "The existing Bet365 page has "
                    "been brought to the front."
                )

            navigation_complete = True

            self._bring_to_front(
                page
            )

        except Exception as exc:
            session.last_error = (
                repr(exc)
            )

            return {
                "successful": False,
                "prepared": False,
                "status": "NAVIGATION_FAILED",
                "bookmaker": "bet365",
                "error": {
                    "type": (
                        type(exc).__name__
                    ),
                    "message": str(exc),
                    "repr": repr(exc),
                },
                "leg": leg.to_dict(),
            }

        try:
            candidate = page.get_by_text(
                leg.selection_name,
                exact=True,
            ).first

            candidate.wait_for(
                state="visible",
                timeout=10_000,
            )

            candidate.click(
                timeout=7_000,
            )

            selection_clicked = True

            actions.append(
                f"Selected "
                f"{leg.selection_name}."
            )

        except PlaywrightTimeoutError:
            warnings.append(
                "Pulse could not automatically locate "
                f"{leg.selection_name} on the page."
            )

        except Exception as exc:
            warnings.append(
                "Runner selection was not completed "
                f"automatically: {repr(exc)}"
            )

        if selection_clicked:
            stake_filled = (
                self._try_fill_bet365_stake(
                    page,
                    leg.stake,
                )
            )

            if stake_filled:
                actions.append(
                    "Stake field populated with "
                    f"£{leg.stake:.2f}."
                )

            else:
                warnings.append(
                    "The selection appears to be in "
                    "the bet slip, but Pulse could not "
                    "identify the stake field."
                )

        if (
            selection_clicked
            and stake_filled
        ):
            status = (
                "READY_FOR_USER_CONFIRMATION"
            )

            message = (
                "Bet365 slip prepared. Verify the "
                "runner, odds and stake, then press "
                "BET manually."
            )

            prepared = True

        elif selection_clicked:
            status = (
                "SELECTION_ADDED_STAKE_REQUIRED"
            )

            message = (
                "Bet365 selection added. Enter or "
                "verify the stake manually before "
                "pressing BET."
            )

            prepared = False

        else:
            status = (
                "EVENT_OPEN_MANUAL_SELECTION_REQUIRED"
            )

            message = (
                "Bet365 page opened, but manual "
                "runner selection is required."
            )

            prepared = False

        return {
            "successful": navigation_complete,
            "prepared": prepared,
            "status": status,
            "bookmaker": "bet365",
            "message": message,
            "navigation_complete": (
                navigation_complete
            ),
            "selection_clicked": (
                selection_clicked
            ),
            "stake_filled": stake_filled,
            "leg": leg.to_dict(),
            "actions": actions,
            "warnings": warnings,
            "final_action_required": (
                "User must verify the bet slip and "
                "press BET manually."
            ),
        }

    @staticmethod
    def _try_fill_bet365_stake(
        page: Page,
        stake: float,
    ) -> bool:
        stake_text = (
            f"{stake:.2f}"
        )

        selectors = [
            'input[placeholder*="Stake" i]',
            'input[aria-label*="Stake" i]',
            'input[data-testid*="stake" i]',
            'input[name*="stake" i]',
            'input[type="number"]',
            'input[inputmode="decimal"]',
        ]

        for selector in selectors:
            try:
                locator = page.locator(
                    selector
                )

                count = locator.count()

                if count < 1:
                    continue

                for index in range(
                    count
                ):
                    candidate = (
                        locator.nth(index)
                    )

                    if not candidate.is_visible():
                        continue

                    candidate.fill(
                        stake_text,
                        timeout=4_000,
                    )

                    return True

            except Exception:
                continue

        return False

    # -----------------------------------------------------
    # Reset session
    # -----------------------------------------------------

    def reset_session(
        self,
        bookmaker: str,
        *,
        reopen_home: bool = True,
    ) -> dict[str, Any]:
        return execution_browser_worker.submit(
            self._reset_session_on_worker,
            bookmaker,
            reopen_home=reopen_home,
            timeout=60,
        )

    def _reset_session_on_worker(
        self,
        bookmaker: str,
        *,
        reopen_home: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            key, config = self._get_config(
                bookmaker
            )

            session = self._get_session(
                key
            )

            session.prepared_leg = None
            session.last_error = None
            session.last_used_at = (
                self._now()
            )

            page = session.page

            try:
                if reopen_home:
                    page.goto(
                        config["home_url"],
                        wait_until=(
                            "domcontentloaded"
                        ),
                        timeout=45_000,
                    )

                else:
                    page.reload(
                        wait_until=(
                            "domcontentloaded"
                        ),
                        timeout=45_000,
                    )

                self._bring_to_front(
                    page
                )

                session.last_url = page.url

                return {
                    "successful": True,
                    "message": (
                        f"{config['name']} execution "
                        "session reset."
                    ),
                    "session": session.to_dict(),
                }

            except Exception as exc:
                session.last_error = (
                    repr(exc)
                )

                return {
                    "successful": False,
                    "message": (
                        f"{config['name']} session "
                        "could not be reset."
                    ),
                    "error": {
                        "type": (
                            type(exc).__name__
                        ),
                        "message": str(exc),
                        "repr": repr(exc),
                    },
                    "session": session.to_dict(),
                }

    # -----------------------------------------------------
    # Close session
    # -----------------------------------------------------

    def close_session(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        return execution_browser_worker.submit(
            self._close_session_on_worker,
            bookmaker,
            timeout=40,
        )

    def _close_session_on_worker(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        with self._lock:
            key, config = self._get_config(
                bookmaker
            )

            session = self._sessions.pop(
                key,
                None,
            )

            browser_result = (
                execution_browser_manager
                .close_bookmaker(
                    key
                )
            )

            if not session:
                return {
                    "successful": True,
                    "closed": bool(
                        browser_result.get(
                            "closed"
                        )
                    ),
                    "message": (
                        f"No tracked {config['name']} "
                        "execution session was open."
                    ),
                }

            return {
                "successful": True,
                "closed": True,
                "message": (
                    f"{config['name']} execution "
                    "session closed."
                ),
            }

    def close_all_sessions(
        self,
    ) -> dict[str, Any]:
        return execution_browser_worker.submit(
            self._close_all_sessions_on_worker,
            timeout=60,
        )

    def _close_all_sessions_on_worker(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            browser_result = (
                execution_browser_manager
                .close_all()
            )

            self._sessions.clear()

            return browser_result


execution_service = ExecutionService()