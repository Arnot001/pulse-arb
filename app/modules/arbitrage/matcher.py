from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


_SUFFIXES = (
    " (IRE)",
    " (GB)",
    " (FR)",
    " (USA)",
    " (GER)",
)


def normalize_runner_name(name: str) -> str:
    """
    Convert a horse name into a canonical key.

    Examples

    King's Gambit
    kings gambit
    KINGS-GAMBIT
    King's Gambit (IRE)

    →

    kingsgambit
    """

    if not name:
        return ""

    name = unicodedata.normalize(
        "NFKD",
        str(name),
    )

    name = (
        name.encode(
            "ascii",
            "ignore",
        )
        .decode()
    )

    name = name.upper().strip()

    for suffix in _SUFFIXES:
        if name.endswith(suffix.upper()):
            name = name[
                : -len(suffix)
            ]

    name = re.sub(
        r"\([^)]*\)",
        "",
        name,
    )

    name = name.replace("&", "AND")

    name = re.sub(
        r"[^A-Z0-9]",
        "",
        name,
    )

    return name.lower()


def similarity(
    left: str,
    right: str,
) -> float:
    return SequenceMatcher(
        None,
        normalize_runner_name(left),
        normalize_runner_name(right),
    ).ratio()


def names_match(
    left: str,
    right: str,
    threshold: float = 0.95,
) -> bool:

    if not left or not right:
        return False

    if (
        normalize_runner_name(left)
        ==
        normalize_runner_name(right)
    ):
        return True

    return (
        similarity(
            left,
            right,
        )
        >= threshold
    )


def find_matching_runner(
    runner_name: str,
    candidates,
    threshold: float = 0.95,
):
    """
    Returns the best matching runner from an iterable.

    candidates may contain:

        strings

    or

        dicts with a 'horse' field.
    """

    best = None
    best_score = 0.0

    for candidate in candidates:

        if isinstance(
            candidate,
            dict,
        ):
            name = candidate.get(
                "horse",
                "",
            )
        else:
            name = str(candidate)

        score = similarity(
            runner_name,
            name,
        )

        if score > best_score:
            best_score = score
            best = candidate

    if best_score >= threshold:
        return best

    return None


def deduplicate_runners(
    runners,
):
    """
    Removes duplicate horses by canonical name.

    Keeps the first occurrence.
    """

    seen = set()
    unique = []

    for runner in runners:

        if isinstance(
            runner,
            dict,
        ):
            name = runner.get(
                "horse",
                "",
            )
        else:
            name = str(runner)

        key = normalize_runner_name(
            name
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(
            runner
        )

    return unique


def build_runner_lookup(
    runners,
):
    """
    Build a dictionary

    canonical_name -> runner
    """

    lookup = {}

    for runner in runners:

        if isinstance(
            runner,
            dict,
        ):
            name = runner.get(
                "horse",
                "",
            )
        else:
            name = str(runner)

        lookup[
            normalize_runner_name(name)
        ] = runner

    return lookup