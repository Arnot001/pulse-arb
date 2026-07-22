from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from math import log1p
from time import perf_counter
import re
import unicodedata
from typing import Iterable, Sequence

from app.browser.dom import DOMExplorer
from app.browser.models import (
    MatchQuality,
    SearchMatch,
    SearchResult,
    VisibleElement,
)


@dataclass(slots=True)
class BrowserFinderConfig:
    """Controls BrowserFinder scoring and filtering."""

    minimum_score: float = 35.0
    maximum_results: int = 20

    exact_weight: float = 55.0
    text_weight: float = 20.0
    token_weight: float = 15.0
    fuzzy_weight: float = 10.0

    clickable_bonus: float = 8.0
    enabled_bonus: float = 3.0
    visible_bonus: float = 2.0
    preferred_role_bonus: float = 5.0
    preferred_tag_bonus: float = 3.0
    secondary_weight: float = 12.0
    proximity_weight: float = 10.0

    exact_threshold: float = 92.0
    strong_threshold: float = 74.0
    possible_threshold: float = 52.0
    weak_threshold: float = 35.0

    prefer_clickable_by_default: bool = False
    allow_disabled_by_default: bool = True
    include_elements_without_text: bool = False

    clickable_tags: tuple[str, ...] = (
        "button",
        "a",
        "input",
        "select",
        "textarea",
        "label",
        "option",
    )

    input_tags: tuple[str, ...] = (
        "input",
        "textarea",
        "select",
    )

    input_roles: tuple[str, ...] = (
        "textbox",
        "searchbox",
        "combobox",
    )


