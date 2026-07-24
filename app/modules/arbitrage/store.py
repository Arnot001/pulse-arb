from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


STORE_ROOT = Path("data/arbitrage")
CURRENT_STATE_FILE = STORE_ROOT / "current.json"
HISTORY_DIR = STORE_ROOT / "opportunities"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value) -> str:
    return str(value or "").strip()

def normalize_bookmaker(bookmaker: str) -> str:
    return (
        clean(bookmaker)
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )

def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file_handle:
        json.dump(
            payload,
            file_handle,
            ensure_ascii=False,
            indent=2,
        )

        file_handle.flush()
        os.fsync(file_handle.fileno())

    temporary_path.replace(path)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "a",
        encoding="utf-8",
    ) as file_handle:
        file_handle.write(
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        file_handle.write("\n")


def load_current_state() -> dict[str, dict]:
    if not CURRENT_STATE_FILE.exists():
        return {}

    try:
        with CURRENT_STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file_handle:
            payload = json.load(file_handle)

    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    records = payload.get("records", payload)

    if not isinstance(records, dict):
        return {}

    return {
        clean(key): value
        for key, value in records.items()
        if clean(key) and isinstance(value, dict)
    }


def _race_details(snapshot: dict) -> tuple[str, str, str]:
    url = clean(snapshot.get("url"))

    race = "Unknown race"
    course = "Unknown"
    race_time = ""

    marker = "/horse-racing/"

    if marker in url:
        remainder = url.split(marker, 1)[1]
        parts = remainder.split("/")

        if parts:
            course = parts[0].replace("-", " ").title()

        if len(parts) >= 2:
            race_time = parts[1]

        race = clean(
            f"{course} {race_time}"
        )

    return race, course, race_time


def _record_key(snapshot: dict) -> str:
    url = clean(snapshot.get("url"))
    canonical = snapshot.get("canonical_arb") or {}

    raw = "|".join(
        [
            url,
            clean(canonical.get("market_type"))
            or "sportsbook_back_back",
        ]
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:20]

    return f"horse-back-back-{digest}"


def _bookmakers_from_snapshot(snapshot: dict) -> list[str]:
    names = set()

    canonical = snapshot.get("canonical_arb") or {}

    for leg in canonical.get("legs", []) or []:
        if not isinstance(leg, dict):
            continue

        bookmaker = clean(
            leg.get("bookmaker")
        )

        if bookmaker:
            names.add(bookmaker)

    if not names:
        for runner in snapshot.get("runners", []) or []:
            if not isinstance(runner, dict):
                continue

            for price in runner.get(
                "sportsbook_prices",
                [],
            ) or []:
                if not isinstance(price, dict):
                    continue

                bookmaker = clean(
                    price.get("bookmaker")
                )

                if bookmaker:
                    names.add(bookmaker)

    return sorted(names)


def classify_snapshot(snapshot: dict) -> str:
    canonical = snapshot.get("canonical_arb") or {}
    validation = snapshot.get("arb_validation") or {}
    verified = snapshot.get("verified_arb") or {}

    verification_status = clean(
        verified.get("verification_status")
    )

    if (
        verification_status
        == "VERIFIED_SPORTSBOOK_BACK_BACK"
    ):
        return "VERIFIED"

    if canonical.get("is_arbitrage") is True:
        if validation.get(
            "eligible_for_verified_arb"
        ) is True:
            return "VERIFIED"

        return "REVIEW"

    if not canonical.get("complete_market"):
        return "INCOMPLETE"

    if validation.get("status") == "INVALID_ALIGNMENT":
        return "INVALID"

    return "OBSERVED"


def build_record(
    snapshot: dict,
    previous: dict | None = None,
) -> dict:
    previous = previous or {}

    canonical = snapshot.get("canonical_arb") or {}
    validation = snapshot.get("arb_validation") or {}
    verified = snapshot.get("verified_arb") or {}

    now = utc_now()
    race, course, race_time = _race_details(snapshot)
    status = classify_snapshot(snapshot)

    first_seen = (
        clean(previous.get("first_seen"))
        or clean(snapshot.get("collected_at"))
        or now
    )

    seen_count = safe_int(
        previous.get("seen_count"),
        0,
    ) + 1

    legs = canonical.get("legs") or []

    return {
        "opportunity_id": _record_key(snapshot),
        "engine": "horse_back_back",
        "market_type": clean(
            canonical.get("market_type")
        ) or "sportsbook_back_back",
        "status": status,
        "verification_status": clean(
            verified.get("verification_status")
        ),
        "validation_status": clean(
            validation.get("status")
        ),
        "validation_score": safe_float(
            validation.get("score")
        ),
        "race": race,
        "course": course,
        "race_time": race_time,
        "url": clean(snapshot.get("url")),
        "source": clean(snapshot.get("source"))
        or "oddschecker_browser",
        "runner_count": safe_int(
            canonical.get(
                "runner_count",
                len(snapshot.get("runners", []) or []),
            )
        ),
        "confirmed_runner_count": safe_int(
            canonical.get("confirmed_runner_count")
        ),
        "bookmaker_count": len(
            _bookmakers_from_snapshot(snapshot)
        ),
        "bookmakers": _bookmakers_from_snapshot(
            snapshot
        ),
        "market_percentage": (
            safe_float(
                canonical.get("market_percentage")
            )
            if canonical.get("market_percentage")
            is not None
            else None
        ),
        "arb_margin_percent": (
            safe_float(
                canonical.get("arb_margin_percent")
            )
            if canonical.get("arb_margin_percent")
            is not None
            else None
        ),
        "roi_percent": safe_float(
            canonical.get("rounded_roi_percent")
        ),
        "profit": safe_float(
            canonical.get("rounded_profit")
        ),
        "total_stake": safe_float(
            canonical.get("rounded_total_stake")
            or canonical.get("requested_total_stake")
        ),
        "guaranteed_return": safe_float(
            canonical.get(
                "rounded_guaranteed_return"
            )
        ),
        "legs": legs,
        "failures": list(
            validation.get("failures") or []
        ),
        "warnings": list(
            validation.get("warnings") or []
        ),
        "first_seen": first_seen,
        "last_seen": clean(
            snapshot.get("collected_at")
        ) or now,
        "seen_count": seen_count,
        "active": True,
        "expired": False,
        "last_event": (
            "CREATED"
            if not previous
            else "UPDATED"
        ),
        "calculation_version": clean(
            canonical.get("calculation_version")
        ),
    }


def record_snapshot(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict):
        raise TypeError(
            "snapshot must be a dictionary"
        )

    key = _record_key(snapshot)
    state = load_current_state()
    previous = state.get(key)

    record = build_record(
        snapshot,
        previous=previous,
    )

    state[key] = record

    _atomic_write_json(
        CURRENT_STATE_FILE,
        {
            "updated_at": utc_now(),
            "records": state,
        },
    )

    event_time = datetime.now(timezone.utc)
    history_path = (
        HISTORY_DIR
        / f"{event_time.date().isoformat()}.jsonl"
    )

    _append_jsonl(
        history_path,
        {
            **record,
            "event_recorded_at": utc_now(),
        },
    )

    return record


def expire_stale_opportunities(
    *,
    stale_after_minutes: int = 30,
) -> int:
    state = load_current_state()

    if not state:
        return 0

    now = datetime.now(timezone.utc)
    expired_count = 0

    for key, record in state.items():
        if record.get("expired") is True:
            continue

        last_seen_raw = clean(
            record.get("last_seen")
        )

        if not last_seen_raw:
            continue

        try:
            last_seen = datetime.fromisoformat(
                last_seen_raw.replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError:
            continue

        age_minutes = (
            now - last_seen.astimezone(timezone.utc)
        ).total_seconds() / 60

        if age_minutes < stale_after_minutes:
            continue

        record["active"] = False
        record["expired"] = True
        record["expired_at"] = utc_now()
        record["last_event"] = "EXPIRED"
        state[key] = record
        expired_count += 1

    if expired_count:
        _atomic_write_json(
            CURRENT_STATE_FILE,
            {
                "updated_at": utc_now(),
                "records": state,
            },
        )

    return expired_count


def current_records(
    *,
    statuses: Iterable[str] | None = None,
    include_expired: bool = False,
) -> list[dict]:
    records = list(
        load_current_state().values()
    )

    if statuses is not None:
        allowed = {
            clean(status).upper()
            for status in statuses
        }

        records = [
            record
            for record in records
            if clean(
                record.get("status")
            ).upper() in allowed
        ]

    if not include_expired:
        records = [
            record
            for record in records
            if record.get("expired") is not True
        ]

    records.sort(
        key=lambda record: clean(
            record.get("last_seen")
        ),
        reverse=True,
    )

    return records


def dashboard_stats() -> dict:
    records = current_records(
        include_expired=False
    )

    verified = [
        record
        for record in records
        if record.get("status") == "VERIFIED"
    ]

    review = [
        record
        for record in records
        if record.get("status") == "REVIEW"
    ]

    bookmakers = {
        bookmaker
        for record in records
        for bookmaker in (
            record.get("bookmakers") or []
        )
        if clean(bookmaker)
    }

    highest_roi = max(
        (
            safe_float(
                record.get("roi_percent")
            )
            for record in verified
        ),
        default=0.0,
    )

    return {
        "markets": len(records),
        "execute": len(verified),
        "review": len(review),
        "highest_roi": round(
            highest_roi,
            2,
        ),
        "bookmakers": len(bookmakers),
        "verified": len(verified),
        "incomplete": sum(
            1
            for record in records
            if record.get("status")
            == "INCOMPLETE"
        ),
        "invalid": sum(
            1
            for record in records
            if record.get("status")
            == "INVALID"
        ),
        "observed": sum(
            1
            for record in records
            if record.get("status")
            == "OBSERVED"
        ),
    }


def recent_opportunities(
    limit: int = 20,
) -> list[dict]:
    records = current_records(
        statuses=(
            "VERIFIED",
            "REVIEW",
        ),
        include_expired=False,
    )

    return records[: max(0, int(limit))]