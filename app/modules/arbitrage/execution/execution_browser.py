from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)


EXECUTION_PROFILE_ROOT = Path(
    "data/browser_profiles/execution"
)

EXECUTION_WINDOW_WIDTH = 1280
EXECUTION_WINDOW_HEIGHT = 900

EXECUTION_WINDOW_X = 120
EXECUTION_WINDOW_Y = 60

EXECUTION_VIEWPORT_WIDTH = 1440
EXECUTION_VIEWPORT_HEIGHT = 1000


@dataclass(slots=True)
class ExecutionBrowserInstance:
    bookmaker: str
    profile_path: Path
    context: BrowserContext
    page: Page
    headless: bool
    browser_channel: str

    @property
    def is_open(self) -> bool:
        try:
            browser = self.context.browser

            if browser and not browser.is_connected():
                return False

            return not self.page.is_closed()

        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        current_url: str | None = None

        if self.is_open:
            try:
                current_url = self.page.url
            except Exception:
                pass

        return {
            "bookmaker": self.bookmaker,
            "is_open": self.is_open,
            "headless": self.headless,
            "browser_channel": self.browser_channel,
            "profile_path": str(
                self.profile_path
            ),
            "current_url": current_url,
        }


class ExecutionBrowserManager:
    """
    Owns persistent execution-only browser profiles.

    This manager is separate from the Live Engine browser manager.

    Each bookmaker receives its own profile directory. Cookies, login state,
    local storage and bookmaker preferences therefore survive Pulse restarts.
    """

    def __init__(self):
        self.playwright: Playwright | None = None

        self._instances: dict[
            str,
            ExecutionBrowserInstance,
        ] = {}

        self._lock = threading.RLock()

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

    @staticmethod
    def _profile_path(
        bookmaker: str,
    ) -> Path:
        path = (
            EXECUTION_PROFILE_ROOT
            / bookmaker
        )

        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        return path.resolve()

    @staticmethod
    def _launch_args(
        headless: bool,
    ) -> list[str]:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-popup-blocking",
            "--disable-notifications",
            "--start-maximized",
        ]

        if not headless:
            args.extend(
                [
                    (
                        "--window-size="
                        f"{EXECUTION_WINDOW_WIDTH},"
                        f"{EXECUTION_WINDOW_HEIGHT}"
                    ),
                    (
                        "--window-position="
                        f"{EXECUTION_WINDOW_X},"
                        f"{EXECUTION_WINDOW_Y}"
                    ),
                ]
            )

        return args

    def _start_playwright(self) -> None:
        if self.playwright is not None:
            return

        self.playwright = (
            sync_playwright().start()
        )

    def _launch_context(
        self,
        *,
        profile_path: Path,
        headless: bool,
    ) -> tuple[
        BrowserContext,
        str,
    ]:
        self._start_playwright()

        if self.playwright is None:
            raise RuntimeError(
                "Execution Playwright instance is unavailable."
            )

        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(
                profile_path
            ),
            "headless": headless,
            "args": self._launch_args(
                headless
            ),
            "locale": "en-GB",
            "timezone_id": "Europe/London",
            "viewport": {
                "width": EXECUTION_VIEWPORT_WIDTH,
                "height": EXECUTION_VIEWPORT_HEIGHT,
            },
            "user_agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/150.0.0.0 "
                "Safari/537.36"
            ),
            "ignore_https_errors": False,
        }

        try:
            context = (
                self.playwright
                .chromium
                .launch_persistent_context(
                    channel="chrome",
                    **launch_kwargs,
                )
            )

            return context, "chrome"

        except Exception as chrome_error:
            print(
                "Execution Chrome launch failed. "
                "Falling back to Playwright Chromium."
            )
            print(
                f"Chrome launch error: {repr(chrome_error)}"
            )

            context = (
                self.playwright
                .chromium
                .launch_persistent_context(
                    **launch_kwargs,
                )
            )

            return context, "chromium"

    @staticmethod
    def _select_page(
        context: BrowserContext,
    ) -> Page:
        for page in context.pages:
            try:
                if not page.is_closed():
                    return page
            except Exception:
                continue

        return context.new_page()

    def open_bookmaker(
        self,
        bookmaker: str,
        *,
        home_url: str,
        headless: bool = False,
        replace: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            key = self._normalise_bookmaker(
                bookmaker
            )

            existing = self._instances.get(
                key
            )

            if (
                existing
                and existing.is_open
                and not replace
            ):
                try:
                    existing.page.bring_to_front()
                except Exception:
                    pass

                return {
                    "successful": True,
                    "created": False,
                    "instance": existing,
                    "browser": existing.to_dict(),
                }

            if existing:
                self._close_instance(
                    existing
                )

                self._instances.pop(
                    key,
                    None,
                )

            profile_path = self._profile_path(
                key
            )

            context, browser_channel = (
                self._launch_context(
                    profile_path=profile_path,
                    headless=headless,
                )
            )

            page = self._select_page(
                context
            )

            instance = ExecutionBrowserInstance(
                bookmaker=key,
                profile_path=profile_path,
                context=context,
                page=page,
                headless=headless,
                browser_channel=browser_channel,
            )

            self._instances[key] = instance

            try:
                current_url = page.url
            except Exception:
                current_url = ""

            if (
                not current_url
                or current_url == "about:blank"
                or replace
            ):
                try:
                    page.goto(
                        home_url,
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )

                except Exception as exc:
                    return {
                        "successful": False,
                        "created": True,
                        "status": "HOMEPAGE_LOAD_FAILED",
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                            "repr": repr(exc),
                        },
                        "instance": instance,
                        "browser": instance.to_dict(),
                    }

            try:
                page.bring_to_front()
            except Exception:
                pass

            print(
                "Persistent execution browser opened "
                f"| bookmaker={key} "
                f"| channel={browser_channel} "
                f"| profile={profile_path}"
            )

            return {
                "successful": True,
                "created": True,
                "instance": instance,
                "browser": instance.to_dict(),
            }

    def get_instance(
        self,
        bookmaker: str,
    ) -> ExecutionBrowserInstance:
        with self._lock:
            key = self._normalise_bookmaker(
                bookmaker
            )

            instance = self._instances.get(
                key
            )

            if not instance or not instance.is_open:
                raise KeyError(
                    f"No open execution browser for {key}."
                )

            return instance

    def close_bookmaker(
        self,
        bookmaker: str,
    ) -> dict[str, Any]:
        with self._lock:
            key = self._normalise_bookmaker(
                bookmaker
            )

            instance = self._instances.pop(
                key,
                None,
            )

            if not instance:
                return {
                    "successful": True,
                    "closed": False,
                    "bookmaker": key,
                }

            self._close_instance(
                instance
            )

            return {
                "successful": True,
                "closed": True,
                "bookmaker": key,
            }

    @staticmethod
    def _close_instance(
        instance: ExecutionBrowserInstance,
    ) -> None:
        try:
            instance.context.close()
        except Exception:
            pass

    def close_all(self) -> dict[str, Any]:
        with self._lock:
            closed: list[str] = []

            for key, instance in list(
                self._instances.items()
            ):
                self._close_instance(
                    instance
                )

                closed.append(
                    key
                )

            self._instances.clear()

            if self.playwright is not None:
                try:
                    self.playwright.stop()
                except Exception:
                    pass

                self.playwright = None

            return {
                "successful": True,
                "closed": closed,
                "closed_count": len(closed),
            }

    @property
    def running_count(self) -> int:
        with self._lock:
            return sum(
                1
                for instance
                in self._instances.values()
                if instance.is_open
            )

    @property
    def is_running(self) -> bool:
        return self.running_count > 0

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self.is_running,
                "running_count": (
                    self.running_count
                ),
                "instances": {
                    key: instance.to_dict()
                    for key, instance
                    in self._instances.items()
                },
            }


execution_browser_manager = (
    ExecutionBrowserManager()
)