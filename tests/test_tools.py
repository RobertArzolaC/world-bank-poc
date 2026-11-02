import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from world_bank_mcp import service
from world_bank_mcp.client import WorldBankClient
from world_bank_mcp.server import compare_countries, get_indicator_series


def fake_client(payload) -> WorldBankClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return WorldBankClient(http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_tool_returns_a_structured_series(monkeypatch):
    payload = [
        {"lastupdated": "2026-10-08"},
        [{"countryiso3code": "PER", "date": "2023", "value": 12345}],
    ]
    monkeypatch.setattr(service, "default_client", lambda: fake_client(payload))

    result = await get_indicator_series(
        entity="Perú",
        indicator="SP.POP.TOTL",
        start_year=2023,
    )

    assert result.entity.iso3 == "PER"
    assert result.series[0].value == 12345.0
    assert result.unit == "personas"


async def test_tool_rejects_unknown_indicator_with_a_clear_message():
    with pytest.raises(ToolError, match="catálogo"):
        await get_indicator_series(entity="Perú", indicator="PIB real", start_year=2023)


async def test_tool_rejects_world_comparison():
    with pytest.raises(ToolError, match="Mundo"):
        await compare_countries(
            country_a="Perú",
            country_b="Mundo",
            indicator="SP.POP.TOTL",
            year=2023,
        )


async def test_tool_rejects_inverted_range():
    with pytest.raises(ToolError, match="invertido"):
        await get_indicator_series(
            entity="Perú",
            indicator="SP.POP.TOTL",
            start_year=2025,
            end_year=2020,
        )


async def test_tool_rejects_out_of_bounds_year():
    with pytest.raises(ToolError, match="fuera del rango"):
        await get_indicator_series(
            entity="Perú",
            indicator="SP.POP.TOTL",
            start_year=1959,
        )
