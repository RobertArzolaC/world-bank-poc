import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from world_bank_mcp import server

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_resource_includes_catalog_and_limits():
    data = json.loads(server.catalog_resource())

    assert len(data["entities"]) == 6
    assert len(data["indicators"]) == 3
    assert data["limits"]["min_year"] == 1960
    assert data["limits"]["max_range_years"] == 10


def test_summarize_keeps_small_lists_intact():
    assert server._summarize(["Perú", "Chile"]) == "Perú, Chile"


def test_summarize_truncates_large_lists_and_points_to_the_resource():
    text = server._summarize([f"item-{index}" for index in range(12)])

    assert "item-9" in text
    assert "item-10" not in text
    assert "y 2 más" in text
    assert "worldbank://catalog" in text


def test_main_configures_stderr_logging_and_runs_stdio(monkeypatch):
    calls: list[tuple[str, object]] = []

    def fake_basic_config(**kwargs):
        calls.append(("basicConfig", kwargs))

    def fake_run():
        calls.append(("run", None))

    monkeypatch.setattr(server.logging, "basicConfig", fake_basic_config)
    monkeypatch.setattr(server.mcp, "run", fake_run)

    server.main()

    action, config = calls[0]
    assert action == "basicConfig"
    assert isinstance(config, dict)
    assert config["stream"] is sys.stderr
    assert config["level"] == logging.INFO
    assert calls[1] == ("run", None)


def test_launcher_reports_invalid_rules_without_a_traceback(tmp_path):
    bad_rules = tmp_path / "rules.yaml"
    bad_rules.write_text("version: 1\nentities: []\nindicators: []\n", encoding="utf-8")
    env = {**os.environ, "WORLD_BANK_RULES_FILE": str(bad_rules)}

    result = subprocess.run(
        [sys.executable, str(ROOT / "server.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 1
    assert "no es válido" in result.stderr
    assert "Traceback" not in result.stderr
