"""Bootstrap the bundled MCP server from an installed plugin directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _plugin_root() -> Path:
    configured = os.environ.get("PLUGIN_ROOT")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[1]


sys.path.insert(0, str(_plugin_root() / "src"))

from vibe_secretary.mcp_server import main  # noqa: E402


if __name__ == "__main__":
    main()
