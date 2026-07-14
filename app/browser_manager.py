import atexit
import os
import threading
from typing import Optional

from dotenv import load_dotenv
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)


load_dotenv()


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class SharedBrowserManager:
    """
    Owns one shared synchronous Playwright instance, Chromium browser,
    and browser context.

    Collectors request pages from this manager instead of launching
    separate browser instances.
    """

    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

        self._headless: Optional[bool] = None
        self._lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        return (
            self.playwright is not None
            and self.browser is not None
            and self.context is not None
            and self.browser.is_connected()
        )

    def _resolve_headless(
        self,
        override: Optional[bool] = None,
    ) -> bool:
        if override is not None:
            return override

        debug_browser = env_flag(
            "DEBUG_BROWSER",
            default=False,
        )

        if debug_browser:
            return False

        return env_flag(
            "HEADLESS",
            default=True,
        )

    def start(
        self,
        headless: Optional[bool] = None,
    ) -> "SharedBrowserManager":
        with self._lock:
            if self.is_running:
                return self

            resolved_headless = self._resolve_headless(
                headless
            )

            self.playwright = sync_playwright().start()

            try:
                self.browser = self.playwright.chromium.launch(
                    headless=resolved_headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ],
                )

                self.context = self.browser.new_context(
                    viewport={
                        "width": 1440,
                        "height": 1000,
                    },
                    user_agent=(
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/142.0.0.0 "
                        "Safari/537.36"
                    ),
                    locale="en-GB",
                    timezone_id="Europe/London",
                )

                self._headless = resolved_headless

                print(
                    "Shared Playwright browser started "
                    f"| headless={resolved_headless}"
                )

            except Exception:
                self._cleanup_failed_start()
                raise

            return self

    def _cleanup_failed_start(self):
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass

        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass

        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass

        self.context = None
        self.browser = None
        self.playwright = None
        self._headless = None

    def new_page(
        self,
        headless: Optional[bool] = None,
    ) -> Page:
        with self._lock:
            self.start(headless=headless)

            if not self.context:
                raise RuntimeError(
                    "Shared browser context is unavailable."
                )

            return self.context.new_page()

    def close_page(
        self,
        page: Optional[Page],
    ):
        if not page:
            return

        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass

    def stop(self):
        with self._lock:
            was_running = any(
                [
                    self.context is not None,
                    self.browser is not None,
                    self.playwright is not None,
                ]
            )

            if self.context:
                try:
                    self.context.close()
                except Exception:
                    pass

            if self.browser:
                try:
                    self.browser.close()
                except Exception:
                    pass

            if self.playwright:
                try:
                    self.playwright.stop()
                except Exception:
                    pass

            self.context = None
            self.browser = None
            self.playwright = None
            self._headless = None

            if was_running:
                print(
                    "Shared Playwright browser stopped"
                )


browser_manager = SharedBrowserManager()


def get_browser_manager() -> SharedBrowserManager:
    return browser_manager


def start_shared_browser(
    headless: Optional[bool] = None,
) -> SharedBrowserManager:
    return browser_manager.start(
        headless=headless
    )


def stop_shared_browser():
    browser_manager.stop()


atexit.register(stop_shared_browser)