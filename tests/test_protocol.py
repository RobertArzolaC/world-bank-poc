import json
import sys
import tempfile
from pathlib import Path

import anyio
import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_client_server_memory_streams

from world_bank_mcp import service
from world_bank_mcp.client import WorldBankClient
from world_bank_mcp.server import mcp

ROOT = Path(__file__).resolve().parents[1]


def fake_client(payload) -> WorldBankClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return WorldBankClient(http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_protocol_lists_tools_and_returns_a_structured_series(monkeypatch):
    payload = [
        {"lastupdated": "2026-10-08"},
        [{"countryiso3code": "PER", "date": "2023", "value": 12345}],
    ]
    monkeypatch.setattr(service, "default_client", lambda: fake_client(payload))

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                mcp._lowlevel_server.run,
                server_streams[0],
                server_streams[1],
                mcp._lowlevel_server.create_initialization_options(),
            )
            async with ClientSession(*client_streams) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {"get_indicator_series", "compare_countries"} <= names

                resources = await session.list_resources()
                assert "worldbank://catalog" in {
                    str(resource.uri) for resource in resources.resources
                }
                catalog_resource = await session.read_resource("worldbank://catalog")
                catalog_payload = json.loads(catalog_resource.contents[0].text)
                assert len(catalog_payload["entities"]) == 6

                result = await session.call_tool(
                    "get_indicator_series",
                    {"entity": "Perú", "indicator": "SP.POP.TOTL", "start_year": 2023},
                )

                assert result.is_error is False
                assert result.structured_content is not None
                assert result.structured_content["series"][0]["value"] == 12345.0
                assert result.structured_content["entity"]["iso3"] == "PER"
            task_group.cancel_scope.cancel()


async def test_protocol_rejects_world_comparison_with_a_tool_error():
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                mcp._lowlevel_server.run,
                server_streams[0],
                server_streams[1],
                mcp._lowlevel_server.create_initialization_options(),
            )
            async with ClientSession(*client_streams) as session:
                await session.initialize()
                result = await session.call_tool(
                    "compare_countries",
                    {
                        "country_a": "Perú",
                        "country_b": "Mundo",
                        "indicator": "SP.POP.TOTL",
                        "year": 2023,
                    },
                )

                assert result.is_error is True
                assert result.content
                assert "Mundo" in result.content[0].text
            task_group.cancel_scope.cancel()


async def test_stdio_launcher_exposes_both_tools_without_touching_the_network():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "server.py")],
        cwd=ROOT,
    )
    stderr = tempfile.TemporaryFile(mode="w+")

    async with stdio_client(params, errlog=stderr) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "get_indicator_series",
                "compare_countries",
            }

            result = await session.call_tool(
                "get_indicator_series",
                {"entity": "Perú", "indicator": "NoExiste", "start_year": 2023},
            )
            assert result.is_error is True
            assert result.content
            assert "catálogo" in result.content[0].text

    stderr.close()
