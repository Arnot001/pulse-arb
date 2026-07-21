from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Iterable

from playwright.sync_api import (
    Frame,
    Locator,
    Page,
)

from app.browser.models import (
    ElementBounds,
    VisibleElement,
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------


@dataclass(slots=True)
class DOMExplorerConfig:
    """
    Controls how DOMExplorer scans a page.
    """

    include_iframes: bool = True
    include_elements_without_text: bool = False
    include_inputs: bool = True
    include_offscreen: bool = False
    include_disabled: bool = True

    max_elements: int = 2_000
    max_text_length: int = 500

    minimum_width: float = 1.0
    minimum_height: float = 1.0

    viewport_margin: float = 200.0

    scan_selector: str = (
        "a, button, input, textarea, select, option, "
        "[role], [onclick], [tabindex], label, "
        "span, div, li, td, th, p, h1, h2, h3, h4, h5, h6"
    )


# ---------------------------------------------------------
# Raw extraction model
# ---------------------------------------------------------


@dataclass(slots=True)
class RawDOMElement:
    """
    Internal representation returned by browser-side JavaScript.
    """

    index: int

    text: str
    tag_name: str

    role: str | None
    visible: bool
    enabled: bool
    clickable: bool

    x: float | None
    y: float | None
    width: float | None
    height: float | None

    href: str | None
    title: str | None
    aria_label: str | None
    placeholder: str | None
    test_id: str | None

    css_classes: tuple[str, ...]

    attributes: dict[str, str]

    frame_url: str | None = None
    frame_name: str | None = None


# ---------------------------------------------------------
# DOM Explorer
# ---------------------------------------------------------


class DOMExplorer:
    """
    Converts a live Playwright page into normalised VisibleElement
    objects for the Pulse Browser Intelligence layer.

    DOMExplorer does not decide which element is the best match.
    It only inspects, normalises and describes the page.

    BrowserFinder is responsible for scoring those elements later.
    """

    CLICKABLE_TAGS = {
        "a",
        "button",
        "input",
        "select",
        "textarea",
        "option",
        "summary",
        "label",
    }

    CLICKABLE_ROLES = {
        "button",
        "link",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "radio",
        "checkbox",
        "switch",
        "tab",
        "treeitem",
        "combobox",
        "textbox",
        "searchbox",
    }

    INTERACTIVE_INPUT_TYPES = {
        "button",
        "submit",
        "reset",
        "checkbox",
        "radio",
        "file",
        "image",
        "range",
        "color",
        "date",
        "datetime-local",
        "email",
        "month",
        "number",
        "password",
        "search",
        "tel",
        "text",
        "time",
        "url",
        "week",
    }

    def __init__(
        self,
        page: Page,
        config: DOMExplorerConfig | None = None,
    ) -> None:
        self.page = page

        self.config = (
            config
            or DOMExplorerConfig()
        )

        self._last_scan_duration_ms: float = 0.0
        self._last_scan_count: int = 0
        self._last_error: str | None = None

    # -----------------------------------------------------
    # Public API
    # -----------------------------------------------------

    @property
    def last_scan_duration_ms(
        self,
    ) -> float:
        return self._last_scan_duration_ms

    @property
    def last_scan_count(
        self,
    ) -> int:
        return self._last_scan_count

    @property
    def last_error(
        self,
    ) -> str | None:
        return self._last_error

    def visible_elements(
        self,
        refresh: bool = True,
    ) -> list[VisibleElement]:
        """
        Scan the main page and optional child frames.

        The refresh argument is retained for the future cache layer.
        DOMExplorer currently performs a fresh scan each time.
        """

        del refresh

        started = perf_counter()

        self._last_error = None

        elements: list[VisibleElement] = []

        try:
            elements.extend(
                self._scan_frame(
                    frame=self.page.main_frame,
                    frame_name="main",
                )
            )

            if self.config.include_iframes:
                for frame in self.page.frames:
                    if frame == self.page.main_frame:
                        continue

                    try:
                        elements.extend(
                            self._scan_frame(
                                frame=frame,
                                frame_name=(
                                    frame.name
                                    or "iframe"
                                ),
                            )
                        )
                    except Exception:
                        continue

            elements = self._deduplicate(
                elements
            )

            if len(elements) > self.config.max_elements:
                elements = elements[
                    :self.config.max_elements
                ]

            self._last_scan_count = len(
                elements
            )

            return elements

        except Exception as exc:
            self._last_error = str(
                exc
            )

            return []

        finally:
            self._last_scan_duration_ms = (
                perf_counter() - started
            ) * 1_000

    def clickable_elements(
        self,
    ) -> list[VisibleElement]:
        return [
            element
            for element in self.visible_elements()
            if element.clickable
        ]

    def text_elements(
        self,
    ) -> list[VisibleElement]:
        return [
            element
            for element in self.visible_elements()
            if element.has_text
        ]

    def inputs(
        self,
    ) -> list[VisibleElement]:
        input_tags = {
            "input",
            "textarea",
            "select",
        }

        return [
            element
            for element in self.visible_elements()
            if element.tag_name in input_tags
            or element.role in {
                "textbox",
                "searchbox",
                "combobox",
            }
        ]

    def page_text(
        self,
        maximum_length: int | None = None,
    ) -> str:
        try:
            text = (
                self.page.locator("body")
                .inner_text(timeout=5_000)
            )
        except Exception:
            return ""

        cleaned = self._clean_text(
            text
        )

        if (
            maximum_length is not None
            and maximum_length >= 0
        ):
            return cleaned[
                :maximum_length
            ]

        return cleaned

    def page_contains_text(
        self,
        text: str,
        case_sensitive: bool = False,
    ) -> bool:
        query = self._clean_text(
            text
        )

        if not query:
            return False

        body = self.page_text()

        if case_sensitive:
            return query in body

        return (
            query.casefold()
            in body.casefold()
        )

    def inspect_locator(
        self,
        locator: Locator,
        metadata: dict[str, Any] | None = None,
    ) -> VisibleElement | None:
        """
        Inspect one existing locator and return the same normalised
        model used by full-page scans.
        """

        try:
            if locator.count() < 1:
                return None

            target = locator.first

            visible = target.is_visible()

            if (
                not visible
                and not self.config.include_offscreen
            ):
                return None

            box = target.bounding_box()

            bounds = self._bounds_from_box(
                box
            )

            if (
                bounds is None
                and not self.config.include_offscreen
            ):
                return None

            text = self._locator_text(
                target
            )

            tag_name = self._safe_evaluate(
                target,
                "(element) => element.tagName.toLowerCase()",
                "",
            )

            role = self._safe_attribute(
                target,
                "role",
            )

            enabled = self._locator_enabled(
                target
            )

            attributes = self._selected_attributes(
                target
            )

            clickable = self._is_locator_clickable(
                locator=target,
                tag_name=tag_name,
                role=role,
                attributes=attributes,
            )

            return VisibleElement(
                locator=target,
                text=text,
                tag_name=tag_name,
                role=role,
                visible=visible,
                enabled=enabled,
                clickable=clickable,
                bounds=bounds,
                href=attributes.get(
                    "href"
                ),
                title=attributes.get(
                    "title"
                ),
                aria_label=attributes.get(
                    "aria-label"
                ),
                placeholder=attributes.get(
                    "placeholder"
                ),
                test_id=(
                    attributes.get(
                        "data-testid"
                    )
                    or attributes.get(
                        "data-test-id"
                    )
                    or attributes.get(
                        "data-test"
                    )
                ),
                css_classes=self._class_tuple(
                    attributes.get(
                        "class"
                    )
                ),
                attributes=attributes,
                metadata=dict(
                    metadata or {}
                ),
            )

        except Exception:
            return None

    def nearest_clickable_ancestor(
        self,
        locator: Locator,
        maximum_depth: int = 8,
    ) -> VisibleElement | None:
        """
        Walk upwards from a text element until a clickable ancestor
        is found.
        """

        try:
            target = locator.first

            for depth in range(
                maximum_depth + 1
            ):
                candidate = (
                    target
                    if depth == 0
                    else target.locator(
                        "/.."
                    )
                )

                inspected = self.inspect_locator(
                    candidate,
                    metadata={
                        "ancestor_depth": depth,
                    },
                )

                if (
                    inspected is not None
                    and inspected.clickable
                ):
                    return inspected

                target = candidate

        except Exception:
            return None

        return None

    def summary(
        self,
    ) -> dict[str, Any]:
        elements = self.visible_elements()

        return {
            "url": self._page_url(),
            "title": self._page_title(),
            "total_elements": len(
                elements
            ),
            "text_elements": sum(
                element.has_text
                for element in elements
            ),
            "clickable_elements": sum(
                element.clickable
                for element in elements
            ),
            "input_elements": sum(
                element.tag_name
                in {
                    "input",
                    "textarea",
                    "select",
                }
                for element in elements
            ),
            "scan_duration_ms": (
                self.last_scan_duration_ms
            ),
            "last_error": self.last_error,
        }

    # -----------------------------------------------------
    # Frame scanning
    # -----------------------------------------------------

    def _scan_frame(
        self,
        frame: Frame,
        frame_name: str,
    ) -> list[VisibleElement]:
        raw_elements = self._extract_raw_elements(
            frame
        )

        results: list[VisibleElement] = []

        frame_locator = frame.locator(
            self.config.scan_selector
        )

        for raw in raw_elements:
            if len(results) >= self.config.max_elements:
                break

            try:
                locator = frame_locator.nth(
                    raw.index
                )

                element = self._build_visible_element(
                    locator=locator,
                    raw=raw,
                    frame_name=frame_name,
                )

                if element is None:
                    continue

                results.append(
                    element
                )

            except Exception:
                continue

        return results

    def _extract_raw_elements(
        self,
        frame: Frame,
    ) -> list[RawDOMElement]:
        javascript = """
        ({ selector, includeOffscreen, viewportMargin, maxTextLength }) => {
            const elements = Array.from(
                document.querySelectorAll(selector)
            );

            const viewportWidth =
                window.innerWidth ||
                document.documentElement.clientWidth ||
                0;

            const viewportHeight =
                window.innerHeight ||
                document.documentElement.clientHeight ||
                0;

            function cleanText(value) {
                return String(value || "")
                    .replace(/\\s+/g, " ")
                    .trim()
                    .slice(0, maxTextLength);
            }

            function getAttributes(element) {
                const names = [
                    "id",
                    "class",
                    "href",
                    "title",
                    "role",
                    "aria-label",
                    "aria-labelledby",
                    "aria-describedby",
                    "placeholder",
                    "name",
                    "type",
                    "value",
                    "tabindex",
                    "disabled",
                    "data-testid",
                    "data-test-id",
                    "data-test",
                    "data-qa",
                    "data-automation-id"
                ];

                const result = {};

                for (const name of names) {
                    const value = element.getAttribute(name);

                    if (value !== null) {
                        result[name] = String(value);
                    }
                }

                return result;
            }

            function isVisible(element, rect, style) {
                if (!rect) {
                    return false;
                }

                if (
                    rect.width <= 0 ||
                    rect.height <= 0
                ) {
                    return false;
                }

                if (
                    style.display === "none" ||
                    style.visibility === "hidden" ||
                    style.visibility === "collapse" ||
                    Number(style.opacity || "1") === 0
                ) {
                    return false;
                }

                if (
                    element.hidden ||
                    element.getAttribute("aria-hidden") === "true"
                ) {
                    return false;
                }

                if (!includeOffscreen) {
                    const outsideViewport =
                        rect.bottom < -viewportMargin ||
                        rect.right < -viewportMargin ||
                        rect.top > viewportHeight + viewportMargin ||
                        rect.left > viewportWidth + viewportMargin;

                    if (outsideViewport) {
                        return false;
                    }
                }

                return true;
            }

            function isEnabled(element) {
                if (element.disabled === true) {
                    return false;
                }

                if (
                    element.getAttribute("disabled") !== null ||
                    element.getAttribute("aria-disabled") === "true"
                ) {
                    return false;
                }

                return true;
            }

            function isClickable(element, style, attributes) {
                const tag = element.tagName.toLowerCase();
                const role = String(
                    attributes.role || ""
                ).toLowerCase();

                const clickableTags = new Set([
                    "a",
                    "button",
                    "input",
                    "select",
                    "textarea",
                    "option",
                    "summary",
                    "label"
                ]);

                const clickableRoles = new Set([
                    "button",
                    "link",
                    "menuitem",
                    "menuitemcheckbox",
                    "menuitemradio",
                    "option",
                    "radio",
                    "checkbox",
                    "switch",
                    "tab",
                    "treeitem",
                    "combobox",
                    "textbox",
                    "searchbox"
                ]);

                if (clickableTags.has(tag)) {
                    return true;
                }

                if (clickableRoles.has(role)) {
                    return true;
                }

                if (
                    element.onclick ||
                    attributes.onclick !== undefined
                ) {
                    return true;
                }

                if (
                    attributes.tabindex !== undefined &&
                    attributes.tabindex !== "-1"
                ) {
                    return true;
                }

                if (
                    style.cursor === "pointer"
                ) {
                    return true;
                }

                return false;
            }

            return elements.map((element, index) => {
                const rect =
                    element.getBoundingClientRect();

                const style =
                    window.getComputedStyle(element);

                const attributes =
                    getAttributes(element);

                let text =
                    cleanText(element.innerText);

                if (!text) {
                    text = cleanText(
                        attributes["aria-label"] ||
                        attributes.title ||
                        attributes.placeholder ||
                        attributes.value
                    );
                }

                return {
                    index,
                    text,
                    tagName:
                        element.tagName.toLowerCase(),
                    role:
                        attributes.role || null,
                    visible:
                        isVisible(element, rect, style),
                    enabled:
                        isEnabled(element),
                    clickable:
                        isClickable(
                            element,
                            style,
                            attributes
                        ),
                    x:
                        Number.isFinite(rect.x)
                            ? rect.x
                            : null,
                    y:
                        Number.isFinite(rect.y)
                            ? rect.y
                            : null,
                    width:
                        Number.isFinite(rect.width)
                            ? rect.width
                            : null,
                    height:
                        Number.isFinite(rect.height)
                            ? rect.height
                            : null,
                    href:
                        attributes.href || null,
                    title:
                        attributes.title || null,
                    ariaLabel:
                        attributes["aria-label"] || null,
                    placeholder:
                        attributes.placeholder || null,
                    testId:
                        attributes["data-testid"] ||
                        attributes["data-test-id"] ||
                        attributes["data-test"] ||
                        null,
                    cssClasses:
                        String(
                            attributes.class || ""
                        )
                        .split(/\\s+/)
                        .filter(Boolean),
                    attributes
                };
            });
        }
        """

        payload = frame.evaluate(
            javascript,
            {
                "selector": (
                    self.config.scan_selector
                ),
                "includeOffscreen": (
                    self.config.include_offscreen
                ),
                "viewportMargin": (
                    self.config.viewport_margin
                ),
                "maxTextLength": (
                    self.config.max_text_length
                ),
            },
        )

        frame_url = self._frame_url(
            frame
        )
        frame_name = (
            frame.name
            or None
        )

        results: list[RawDOMElement] = []

        for item in payload or []:
            try:
                raw = RawDOMElement(
                    index=int(
                        item.get(
                            "index",
                            0,
                        )
                    ),
                    text=self._clean_text(
                        item.get(
                            "text"
                        )
                    ),
                    tag_name=str(
                        item.get(
                            "tagName",
                            "",
                        )
                    ).lower(),
                    role=self._optional_text(
                        item.get(
                            "role"
                        )
                    ),
                    visible=bool(
                        item.get(
                            "visible",
                            False,
                        )
                    ),
                    enabled=bool(
                        item.get(
                            "enabled",
                            True,
                        )
                    ),
                    clickable=bool(
                        item.get(
                            "clickable",
                            False,
                        )
                    ),
                    x=self._optional_float(
                        item.get(
                            "x"
                        )
                    ),
                    y=self._optional_float(
                        item.get(
                            "y"
                        )
                    ),
                    width=self._optional_float(
                        item.get(
                            "width"
                        )
                    ),
                    height=self._optional_float(
                        item.get(
                            "height"
                        )
                    ),
                    href=self._optional_text(
                        item.get(
                            "href"
                        )
                    ),
                    title=self._optional_text(
                        item.get(
                            "title"
                        )
                    ),
                    aria_label=self._optional_text(
                        item.get(
                            "ariaLabel"
                        )
                    ),
                    placeholder=self._optional_text(
                        item.get(
                            "placeholder"
                        )
                    ),
                    test_id=self._optional_text(
                        item.get(
                            "testId"
                        )
                    ),
                    css_classes=tuple(
                        str(value)
                        for value in (
                            item.get(
                                "cssClasses"
                            )
                            or []
                        )
                        if value
                    ),
                    attributes={
                        str(key): str(value)
                        for key, value in (
                            item.get(
                                "attributes"
                            )
                            or {}
                        ).items()
                    },
                    frame_url=frame_url,
                    frame_name=frame_name,
                )

                if self._raw_element_allowed(
                    raw
                ):
                    results.append(
                        raw
                    )

            except Exception:
                continue

        return results

    # -----------------------------------------------------
    # Element construction
    # -----------------------------------------------------

    def _build_visible_element(
        self,
        locator: Locator,
        raw: RawDOMElement,
        frame_name: str,
    ) -> VisibleElement | None:
        bounds = self._bounds_from_raw(
            raw
        )

        if (
            bounds is None
            and not self.config.include_offscreen
        ):
            return None

        return VisibleElement(
            locator=locator,
            text=raw.text,
            tag_name=raw.tag_name,
            role=raw.role,
            visible=raw.visible,
            enabled=raw.enabled,
            clickable=raw.clickable,
            bounds=bounds,
            href=raw.href,
            title=raw.title,
            aria_label=raw.aria_label,
            placeholder=raw.placeholder,
            test_id=raw.test_id,
            css_classes=raw.css_classes,
            attributes=dict(
                raw.attributes
            ),
            metadata={
                "frame_url": raw.frame_url,
                "frame_name": (
                    raw.frame_name
                    or frame_name
                ),
                "dom_index": raw.index,
            },
        )

    def _raw_element_allowed(
        self,
        raw: RawDOMElement,
    ) -> bool:
        if (
            not raw.visible
            and not self.config.include_offscreen
        ):
            return False

        if (
            not raw.enabled
            and not self.config.include_disabled
        ):
            return False

        if (
            raw.width is not None
            and raw.width
            < self.config.minimum_width
        ):
            return False

        if (
            raw.height is not None
            and raw.height
            < self.config.minimum_height
        ):
            return False

        if (
            raw.tag_name
            in {
                "input",
                "textarea",
                "select",
            }
            and not self.config.include_inputs
        ):
            return False

        if (
            not self.config.include_elements_without_text
            and not self._raw_has_searchable_text(
                raw
            )
        ):
            return False

        return True

    def _raw_has_searchable_text(
        self,
        raw: RawDOMElement,
    ) -> bool:
        return any(
            (
                raw.text,
                raw.aria_label,
                raw.title,
                raw.placeholder,
            )
        )

    # -----------------------------------------------------
    # Locator inspection helpers
    # -----------------------------------------------------

    def _locator_text(
        self,
        locator: Locator,
    ) -> str:
        for getter in (
            lambda: locator.inner_text(
                timeout=1_500
            ),
            lambda: locator.text_content(
                timeout=1_500
            ),
            lambda: locator.get_attribute(
                "aria-label"
            ),
            lambda: locator.get_attribute(
                "title"
            ),
            lambda: locator.get_attribute(
                "placeholder"
            ),
            lambda: locator.get_attribute(
                "value"
            ),
        ):
            try:
                value = getter()

                cleaned = self._clean_text(
                    value
                )

                if cleaned:
                    return cleaned[
                        :self.config.max_text_length
                    ]

            except Exception:
                continue

        return ""

    def _locator_enabled(
        self,
        locator: Locator,
    ) -> bool:
        try:
            return locator.is_enabled()
        except Exception:
            pass

        disabled = self._safe_attribute(
            locator,
            "disabled",
        )

        aria_disabled = self._safe_attribute(
            locator,
            "aria-disabled",
        )

        return (
            disabled is None
            and aria_disabled != "true"
        )

    def _is_locator_clickable(
        self,
        locator: Locator,
        tag_name: str,
        role: str | None,
        attributes: dict[str, str],
    ) -> bool:
        if tag_name in self.CLICKABLE_TAGS:
            if tag_name == "input":
                input_type = (
                    attributes.get(
                        "type",
                        "text",
                    )
                    .strip()
                    .lower()
                )

                return (
                    input_type
                    in self.INTERACTIVE_INPUT_TYPES
                )

            return True

        if (
            role
            and role.lower()
            in self.CLICKABLE_ROLES
        ):
            return True

        if (
            "onclick"
            in attributes
        ):
            return True

        tabindex = attributes.get(
            "tabindex"
        )

        if (
            tabindex is not None
            and tabindex != "-1"
        ):
            return True

        cursor = self._safe_evaluate(
            locator,
            (
                "(element) => "
                "window.getComputedStyle(element).cursor"
            ),
            "",
        )

        return cursor == "pointer"

    def _selected_attributes(
        self,
        locator: Locator,
    ) -> dict[str, str]:
        names = (
            "id",
            "class",
            "href",
            "title",
            "role",
            "aria-label",
            "aria-labelledby",
            "aria-describedby",
            "placeholder",
            "name",
            "type",
            "value",
            "tabindex",
            "disabled",
            "data-testid",
            "data-test-id",
            "data-test",
            "data-qa",
            "data-automation-id",
        )

        values: dict[str, str] = {}

        for name in names:
            value = self._safe_attribute(
                locator,
                name,
            )

            if value is not None:
                values[name] = value

        return values

    # -----------------------------------------------------
    # Geometry helpers
    # -----------------------------------------------------

    def _bounds_from_raw(
        self,
        raw: RawDOMElement,
    ) -> ElementBounds | None:
        if None in {
            raw.x,
            raw.y,
            raw.width,
            raw.height,
        }:
            return None

        return ElementBounds(
            x=float(
                raw.x
            ),
            y=float(
                raw.y
            ),
            width=float(
                raw.width
            ),
            height=float(
                raw.height
            ),
        )

    def _bounds_from_box(
        self,
        box: dict[str, float] | None,
    ) -> ElementBounds | None:
        if not box:
            return None

        try:
            return ElementBounds(
                x=float(
                    box.get(
                        "x",
                        0.0,
                    )
                ),
                y=float(
                    box.get(
                        "y",
                        0.0,
                    )
                ),
                width=float(
                    box.get(
                        "width",
                        0.0,
                    )
                ),
                height=float(
                    box.get(
                        "height",
                        0.0,
                    )
                ),
            )

        except Exception:
            return None

    # -----------------------------------------------------
    # Deduplication
    # -----------------------------------------------------

    def _deduplicate(
        self,
        elements: Iterable[VisibleElement],
    ) -> list[VisibleElement]:
        unique: list[VisibleElement] = []

        seen: set[
            tuple[Any, ...]
        ] = set()

        for element in elements:
            bounds = element.bounds

            key = (
                element.metadata.get(
                    "frame_url"
                ),
                element.tag_name,
                element.searchable_text.casefold(),
                round(
                    bounds.x,
                    1,
                )
                if bounds
                else None,
                round(
                    bounds.y,
                    1,
                )
                if bounds
                else None,
                round(
                    bounds.width,
                    1,
                )
                if bounds
                else None,
                round(
                    bounds.height,
                    1,
                )
                if bounds
                else None,
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            unique.append(
                element
            )

        return unique

    # -----------------------------------------------------
    # Safe utility helpers
    # -----------------------------------------------------

    def _page_url(
        self,
    ) -> str | None:
        try:
            return self.page.url
        except Exception:
            return None

    def _page_title(
        self,
    ) -> str | None:
        try:
            return self.page.title()
        except Exception:
            return None

    @staticmethod
    def _frame_url(
        frame: Frame,
    ) -> str | None:
        try:
            return frame.url
        except Exception:
            return None

    @staticmethod
    def _safe_attribute(
        locator: Locator,
        name: str,
    ) -> str | None:
        try:
            value = locator.get_attribute(
                name
            )

            if value is None:
                return None

            cleaned = str(
                value
            ).strip()

            return (
                cleaned
                if cleaned
                else None
            )

        except Exception:
            return None

    @staticmethod
    def _safe_evaluate(
        locator: Locator,
        expression: str,
        default: Any = None,
    ) -> Any:
        try:
            return locator.evaluate(
                expression
            )
        except Exception:
            return default

    @staticmethod
    def _clean_text(
        value: Any,
    ) -> str:
        if value is None:
            return ""

        return " ".join(
            str(
                value
            ).split()
        ).strip()

    @staticmethod
    def _optional_text(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        cleaned = str(
            value
        ).strip()

        return (
            cleaned
            if cleaned
            else None
        )

    @staticmethod
    def _optional_float(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            return float(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _class_tuple(
        value: str | None,
    ) -> tuple[str, ...]:
        if not value:
            return ()

        return tuple(
            item
            for item in value.split()
            if item
        )