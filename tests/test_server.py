import logging
import sys

from world_bank_mcp import server


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
