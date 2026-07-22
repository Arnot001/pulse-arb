from __future__ import annotations

import asyncio
import os
import queue
import threading
from concurrent.futures import Future
from typing import Any, Callable


Command = tuple[
    Callable[..., Any] | None,
    tuple[Any, ...],
    dict[str, Any],
    Future[Any] | None,
]


class ExecutionBrowserWorker:
    """
    Owns one dedicated thread for all Execution Centre browser work.

    Synchronous Playwright objects must be created and used on the same
    thread. FastAPI routes therefore submit browser commands to this worker.
    """

    def __init__(self):
        self._commands: queue.Queue[Command] = queue.Queue()

        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

        self._running = threading.Event()
        self._startup_complete = threading.Event()

        self._startup_error: BaseException | None = None

    @property
    def is_running(self) -> bool:
        return bool(
            self._thread
            and self._thread.is_alive()
            and self._running.is_set()
        )

    def start(self) -> None:
        with self._start_lock:
            if self.is_running:
                return

            self._running.clear()
            self._startup_complete.clear()
            self._startup_error = None

            self._thread = threading.Thread(
                target=self._run,
                name="pulse-execution-browser",
                daemon=True,
            )

            self._thread.start()

            if not self._startup_complete.wait(timeout=10):
                raise RuntimeError(
                    "Execution browser worker startup timed out."
                )

            if self._startup_error is not None:
                startup_error = self._startup_error
                self._startup_error = None

                raise RuntimeError(
                    "Execution browser worker failed to start."
                ) from startup_error

            if not self.is_running:
                raise RuntimeError(
                    "Execution browser worker stopped during startup."
                )

    def submit(
        self,
        function: Callable[..., Any],
        *args: Any,
        timeout: float = 60,
        **kwargs: Any,
    ) -> Any:
        self.start()

        if (
            self._thread
            and threading.current_thread() is self._thread
        ):
            return function(
                *args,
                **kwargs,
            )

        future: Future[Any] = Future()

        self._commands.put(
            (
                function,
                args,
                kwargs,
                future,
            )
        )

        return future.result(
            timeout=timeout
        )

    def stop(self) -> None:
        thread = self._thread

        if not thread:
            return

        if not thread.is_alive():
            self._thread = None
            self._running.clear()
            return

        self._commands.put(
            (
                None,
                (),
                {},
                None,
            )
        )

        if threading.current_thread() is not thread:
            thread.join(
                timeout=15
            )

        self._thread = None
        self._running.clear()

    @staticmethod
    def _configure_windows_event_loop() -> None:
        if os.name != "nt":
            return

        policy_class = getattr(
            asyncio,
            "WindowsProactorEventLoopPolicy",
            None,
        )

        if policy_class is None:
            return

        current_policy = asyncio.get_event_loop_policy()

        if not isinstance(
            current_policy,
            policy_class,
        ):
            asyncio.set_event_loop_policy(
                policy_class()
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    def _run(self) -> None:
        try:
            self._configure_windows_event_loop()

            self._running.set()
            self._startup_complete.set()

            while True:
                (
                    function,
                    args,
                    kwargs,
                    future,
                ) = self._commands.get()

                if function is None:
                    break

                if future is None:
                    continue

                if future.cancelled():
                    continue

                try:
                    result = function(
                        *args,
                        **kwargs,
                    )

                except BaseException as exc:
                    if not future.done():
                        future.set_exception(
                            exc
                        )

                else:
                    if not future.done():
                        future.set_result(
                            result
                        )

        except BaseException as exc:
            self._startup_error = exc

            if not self._startup_complete.is_set():
                self._startup_complete.set()

        finally:
            self._running.clear()

            try:
                loop = asyncio.get_event_loop()

                if not loop.is_closed():
                    loop.close()

            except Exception:
                pass


execution_browser_worker = ExecutionBrowserWorker()