"""Codex PreToolUse hook bootstrap."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _plugin_root() -> Path:
    configured = os.environ.get("PLUGIN_ROOT")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[1]


sys.path.insert(0, str(_plugin_root() / "src"))

from vibe_secretary.hooks import pre_tool_use  # noqa: E402


def main() -> int:
    try:
        payload: dict[str, Any] = json.load(sys.stdin)
        result = pre_tool_use(payload)
        if result:
            json.dump(result, sys.stdout, ensure_ascii=True)
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
