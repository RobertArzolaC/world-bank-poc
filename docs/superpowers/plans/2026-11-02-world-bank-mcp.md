# World Bank MCP PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a local stdio MCP server that answers controlled World Bank indicator queries and equivalent country comparisons, rejecting invalid requests before calling the API.

**Architecture:** A small Python package separates the catalog, Pydantic I/O models, business rules, the `httpx` client, and the MCP tool surface. `server.py` at the repository root is the absolute-path launcher the agent executes; it starts the official MCP SDK over stdio. No FastAPI, HTTP server, database, or authentication.

**Tech Stack:** Python 3.14, `uv`, `mcp>=2.3` (`MCPServer`, formerly `FastMCP`), `pydantic>=2.12`, `httpx>=0.28`, `pytest` + `pytest-asyncio`, `ruff`.

**Spec:** `docs/summary.pdf` (PoC Python para consultar el Banco Mundial con MCP).

**Status:** Implemented on 2026-11-02. The suite now has 76 tests with 100% line and
branch coverage; it includes the configurable rules layer (`rules.yaml`, validation, CLI,
and the `worldbank://catalog` resource).

## Global Constraints

- Demo entities only: Perú (`PER`), Chile (`CHL`), Colombia (`COL`), Estados Unidos (`USA`), China (`CHN`), Mundo (`WLD`).
- Demo indicators only, `source=2` (WDI): `SP.POP.TOTL`, `NY.GDP.MKTP.CD`, `NY.GDP.PCAP.CD`.
- Years: 1960 through the current year; series ranges of at most 10 years inclusive.
- Never substitute a missing value with zero or another year.
- Never compute a comparison when either value is missing.
- Reject Mundo in `compare_countries`; allow it in `get_indicator_series`.
- Every successful result carries value, indicator, entity, year, unit, source, retrieval timestamp, and relevant warnings.
- Tool inputs are closed: no URL, domain, endpoint, or arbitrary field parameters.
- Logs go to stderr; stdout belongs to the MCP protocol.
- Tests never call the real World Bank API.

## Review Focus

- A tool argument arrives as a capitalized or accented country name (`Perú`, `United States`): it must resolve or fail clearly, never reach the API unresolved.
- The API returns `null` for an in-range year or omits the record entirely: both are reported as missing, not as an error and not as zero.
- The API returns a non-200 status, malformed JSON, or its `{"message": ...}` error shape: the tool reports the problem without inventing values.
- A comparison request names the same country twice: reject it with a clear message instead of returning a meaningless zero.
- `end_year` is earlier than `start_year` or the range exceeds 10 years: reject before any network call.

---

### Task 1: Project scaffolding and dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Delete: `main.py`
- Create: `world_bank_mcp/__init__.py`

**Interfaces:**
- Produces: an installable package importable as `world_bank_mcp`, with runtime and dev dependencies resolvable via `uv sync`.

- [x] **Step 1: Replace `pyproject.toml`**

Set `requires-python = ">=3.12"`, runtime dependencies `httpx>=0.28.1`, `mcp>=2.3,<3`, `pydantic>=2.12`, and a `dev` dependency group with `pytest>=8.3`, `pytest-asyncio>=1.0`, `ruff>=0.8`. Configure pytest with `asyncio_mode = "auto"` and ruff with line length 100, target `py312`.

- [x] **Step 2: Delete the placeholder entry point**

Remove `main.py`; it only prints a greeting and would be dead code.

- [x] **Step 3: Create the package marker**

Create `world_bank_mcp/__init__.py` with the package docstring and `__version__ = "0.1.0"`.

- [x] **Step 4: Install and verify**

Run: `uv sync`
Expected: lock file created and the virtual environment resolves successfully.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore world_bank_mcp/__init__.py
git rm main.py
git commit -m "chore: scaffold world bank mcp package"
```

---

### Task 2: Catalog, models, and rules

**Files:**
- Create: `world_bank_mcp/catalog.py`
- Create: `world_bank_mcp/models.py`
- Create: `world_bank_mcp/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Produces:
  - `catalog.Entity(iso3: str, name: str, is_aggregate: bool)`
  - `catalog.Indicator(code: str, name: str, unit: str, warnings: tuple[str, ...])`
  - `catalog.resolve_entity(raw: str) -> Entity`
  - `catalog.resolve_indicator(raw: str) -> Indicator`
  - `catalog.MIN_YEAR`, `catalog.MAX_YEAR`, `catalog.MAX_RANGE_YEARS`
  - `models.SeriesQuery(entity: str, indicator: str, start_year: int, end_year: int)`
  - `models.ComparisonQuery(country_a: str, country_b: str, indicator: str, year: int)`
  - `models.SeriesResult`, `models.ComparisonResult`
  - `rules.QueryError(ValueError)`
  - `rules.ensure_comparable(a: Entity, b: Entity) -> None`
  - `rules.series_warnings(indicator: Indicator) -> list[str]`
  - `rules.comparison_warnings(indicator: Indicator) -> list[str]`

