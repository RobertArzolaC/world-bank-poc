# Configurable Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Move the demo catalog and warning texts out of Python into a validated `rules.yaml`, while keeping correctness invariants and context size under control.

**Architecture:** A Pydantic-validated YAML file defines entities, indicators, aliases, units, and additional warnings. `config.py` loads and validates it, `catalog.py` becomes a `Catalog` runtime object built from that config, and `server.py` derives bounded tool descriptions plus a `worldbank://catalog` MCP resource from the validated catalog. Invariants (years, missing values, equivalent comparison, no arbitrary URLs) stay in code.

**Tech Stack:** Python 3.14, `uv`, `mcp>=2.3`, Pydantic 2, `httpx`, PyYAML, pytest, pytest-cov, ruff.

**Spec:** `docs/summary.pdf` and the design discussion in this session. The previous implementation plan is `docs/superpowers/plans/2026-11-02-world-bank-mcp.md`.

**Status:** Implemented on 2026-11-02. Quality gate: 76 tests passing, 100% line and branch coverage, `ruff check` and `ruff format --check` clean, plus a live stdio handshake that lists two tools and the `worldbank://catalog` resource.

## Global Constraints

- Only the catalog and additional warning texts are user-editable. Correctness invariants remain in code.
- Years stay fixed at 1960–current and a maximum range of 10 years.
- Missing values are never replaced; comparisons require both values.
- Aggregates remain queryable in series but never comparable.
- The World Bank domain, WDI source, timeout, and page size stay in code.
- Config validation is strict: unknown fields, duplicates, invalid codes, and invalid aliases fail with an actionable message.
- An invalid config must fail fast at startup, never expose a partial catalog.
- Tool descriptions must stay bounded even if the catalog grows; the full catalog lives in `worldbank://catalog`.
- Tests must not call the real API.
- Coverage target: 100% lines and branches.

## Review Focus

- A malformed or semantically invalid YAML must produce a message naming the file and field, not a traceback.
- Duplicate aliases across entities or indicators must be rejected before they silently redirect a lookup.
- An aggregate entity other than `WLD` must still be rejected in comparisons.
- A catalog larger than the description budget must still produce a short tool description that points to the resource.
- The lazy catalog load must not create an import cycle between `catalog.py` and `config.py`.
- Restarting is required after a catalog change; documentation must say so.

---

### Task 1: YAML config, validation, and CLI

**Files:**
- Create: `rules.yaml`
- Create: `world_bank_mcp/config.py`
- Modify: `world_bank_mcp/errors.py`
- Modify: `world_bank_mcp/constants.py`
- Modify: `pyproject.toml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `config.EntityConfig`, `config.IndicatorConfig`, `config.RulesConfig`
  - `config.DEFAULT_RULES_PATH`, `config.RULES_FILE_ENV`
  - `config.default_rules_path() -> Path`
  - `config.load_catalog(path: Path | None = None) -> Catalog`
  - `config.main(argv: list[str] | None = None) -> int`
  - `errors.RulesConfigError(ValueError)`
  - `constants.MAX_CATALOG_ENTITIES`, `constants.MAX_CATALOG_INDICATORS`

- [x] **Step 1: Write failing tests**

Cover a valid YAML round-trip, unknown fields, duplicate ISO3/code/alias, invalid ISO3/code, empty lists, malformed YAML, missing file, non-mapping root, `check` success/failure, `schema` to stdout/file, and `WORLD_BANK_RULES_FILE` override.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError` for `world_bank_mcp.config`.

- [x] **Step 3: Add PyYAML**

Add `pyyaml>=6.0` as a runtime dependency with `uv add pyyaml`.

- [x] **Step 4: Implement the config models and loader**

Use `ConfigDict(extra="forbid")`, ISO3/code regexes, non-empty names and units, normalized alias collision checks, at least one non-aggregate entity, and catalog size caps. Convert Pydantic `ValidationError` into `RulesConfigError` with `path → field: message` lines. Read YAML with `yaml.safe_load`.

- [x] **Step 5: Implement the CLI**

