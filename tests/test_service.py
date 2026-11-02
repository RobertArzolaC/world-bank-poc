import httpx
import pytest
from pydantic import ValidationError

from world_bank_mcp.client import WorldBankClient
from world_bank_mcp.errors import QueryError
from world_bank_mcp.models import ComparisonQuery, SeriesQuery
from world_bank_mcp.service import compare_countries, default_client, get_indicator_series


def client_with(payload, *, called: list[bool] | None = None) -> WorldBankClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if called is not None:
            called.append(True)
        return httpx.Response(200, json=payload)

    return WorldBankClient(http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_default_client_builds_a_world_bank_client():
    assert isinstance(default_client(), WorldBankClient)


async def test_series_returns_value_unit_source_and_timestamp():
    payload = [
        {"lastupdated": "2026-10-08"},
        [{"countryiso3code": "PER", "date": "2023", "value": 33845617}],
    ]
    query = SeriesQuery(entity="Perú", indicator="Población total", start_year=2023)

    result = await get_indicator_series(query, client=client_with(payload))

    assert result.entity.iso3 == "PER"
    assert result.indicator.code == "SP.POP.TOTL"
    assert result.series[0].year == 2023
    assert result.series[0].value == 33845617.0
    assert result.missing_years == []
    assert result.unit == "personas"
    assert "World Development Indicators" in result.source
    assert result.retrieved_at.tzinfo is not None
    assert any("serie disponible hoy" in warning for warning in result.warnings)


async def test_comparison_returns_both_values_and_difference():
    payload = [
        {"lastupdated": "2026-10-08"},
        [
            {"countryiso3code": "PER", "date": "2023", "value": 7919.04634828547},
            {"countryiso3code": "CHL", "date": "2023", "value": 17081.5180740049},
        ],
    ]
    query = ComparisonQuery(
        country_a="Perú",
        country_b="Chile",
        indicator="PIB per cápita",
        year=2023,
    )

    result = await compare_countries(query, client=client_with(payload))

    assert result.country_a.value == pytest.approx(7919.04634828547)
    assert result.country_b.value == pytest.approx(17081.5180740049)
    assert result.difference == pytest.approx(7919.04634828547 - 17081.5180740049)
    assert result.unit == "USD corrientes por habitante"
    assert any("no es el salario personal" in warning for warning in result.warnings)


async def test_inverted_range_is_rejected_at_model_construction():
    with pytest.raises(ValidationError, match="invertido"):
        SeriesQuery(entity="Perú", indicator="SP.POP.TOTL", start_year=2025, end_year=2020)


async def test_world_aggregate_is_rejected_in_comparison_before_any_request():
    called: list[bool] = []
    query = ComparisonQuery(
        country_a="Perú",
        country_b="Mundo",
        indicator="SP.POP.TOTL",
        year=2023,
    )

    with pytest.raises(QueryError, match="Mundo"):
        await compare_countries(query, client=client_with([], called=called))

    assert called == []


async def test_world_aggregate_is_allowed_in_a_series():
    payload = [
        {"lastupdated": "2026-10-08"},
        [{"countryiso3code": "WLD", "date": "2023", "value": 8062923417}],
    ]
    query = SeriesQuery(entity="Mundo", indicator="SP.POP.TOTL", start_year=2023)

    result = await get_indicator_series(query, client=client_with(payload))

    assert result.entity.iso3 == "WLD"
    assert result.series[0].value == 8062923417.0
    assert result.missing_years == []


async def test_series_preserves_missing_year_as_null():
    payload = [
        {"lastupdated": "2026-10-08"},
        [
            {"countryiso3code": "PER", "date": "2020", "value": 33304768},
            {"countryiso3code": "PER", "date": "2021", "value": None},
        ],
    ]
    query = SeriesQuery(entity="PER", indicator="SP.POP.TOTL", start_year=2020, end_year=2021)

    result = await get_indicator_series(query, client=client_with(payload))

    assert [point.value for point in result.series] == [33304768.0, None]
    assert result.missing_years == [2021]


async def test_series_marks_an_omitted_record_as_missing():
    payload = [
        {"lastupdated": "2026-10-08"},
        [{"countryiso3code": "PER", "date": "2020", "value": 33304768}],
    ]
    query = SeriesQuery(entity="PER", indicator="SP.POP.TOTL", start_year=2020, end_year=2021)

    result = await get_indicator_series(query, client=client_with(payload))

    assert [point.value for point in result.series] == [33304768.0, None]
    assert result.missing_years == [2021]


async def test_comparison_with_a_missing_value_is_not_computed():
    payload = [
        {"lastupdated": "2026-10-08"},
        [
            {"countryiso3code": "PER", "date": "2023", "value": 7919.0},
            {"countryiso3code": "CHL", "date": "2023", "value": None},
        ],
    ]
    query = ComparisonQuery(
        country_a="Perú",
        country_b="Chile",
        indicator="PIB per cápita",
        year=2023,
    )

    with pytest.raises(QueryError, match="Chile"):
        await compare_countries(query, client=client_with(payload))
