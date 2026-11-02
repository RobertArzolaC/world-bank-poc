"""Shared constants for the World Bank MCP PoC.

Values that define the demo's policy, the external API contract, or warning
text live here so the catalog, client, rules, and server cannot drift apart.
"""

from datetime import date

# Demo time window.
MIN_YEAR = 1960
MAX_YEAR = date.today().year
MAX_RANGE_YEARS = 10

# World Bank Indicators API v2, World Development Indicators.
WORLD_BANK_BASE_URL = "https://api.worldbank.org/v2"
WDI_SOURCE_ID = "2"
SOURCE_LABEL = "Banco Mundial — World Development Indicators (source=2)"
DEFAULT_TIMEOUT_SECONDS = 15.0
PER_PAGE = 200

# Warning text attached to results.
TEMPORALITY_WARNING = (
    "Los valores corresponden a la serie disponible hoy; no reconstruyen qué información "
    "se conocía en una fecha pasada."
)
COMPARISON_WARNING = (
    "La diferencia es una operación aritmética entre dos valores del mismo indicador, "
    "unidad y año, para dos entidades distintas; no implica causalidad."
)
