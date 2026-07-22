from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable

from app.browser import BrowserPage
from app.browser_manager import SharedBrowserManager
from app.modules.arbitrage.execution import (
    ExecutionLeg,
    ExecutionManager,
    ExecutionSessionConfig,
)


@dataclass(slots=True)
class ExecutionCommand:
    name: str
    payload: dict[str, Any]
    future: Future


class ExecutionService:
    """
    Thread-owned bookmaker execution service.

    Playwright's synchronous objects must stay on the thread that created
    them. FastAPI request handlers therefore submit commands to this
    worker instead of touching Playwright pages directly.
    """

    def __init__(self) -> None:
        self.manager = ExecutionManager()
        self.browser_manager: SharedBrowserManager | None = None

        self._commands: queue.Queue[ExecutionCommand | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stopped = threading.Event()
        self._lock = threading.RLock()

    # -----------------------------------------------------
    # Public lifecycle
    # -----------------------------------------------------

    @property
    def running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._started.is_set()
            and not self._stopped.is_set()
        )

    def start(self, timeout: float = 15.0) -> None:
        with self._lock:
            if self.running:
                return

            self._started.clear()
            self._stopped.clear()

            self._thread = threading.Thread(
                target=self._run,
                name="pulse-execution-service",
                daemon=True,
            )
            self._thread.start()

        if not self._started.wait(timeout):
            raise RuntimeError(
                "Pulse execution service did not start in time."
            )

    def stop(self, timeout: float = 10.0) -> None:
        with self._lock:
            if self._thread is None:
                return

            self._commands.put(None)
            thread = self._thread

        thread.join(timeout=timeout)

        if thread.is_alive():
            raise RuntimeError(
                "Pulse execution service did not stop in time."
            )

    # -----------------------------------------------------
    # Public commands
    # -----------------------------------------------------

    def open_session(
        self,
        bookmaker: str,
        *,
        headless: bool = False,
        replace: bool = False,
    ) -> dict[str, Any]:
        return self._submit(
            "open_session",
            {
                "bookmaker": bookmaker,
                "headless": headless,
                "replace": replace,
            },
        )

    def login_check(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        return self._submit(
            "login_check",
            {"bookmaker": bookmaker},
        )

    def prepare_leg(
        self,
        leg: ExecutionLeg,
    ) -> dict[str, Any]:
        return self._submit(
            "prepare_leg",
            {"leg": leg},
            timeout=90.0,
        )

    def reset_session(
        self,
        bookmaker: str,
        *,
        reopen_home: bool = True,
    ) -> dict[str, Any]:
        return self._submit(
            "reset_session",
            {
                "bookmaker": bookmaker,
                "reopen_home": reopen_home,
            },
        )

    def close_session(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        return self._submit(
            "close_session",
            {"bookmaker": bookmaker},
        )

    def health(self) -> dict[str, Any]:
        return self._submit(
            "health",
            {},
            timeout=10.0,
        )

    # -----------------------------------------------------
    # Worker
    # -----------------------------------------------------

    def _run(self) -> None:
        try:
            self.browser_manager = SharedBrowserManager()
            self._started.set()

            while True:
                command = self._commands.get()

                if command is None:
                    break

                try:
                    handler = self._handler(command.name)
                    result = handler(**command.payload)
                except Exception as exc:
                    command.future.set_exception(exc)
                else:
                    command.future.set_result(result)

        finally:
            try:
                self.manager.clear(
                    reason="Pulse execution service stopped."
                )
            except Exception:
                pass

            try:
                if self.browser_manager is not None:
                    self.browser_manager.stop()
            except Exception:
                pass

            self._stopped.set()

    def _handler(
        self,
        name: str,
    ) -> Callable[..., dict[str, Any]]:
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "open_session": self._open_session,
            "login_check": self._login_check,
            "prepare_leg": self._prepare_leg,
            "reset_session": self._reset_session,
            "close_session": self._close_session,
            "health": self._health,
        }

        try:
            return handlers[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown execution command: {name!r}."
            ) from exc

    # -----------------------------------------------------
    # Worker command implementations
    # -----------------------------------------------------

    def _open_session(
        self,
        bookmaker: str,
        headless: bool,
        replace: bool,
    ) -> dict[str, Any]:
        if self.browser_manager is None:
            raise RuntimeError(
                "Execution browser manager is unavailable."
            )

        if self.manager.contains(bookmaker) and not replace:
            session = self.manager.get(bookmaker)
            return {
                "successful": True,
                "created": False,
                "message": (
                    f"{session.display_name} execution session already exists."
                ),
                "session": session.health_dict(),
            }

        page = self.browser_manager.new_page(
            headless=headless
        )
        browser = BrowserPage(page)

        config = ExecutionSessionConfig(
            auto_open_home=True,
            auto_login_check=False,
        )

        session = self.manager.add_session(
            bookmaker,
            browser=browser,
            config=config,
            replace=replace,
        )

        return {
            "successful": True,
            "created": True,
            "message": (
                f"{session.display_name} opened. "
                "Log in manually in the bookmaker window."
            ),
            "session": session.health_dict(),
        }

    def _login_check(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        session = self.manager.get(bookmaker)
        result = session.check_login()

        return {
            "successful": result.successful,
            "message": result.message,
            "result": result.to_dict(),
            "session": session.health_dict(),
        }

    def _prepare_leg(
        self,
        leg: ExecutionLeg,
    ) -> dict[str, Any]:
        if not self.manager.contains(leg.bookmaker):
            self._open_session(
                bookmaker=leg.bookmaker,
                headless=False,
                replace=False,
            )

        result = self.manager.prepare_leg(leg)

        return {
            "successful": result.successful,
            "ready_for_manual_confirmation": (
                result.ready_for_manual_confirmation
            ),
            "message": result.message,
            "result": result.to_dict(),
            "session": self.manager.get(
                leg.bookmaker
            ).health_dict(),
        }

    def _reset_session(
        self,
        bookmaker: str,
        reopen_home: bool,
    ) -> dict[str, Any]:
        session = self.manager.get(bookmaker)
        health = session.reset(
            reopen_home=reopen_home
        )

        return {
            "successful": not health.browser_closed,
            "message": f"{session.display_name} session reset.",
            "session": health.to_dict(),
        }

    def _close_session(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        session = self.manager.remove_session(
            bookmaker,
            reason="Closed through execution API.",
        )

        try:
            if (
                self.browser_manager is not None
                and not session.browser.is_closed
            ):
                self.browser_manager.close_page(
                    session.browser.page
                )
        except Exception:
            pass

        return {
            "successful": True,
            "message": f"{session.display_name} session closed.",
        }

    def _health(self) -> dict[str, Any]:
        return {
            "successful": True,
            "service_running": self.running,
            "manager": self.manager.health(),
        }

    # -----------------------------------------------------
    # Submission
    # -----------------------------------------------------

    def _submit(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        if not self.running:
            self.start()

        future: Future = Future()

        self._commands.put(
            ExecutionCommand(
                name=name,
                payload=payload,
                future=future,
            )
        )

        return future.result(timeout=timeout)


execution_service = ExecutionService()