`python -m world_bank_mcp.config check [path]` prints `OK: N entidades, M indicadores` or an error and exit code 1. `python -m world_bank_mcp.config schema [path]` writes the JSON Schema with the 2020-12 `$schema` key.

- [x] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

---

### Task 2: Catalog runtime and invariants

**Files:**
- Modify: `world_bank_mcp/catalog.py`
- Modify: `world_bank_mcp/constants.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces:
  - `catalog.Catalog(entities, indicators)` with `resolve_entity`, `resolve_indicator`, and `to_dict`
  - `catalog.normalize_alias(value: str) -> str`
  - `catalog.get_catalog() -> Catalog`
  - `catalog.set_catalog(catalog: Catalog | None) -> None`
  - `catalog.resolve_entity(raw: str) -> Entity`
  - `catalog.resolve_indicator(raw: str) -> Indicator`

- [x] **Step 1: Write failing catalog tests**

Cover default catalog counts, name/alias/ISO3 resolution, unknown entity/indicator messages, aggregate lookup, `to_dict`, and singleton replacement with `set_catalog`.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_catalog.py -v`
Expected: FAIL because `Catalog` does not exist.

- [x] **Step 3: Implement `Catalog` and remove hardcoded data**

Move the current entities and indicators into `rules.yaml`. Build normalized indexes in `Catalog.__post_init__`. Keep module-level `resolve_entity`/`resolve_indicator` as lazy wrappers around `get_catalog()` so existing service and rules imports keep working without an import cycle.

- [x] **Step 4: Preserve invariants**

`rules.py` continues to enforce years, comparable entities, and warning assembly. Aggregate status now comes from config, so any entity marked `aggregate: true` is rejected by `ensure_comparable`, not only `WLD`.

- [x] **Step 5: Run tests**

Run: `uv run pytest tests/test_catalog.py tests/test_rules.py tests/test_service.py -v`
Expected: PASS.

---

### Task 3: Bounded tool descriptions and catalog resource

**Files:**
- Modify: `world_bank_mcp/server.py`
- Test: `tests/test_server.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Consumes: `catalog.get_catalog()`, `Catalog.to_dict()`.
- Produces:
  - Short `SERIES_DESCRIPTION` / `COMPARISON_DESCRIPTION` that summarize large catalogs.
  - MCP resource `worldbank://catalog` returning JSON.

- [x] **Step 1: Write failing tests**

Assert that the resource exists and returns the six entities/three indicators, and that `_summarize` truncates a large list and points to the resource.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL for the missing resource and summary helper.

- [x] **Step 3: Implement the bounded descriptions and resource**

Load the catalog once at import, derive display lists from it, and cap each list at 10 items. Register `@mcp.resource("worldbank://catalog", mime_type="application/json")` returning `json.dumps(CATALOG.to_dict(), ensure_ascii=False, indent=2)`.

- [x] **Step 4: Run protocol and server tests**

Run: `uv run pytest tests/test_server.py tests/test_protocol.py -v`
Expected: PASS; stdio still lists exactly two tools.

---

### Task 4: Documentation, coverage, commit, and push

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-11-02-world-bank-mcp.md`
- Generate: `rules.schema.json`

- [x] **Step 1: Document rule management**

Explain what is editable, what is invariant, how to run `check`/`schema`, the restart requirement, and the `worldbank://catalog` resource. Note that invalid config prevents startup.

- [x] **Step 2: Generate the schema**

Run: `uv run python -m world_bank_mcp.config schema rules.schema.json`
Expected: file created and `rules.yaml` references it in its header comment.

- [x] **Step 3: Run the quality gate**

Run: `uv run pytest --cov=world_bank_mcp --cov-branch --cov-report=term-missing -q && uv run ruff check . && uv run ruff format --check .`
Expected: 100% lines and branches, all checks pass.

- [x] **Step 4: Smoke-test stdio**

List tools, read `worldbank://catalog`, and run one query against the mock/real API as appropriate. Confirm two tools plus one resource.

- [x] **Step 5: Commit and push**

```bash
git add rules.yaml rules.schema.json world_bank_mcp tests README.md pyproject.toml uv.lock .gitignore docs
git commit -m "feat: move world bank catalog rules to validated yaml"
git push origin master
```
