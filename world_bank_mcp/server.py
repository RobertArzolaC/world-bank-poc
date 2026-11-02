"""MCP tool surface for the World Bank PoC, served over stdio."""

from __future__ import annotations

import json
import logging
import sys
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from world_bank_mcp import __version__
from world_bank_mcp.catalog import Catalog, get_catalog
from world_bank_mcp.constants import MAX_RANGE_YEARS, MAX_YEAR, MIN_YEAR, SOURCE_LABEL
from world_bank_mcp.errors import QueryError, WorldBankAPIError
from world_bank_mcp.models import ComparisonQuery, ComparisonResult, SeriesQuery, SeriesResult
from world_bank_mcp.service import compare_countries as compare_countries_service
from world_bank_mcp.service import get_indicator_series as get_indicator_series_service

logger = logging.getLogger(__name__)

DESCRIPTION_LIST_LIMIT = 10
CATALOG: Catalog = get_catalog()


def _summarize(values: list[str], limit: int = DESCRIPTION_LIST_LIMIT) -> str:
    if len(values) <= limit:
        return ", ".join(values)
    remaining = len(values) - limit
    return (
        f"{', '.join(values[:limit])} y {remaining} más (consulta el recurso worldbank://catalog)"
    )


ENTITY_LIST = _summarize([entity.name for entity in CATALOG.entities])
COUNTRY_LIST = _summarize([entity.name for entity in CATALOG.entities if not entity.is_aggregate])
INDICATOR_LIST = _summarize(
    [f"{indicator.code} ({indicator.name}, {indicator.unit})" for indicator in CATALOG.indicators]
)
INDICATOR_CODES = _summarize([indicator.code for indicator in CATALOG.indicators])

SERIES_DESCRIPTION = f"""\
Devuelve la serie de un indicador del Banco Mundial para una sola entidad.

Entidades permitidas: {ENTITY_LIST}.
Indicadores permitidos: {INDICATOR_LIST}. Fuente fija: World Development
Indicators (source=2).

Acepta un año o un rango de hasta {MAX_RANGE_YEARS} años entre {MIN_YEAR} y {MAX_YEAR}.
Los años sin dato se devuelven como null y se listan en missing_years: nunca se
sustituyen por cero ni por otro año. Los valores son la serie disponible hoy, no
una reconstrucción de lo que se conocía en una fecha pasada. Incluye valor,
indicador, entidad, año, unidad, fuente, fecha de consulta y advertencias.
El catálogo completo está en el recurso worldbank://catalog.
"""

COMPARISON_DESCRIPTION = f"""\
Compara el mismo indicador y el mismo año para dos países distintos.

Países permitidos: {COUNTRY_LIST}. Los agregados no pueden participar en una
comparación; consúltalos individualmente con get_indicator_series. Indicadores
permitidos: {INDICATOR_LIST} (fuente WDI, source=2). El año debe estar entre
{MIN_YEAR} y {MAX_YEAR}.

Si falta cualquiera de los dos valores, no se calcula la diferencia y se informa
el faltante. Devuelve ambos valores, la diferencia en la misma unidad, la fuente,
la fecha de consulta y las advertencias de interpretación.
El catálogo completo está en el recurso worldbank://catalog.
"""

READ_ONLY_TOOL = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=True,
)

mcp = MCPServer(
    "world-bank-mcp",
    title="Banco Mundial (PoC)",
    description="Consultas controladas de indicadores del Banco Mundial.",
    version=__version__,
    instructions=(
        "Este servidor solo consulta la API pública del Banco Mundial (WDI, source=2) "
        "para las entidades e indicadores del catálogo de la demo. Usa las herramientas "
        "en lugar de inventar cifras. Si una regla falla, explica el mensaje devuelto. "
        "No presentes el PIB nominal como PIB real ni el PIB per cápita como salario, y "
        "no afirmes qué datos se conocían en una fecha pasada: la serie es la disponible "
        f"hoy. Fuente: {SOURCE_LABEL}."
    ),
)


@mcp.resource(
    "worldbank://catalog",
    name="Catálogo del Banco Mundial",
    description="Entidades, indicadores, alias, unidades y advertencias del catálogo validado.",
    mime_type="application/json",
)
def catalog_resource() -> str:
    payload = get_catalog().to_dict()
    payload["limits"] = {
        "min_year": MIN_YEAR,
        "max_year": MAX_YEAR,
        "max_range_years": MAX_RANGE_YEARS,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(title="Serie de un indicador", description=SERIES_DESCRIPTION, annotations=READ_ONLY_TOOL)
async def get_indicator_series(
    entity: Annotated[
        str,
        Field(description=f"Entidad del catálogo: {ENTITY_LIST}."),
    ],
    indicator: Annotated[
        str,
        Field(description=f"{INDICATOR_CODES} (código o nombre)."),
    ],
    start_year: Annotated[int, Field(description=f"Año inicial entre {MIN_YEAR} y {MAX_YEAR}.")],
    end_year: Annotated[
        int | None,
        Field(description="Año final opcional; si se omite, se consulta solo start_year."),
    ] = None,
) -> SeriesResult:
    """Consulta una serie individual y reporta sus años faltantes."""
    logger.info(
        "get_indicator_series entity=%r indicator=%r start_year=%s end_year=%s",
        entity,
        indicator,
        start_year,
        end_year,
    )
    try:
        query = SeriesQuery(
            entity=entity,
            indicator=indicator,
            start_year=start_year,
            end_year=end_year,
        )
        return await get_indicator_series_service(query)
    except (ValidationError, QueryError, WorldBankAPIError) as exc:
        logger.warning("get_indicator_series rejected: %s", _error_message(exc))
        raise _tool_error(exc) from None


@mcp.tool(
    title="Comparar dos países",
    description=COMPARISON_DESCRIPTION,
    annotations=READ_ONLY_TOOL,
)
async def compare_countries(
    country_a: Annotated[
        str,
        Field(description=f"Primer país: {COUNTRY_LIST}."),
    ],
    country_b: Annotated[
        str,
        Field(description=f"Segundo país: {COUNTRY_LIST}."),
    ],
    indicator: Annotated[
        str,
        Field(description=f"Indicador compartido: {INDICATOR_CODES}."),
    ],
    year: Annotated[int, Field(description=f"Año único entre {MIN_YEAR} y {MAX_YEAR}.")],
) -> ComparisonResult:
    """Compara el mismo indicador y año para dos países distintos."""
    logger.info(
        "compare_countries country_a=%r country_b=%r indicator=%r year=%s",
        country_a,
        country_b,
        indicator,
        year,
    )
    try:
        query = ComparisonQuery(
            country_a=country_a,
            country_b=country_b,
            indicator=indicator,
            year=year,
        )
        return await compare_countries_service(query)
    except (ValidationError, QueryError, WorldBankAPIError) as exc:
        logger.warning("compare_countries rejected: %s", _error_message(exc))
        raise _tool_error(exc) from None


def _error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        messages: list[str] = []
        for error in exc.errors():
            message = str(error.get("msg", "")).removeprefix("Value error, ")
            messages.append(message)
        return "; ".join(messages) or str(exc)
    return str(exc)


def _tool_error(exc: Exception) -> ToolError:
    return ToolError(_error_message(exc))


def main() -> None:
    """Run the MCP server over stdio. Logs must never reach stdout."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    logger.info("Iniciando world-bank-mcp %s por stdio", __version__)
    mcp.run()
