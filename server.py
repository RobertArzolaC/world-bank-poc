"""Absolute-path launcher for the World Bank MCP server (stdio)."""

import sys

from world_bank_mcp.errors import RulesConfigError

try:
    from world_bank_mcp.server import main
except RulesConfigError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    raise SystemExit(1) from None

if __name__ == "__main__":
    main()
