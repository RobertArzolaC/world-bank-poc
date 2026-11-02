import json
from pathlib import Path

import pytest
import yaml

from world_bank_mcp import config
from world_bank_mcp.errors import RulesConfigError


def valid_rules() -> dict:
    return {
        "version": 1,
        "entities": [
            {"iso3": "PER", "name": "Perú", "aliases": ["peru", "per"]},
            {"iso3": "CHL", "name": "Chile", "aliases": ["chile", "chl"]},
            {"iso3": "WLD", "name": "Mundo", "aliases": ["world"], "aggregate": True},
        ],
        "indicators": [
            {
                "code": "SP.POP.TOTL",
                "name": "Población total",
                "unit": "personas",
                "aliases": ["poblacion"],
            },
            {
                "code": "NY.GDP.MKTP.CD",
                "name": "PIB nominal",
                "unit": "USD corrientes",
                "aliases": ["pib"],
                "warnings": ["El PIB nominal no es PIB real."],
            },
        ],
    }


def write_rules(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_load_catalog_reads_a_valid_yaml(tmp_path):
    path = write_rules(tmp_path, valid_rules())

    catalog = config.load_catalog(path)

    assert catalog.resolve_entity("Perú").iso3 == "PER"
    assert catalog.resolve_entity("world").iso3 == "WLD"
    assert catalog.resolve_indicator("poblacion").code == "SP.POP.TOTL"
    assert catalog.resolve_indicator("PIB nominal").code == "NY.GDP.MKTP.CD"
    assert catalog.indicators[1].warnings == ("El PIB nominal no es PIB real.",)


def test_default_rules_file_loads_the_demo_catalog():
    catalog = config.load_catalog()

    assert len(catalog.entities) == 6
    assert len(catalog.indicators) == 3
    assert catalog.resolve_entity("Mundo").is_aggregate is True
    assert catalog.resolve_indicator("NY.GDP.PCAP.CD").unit == "USD corrientes por habitante"


def test_default_rules_path_honors_the_environment_override(monkeypatch, tmp_path):
    override = tmp_path / "custom.yaml"
    monkeypatch.setenv(config.RULES_FILE_ENV, str(override))

    assert config.default_rules_path() == override


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rules: rules.update({"unexpected": True}),
        lambda rules: rules["entities"][0].update({"unexpected": True}),
        lambda rules: rules["indicators"][0].update({"unexpected": True}),
    ],
)
def test_unknown_fields_are_rejected(tmp_path, mutate):
    rules = valid_rules()
    mutate(rules)

    with pytest.raises(RulesConfigError, match="no es válido"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_duplicate_iso3_is_rejected(tmp_path):
    rules = valid_rules()
    rules["entities"][1]["iso3"] = "PER"

    with pytest.raises(RulesConfigError, match="ISO3 duplicado"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_duplicate_indicator_code_is_rejected(tmp_path):
    rules = valid_rules()
    rules["indicators"][1]["code"] = "SP.POP.TOTL"

    with pytest.raises(RulesConfigError, match="código de indicador duplicado"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_alias_collision_across_entities_is_rejected(tmp_path):
    rules = valid_rules()
    rules["entities"][0]["aliases"].append("Chile")

    with pytest.raises(RulesConfigError, match="colisiona"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_invalid_iso3_is_rejected(tmp_path):
    rules = valid_rules()
    rules["entities"][0]["iso3"] = "per"

    with pytest.raises(RulesConfigError, match="entities.0.iso3"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_invalid_indicator_code_is_rejected(tmp_path):
    rules = valid_rules()
    rules["indicators"][0]["code"] = "sp.pop"

    with pytest.raises(RulesConfigError, match="indicators.0.code"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_empty_entity_or_indicator_list_is_rejected(tmp_path):
    rules = valid_rules()
    rules["entities"] = []

    with pytest.raises(RulesConfigError, match="entities"):
        config.load_catalog(write_rules(tmp_path, rules))

    rules = valid_rules()
    rules["indicators"] = []

    with pytest.raises(RulesConfigError, match="indicators"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_at_least_one_non_aggregate_entity_is_required(tmp_path):
    rules = valid_rules()
    rules["entities"] = [{"iso3": "WLD", "name": "Mundo", "aggregate": True}]

    with pytest.raises(RulesConfigError, match="no agregada"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_empty_alias_and_warning_are_rejected(tmp_path):
    rules = valid_rules()
    rules["entities"][0]["aliases"].append("  ")

    with pytest.raises(RulesConfigError, match="alias"):
        config.load_catalog(write_rules(tmp_path, rules))

    rules = valid_rules()
    rules["indicators"][1]["warnings"].append("")

    with pytest.raises(RulesConfigError, match="advertencia"):
        config.load_catalog(write_rules(tmp_path, rules))


def test_malformed_yaml_and_non_mapping_root_are_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(RulesConfigError, match="YAML inválido"):
        config.load_catalog(path)

    path.write_text("- item\n", encoding="utf-8")

    with pytest.raises(RulesConfigError, match="objeto YAML"):
        config.load_catalog(path)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(RulesConfigError, match="No se pudo leer"):
        config.load_catalog(tmp_path / "missing.yaml")


def test_check_command_reports_success_and_failure(tmp_path, capsys):
    path = write_rules(tmp_path, valid_rules())

    assert config.main(["check", str(path)]) == 0
    assert "OK: 3 entidades, 2 indicadores" in capsys.readouterr().out

    rules = valid_rules()
    rules["entities"] = []
    invalid = write_rules(tmp_path, rules)

    assert config.main(["check", str(invalid)]) == 1
    assert "no es válido" in capsys.readouterr().err


def test_schema_command_writes_json_schema(tmp_path, capsys):
    assert config.main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert {"version", "entities", "indicators"} <= set(schema["properties"])

    output = tmp_path / "rules.schema.json"
    assert config.main(["schema", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["title"] == "RulesConfig"
