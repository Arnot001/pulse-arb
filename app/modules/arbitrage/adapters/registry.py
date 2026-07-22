from __future__ import annotations

from typing import Type

from app.modules.arbitrage.adapters.base import (
    BookmakerAdapter,
)
from app.modules.arbitrage.adapters.bet365 import (
    Bet365Adapter,
)
from app.modules.arbitrage.bookmakers import (
    get_bookmaker,
)


ADAPTER_CLASSES: dict[
    str,
    Type[BookmakerAdapter],
] = {
    "bet365": Bet365Adapter,
}


def supported_adapter_ids() -> list[str]:
    return sorted(
        ADAPTER_CLASSES.keys()
    )


def adapter_supported(
    bookmaker_id: str,
) -> bool:
    cleaned_id = (
        bookmaker_id or ""
    ).strip().lower()

    return cleaned_id in ADAPTER_CLASSES


def get_adapter(
    bookmaker_id: str,
) -> BookmakerAdapter | None:
    bookmaker = get_bookmaker(
        bookmaker_id
    )

    if bookmaker is None:
        return None

    adapter_class = ADAPTER_CLASSES.get(
        bookmaker.id
    )

    if adapter_class is None:
        return None

    return adapter_class(
        bookmaker=bookmaker
    )


def require_adapter(
    bookmaker_id: str,
) -> BookmakerAdapter:
    adapter = get_adapter(
        bookmaker_id
    )

    if adapter is None:
        raise KeyError(
            f"No adapter is registered for "
            f"bookmaker: {bookmaker_id}"
        )

    return adapter