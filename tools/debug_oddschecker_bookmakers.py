from __future__ import annotations

import json
from pathlib import Path

from app.browser_manager import get_browser_manager
from collectors.live_oddschecker import (
    accept_cookies,
    wait_for_oddschecker_access,
)


LIVE_MARKET_DIR = Path(
    "data/horses/live_market"
)


def load_latest_race_url() -> str:
    files = sorted(
        LIVE_MARKET_DIR.glob("*.jsonl"),
        reverse=True,
    )

    for file_path in files:
        lines = file_path.read_text(
            encoding="utf-8"
        ).splitlines()

        for line in reversed(lines):
            if not line.strip():
                continue

            try:
                snapshot = json.loads(
                    line
                )
            except json.JSONDecodeError:
                continue

            url = snapshot.get(
                "url"
            )

            if url:
                return str(url)

    raise RuntimeError(
        "No saved Oddschecker race URL found."
    )


def main():
    url = load_latest_race_url()

    browser_manager = get_browser_manager()

    page = browser_manager.new_page(
        headless=False
    )

    try:
        print("=" * 80)
        print("ODDSCHECKER BOOKMAKER DOM INSPECTOR")
        print("=" * 80)
        print(f"URL: {url}")

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        if not wait_for_oddschecker_access(
            page,
            timeout_seconds=180,
        ):
            raise RuntimeError(
                "Oddschecker access verification failed."
            )

        accept_cookies(
            page
        )

        page.wait_for_timeout(
            3000
        )

        candidates = page.evaluate(
            """
            () => {
                const results = [];
                const seen = new Set();

                const selectors = [
                    "img[alt]",
                    "img[title]",
                    "[aria-label]",
                    "[data-bookmaker]",
                    "[data-bk]",
                    "[data-testid]",
                    "a[href]"
                ];

                const elements = Array.from(
                    document.querySelectorAll(
                        selectors.join(",")
                    )
                );

                for (const element of elements) {
                    const rect =
                        element.getBoundingClientRect();

                    if (
                        rect.width === 0 ||
                        rect.height === 0
                    ) {
                        continue;
                    }

                    const record = {
                        tag:
                            element.tagName || "",
                        text:
                            (
                                element.innerText ||
                                element.textContent ||
                                ""
                            ).trim(),
                        alt:
                            element.getAttribute(
                                "alt"
                            ) || "",
                        title:
                            element.getAttribute(
                                "title"
                            ) || "",
                        ariaLabel:
                            element.getAttribute(
                                "aria-label"
                            ) || "",
                        dataBookmaker:
                            element.getAttribute(
                                "data-bookmaker"
                            ) || "",
                        dataBk:
                            element.getAttribute(
                                "data-bk"
                            ) || "",
                        dataTestId:
                            element.getAttribute(
                                "data-testid"
                            ) || "",
                        href:
                            element.href || "",
                        className:
                            typeof element.className === "string"
                                ? element.className
                                : "",
                        x:
                            Math.round(rect.x),
                        y:
                            Math.round(rect.y),
                        width:
                            Math.round(rect.width),
                        height:
                            Math.round(rect.height)
                    };

                    const combined = [
                        record.text,
                        record.alt,
                        record.title,
                        record.ariaLabel,
                        record.dataBookmaker,
                        record.dataBk,
                        record.dataTestId,
                        record.href,
                        record.className
                    ]
                        .join(" ")
                        .toLowerCase();

                    const relevant =
                        combined.includes("bet365") ||
                        combined.includes("betfair") ||
                        combined.includes("william") ||
                        combined.includes("paddy") ||
                        combined.includes("ladbrokes") ||
                        combined.includes("coral") ||
                        combined.includes("sky bet") ||
                        combined.includes("skybet") ||
                        combined.includes("unibet") ||
                        combined.includes("betvictor") ||
                        combined.includes("boylesports") ||
                        combined.includes("888") ||
                        combined.includes("betway") ||
                        combined.includes("smarkets") ||
                        combined.includes("matchbook") ||
                        combined.includes("bookmaker") ||
                        combined.includes("odds-grid") ||
                        combined.includes("oddsgrid");

                    if (!relevant) {
                        continue;
                    }

                    const key = JSON.stringify(
                        record
                    );

                    if (seen.has(key)) {
                        continue;
                    }

                    seen.add(key);
                    results.push(record);
                }

                results.sort(
                    (left, right) =>
                        left.y - right.y ||
                        left.x - right.x
                );

                return results;
            }
            """
        )

        print()
        print(
            f"Relevant DOM candidates: "
            f"{len(candidates)}"
        )
        print("=" * 80)

        for index, candidate in enumerate(
            candidates,
            start=1,
        ):
            print()
            print(
                f"CANDIDATE {index}"
            )
            print(
                json.dumps(
                    candidate,
                    indent=2,
                    ensure_ascii=False,
                )
            )

    finally:
        browser_manager.close_page(
            page
        )


if __name__ == "__main__":
    main()