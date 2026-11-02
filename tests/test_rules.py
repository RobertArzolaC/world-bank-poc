import pytest

from world_bank_mcp.catalog import resolve_entity, resolve_indicator
from world_bank_mcp.constants import MAX_YEAR
from world_bank_mcp.rules import (
    QueryError,
    comparison_warnings,
    ensure_comparable,
    series_warnings,
    validate_year_range,
)


def test_resolve_entity_accepts_names_and_codes():
    assert resolve_entity("Perú").iso3 == "PER"
    assert resolve_entity("per").iso3 == "PER"
    assert resolve_entity("Estados Unidos").iso3 == "USA"
    assert resolve_entity("EE. UU.").iso3 == "USA"
    assert resolve_entity("Mundo").iso3 == "WLD"


def test_resolve_entity_rejects_unknown_entity():
    with pytest.raises(QueryError, match="no está en el catálogo"):
        resolve_entity("Marte")


def test_resolve_indicator_accepts_codes_and_names():
    assert resolve_indicator("PIB per cápita").code == "NY.GDP.PCAP.CD"
    assert resolve_indicator("SP.POP.TOTL").code == "SP.POP.TOTL"
    assert resolve_indicator("PIB nominal").code == "NY.GDP.MKTP.CD"


def test_comparison_rejects_aggregate_and_same_country():
    with pytest.raises(QueryError, match="Mundo"):
        ensure_comparable(resolve_entity("Mundo"), resolve_entity("Perú"))
    with pytest.raises(QueryError, match="misma"):
        ensure_comparable(resolve_entity("Perú"), resolve_entity("Perú"))


def test_warnings_include_temporality_and_indicator_specific_text():
    population = series_warnings(resolve_indicator("SP.POP.TOTL"))
    gdp = series_warnings(resolve_indicator("NY.GDP.MKTP.CD"))

    assert any("serie disponible hoy" in warning for warning in population)
    assert any("PIB real" in warning for warning in gdp)
    assert any("bienestar" in warning for warning in gdp)
    assert not any("PIB real" in warning for warning in population)
    assert any(
        "aritmética" in warning for warning in comparison_warnings(resolve_indicator("SP.POP.TOTL"))
    )
    assert any(
        "dos entidades distintas" in warning
        for warning in comparison_warnings(resolve_indicator("SP.POP.TOTL"))
    )


def test_year_range_accepts_ten_years_and_rejects_eleven():
    validate_year_range(2010, 2019)
    with pytest.raises(QueryError, match="máximo permitido"):
        validate_year_range(2010, 2020)


def test_year_range_rejects_inverted_out_of_bounds_and_too_long():
    with pytest.raises(QueryError, match="invertido"):
        validate_year_range(2025, 2020)
    with pytest.raises(QueryError, match="fuera del rango"):
        validate_year_range(1959, 1960)
    with pytest.raises(QueryError, match="máximo permitido"):
        validate_year_range(2010, MAX_YEAR)
