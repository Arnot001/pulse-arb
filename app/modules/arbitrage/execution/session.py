from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from time import perf_counter
from typing import Any, Callable

from app.browser import BrowserActions, BrowserPage
from app.modules.arbitrage.execution.adapter import (
    AdapterExecutionResult,
    AdapterStatus,
    BrowserAdapterConfig,
    ExecutionLeg,
)
from app.modules.arbitrage.execution.registry import (
    AdapterRegistry,
    adapter_registry,
    normalize_bookmaker_name,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


class SessionStatus(str, Enum):
    CREATED = "CREATED"
    OPENING = "OPENING"
    OPEN = "OPEN"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    READY = "READY"
    BUSY = "BUSY"
    ERROR = "ERROR"
    CLOSED = "CLOSED"


@dataclass(slots=True)
class ExecutionSessionConfig:
    auto_open_home: bool = False
    auto_login_check: bool = True
    keep_history: bool = True
    max_history: int = 100
    adapter_config: BrowserAdapterConfig = field(default_factory=BrowserAdapterConfig)


@dataclass(slots=True)
class SessionEvent:
    event_type: str
    created_at: datetime = field(default_factory=utc_now)
    successful: bool = True
    message: str = ""
    elapsed_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "created_at": iso_utc(self.created_at),
            "successful": self.successful,
            "message": self.message,
            "elapsed_ms": self.elapsed_ms,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class SessionHealth:
    bookmaker: str
    display_name: str
    status: SessionStatus
    browser_closed: bool
    adapter_status: AdapterStatus
    logged_in: bool | None
    ready: bool
    url: str
    title: str
    last_error: str | None
    created_at: datetime
    last_activity_at: datetime
    last_heartbeat_at: datetime | None
    current_leg: ExecutionLeg | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bookmaker": self.bookmaker,
            "display_name": self.display_name,
            "status": self.status.value,
            "browser_closed": self.browser_closed,
            "adapter_status": self.adapter_status.value,
            "logged_in": self.logged_in,
            "ready": self.ready,
            "url": self.url,
            "title": self.title,
            "last_error": self.last_error,
            "created_at": iso_utc(self.created_at),
            "last_activity_at": iso_utc(self.last_activity_at),
            "last_heartbeat_at": iso_utc(self.last_heartbeat_at),
            "current_leg": self.current_leg.to_dict() if self.current_leg else None,
        }


