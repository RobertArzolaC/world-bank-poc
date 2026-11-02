import pytest

from world_bank_mcp import catalog
from world_bank_mcp.catalog import Catalog, Entity, Indicator, get_catalog, set_catalog
from world_bank_mcp.errors import QueryError


def test_default_catalog_resolves_names_aliases_and_codes():
    assert catalog.resolve_entity("Perú").iso3 == "PER"
    assert catalog.resolve_entity("peru").iso3 == "PER"
    assert catalog.resolve_entity("WLD").is_aggregate is True
    assert catalog.resolve_indicator("PIB per cápita").code == "NY.GDP.PCAP.CD"
    assert catalog.resolve_indicator("SP.POP.TOTL").unit == "personas"


def test_unknown_entity_and_indicator_raise_clear_errors():
    with pytest.raises(QueryError, match="catálogo"):
        catalog.resolve_entity("Marte")

    with pytest.raises(QueryError, match="catálogo"):
        catalog.resolve_indicator("PIB real")


def test_to_dict_exposes_the_catalog_for_the_resource():
    payload = get_catalog().to_dict()

    assert len(payload["entities"]) == 6
    assert len(payload["indicators"]) == 3
    assert payload["entities"][-1]["aggregate"] is True
    assert payload["indicators"][0]["aliases"] == [
        "poblacion",
        "poblacion total",
        "population",
        "population total",
    ]


def test_set_catalog_replaces_the_singleton_and_none_reloads_default():
    original = get_catalog()
    custom = Catalog(
        entities=(Entity("PER", "Perú"),),
        indicators=(Indicator("SP.POP.TOTL", "Población", "personas"),),
    )

    set_catalog(custom)
    assert catalog.resolve_entity("Perú").iso3 == "PER"
    assert len(get_catalog().entities) == 1

    set_catalog(None)
    assert len(get_catalog().entities) == 6

    set_catalog(original)


def test_large_catalog_error_message_is_bounded():
    entities = tuple(Entity(f"E{index:02d}", f"País {index}") for index in range(12))
    custom = Catalog(
        entities=entities,
        indicators=(Indicator("SP.POP.TOTL", "Población", "personas"),),
    )

    with pytest.raises(QueryError, match="y 2 más"):
        custom.resolve_entity("Marte")
