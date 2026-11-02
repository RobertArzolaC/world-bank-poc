"""Use cases that turn validated queries into traceable results."""

from datetime import UTC, datetime

from world_bank_mcp.catalog import Indicator, resolve_entity, resolve_indicator
from world_bank_mcp.client import WorldBankClient, WorldBankResponse, source_description
from world_bank_mcp.errors import QueryError
from world_bank_mcp.models import (
    ComparisonQuery,
    ComparisonResult,
    CountryValue,
    EntityRef,
    IndicatorRef,
    SeriesPoint,
    SeriesQuery,
    SeriesResult,
)
from world_bank_mcp.rules import comparison_warnings, ensure_comparable, series_warnings


def default_client() -> WorldBankClient:
    """Build the HTTP client used when a caller does not inject one."""
    return WorldBankClient()


async def get_indicator_series(
    query: SeriesQuery,
    client: WorldBankClient | None = None,
) -> SeriesResult:
    """Return one entity's series with explicit gaps; never fill a missing value."""
    entity = resolve_entity(query.entity)
    indicator = resolve_indicator(query.indicator)
    response = await (client or default_client()).fetch(
        indicator.code,
        [entity.iso3],
        query.start_year,
        query.resolved_end_year,
    )

    observed = {
        (observation.entity_iso3, observation.year): observation.value
        for observation in response.observations
    }
    series = [
        SeriesPoint(year=year, value=observed.get((entity.iso3, year)))
        for year in range(query.start_year, query.resolved_end_year + 1)
    ]

    return SeriesResult(
        indicator=_indicator_ref(indicator),
        entity=_entity_ref(entity.iso3, entity.name),
        unit=indicator.unit,
        source=source_description(response),
        retrieved_at=datetime.now(UTC),
        series=series,
        missing_years=[point.year for point in series if point.value is None],
        warnings=series_warnings(indicator),
    )


async def compare_countries(
    query: ComparisonQuery,
    client: WorldBankClient | None = None,
) -> ComparisonResult:
    """Compare the same indicator and year for two countries, or refuse to calculate."""
    country_a = resolve_entity(query.country_a)
    country_b = resolve_entity(query.country_b)
    ensure_comparable(country_a, country_b)
    indicator = resolve_indicator(query.indicator)

    response = await (client or default_client()).fetch(
        indicator.code,
        [country_a.iso3, country_b.iso3],
        query.year,
        query.year,
    )
    value_a, value_b = _values_for(response, query.year, country_a.iso3, country_b.iso3)

    missing = [
        name
        for name, value in ((country_a.name, value_a), (country_b.name, value_b))
        if value is None
    ]
    if value_a is None or value_b is None:
        raise QueryError(
            f"No se calcula la comparación porque falta el valor de {', '.join(missing)} "
            f"en {query.year}. No se sustituye por cero ni por otro año."
        )

    return ComparisonResult(
        indicator=_indicator_ref(indicator),
        year=query.year,
        unit=indicator.unit,
        source=source_description(response),
        retrieved_at=datetime.now(UTC),
        country_a=CountryValue(
            entity=_entity_ref(country_a.iso3, country_a.name),
            value=value_a,
        ),
        country_b=CountryValue(
            entity=_entity_ref(country_b.iso3, country_b.name),
            value=value_b,
        ),
        difference=value_a - value_b,
        warnings=comparison_warnings(indicator),
    )


def _values_for(
    response: WorldBankResponse,
    year: int,
    iso3_a: str,
    iso3_b: str,
) -> tuple[float | None, float | None]:
    values = {
        observation.entity_iso3: observation.value
        for observation in response.observations
        if observation.year == year
    }
    return values.get(iso3_a), values.get(iso3_b)


def _entity_ref(iso3: str, name: str) -> EntityRef:
    return EntityRef(iso3=iso3, name=name)


def _indicator_ref(indicator: Indicator) -> IndicatorRef:
    return IndicatorRef(code=indicator.code, name=indicator.name)