class BrowserFinder:
    """
    Intelligent ranked search over DOMExplorer VisibleElement objects.

    BrowserFinder does not click anything. It scores, filters and ranks
    candidates so BrowserClicker and bookmaker adapters can act on the
    best element.
    """

    _PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
    _WHITESPACE_RE = re.compile(r"\s+")
    _NUMBER_RE = re.compile(r"\d+(?:[.:/]\d+)*")
    _TOKEN_RE = re.compile(r"\w+", re.UNICODE)

    def __init__(
        self,
        explorer: DOMExplorer,
        config: BrowserFinderConfig | None = None,
    ) -> None:
        self.explorer = explorer
        self.config = config or BrowserFinderConfig()

    def find(
        self,
        query: str,
        *,
        secondary_query: str | None = None,
        prefer_clickable: bool | None = None,
        require_clickable: bool = False,
        require_enabled: bool = False,
        role: str | Sequence[str] | None = None,
        tag: str | Sequence[str] | None = None,
        near: VisibleElement | SearchMatch | None = None,
        maximum_results: int | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> SearchResult:
        elements = self.explorer.visible_elements(refresh=refresh)

        return self.find_in_elements(
            query=query,
            elements=elements,
            secondary_query=secondary_query,
            prefer_clickable=prefer_clickable,
            require_clickable=require_clickable,
            require_enabled=require_enabled,
            role=role,
            tag=tag,
            near=near,
            maximum_results=maximum_results,
            minimum_score=minimum_score,
        )

    def find_all(self, query: str, **kwargs) -> list[SearchMatch]:
        return self.find(query, **kwargs).matches

    def find_clickable(
        self,
        query: str,
        *,
        secondary_query: str | None = None,
        role: str | Sequence[str] | None = None,
        tag: str | Sequence[str] | None = None,
        near: VisibleElement | SearchMatch | None = None,
        maximum_results: int | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> SearchResult:
        return self.find(
            query=query,
            secondary_query=secondary_query,
            prefer_clickable=True,
            require_clickable=True,
            require_enabled=True,
            role=role,
            tag=tag,
            near=near,
            maximum_results=maximum_results,
            minimum_score=minimum_score,
            refresh=refresh,
        )

    def find_input(
        self,
        query: str,
        *,
        secondary_query: str | None = None,
        near: VisibleElement | SearchMatch | None = None,
        maximum_results: int | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> SearchResult:
        del refresh

        return self.find_in_elements(
            query=query,
            elements=self.explorer.inputs(),
            secondary_query=secondary_query,
            prefer_clickable=True,
            require_enabled=True,
            near=near,
            maximum_results=maximum_results,
            minimum_score=minimum_score,
        )

    def find_by_role(
        self,
        query: str,
        role: str | Sequence[str],
        *,
        secondary_query: str | None = None,
        require_clickable: bool = False,
        require_enabled: bool = False,
        near: VisibleElement | SearchMatch | None = None,
        maximum_results: int | None = None,
        minimum_score: float | None = None,
        refresh: bool = True,
    ) -> SearchResult:
        return self.find(
            query=query,
            secondary_query=secondary_query,
            prefer_clickable=require_clickable,
            require_clickable=require_clickable,
            require_enabled=require_enabled,
            role=role,
            near=near,
            maximum_results=maximum_results,
            minimum_score=minimum_score,
            refresh=refresh,
        )

    def find_in_elements(
        self,
        query: str,
        elements: Iterable[VisibleElement],
        *,
        secondary_query: str | None = None,
        prefer_clickable: bool | None = None,
        require_clickable: bool = False,
        require_enabled: bool = False,
        role: str | Sequence[str] | None = None,
        tag: str | Sequence[str] | None = None,
        near: VisibleElement | SearchMatch | None = None,
        maximum_results: int | None = None,
        minimum_score: float | None = None,
    ) -> SearchResult:
        started = perf_counter()
        cleaned_query = self.clean_text(query)
        cleaned_secondary = self.clean_text(secondary_query or "")

        result = SearchResult(
            query=query,
            secondary_query=secondary_query,
        )

        if not cleaned_query:
            result.duration_ms = (perf_counter() - started) * 1_000
            result.metadata["error"] = "Empty search query"
            return result

        role_values = self._normalise_filter_values(role)
        tag_values = self._normalise_filter_values(tag)
        target_near = self._element_from_reference(near)

        prefer_clickable_value = (
            self.config.prefer_clickable_by_default
            if prefer_clickable is None
            else prefer_clickable
        )
        score_floor = (
            self.config.minimum_score
            if minimum_score is None
            else float(minimum_score)
        )
        limit = (
            self.config.maximum_results
            if maximum_results is None
            else max(1, int(maximum_results))
        )

        source_elements = list(elements)
        result.scanned_elements = len(source_elements)

        for element in source_elements:
            if not self._element_allowed(
                element=element,
                require_clickable=require_clickable,
                require_enabled=require_enabled,
                role_values=role_values,
                tag_values=tag_values,
            ):
                continue

            result.filtered_elements += 1
            match = self._score_element(
                query=query,
                cleaned_query=cleaned_query,
                secondary_query=secondary_query,
                cleaned_secondary=cleaned_secondary,
                element=element,
                prefer_clickable=prefer_clickable_value,
                role_values=role_values,
                tag_values=tag_values,
                near=target_near,
            )

            if match.score >= score_floor:
                result.matches.append(match)

        result.sort_matches()
        result.matches = result.matches[:limit]
        result.duration_ms = (perf_counter() - started) * 1_000
        result.metadata.update(
            {
                "minimum_score": score_floor,
                "maximum_results": limit,
                "prefer_clickable": prefer_clickable_value,
                "require_clickable": require_clickable,
                "require_enabled": require_enabled,
                "role_filter": sorted(role_values),
                "tag_filter": sorted(tag_values),
                "explorer_scan_duration_ms": self.explorer.last_scan_duration_ms,
                "explorer_last_error": self.explorer.last_error,
            }
        )
        return result

    def _score_element(
        self,
        *,
        query: str,
        cleaned_query: str,
        secondary_query: str | None,
        cleaned_secondary: str,
        element: VisibleElement,
        prefer_clickable: bool,
        role_values: set[str],
        tag_values: set[str],
        near: VisibleElement | None,
    ) -> SearchMatch:
        candidate = self.clean_text(element.searchable_text)
        candidate_compact = self.compact_text(candidate)
        query_compact = self.compact_text(cleaned_query)

        exact_score, exact_reasons = self._exact_score(
            cleaned_query,
            candidate,
            query_compact,
            candidate_compact,
        )
        text_score, text_reasons = self._text_score(
            cleaned_query,
            candidate,
        )
        token_score, token_reasons = self._token_score(
            cleaned_query,
            candidate,
        )
        fuzzy_score, fuzzy_reasons = self._fuzzy_score(
            cleaned_query,
            candidate,
        )

        secondary_score = 0.0
        secondary_reasons: list[str] = []
        if cleaned_secondary:
            secondary_score, secondary_reasons = self._secondary_score(
                cleaned_secondary,
                candidate,
                element,
            )

        clickable_score = 0.0
        state_reasons: list[str] = []

        if element.visible:
            clickable_score += self.config.visible_bonus
            state_reasons.append("visible")
        if element.enabled:
            clickable_score += self.config.enabled_bonus
            state_reasons.append("enabled")
        if element.clickable:
            bonus = (
                self.config.clickable_bonus
                if prefer_clickable
                else self.config.clickable_bonus * 0.45
            )
            clickable_score += bonus
            state_reasons.append("clickable")
        if role_values and (element.role or "").casefold() in role_values:
            clickable_score += self.config.preferred_role_bonus
            state_reasons.append("preferred role")
        if tag_values and element.tag_name.casefold() in tag_values:
            clickable_score += self.config.preferred_tag_bonus
            state_reasons.append("preferred tag")

        proximity_score = self._proximity_score(element, near)
        base_score = (
            exact_score
            + text_score
            + token_score
            + fuzzy_score
            + secondary_score
            + clickable_score
            + proximity_score
        )
        length_penalty = self._length_penalty(
            query=cleaned_query,
            candidate=candidate,
        )
        area_penalty = self._area_penalty(element)
        score = max(
            0.0,
            min(100.0, base_score - length_penalty - area_penalty),
        )

        quality = self._quality_for_score(
            score=score,
            exact_score=exact_score,
        )

        match = SearchMatch(
            element=element,
            query=query,
            score=round(score, 3),
            quality=quality,
            text_score=round(text_score, 3),
            exact_score=round(exact_score, 3),
            token_score=round(token_score, 3),
            secondary_score=round(secondary_score, 3),
            clickable_score=round(clickable_score, 3),
            proximity_score=round(proximity_score, 3),
            matched_text=element.searchable_text,
            metadata={
                "fuzzy_score": round(fuzzy_score, 3),
                "length_penalty": round(length_penalty, 3),
                "area_penalty": round(area_penalty, 3),
                "normalised_query": cleaned_query,
                "normalised_candidate": candidate,
                "secondary_query": secondary_query,
            },
        )

        for reason in (
            exact_reasons
            + text_reasons
            + token_reasons
            + fuzzy_reasons
            + secondary_reasons
            + state_reasons
        ):
            match.add_reason(reason)

        if proximity_score > 0:
            match.add_reason("near reference element")
        if length_penalty > 0:
            match.add_reason("long-text penalty")
        if area_penalty > 0:
            match.add_reason("large-container penalty")

        return match

    def _exact_score(
        self,
        query: str,
        candidate: str,
        query_compact: str,
        candidate_compact: str,
    ) -> tuple[float, list[str]]:
        if not candidate:
            return 0.0, []
        if candidate == query:
            return self.config.exact_weight, ["exact text match"]
        if candidate_compact == query_compact:
            return self.config.exact_weight * 0.97, ["exact normalised match"]
        if candidate.casefold() == query.casefold():
            return self.config.exact_weight * 0.95, ["case-insensitive exact match"]
        return 0.0, []

    def _text_score(
        self,
        query: str,
        candidate: str,
    ) -> tuple[float, list[str]]:
        if not candidate:
            return 0.0, []

        weight = self.config.text_weight
        if candidate.startswith(query):
            return weight, ["starts with query"]
        if candidate.endswith(query):
            return weight * 0.9, ["ends with query"]
        if query in candidate:
            ratio = len(query) / max(1, len(candidate))
            return weight * (0.68 + 0.32 * ratio), ["contains query"]
        if candidate in query:
            ratio = len(candidate) / max(1, len(query))
            return weight * (0.52 + 0.28 * ratio), ["query contains candidate"]

        query_numbers = self._NUMBER_RE.findall(query)
        candidate_numbers = self._NUMBER_RE.findall(candidate)
        if query_numbers and query_numbers == candidate_numbers:
            return weight * 0.45, ["numeric sequence match"]
        return 0.0, []

    def _token_score(
        self,
        query: str,
        candidate: str,
    ) -> tuple[float, list[str]]:
        query_tokens = self.tokenise(query)
        candidate_tokens = self.tokenise(candidate)
        if not query_tokens or not candidate_tokens:
            return 0.0, []

        query_set = set(query_tokens)
        candidate_set = set(candidate_tokens)
        common = query_set & candidate_set
        if not common:
            return 0.0, []

        coverage = len(common) / len(query_set)
        precision = len(common) / len(candidate_set)
        ordered = self._ordered_token_ratio(query_tokens, candidate_tokens)
        combined = coverage * 0.55 + precision * 0.20 + ordered * 0.25
        score = self.config.token_weight * combined

        reasons = [f"token overlap {len(common)}/{len(query_set)}"]
        if coverage == 1.0:
            reasons.append("all query tokens matched")
        if ordered == 1.0:
            reasons.append("token order matched")
        return score, reasons

    def _fuzzy_score(
        self,
        query: str,
        candidate: str,
    ) -> tuple[float, list[str]]:
        if not candidate:
            return 0.0, []

        similarity = max(
            SequenceMatcher(None, query, candidate).ratio(),
            SequenceMatcher(
                None,
                self.compact_text(query),
                self.compact_text(candidate),
            ).ratio(),
        )
        if similarity < 0.45:
            return 0.0, []
        return (
            self.config.fuzzy_weight * similarity,
            [f"fuzzy similarity {similarity:.2f}"],
        )

    def _secondary_score(
        self,
        secondary_query: str,
        candidate: str,
        element: VisibleElement,
    ) -> tuple[float, list[str]]:
        values = [
            candidate,
            self.clean_text(element.attributes.get("aria-describedby", "")),
            self.clean_text(element.attributes.get("aria-labelledby", "")),
            self.clean_text(element.metadata.get("context_text", "")),
        ]
        best = 0.0

        for value in values:
            if not value:
                continue
            if value == secondary_query:
                best = max(best, 1.0)
            elif secondary_query in value:
                best = max(
                    best,
                    len(secondary_query) / max(len(value), len(secondary_query)),
                )
            else:
                best = max(
                    best,
                    SequenceMatcher(None, secondary_query, value).ratio() * 0.7,
                )

        if best <= 0:
            return 0.0, []
        return self.config.secondary_weight * best, ["secondary query matched"]

    def _proximity_score(
        self,
        element: VisibleElement,
        near: VisibleElement | None,
    ) -> float:
        if near is None or near.bounds is None or element.bounds is None:
            return 0.0
        distance = element.bounds.distance_to(near.bounds)
        factor = 1.0 / (1.0 + distance / 180.0)
        return self.config.proximity_weight * factor

    def _element_allowed(
        self,
        *,
        element: VisibleElement,
        require_clickable: bool,
        require_enabled: bool,
        role_values: set[str],
        tag_values: set[str],
    ) -> bool:
        if not self.config.include_elements_without_text and not element.has_text:
            return False
        if require_clickable and not element.clickable:
            return False
        if require_enabled and not element.enabled:
            return False
        if not self.config.allow_disabled_by_default and not element.enabled:
            return False
        if role_values and (element.role or "").casefold() not in role_values:
            return False
        if tag_values and element.tag_name.casefold() not in tag_values:
            return False
        return True

    def _quality_for_score(
        self,
        *,
        score: float,
        exact_score: float,
    ) -> MatchQuality:
        if (
            exact_score >= self.config.exact_weight * 0.9
            and score >= self.config.strong_threshold
        ):
            return MatchQuality.EXACT
        if score >= self.config.exact_threshold:
            return MatchQuality.EXACT
        if score >= self.config.strong_threshold:
            return MatchQuality.STRONG
        if score >= self.config.possible_threshold:
            return MatchQuality.POSSIBLE
        if score >= self.config.weak_threshold:
            return MatchQuality.WEAK
        return MatchQuality.NONE

    def _length_penalty(self, *, query: str, candidate: str) -> float:
        if not candidate or len(candidate) <= len(query):
            return 0.0
        excess_ratio = (len(candidate) - len(query)) / max(1, len(query))
        return min(12.0, log1p(excess_ratio) * 4.0)

    @staticmethod
    def _area_penalty(element: VisibleElement) -> float:
        if element.bounds is None or element.clickable:
            return 0.0
        area = element.bounds.area
        if area <= 25_000:
            return 0.0
        return min(8.0, log1p(area / 25_000) * 2.0)

    @classmethod
    def clean_text(cls, value: object) -> str:
        if value is None:
            return ""

        text = unicodedata.normalize("NFKD", str(value))
        text = "".join(
            character
            for character in text
            if not unicodedata.combining(character)
        )
        text = (
            text.replace("’", "'")
            .replace("‘", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("–", "-")
            .replace("—", "-")
        )
        text = cls._PUNCTUATION_RE.sub(" ", text.casefold())
        return cls._WHITESPACE_RE.sub(" ", text).strip()

    @classmethod
    def compact_text(cls, value: object) -> str:
        return "".join(cls.tokenise(cls.clean_text(value)))

    @classmethod
    def tokenise(cls, value: object) -> list[str]:
        cleaned = cls.clean_text(value)
        return [
            token
            for token in cls._TOKEN_RE.findall(cleaned)
            if token
        ]

    @staticmethod
    def _ordered_token_ratio(
        query_tokens: Sequence[str],
        candidate_tokens: Sequence[str],
    ) -> float:
        if not query_tokens or not candidate_tokens:
            return 0.0

        candidate_index = 0
        matched = 0
        for query_token in query_tokens:
            for index in range(candidate_index, len(candidate_tokens)):
                if candidate_tokens[index] == query_token:
                    matched += 1
                    candidate_index = index + 1
                    break
        return matched / len(query_tokens)

    @staticmethod
    def _normalise_filter_values(
        value: str | Sequence[str] | None,
    ) -> set[str]:
        if value is None:
            return set()
        values = [value] if isinstance(value, str) else list(value)
        return {
            str(item).strip().casefold()
            for item in values
            if str(item).strip()
        }

    @staticmethod
    def _element_from_reference(
        value: VisibleElement | SearchMatch | None,
    ) -> VisibleElement | None:
        if isinstance(value, SearchMatch):
            return value.element
        return value