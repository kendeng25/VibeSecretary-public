"""Codex UserPromptSubmit hook bootstrap."""

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

from vibe_secretary.hooks import user_prompt_submit  # noqa: E402


def main() -> int:
    try:
        payload: dict[str, Any] = json.load(sys.stdin)
        result = user_prompt_submit(payload)
        output = result.get("hookSpecificOutput") if isinstance(result, dict) else None
        context = output.get("additionalContext") if isinstance(output, dict) else None
        if isinstance(context, str) and context:
            # Codex accepts plain stdout as UserPromptSubmit developer context. Using text here
            # avoids host-version differences in hook-specific JSON validation.
            sys.stdout.write(context)
        elif result:
            json.dump(result, sys.stdout, ensure_ascii=True)
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
