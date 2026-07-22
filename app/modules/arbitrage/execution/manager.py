from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from time import perf_counter
from typing import Any, Iterable, Mapping

from app.browser import BrowserActions, BrowserPage
from app.modules.arbitrage.execution.adapter import (
    AdapterExecutionResult,
    ExecutionLeg,
)
from app.modules.arbitrage.execution.registry import (
    AdapterRegistry,
    adapter_registry,
    normalize_bookmaker_name,
)
from app.modules.arbitrage.execution.session import (
    ExecutionSession,
    ExecutionSessionConfig,
    ExecutionSessionFactory,
    SessionHealth,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


@dataclass(slots=True)
class ManagerSessionResult:
    bookmaker: str
    successful: bool
    message: str = ""
    error: str | None = None
    health: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bookmaker": self.bookmaker,
            "successful": self.successful,
            "message": self.message,
            "error": self.error,
            "health": self.health,
        }


@dataclass(slots=True)
class BatchExecutionResult:
    successful: bool
    all_ready_for_manual_confirmation: bool
    started_at: datetime
    completed_at: datetime
    elapsed_ms: float
    results: list[AdapterExecutionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ready_count(self) -> int:
        return sum(
            1
            for result in self.results
            if result.ready_for_manual_confirmation
        )

    @property
    def total_count(self) -> int:
        return len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "successful": self.successful,
            "all_ready_for_manual_confirmation": (
                self.all_ready_for_manual_confirmation
            ),
            "started_at": iso_utc(self.started_at),
            "completed_at": iso_utc(self.completed_at),
            "elapsed_ms": self.elapsed_ms,
            "ready_count": self.ready_count,
            "total_count": self.total_count,
            "results": [
                result.to_dict()
                for result in self.results
            ],
            "errors": self.errors,
        }


