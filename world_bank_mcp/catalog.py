"""Closed catalog of demo entities and indicators.

The catalog is the single source of truth for what the MCP may query. Tool
inputs are resolved against it, so no arbitrary World Bank code or URL can
reach the API.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

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


ENTITIES: dict[str, Entity] = {
    "PER": Entity("PER", "Perú", ("peru", "per")),
    "CHL": Entity("CHL", "Chile", ("chile", "chl")),
    "COL": Entity("COL", "Colombia", ("colombia", "col")),
    "USA": Entity(
        "USA",
        "Estados Unidos",
        (
            "estados unidos",
            "united states",
            "united states of america",
            "usa",
            "eeuu",
            "ee uu",
            "us",
        ),
    ),
    "CHN": Entity("CHN", "China", ("china", "chn")),
    "WLD": Entity("WLD", "Mundo", ("mundo", "world", "wld"), is_aggregate=True),
}

INDICATORS: dict[str, Indicator] = {
    "SP.POP.TOTL": Indicator(
        "SP.POP.TOTL",
        "Población total",
        "personas",
        ("poblacion", "poblacion total", "population", "population total"),
    ),
    "NY.GDP.MKTP.CD": Indicator(
        "NY.GDP.MKTP.CD",
        "PIB nominal",
        "USD corrientes",
        ("pib", "pib nominal", "pib total", "gdp", "gdp nominal", "nominal gdp"),
        (
            "El PIB nominal está expresado en USD corrientes: no es PIB real ni ajusta "
            "por inflación.",
            "Un aumento del PIB nominal no implica por sí solo una mejora del bienestar.",
        ),
    ),
    "NY.GDP.PCAP.CD": Indicator(
        "NY.GDP.PCAP.CD",
        "PIB nominal per cápita",
        "USD corrientes por habitante",
        ("pib per capita", "pib por habitante", "gdp per capita", "per capita gdp"),
        (
            "El PIB per cápita es un promedio económico en USD corrientes por habitante; "
            "no es PIB real, no ajusta por inflación y no es el salario personal ni el "
            "ingreso de una persona.",
        ),
    ),
}


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.replace(".", " ").split())


def _build_index(
    items: dict[str, Entity] | dict[str, Indicator],
) -> dict[str, Entity | Indicator]:
    index: dict[str, Entity | Indicator] = {}
    for item in items.values():
        if isinstance(item, Entity):
            candidates = [item.iso3, item.name, *item.aliases]
        else:
            candidates = [item.code, item.name, *item.aliases]
        for candidate in candidates:
            index[_normalize(candidate)] = item
    return index


_ENTITY_INDEX = _build_index(ENTITIES)
_INDICATOR_INDEX = _build_index(INDICATORS)


def resolve_entity(raw: str) -> Entity:
    """Resolve an ISO3 code, Spanish/English name, or catalog alias."""
    entity = _ENTITY_INDEX.get(_normalize(raw))
    if not isinstance(entity, Entity):
        raise QueryError(
            f"La entidad {raw!r} no está en el catálogo de la demo. "
            "Usa Perú, Chile, Colombia, Estados Unidos, China o Mundo."
        )
    return entity


def resolve_indicator(raw: str) -> Indicator:
    """Resolve an indicator code, Spanish/English name, or catalog alias."""
    indicator = _INDICATOR_INDEX.get(_normalize(raw))
    if not isinstance(indicator, Indicator):
        raise QueryError(
            f"El indicador {raw!r} no está en el catálogo de la demo. "
            "Usa SP.POP.TOTL, NY.GDP.MKTP.CD o NY.GDP.PCAP.CD."
        )
    return indicator
