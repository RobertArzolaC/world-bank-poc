"""Load, validate, and inspect the user-managed rules file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from world_bank_mcp.catalog import Catalog, Entity, Indicator, normalize_alias
from world_bank_mcp.constants import MAX_CATALOG_ENTITIES, MAX_CATALOG_INDICATORS
from world_bank_mcp.errors import RulesConfigError

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "rules.yaml"
RULES_FILE_ENV = "WORLD_BANK_RULES_FILE"
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Iso3Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z]{3}$")]
IndicatorCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[A-Z0-9][A-Z0-9.]*$"),
]


class EntityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iso3: Iso3Code
    name: NonEmptyText
    aliases: list[str] = Field(default_factory=list)
    aggregate: bool = False

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, aliases: list[str]) -> list[str]:
        return _clean_strings(aliases, "alias")


class IndicatorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: IndicatorCode
    name: NonEmptyText
    unit: NonEmptyText
    aliases: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, aliases: list[str]) -> list[str]:
        return _clean_strings(aliases, "alias")

    @field_validator("warnings")
    @classmethod
    def _clean_warnings(cls, warnings: list[str]) -> list[str]:
        return _clean_strings(warnings, "advertencia")


class RulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    entities: list[EntityConfig] = Field(min_length=1, max_length=MAX_CATALOG_ENTITIES)
    indicators: list[IndicatorConfig] = Field(
        min_length=1,
        max_length=MAX_CATALOG_INDICATORS,
    )

    @model_validator(mode="after")
    def _validate_catalog(self) -> RulesConfig:
        _ensure_unique((entity.iso3 for entity in self.entities), "ISO3")
        _ensure_unique((indicator.code for indicator in self.indicators), "código de indicador")

        if not any(not entity.aggregate for entity in self.entities):
            raise ValueError("Debe existir al menos una entidad no agregada (un país).")

        owners: dict[str, str] = {}
        for entity in self.entities:
            owner = f"entidad {entity.iso3}"
            _register(owners, entity.iso3, owner)
            _register(owners, entity.name, owner)
            for alias in entity.aliases:
                _register(owners, alias, owner)

        for indicator in self.indicators:
            owner = f"indicador {indicator.code}"
            _register(owners, indicator.code, owner)
            _register(owners, indicator.name, owner)
            for alias in indicator.aliases:
                _register(owners, alias, owner)

        return self

    def to_catalog(self) -> Catalog:
        return Catalog(
            entities=tuple(
                Entity(
                    iso3=entity.iso3,
                    name=entity.name,
                    aliases=tuple(entity.aliases),
                    is_aggregate=entity.aggregate,
                )
                for entity in self.entities
            ),
            indicators=tuple(
                Indicator(
                    code=indicator.code,
                    name=indicator.name,
                    unit=indicator.unit,
                    aliases=tuple(indicator.aliases),
                    warnings=tuple(indicator.warnings),
                )
                for indicator in self.indicators
            ),
        )


def default_rules_path() -> Path:
    override = os.getenv(RULES_FILE_ENV)
    return Path(override).expanduser() if override else DEFAULT_RULES_PATH


def load_catalog(path: Path | None = None) -> Catalog:
    """Read and validate a rules file, returning a ready-to-use catalog."""
    rules_path = path or default_rules_path()
    try:
        text = rules_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RulesConfigError(f"No se pudo leer {rules_path}: {exc}") from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulesConfigError(f"{rules_path}: YAML inválido: {exc}") from exc

    if not isinstance(raw, dict):
        raise RulesConfigError(f"{rules_path}: la raíz debe ser un objeto YAML.")

    try:
        rules = RulesConfig.model_validate(raw)
    except ValidationError as exc:
        raise RulesConfigError(_format_validation_error(rules_path, exc)) from exc

    return rules.to_catalog()


def _clean_strings(values: list[str], label: str) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        text = value.strip()
        if not text:
            raise ValueError(f"El campo {label} no puede estar vacío.")
        cleaned.append(text)
    return cleaned


def _ensure_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{label} duplicado: {value}.")
        seen.add(value)


def _register(owners: dict[str, str], token: str, owner: str) -> None:
    key = normalize_alias(token)
    previous = owners.get(key)
    if previous is not None and previous != owner:
        raise ValueError(f"El alias {token!r} colisiona entre {previous} y {owner}.")
    owners[key] = owner


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "(raíz)"
        lines.append(f"  - {location}: {error['msg']}")
    return f"{path} no es válido:\n" + "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m world_bank_mcp.config",
        description="Valida o genera el esquema del catálogo editable de la PoC.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Valida un archivo de reglas.")
    check.add_argument("path", nargs="?", type=Path, default=None)

    schema = subparsers.add_parser("schema", help="Genera el JSON Schema del archivo de reglas.")
    schema.add_argument("path", nargs="?", type=Path, default=None)

    args = parser.parse_args(argv)

    if args.command == "check":
        try:
            catalog = load_catalog(args.path)
        except RulesConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"OK: {len(catalog.entities)} entidades, {len(catalog.indicators)} indicadores")
        return 0

    schema_data = RulesConfig.model_json_schema()
    schema_data["$schema"] = SCHEMA_URI
    text = json.dumps(schema_data, ensure_ascii=False, indent=2) + "\n"
    if args.path is None:
        sys.stdout.write(text)
    else:
        args.path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
