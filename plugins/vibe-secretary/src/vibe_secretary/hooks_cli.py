"""Console entrypoint dispatching the three lifecycle hooks to the shared runtime.

Codex invokes ``vibe-secretary-hook <event>`` with a JSON payload on stdin; the DSH
bundle bridge invokes the same command and parses stdout. Each hook must never fail
the host, so unexpected errors degrade silently to an empty result.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from vibe_secretary.hooks import pre_tool_use, session_start, user_prompt_submit

_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "session-start": session_start,
    "pre-tool-use": pre_tool_use,
    "user-prompt-submit": user_prompt_submit,
}

_USAGE = "Usage: vibe-secretary-hook <session-start|pre-tool-use|user-prompt-submit>"


def _emit_result(name: str, result: dict[str, Any]) -> None:
    if name == "user-prompt-submit":
        output = result.get("hookSpecificOutput") if isinstance(result, dict) else None
        context = output.get("additionalContext") if isinstance(output, dict) else None
        if isinstance(context, str) and context:
            # Codex accepts plain stdout as UserPromptSubmit developer context; the
            # DSH bridge reads the same plain text and injects it as user context.
            sys.stdout.write(context)
            return
        if result:
            json.dump(result, sys.stdout, ensure_ascii=True)
        return
    if result:
        json.dump(result, sys.stdout, ensure_ascii=True)


def _run(name: str) -> int:
    handler = _HANDLERS.get(name)
    if handler is None:
        sys.stderr.write(f"Unknown VibeSecretary hook: {name}\n{_USAGE}\n")
        return 2
    try:
        payload: dict[str, Any] = json.load(sys.stdin)
        result = handler(payload)
    except Exception:
        return 0
    _emit_result(name, result)
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write(f"{_USAGE}\n")
        return 2
    return _run(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
