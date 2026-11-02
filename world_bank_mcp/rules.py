"""Executable business rules for the World Bank demo."""

from world_bank_mcp.catalog import Entity, Indicator
from world_bank_mcp.constants import (
    COMPARISON_WARNING,
    MAX_RANGE_YEARS,
    MAX_YEAR,
    MIN_YEAR,
    TEMPORALITY_WARNING,
)
from world_bank_mcp.errors import QueryError

__all__ = [
    "QueryError",
    "comparison_warnings",
    "ensure_comparable",
    "series_warnings",
    "validate_year_range",
]


def validate_year_range(start_year: int, end_year: int) -> None:
    """Reject years outside 1960–current, inverted ranges, and ranges over 10 years."""
    for year in (start_year, end_year):
        if year < MIN_YEAR or year > MAX_YEAR:
            raise QueryError(
                f"El año {year} está fuera del rango permitido ({MIN_YEAR}–{MAX_YEAR})."
            )

    if start_year > end_year:
        raise QueryError(
            "El rango está invertido: el año inicial no puede ser mayor que el año final."
        )

    span = end_year - start_year + 1
    if span > MAX_RANGE_YEARS:
        raise QueryError(
            f"El rango solicitado abarca {span} años; el máximo permitido es "
            f"{MAX_RANGE_YEARS} años."
        )


def ensure_comparable(country_a: Entity, country_b: Entity) -> None:
    """Reject comparisons against an aggregate or against the same entity."""
    if country_a.is_aggregate or country_b.is_aggregate:
        raise QueryError(
            "No se puede comparar un país con el agregado Mundo en compare_countries. "
            "Mundo solo puede consultarse individualmente con get_indicator_series."
        )

    if country_a.iso3 == country_b.iso3:
        raise QueryError(
            "No se puede comparar una entidad consigo misma; elige dos países distintos."
        )


def series_warnings(indicator: Indicator) -> list[str]:
    """Warnings that always travel with a single-entity series."""
    return [TEMPORALITY_WARNING, *indicator.warnings]


def comparison_warnings(indicator: Indicator) -> list[str]:
    """Warnings for a two-country comparison."""
    return [*series_warnings(indicator), COMPARISON_WARNING]