- [x] **Step 1: Write failing tests for catalog and rules**

Create `tests/test_rules.py` covering: `resolve_entity("Perú")` and `resolve_entity("per")` return `PER`; `resolve_entity("Marte")` raises `QueryError`; `resolve_indicator("PIB per cápita")` resolves to `NY.GDP.PCAP.CD`; `ensure_comparable(WLD, PER)` raises; `ensure_comparable(PER, PER)` raises; every warning set includes the temporality warning and the nominal-GDP warning only for GDP indicators.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError` for `world_bank_mcp.catalog`.

- [x] **Step 3: Implement the catalog**

Define the six entities with Spanish names, ISO3 codes, alias sets, and an `is_aggregate` flag for `WLD`. Define the three indicators with Spanish names, units (`personas`, `USD corrientes`, `USD corrientes por habitante`), and indicator-specific warnings. Normalize lookups by stripping accents with `unicodedata`, casefolding, and collapsing whitespace.

- [x] **Step 4: Implement the Pydantic models**

`SeriesQuery` normalizes `start_year`/`end_year` (defaulting the end to the start), rejects out-of-range years, inverted ranges, and ranges longer than 10 years. `ComparisonQuery` does the same for one year. `SeriesResult` contains `indicator` (code/name), `entity` (iso3/name), `unit`, `source`, `retrieved_at`, `series` (`year`, `value`), `missing_years`, and `warnings`. `ComparisonResult` contains `indicator`, `year`, `unit`, `source`, `retrieved_at`, `country_a`, `country_b`, `difference`, and `warnings`.

- [x] **Step 5: Implement the rules**

`ensure_comparable` rejects aggregates and identical entities. `series_warnings` and `comparison_warnings` prepend the temporality warning, append the indicator warnings, and add the comparison arithmetic warning. Raise `QueryError` with messages in Spanish.

- [x] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules.py -v`
Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add world_bank_mcp/catalog.py world_bank_mcp/models.py world_bank_mcp/rules.py tests/test_rules.py
git commit -m "feat: add world bank catalog models and rules"
```

---

### Task 3: World Bank HTTP client

**Files:**
- Create: `world_bank_mcp/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Produces:
  - `client.WorldBankAPIError(RuntimeError)`
  - `client.Observation(entity_iso3: str, year: int, value: float | None)`
  - `client.WorldBankResponse(observations: list[Observation], dataset_last_updated: date | None)`
  - `client.WorldBankClient(http: httpx.AsyncClient | None = None)`
  - `WorldBankClient.fetch(indicator: str, entities: list[str], start_year: int, end_year: int) -> WorldBankResponse`

- [x] **Step 1: Write failing client tests**

Using `httpx.MockTransport`, cover: a two-element payload is parsed into observations and the metadata date; a `{"message": [...]}` payload raises `WorldBankAPIError`; a non-200 status raises; a malformed payload raises; a `null` value becomes `Observation(value=None)`. Assert the request path uses `https://api.worldbank.org/v2/country/PER;CHL/indicator/NY.GDP.PCAP.CD` and includes `source=2` and the year range.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError` for `world_bank_mcp.client`.

- [x] **Step 3: Implement the client**

Build the URL from constants only, join entity codes with `;`, send `format=json`, `source=2`, `date=start:end`, `per_page=200`, and a 15-second timeout. Reject responses that are not a two-element list with a dict metadata first element and a list-or-null second element. Convert rows defensively; accept numeric values only, map anything else to `None`. Wrap `httpx.HTTPError` and JSON decoding failures in `WorldBankAPIError` with actionable Spanish messages.

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add world_bank_mcp/client.py tests/test_client.py
git commit -m "feat: add world bank api client"
```