class ExecutionSession:
    """Owns one persistent bookmaker page, actions object and adapter."""

    def __init__(
        self,
        *,
        bookmaker: str,
        browser: BrowserPage,
        registry: AdapterRegistry | None = None,
        actions: BrowserActions | None = None,
        config: ExecutionSessionConfig | None = None,
    ) -> None:
        self.registry = registry or adapter_registry
        self.config = config or ExecutionSessionConfig()
        self.bookmaker = self.registry.resolve_key(bookmaker)
        self.browser = browser
        self.actions = actions or BrowserActions(browser)
        self.adapter = self.registry.create(
            self.bookmaker,
            browser=self.browser,
            actions=self.actions,
            config=self.config.adapter_config,
        )
        self.status = SessionStatus.CREATED
        self.logged_in: bool | None = None
        self.last_error: str | None = None
        self.current_leg: ExecutionLeg | None = None
        self.last_result: AdapterExecutionResult | None = None
        self.created_at = utc_now()
        self.last_activity_at = self.created_at
        self.last_heartbeat_at: datetime | None = None
        self.history: list[SessionEvent] = []
        self._lock = RLock()
        self._record("session_created", message=f"{self.display_name} session created.")

        if self.config.auto_open_home:
            self.open_home()
        if self.config.auto_login_check and not self.browser.is_closed:
            self.check_login()

    @property
    def display_name(self) -> str:
        return self.adapter.display_name

    @property
    def key(self) -> str:
        return normalize_bookmaker_name(self.bookmaker)

    @property
    def is_closed(self) -> bool:
        return self.status == SessionStatus.CLOSED or self.browser.is_closed

    @property
    def is_busy(self) -> bool:
        return self.status == SessionStatus.BUSY

    @property
    def is_ready(self) -> bool:
        return (
            not self.is_closed
            and self.logged_in is True
            and self.status == SessionStatus.READY
            and self.adapter.is_ready
        )

    @property
    def url(self) -> str:
        return self.browser.url

    @property
    def title(self) -> str:
        return self.browser.title

    def open_home(self):
        with self._lock:
            if self.browser.is_closed:
                return self._mark_closed_event("open_home")
            started = perf_counter()
            self.status = SessionStatus.OPENING
            self._touch()
            result = self.adapter.open_home()
            self.status = SessionStatus.OPEN if result.successful else SessionStatus.ERROR
            self.last_error = None if result.successful else result.error
            self._record(
                "open_home",
                successful=result.successful,
                message=result.message,
                elapsed_ms=self._elapsed_ms(started),
                metadata=result.to_dict(),
            )
            return result

    def check_login(self):
        with self._lock:
            if self.browser.is_closed:
                self.logged_in = False
                return self._mark_closed_event("login_check")
            started = perf_counter()
            self._touch()
            result = self.adapter.login_check()
            self.logged_in = result.successful
            if result.successful:
                self.status = SessionStatus.READY
                self.last_error = None
            else:
                self.status = SessionStatus.ERROR if result.error else SessionStatus.LOGIN_REQUIRED
                self.last_error = result.error
            self._record(
                "login_check",
                successful=result.successful,
                message=result.message,
                elapsed_ms=self._elapsed_ms(started),
                metadata=result.to_dict(),
            )
            return result

    def prepare(self, leg: ExecutionLeg) -> AdapterExecutionResult:
        with self._lock:
            started = perf_counter()
            self._touch()
            if self.browser.is_closed:
                result = AdapterExecutionResult(
                    bookmaker=self.bookmaker,
                    successful=False,
                    ready_for_manual_confirmation=False,
                    elapsed_ms=self._elapsed_ms(started),
                    message="Cannot prepare a closed bookmaker session.",
                    error="Browser page is closed.",
                    leg=leg,
                )
            elif self.is_busy:
                result = AdapterExecutionResult(
                    bookmaker=self.bookmaker,
                    successful=False,
                    ready_for_manual_confirmation=False,
                    elapsed_ms=self._elapsed_ms(started),
                    message="Bookmaker session is already busy.",
                    error="Session is busy.",
                    leg=leg,
                )
            else:
                self.status = SessionStatus.BUSY
                self.current_leg = leg
                try:
                    result = self.adapter.prepare(leg)
                except Exception as exc:
                    result = AdapterExecutionResult(
                        bookmaker=self.bookmaker,
                        successful=False,
                        ready_for_manual_confirmation=False,
                        elapsed_ms=self._elapsed_ms(started),
                        message="Bookmaker preparation raised an exception.",
                        error=str(exc),
                        leg=leg,
                    )
            self._apply_result(result)
            self._record(
                "prepare",
                successful=result.successful,
                message=result.message,
                elapsed_ms=result.elapsed_ms,
                metadata=result.to_dict(),
            )
            return result

    def heartbeat(self, *, login_check: bool = False) -> SessionHealth:
        with self._lock:
            self.last_heartbeat_at = utc_now()
            self._touch()
            if self.browser.is_closed:
                self.status = SessionStatus.CLOSED
                self.logged_in = False
                self.last_error = self.last_error or "Browser page is closed."
            elif login_check:
                self.check_login()
            elif self.status == SessionStatus.CREATED:
                self.status = SessionStatus.OPEN
            self._record(
                "heartbeat",
                successful=not self.browser.is_closed,
                message="Session heartbeat completed.",
                metadata={"login_check": login_check, "url": self.browser.url},
            )
            return self.health()

    def reset(self) -> None:
        with self._lock:
            self.current_leg = None
            self.last_result = None
            self.last_error = None
            self.adapter.reset()
            self._touch()
            if self.browser.is_closed:
                self.status = SessionStatus.CLOSED
                self.logged_in = False
            elif self.logged_in is True:
                self.status = SessionStatus.READY
            elif self.logged_in is False:
                self.status = SessionStatus.LOGIN_REQUIRED
            else:
                self.status = SessionStatus.OPEN
            self._record("session_reset", message=f"{self.display_name} session reset.")

    def recover(self, *, reopen_home: bool = True, login_check: bool = True) -> SessionHealth:
        with self._lock:
            self.reset()
            if self.browser.is_closed:
                return self.health()
            if reopen_home and not self.open_home().successful:
                return self.health()
            if login_check:
                self.check_login()
            self._record(
                "recover",
                successful=self.status != SessionStatus.ERROR,
                message="Session recovery completed.",
                metadata={"reopen_home": reopen_home, "login_check": login_check},
            )
            return self.health()

    def mark_closed(self, *, reason: str | None = None) -> None:
        with self._lock:
            self.status = SessionStatus.CLOSED
            self.logged_in = False
            self.current_leg = None
            self.last_error = reason
            self._touch()
            self._record(
                "session_closed",
                successful=reason is None,
                message=reason or f"{self.display_name} session marked closed.",
            )

    def health(self) -> SessionHealth:
        return SessionHealth(
            bookmaker=self.bookmaker,
            display_name=self.display_name,
            status=self.status,
            browser_closed=self.browser.is_closed,
            adapter_status=self.adapter.status,
            logged_in=self.logged_in,
            ready=self.is_ready,
            url=self.browser.url,
            title=self.browser.title,
            last_error=self.last_error,
            created_at=self.created_at,
            last_activity_at=self.last_activity_at,
            last_heartbeat_at=self.last_heartbeat_at,
            current_leg=self.current_leg,
        )

    def health_dict(self) -> dict[str, Any]:
        payload = self.health().to_dict()
        payload["adapter"] = self.adapter.health()
        payload["last_result"] = self.last_result.to_dict() if self.last_result else None
        payload["history_size"] = len(self.history)
        return payload

    def recent_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.history[-max(limit, 0):]] if limit else []

    def _apply_result(self, result: AdapterExecutionResult) -> None:
        self.last_result = result
        self.current_leg = result.leg
        self.last_error = result.error
        self._touch()
        if result.successful:
            self.status = SessionStatus.READY
            self.logged_in = True
        elif self.browser.is_closed:
            self.status = SessionStatus.CLOSED
            self.logged_in = False
        elif self.adapter.status == AdapterStatus.LOGIN_REQUIRED:
            self.status = SessionStatus.LOGIN_REQUIRED
            self.logged_in = False
        else:
            self.status = SessionStatus.ERROR

    def _record(
        self,
        event_type: str,
        *,
        successful: bool = True,
        message: str = "",
        elapsed_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> SessionEvent:
        event = SessionEvent(
            event_type=event_type,
            successful=successful,
            message=message,
            elapsed_ms=elapsed_ms,
            metadata=metadata or {},
        )
        if self.config.keep_history:
            self.history.append(event)
            overflow = len(self.history) - self.config.max_history
            if overflow > 0:
                del self.history[:overflow]
        return event

    def _mark_closed_event(self, event_type: str) -> SessionEvent:
        self.status = SessionStatus.CLOSED
        self.logged_in = False
        self.last_error = "Browser page is closed."
        self._touch()
        return self._record(event_type, successful=False, message=self.last_error)

    def _touch(self) -> None:
        self.last_activity_at = utc_now()

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1_000, 3)


class ExecutionSessionFactory:
    def __init__(
        self,
        *,
        registry: AdapterRegistry | None = None,
        config_factory: Callable[[str], ExecutionSessionConfig] | None = None,
    ) -> None:
        self.registry = registry or adapter_registry
        self.config_factory = config_factory

    def create(
        self,
        *,
        bookmaker: str,
        browser: BrowserPage,
        actions: BrowserActions | None = None,
        config: ExecutionSessionConfig | None = None,
    ) -> ExecutionSession:
        resolved_config = config
        if resolved_config is None and self.config_factory is not None:
            resolved_config = self.config_factory(bookmaker)
        return ExecutionSession(
            bookmaker=bookmaker,
            browser=browser,
            registry=self.registry,
            actions=actions,
            config=resolved_config,
        )