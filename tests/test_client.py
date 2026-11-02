from datetime import date

import httpx
import pytest

from world_bank_mcp.client import (
    Observation,
    WorldBankAPIError,
    WorldBankClient,
    WorldBankResponse,
    source_description,
)
from world_bank_mcp.constants import SOURCE_LABEL


def make_client(payload, *, status_code: int = 200, captured: list[httpx.Request] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return httpx.Response(status_code, json=payload)

    return WorldBankClient(http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_fetch_parses_observations_and_dataset_date():
    payload = [
        {"page": 1, "pages": 1, "per_page": 50, "lastupdated": "2026-10-08"},
        [
            {
                "countryiso3code": "CHL",
                "date": "2023",
                "value": 17081.5,
            },
            {
                "countryiso3code": "PER",
                "date": "2023",
                "value": 7919.0,
            },
        ],
    ]
    client = make_client(payload)

    response = await client.fetch("NY.GDP.PCAP.CD", ["PER", "CHL"], 2023, 2023)

    assert response.dataset_last_updated == date(2026, 10, 8)
    assert response.observations == [
        Observation("CHL", 2023, 17081.5),
        Observation("PER", 2023, 7919.0),
    ]


async def test_fetch_builds_the_fixed_world_bank_request():
    captured: list[httpx.Request] = []
    client = make_client([{"lastupdated": "2026-10-08"}, []], captured=captured)

    await client.fetch("NY.GDP.PCAP.CD", ["PER", "CHL"], 2022, 2023)

    request = captured[0]
    assert request.url.path == "/v2/country/PER;CHL/indicator/NY.GDP.PCAP.CD"
    assert request.url.params["format"] == "json"
    assert request.url.params["source"] == "2"
    assert request.url.params["date"] == "2022:2023"


async def test_fetch_reports_world_bank_error_payload():
    payload = [
        {
            "message": [
                {
                    "id": "120",
                    "key": "Invalid value",
                    "value": "The provided parameter value is not valid",
                }
            ]
        }
    ]
    client = make_client(payload)

    with pytest.raises(WorldBankAPIError, match="rechazó la consulta"):
        await client.fetch("SP.POP.TOTL", ["PER"], 2023, 2023)


async def test_fetch_reports_http_and_malformed_responses():
    with pytest.raises(WorldBankAPIError, match="HTTP 500"):
        await make_client({}, status_code=500).fetch("SP.POP.TOTL", ["PER"], 2023, 2023)

    with pytest.raises(WorldBankAPIError, match="formato no válido"):
        await make_client({"unexpected": True}).fetch("SP.POP.TOTL", ["PER"], 2023, 2023)


async def test_fetch_keeps_null_values_as_missing():
    payload = [
        {"lastupdated": "2026-10-08"},
        [{"countryiso3code": "PER", "date": "2021", "value": None}],
    ]

    response = await make_client(payload).fetch("SP.POP.TOTL", ["PER"], 2020, 2021)

    assert response.observations == [Observation("PER", 2021, None)]


async def test_fetch_rejects_a_truncated_payload():
    payload = [{"page": 1, "pages": 1, "lastupdated": "2026-10-08"}]

    with pytest.raises(WorldBankAPIError, match="formato no válido"):
        await make_client(payload).fetch("SP.POP.TOTL", ["PER"], 2023, 2023)


async def test_fetch_wraps_transport_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    client = WorldBankClient(http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(WorldBankAPIError, match="No fue posible consultar"):
        await client.fetch("SP.POP.TOTL", ["PER"], 2023, 2023)


async def test_fetch_rejects_a_non_json_body():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html>"))
    client = WorldBankClient(http=httpx.AsyncClient(transport=transport))

    with pytest.raises(WorldBankAPIError, match="formato no válido"):
        await client.fetch("SP.POP.TOTL", ["PER"], 2023, 2023)


@pytest.mark.parametrize(
    "payload",
    [
        ["not-a-metadata-dict", []],
        [{"lastupdated": None}, "not-a-rows-list"],
    ],
)
async def test_fetch_rejects_invalid_metadata_or_rows(payload):
    with pytest.raises(WorldBankAPIError, match="formato no válido"):
        await make_client(payload).fetch("SP.POP.TOTL", ["PER"], 2023, 2023)


@pytest.mark.parametrize(
    "row",
    [
        "not-a-dict",
        {"countryiso3code": "", "date": "2023", "value": 1},
        {"date": "2023", "value": 1},
        {"countryiso3code": "PER", "value": 1},
        {"countryiso3code": "PER", "date": "not-a-year", "value": 1},
        {"countryiso3code": "PER", "date": "2023", "value": True},
        {"countryiso3code": "PER", "date": "2023", "value": "123"},
    ],
)
async def test_fetch_rejects_malformed_observations(row):
    payload = [{"lastupdated": "2026-10-08"}, [row]]

    with pytest.raises(WorldBankAPIError, match="formato no válido"):
        await make_client(payload).fetch("SP.POP.TOTL", ["PER"], 2023, 2023)


@pytest.mark.parametrize("last_updated", [None, 123, "not-a-date"])
async def test_fetch_accepts_missing_rows_and_unparseable_dates(last_updated):
    payload = [{"lastupdated": last_updated}, None]

    response = await make_client(payload).fetch("SP.POP.TOTL", ["PER"], 2023, 2023)

    assert response.observations == []
    assert response.dataset_last_updated is None


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        ([], "sin detalle"),
        (["plain failure"], "plain failure"),
    ],
)
async def test_fetch_describes_world_bank_error_details(messages, expected):
    payload = [{"message": messages}]

    with pytest.raises(WorldBankAPIError, match=expected):
        await make_client(payload).fetch("SP.POP.TOTL", ["PER"], 2023, 2023)


def test_source_description_without_dataset_date():
    response = WorldBankResponse(observations=[], dataset_last_updated=None)

    assert source_description(response) == SOURCE_LABEL


async def test_fetch_creates_its_own_client_when_none_is_injected(monkeypatch):
    class StubAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params):
            assert params["source"] == "2"
            return httpx.Response(
                200,
                json=[
                    {"lastupdated": "2026-10-08"},
                    [{"countryiso3code": "PER", "date": "2023", "value": 12345}],
                ],
            )

    monkeypatch.setattr("world_bank_mcp.client.httpx.AsyncClient", StubAsyncClient)

    response = await WorldBankClient().fetch("SP.POP.TOTL", ["PER"], 2023, 2023)

    assert response.observations == [Observation("PER", 2023, 12345.0)]