---

### Task 4: Series and comparison services

**Files:**
- Create: `world_bank_mcp/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: catalog, models, rules, and `WorldBankClient`.
- Produces:
  - `service.get_indicator_series(query: SeriesQuery, client: WorldBankClient | None = None) -> SeriesResult`
  - `service.compare_countries(query: ComparisonQuery, client: WorldBankClient | None = None) -> ComparisonResult`

- [x] **Step 1: Write the five reproducible tests**

Create `tests/test_service.py` covering: (1) a correct population query returns the value, `personas`, the WDI source, a timezone-aware timestamp, and no missing years; (2) a correct GDP-per-capita comparison returns both values and their difference; (3) an inverted range is rejected before the mock handler is called; (4) a Perú-vs-Mundo comparison is rejected before the mock handler is called; (5) a payload with a `null` year preserves `None` and reports the year in `missing_years`. Add a sixth test that a comparison with a missing value raises `QueryError`.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError` for `world_bank_mcp.service`.

- [x] **Step 3: Implement the series service**

Resolve entity and indicator, fetch the range once, index observations by ISO3 and year, build one `SeriesPoint` per requested year in ascending order, and derive `missing_years` from `None` values. Populate source as `Banco Mundial — World Development Indicators (source=2)` plus the dataset update date when available. Set `retrieved_at` to `datetime.now(UTC)`.

- [x] **Step 4: Implement the comparison service**

Resolve both entities, call `ensure_comparable`, fetch both countries in one request, and read the exact year for each. If either value is `None`, raise `QueryError` naming the missing country and year. Otherwise compute `difference = country_a.value - country_b.value` with the shared unit and warnings.

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_service.py -v`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add world_bank_mcp/service.py tests/test_service.py
git commit -m "feat: implement series and comparison services"
```

---

### Task 5: MCP tools and stdio launcher

**Files:**
- Create: `world_bank_mcp/server.py`
- Create: `server.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Produces:
  - MCP tools `get_indicator_series` and `compare_countries` with flat arguments and Pydantic output schemas.
  - `world_bank_mcp.server.main() -> None`, running stdio.
  - root `server.py`, executable as `python /absolute/path/server.py`.

- [x] **Step 1: Write failing tool tests**

Test that the tool functions validate arguments before touching the network: an invalid indicator raises `ToolError`, a World comparison raises `ToolError`, and an inverted range raises `ToolError`. Use `monkeypatch` on the service module client factory so no real request is attempted.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError` for `world_bank_mcp.server`.

- [x] **Step 3: Implement the MCP server**

Create `MCPServer("world-bank-mcp", instructions=...)`. Register both tools with Spanish descriptions that state the allowed entities, indicators, year bounds, units, and the no-substitution/no-World-comparison rules. Convert `pydantic.ValidationError` and `QueryError` into `ToolError` with the original Spanish message. Configure logging to stderr. `main()` calls `mcp.run()`.

- [x] **Step 4: Create the root launcher**

`server.py` imports `main` from `world_bank_mcp.server` and calls it under `if __name__ == "__main__"`, so an absolute path works without `PYTHONPATH`.

- [x] **Step 5: Verify the stdio handshake**

Run a short MCP client script over stdio that lists tools and calls `get_indicator_series` against a mocked transport. Expected: two tools, no stdout logging, clean shutdown.

- [x] **Step 6: Commit**

```bash
git add world_bank_mcp/server.py server.py tests/test_tools.py
git commit -m "feat: expose world bank tools over stdio mcp"
```

---

### Task 6: README, demo guide, and final verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: install/run instructions, MCP configuration, version list, demo question table, and learning note.

- [x] **Step 1: Write the README**

Document `uv sync`, `uv run python server.py`, the absolute-path stdio configuration, the two tools, the six rules, the five tests, and the ten demo questions with expected behavior. Include a short "nota de aprendizaje" section for the Bluefire follow-up and keep the OpenCode reference to a single generic configuration example.

- [x] **Step 2: Run the full quality gate**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: all tests pass, no lint errors, formatting clean.

- [x] **Step 3: Smoke-test the server**

Start `uv run python server.py` with a stdio client, list tools, call one valid query, and stop it. Expected: valid JSON result with value, unit, source, timestamp, and warnings.

- [x] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document world bank mcp setup and demo"
```
