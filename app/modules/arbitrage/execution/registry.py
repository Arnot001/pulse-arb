from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeVar

from app.browser import BrowserActions, BrowserPage
from app.modules.arbitrage.execution.adapter import (
    BrowserAdapter,
    BrowserAdapterConfig,
)


AdapterType = TypeVar(
    "AdapterType",
    bound=BrowserAdapter,
)


def normalize_bookmaker_name(
    bookmaker: str,
) -> str:
    """
    Convert bookmaker names and aliases into a stable registry key.
    """

    return "".join(
        character
        for character in bookmaker.strip().lower()
        if character.isalnum()
    )


@dataclass(slots=True, frozen=True)
class RegisteredAdapter:
    """
    Metadata stored for one bookmaker adapter.
    """

    key: str
    adapter_class: type[BrowserAdapter]
    aliases: tuple[str, ...]

    @property
    def bookmaker(self) -> str:
        return self.adapter_class.BOOKMAKER

    @property
    def display_name(self) -> str:
        return (
            self.adapter_class.DISPLAY_NAME.strip()
            or self.adapter_class.BOOKMAKER
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "bookmaker": self.bookmaker,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "adapter_class": self.adapter_class.__name__,
        }


class AdapterRegistry:
    """
    Registry and factory for bookmaker browser adapters.

    Concrete bookmaker adapters register once and can then be created by
    canonical bookmaker name or any configured alias.
    """

    def __init__(self) -> None:
        self._adapters: dict[
            str,
            RegisteredAdapter,
        ] = {}
        self._aliases: dict[
            str,
            str,
        ] = {}

    # -----------------------------------------------------
    # Registration
    # -----------------------------------------------------

    def register(
        self,
        adapter_class: type[AdapterType],
        *,
        aliases: Iterable[str] | None = None,
        replace: bool = False,
    ) -> type[AdapterType]:
        """
        Register one concrete BrowserAdapter class.

        The adapter's BOOKMAKER value is used as the canonical key.
        """

        if not isinstance(
            adapter_class,
            type,
        ):
            raise TypeError(
                "adapter_class must be a class."
            )

        if not issubclass(
            adapter_class,
            BrowserAdapter,
        ):
            raise TypeError(
                "adapter_class must inherit from BrowserAdapter."
            )

        bookmaker = adapter_class.BOOKMAKER.strip()

        if not bookmaker:
            raise ValueError(
                "Registered adapter must define BOOKMAKER."
            )

        key = normalize_bookmaker_name(
            bookmaker
        )

        if not key:
            raise ValueError(
                "BOOKMAKER does not produce a valid registry key."
            )

        if (
            key in self._adapters
            and not replace
        ):
            existing = self._adapters[key]

            raise ValueError(
                f"Adapter {key!r} is already registered by "
                f"{existing.adapter_class.__name__}."
            )

        resolved_aliases = self._build_aliases(
            adapter_class=adapter_class,
            aliases=aliases,
        )

        if replace and key in self._adapters:
            self.unregister(key)

        self._validate_aliases(
            canonical_key=key,
            aliases=resolved_aliases,
            replace=replace,
        )

        registered = RegisteredAdapter(
            key=key,
            adapter_class=adapter_class,
            aliases=resolved_aliases,
        )

        self._adapters[key] = registered
        self._aliases[key] = key

        for alias in resolved_aliases:
            self._aliases[
                normalize_bookmaker_name(alias)
            ] = key

        return adapter_class

    def unregister(
        self,
        bookmaker: str,
    ) -> type[BrowserAdapter]:
        """
        Remove a registered bookmaker adapter.
        """

        key = self.resolve_key(
            bookmaker
        )

        registered = self._adapters.pop(
            key
        )

        aliases_to_remove = [
            alias
            for alias, canonical_key in self._aliases.items()
            if canonical_key == key
        ]

        for alias in aliases_to_remove:
            self._aliases.pop(
                alias,
                None,
            )

        return registered.adapter_class

    def clear(
        self,
    ) -> None:
        self._adapters.clear()
        self._aliases.clear()

    # -----------------------------------------------------
    # Lookup
    # -----------------------------------------------------

    def resolve_key(
        self,
        bookmaker: str,
    ) -> str:
        normalized = normalize_bookmaker_name(
            bookmaker
        )

        if not normalized:
            raise KeyError(
                "Bookmaker name is empty."
            )

        try:
            return self._aliases[normalized]
        except KeyError as exc:
            supported = ", ".join(
                self.keys()
            )

            message = (
                f"No browser adapter is registered for "
                f"{bookmaker!r}."
            )

            if supported:
                message += (
                    f" Supported bookmakers: {supported}."
                )

            raise KeyError(
                message
            ) from exc

    def get(
        self,
        bookmaker: str,
    ) -> type[BrowserAdapter]:
        """
        Return the registered adapter class.
        """

        key = self.resolve_key(
            bookmaker
        )

        return self._adapters[
            key
        ].adapter_class

    def describe(
        self,
        bookmaker: str,
    ) -> RegisteredAdapter:
        key = self.resolve_key(
            bookmaker
        )

        return self._adapters[key]

    def contains(
        self,
        bookmaker: str,
    ) -> bool:
        normalized = normalize_bookmaker_name(
            bookmaker
        )

        return normalized in self._aliases

    def keys(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                self._adapters
            )
        )

    def aliases(
        self,
    ) -> dict[str, str]:
        return dict(
            sorted(
                self._aliases.items()
            )
        )

    def registered(
        self,
    ) -> tuple[RegisteredAdapter, ...]:
        return tuple(
            self._adapters[key]
            for key in self.keys()
        )

    # -----------------------------------------------------
    # Factory
    # -----------------------------------------------------

    def create(
        self,
        bookmaker: str,
        *,
        browser: BrowserPage,
        actions: BrowserActions | None = None,
        config: BrowserAdapterConfig | None = None,
    ) -> BrowserAdapter:
        """
        Create a bookmaker adapter around an existing persistent page.
        """

        adapter_class = self.get(
            bookmaker
        )

        return adapter_class(
            browser=browser,
            actions=actions,
            config=config,
        )

    # -----------------------------------------------------
    # Decorator
    # -----------------------------------------------------

    def decorator(
        self,
        *,
        aliases: Iterable[str] | None = None,
        replace: bool = False,
    ):
        """
        Register an adapter with decorator syntax.

        Example:
            @adapter_registry.decorator(
                aliases=("bet 365",),
            )
            class Bet365Adapter(BrowserAdapter):
                ...
        """

        def register_class(
            adapter_class: type[AdapterType],
        ) -> type[AdapterType]:
            return self.register(
                adapter_class,
                aliases=aliases,
                replace=replace,
            )

        return register_class

    # -----------------------------------------------------
    # Private helpers
    # -----------------------------------------------------

    @staticmethod
    def _build_aliases(
        *,
        adapter_class: type[BrowserAdapter],
        aliases: Iterable[str] | None,
    ) -> tuple[str, ...]:
        values: list[str] = []

        display_name = (
            adapter_class.DISPLAY_NAME.strip()
        )

        if display_name:
            values.append(
                display_name
            )

        if aliases is not None:
            values.extend(
                alias
                for alias in aliases
                if alias and alias.strip()
            )

        canonical = normalize_bookmaker_name(
            adapter_class.BOOKMAKER
        )

        deduplicated: dict[
            str,
            str,
        ] = {}

        for value in values:
            normalized = normalize_bookmaker_name(
                value
            )

            if (
                normalized
                and normalized != canonical
            ):
                deduplicated[
                    normalized
                ] = value.strip()

        return tuple(
            deduplicated[key]
            for key in sorted(
                deduplicated
            )
        )

    def _validate_aliases(
        self,
        *,
        canonical_key: str,
        aliases: tuple[str, ...],
        replace: bool,
    ) -> None:
        candidate_keys = {
            canonical_key,
            *(
                normalize_bookmaker_name(alias)
                for alias in aliases
            ),
        }

        for alias_key in candidate_keys:
            existing_key = self._aliases.get(
                alias_key
            )

            if existing_key is None:
                continue

            if (
                existing_key == canonical_key
                and replace
            ):
                continue

            raise ValueError(
                f"Registry alias {alias_key!r} is already assigned "
                f"to {existing_key!r}."
            )


adapter_registry = AdapterRegistry()


def register_adapter(
    adapter_class: type[AdapterType] | None = None,
    *,
    aliases: Iterable[str] | None = None,
    replace: bool = False,
):
    """
    Register an adapter using direct-call or decorator syntax.

    Direct:
        register_adapter(
            Bet365Adapter,
            aliases=("bet 365",),
        )

    Decorator:
        @register_adapter(
            aliases=("bet 365",),
        )
        class Bet365Adapter(BrowserAdapter):
            ...
    """

    if adapter_class is not None:
        return adapter_registry.register(
            adapter_class,
            aliases=aliases,
            replace=replace,
        )

    return adapter_registry.decorator(
        aliases=aliases,
        replace=replace,
    )