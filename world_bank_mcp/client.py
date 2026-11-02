"""Minimal async client for the World Bank Indicators API v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from world_bank_mcp.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    PER_PAGE,
    SOURCE_LABEL,
    WDI_SOURCE_ID,
    WORLD_BANK_BASE_URL,
)
from world_bank_mcp.errors import WorldBankAPIError

INVALID_RESPONSE = "La API del Banco Mundial devolvió una respuesta con un formato no válido."


@dataclass(frozen=True, slots=True)
class Observation:
    entity_iso3: str
    year: int
    value: float | None


@dataclass(frozen=True, slots=True)
class WorldBankResponse:
    observations: list[Observation]
    dataset_last_updated: date | None


class WorldBankClient:
    """Fetch observations from a fixed World Bank domain.

    Pass an ``httpx.AsyncClient`` to reuse a connection pool or to inject a
    mock transport in tests. Otherwise a short-lived client is created per call.
    """

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self._http = http

    async def fetch(
        self,
        indicator: str,
        entities: list[str],
        start_year: int,
        end_year: int,
    ) -> WorldBankResponse:
        url = f"{WORLD_BANK_BASE_URL}/country/{';'.join(entities)}/indicator/{indicator}"
        params = {
            "format": "json",
            "source": WDI_SOURCE_ID,
            "date": f"{start_year}:{end_year}",
            "per_page": str(PER_PAGE),
        }

        try:
            if self._http is None:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as http:
                    response = await http.get(url, params=params)
            else:
                response = await self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            raise WorldBankAPIError(
                "No fue posible consultar la API del Banco Mundial. Revisa la conexión "
                "e inténtalo de nuevo."
            ) from exc

        if response.status_code != 200:
            raise WorldBankAPIError(
                f"La API del Banco Mundial respondió con HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise WorldBankAPIError(INVALID_RESPONSE) from exc

        return self._parse(payload)

    def _parse(self, payload: Any) -> WorldBankResponse:
        if not isinstance(payload, list) or not payload:
            raise WorldBankAPIError(INVALID_RESPONSE)

        metadata = payload[0]
        if isinstance(metadata, dict) and "message" in metadata:
            raise WorldBankAPIError(
                f"La API del Banco Mundial rechazó la consulta: {_error_detail(metadata)}."
            )
        if len(payload) != 2:
            raise WorldBankAPIError(INVALID_RESPONSE)
        if not isinstance(metadata, dict):
            raise WorldBankAPIError(INVALID_RESPONSE)

        rows = payload[1]
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise WorldBankAPIError(INVALID_RESPONSE)

        observations = [_parse_observation(row) for row in rows]
        return WorldBankResponse(
            observations=observations,
            dataset_last_updated=_parse_date(metadata.get("lastupdated")),
        )


def _parse_observation(row: Any) -> Observation:
    if not isinstance(row, dict):
        raise WorldBankAPIError(INVALID_RESPONSE)

    iso3 = row.get("countryiso3code")
    raw_year = row.get("date")
    raw_value = row.get("value")
    if not isinstance(iso3, str) or not iso3 or not isinstance(raw_year, str):
        raise WorldBankAPIError(INVALID_RESPONSE)

    try:
        year = int(raw_year)
    except ValueError as exc:
        raise WorldBankAPIError(INVALID_RESPONSE) from exc

    if raw_value is None:
        value: float | None = None
    elif isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise WorldBankAPIError(INVALID_RESPONSE)
    else:
        value = float(raw_value)

    return Observation(entity_iso3=iso3, year=year, value=value)


def _parse_date(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _error_detail(metadata: dict[str, Any]) -> str:
    messages = metadata.get("message")
    if not isinstance(messages, list) or not messages:
        return "sin detalle"

    details: list[str] = []
    for message in messages:
        if isinstance(message, dict):
            details.append(str(message.get("value") or message.get("key") or message))
        else:
            details.append(str(message))
    return "; ".join(details) or "sin detalle"


def source_description(response: WorldBankResponse) -> str:
    """Human-readable source with the dataset edition when the API provides it."""
    if response.dataset_last_updated is None:
        return SOURCE_LABEL
    return (
        f"{SOURCE_LABEL}; última actualización del dataset: "
        f"{response.dataset_last_updated.isoformat()}"
    )