class ExecutionManager:
    """
    Owns all active bookmaker execution sessions.

    The manager does not create Playwright pages itself. Callers provide
    BrowserPage instances sourced from the shared browser manager.
    """

    def __init__(
        self,
        *,
        registry: AdapterRegistry | None = None,
        session_factory: ExecutionSessionFactory | None = None,
    ) -> None:
        self.registry = registry or adapter_registry
        self.session_factory = session_factory or ExecutionSessionFactory(
            registry=self.registry
        )
        self._sessions: dict[str, ExecutionSession] = {}
        self._lock = RLock()

    # -----------------------------------------------------
    # Session management
    # -----------------------------------------------------

    def add_session(
        self,
        bookmaker: str,
        *,
        browser: BrowserPage,
        actions: BrowserActions | None = None,
        config: ExecutionSessionConfig | None = None,
        replace: bool = False,
    ) -> ExecutionSession:
        key = self.registry.resolve_key(bookmaker)

        with self._lock:
            if key in self._sessions and not replace:
                raise ValueError(
                    f"Execution session already exists for {key!r}."
                )

            if key in self._sessions and replace:
                self._sessions[key].mark_closed(
                    reason="Session replaced by ExecutionManager."
                )

            session = self.session_factory.create(
                bookmaker=key,
                browser=browser,
                actions=actions,
                config=config,
            )
            self._sessions[key] = session
            return session

    def set_session(
        self,
        session: ExecutionSession,
        *,
        replace: bool = False,
    ) -> ExecutionSession:
        key = self.registry.resolve_key(session.bookmaker)

        with self._lock:
            if key in self._sessions and not replace:
                raise ValueError(
                    f"Execution session already exists for {key!r}."
                )

            self._sessions[key] = session
            return session

    def remove_session(
        self,
        bookmaker: str,
        *,
        reason: str | None = None,
    ) -> ExecutionSession:
        key = self.registry.resolve_key(bookmaker)

        with self._lock:
            session = self._sessions.pop(key)
            session.mark_closed(
                reason=reason or "Removed from ExecutionManager."
            )
            return session

    def get(
        self,
        bookmaker: str,
    ) -> ExecutionSession:
        key = self.registry.resolve_key(bookmaker)

        try:
            return self._sessions[key]
        except KeyError as exc:
            raise KeyError(
                f"No active execution session exists for {bookmaker!r}."
            ) from exc

    def contains(
        self,
        bookmaker: str,
    ) -> bool:
        try:
            key = self.registry.resolve_key(bookmaker)
        except KeyError:
            return False

        return key in self._sessions

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._sessions))

    def sessions(self) -> tuple[ExecutionSession, ...]:
        with self._lock:
            return tuple(
                self._sessions[key]
                for key in sorted(self._sessions)
            )

    def clear(
        self,
        *,
        reason: str | None = None,
    ) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for session in sessions:
            session.mark_closed(
                reason=reason or "ExecutionManager cleared."
            )

    # -----------------------------------------------------
    # Execution
    # -----------------------------------------------------

    def prepare_leg(
        self,
        leg: ExecutionLeg,
    ) -> AdapterExecutionResult:
        session = self.get(leg.bookmaker)
        return session.prepare(leg)

    def prepare_all(
        self,
        legs: Iterable[ExecutionLeg],
        *,
        stop_on_failure: bool = False,
    ) -> BatchExecutionResult:
        started_at = utc_now()
        started = perf_counter()
        results: list[AdapterExecutionResult] = []
        errors: list[str] = []

        for leg in legs:
            try:
                result = self.prepare_leg(leg)
            except Exception as exc:
                result = AdapterExecutionResult(
                    bookmaker=normalize_bookmaker_name(
                        leg.bookmaker
                    ),
                    successful=False,
                    ready_for_manual_confirmation=False,
                    message="Execution manager could not prepare leg.",
                    error=str(exc),
                    leg=leg,
                )

            results.append(result)

            if not result.successful:
                if result.error:
                    errors.append(result.error)

                if stop_on_failure:
                    break

        completed_at = utc_now()
        successful = bool(results) and all(
            result.successful
            for result in results
        )
        all_ready = bool(results) and all(
            result.ready_for_manual_confirmation
            for result in results
        )

        return BatchExecutionResult(
            successful=successful,
            all_ready_for_manual_confirmation=all_ready,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_ms=round(
                (perf_counter() - started) * 1_000,
                3,
            ),
            results=results,
            errors=errors,
        )

    # -----------------------------------------------------
    # Health and lifecycle
    # -----------------------------------------------------

    def heartbeat_all(
        self,
        *,
        login_check: bool = False,
    ) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}

        for session in self.sessions():
            health = session.heartbeat(
                login_check=login_check
            )
            output[session.bookmaker] = health.to_dict()

        return output

    def recover_session(
        self,
        bookmaker: str,
        *,
        reopen_home: bool = True,
        login_check: bool = True,
    ) -> SessionHealth:
        return self.get(bookmaker).recover(
            reopen_home=reopen_home,
            login_check=login_check,
        )

    def recover_all(
        self,
        *,
        reopen_home: bool = True,
        login_check: bool = True,
    ) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}

        for session in self.sessions():
            health = session.recover(
                reopen_home=reopen_home,
                login_check=login_check,
            )
            output[session.bookmaker] = health.to_dict()

        return output

    def health(
        self,
    ) -> dict[str, Any]:
        sessions = self.sessions()
        ready = sum(1 for session in sessions if session.is_ready)
        busy = sum(1 for session in sessions if session.is_busy)
        closed = sum(1 for session in sessions if session.is_closed)

        return {
            "session_count": len(sessions),
            "ready_count": ready,
            "busy_count": busy,
            "closed_count": closed,
            "sessions": {
                session.bookmaker: session.health_dict()
                for session in sessions
            },
        }

    def recent_history(
        self,
        *,
        limit_per_session: int = 20,
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            session.bookmaker: session.recent_history(
                limit=limit_per_session
            )
            for session in self.sessions()
        }


execution_manager = ExecutionManager()