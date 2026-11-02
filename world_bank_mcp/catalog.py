"""Runtime catalog built from validated rules.

The catalog is the single source of truth for what the MCP may query. Tool
inputs are resolved against it, so no arbitrary World Bank code or URL can
reach the API. Catalog data comes from ``rules.yaml``; the invariants that
must never change stay in code.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from world_bank_mcp.errors import QueryError


@dataclass(frozen=True, slots=True)
class Entity:
    iso3: str
    name: str
    aliases: tuple[str, ...] = ()
    is_aggregate: bool = False


@dataclass(frozen=True, slots=True)
class Indicator:
    code: str
    name: str
    unit: str
    aliases: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class Catalog:
    """Validated entities and indicators with normalized lookup indexes."""

    entities: tuple[Entity, ...]
    indicators: tuple[Indicator, ...]
    _entity_index: dict[str, Entity] = field(init=False, repr=False)
    _indicator_index: dict[str, Indicator] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._entity_index = _build_index(
            self.entities,
            lambda entity: (entity.iso3, entity.name, *entity.aliases),
        )
        self._indicator_index = _build_index(
            self.indicators,
            lambda indicator: (indicator.code, indicator.name, *indicator.aliases),
        )

    def resolve_entity(self, raw: str) -> Entity:
        entity = self._entity_index.get(normalize_alias(raw))
        if entity is None:
            raise QueryError(
                f"La entidad {raw!r} no está en el catálogo de la demo. "
                f"Usa una de: {_summarize(entity.name for entity in self.entities)}."
            )
        return entity

    def resolve_indicator(self, raw: str) -> Indicator:
        indicator = self._indicator_index.get(normalize_alias(raw))
        if indicator is None:
            raise QueryError(
                f"El indicador {raw!r} no está en el catálogo de la demo. "
                f"Usa uno de: {_summarize(indicator.code for indicator in self.indicators)}."
            )
        return indicator

    def to_dict(self) -> dict[str, object]:
        """Serializable view used by the MCP catalog resource."""
        return {
            "entities": [
                {
                    "iso3": entity.iso3,
                    "name": entity.name,
                    "aliases": list(entity.aliases),
                    "aggregate": entity.is_aggregate,
                }
                for entity in self.entities
            ],
            "indicators": [
                {
                    "code": indicator.code,
                    "name": indicator.name,
                    "unit": indicator.unit,
                    "aliases": list(indicator.aliases),
                    "warnings": list(indicator.warnings),
                }
                for indicator in self.indicators
            ],
        }


def normalize_alias(value: str) -> str:
    """Casefold, strip accents, remove dots, and collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.replace(".", " ").split())


def _build_index[T](items: Iterable[T], candidates: Callable[[T], Iterable[str]]) -> dict[str, T]:
    index: dict[str, T] = {}
    for item in items:
        for candidate in candidates(item):
            index[normalize_alias(candidate)] = item
    return index


def _summarize(values: Iterable[str], limit: int = 10) -> str:
    items = list(values)
    if len(items) <= limit:
        return ", ".join(items)
    return f"{', '.join(items[:limit])} y {len(items) - limit} más"


_catalog: Catalog | None = None


def get_catalog() -> Catalog:
    """Load the catalog from the configured rules file on first use."""
    global _catalog
    if _catalog is None:
        from world_bank_mcp.config import load_catalog

        _catalog = load_catalog()
    return _catalog


def set_catalog(catalog: Catalog | None) -> None:
    """Replace the cached catalog, mainly for tests and future reloads."""
    global _catalog
    _catalog = catalog


def resolve_entity(raw: str) -> Entity:
    return get_catalog().resolve_entity(raw)


def resolve_indicator(raw: str) -> Indicator:
    return get_catalog().resolve_indicator(raw)
