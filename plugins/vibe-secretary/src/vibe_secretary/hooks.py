"""Codex lifecycle hook handlers for the plugin foundation and modules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from vibe_secretary.audit import write_audit_event
from vibe_secretary.config import load_config
from vibe_secretary.errors import FoundationError
from vibe_secretary.implementation_service import ImplementationLensService
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.prompt_service import PromptCopilotService
from vibe_secretary.scope import ScopePolicy
from vibe_secretary.process_service import ProcessHubService
from vibe_secretary.service import FoundationService

_PATH_KEYS = {"path", "file_path", "directory", "root", "cwd", "target"}
_PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
_PROCESS_USAGE_TOTAL_BUDGET = 1600
_PROCESS_USAGE_ITEM_BUDGET = 320


def _process_usage_context(process_data: dict[str, Any]) -> str:
    collections = process_data.get("collections", [])
    if not isinstance(collections, list):
        return ""
    lines = [" Confirmed Process Hub collection guidance:"]
    for item in collections:
        if not isinstance(item, dict):
            continue
        collection_id = item.get("id")
        usage = item.get("usage")
        if not isinstance(collection_id, str) or not isinstance(usage, str):
            continue
        normalized = " ".join(usage.split())[:_PROCESS_USAGE_ITEM_BUDGET]
        candidate = f"\n- {collection_id}: {normalized}"
        if len("".join(lines)) + len(candidate) > _PROCESS_USAGE_TOTAL_BUDGET:
            break
        lines.append(candidate)
    if len(lines) == 1:
        return ""
    lines.append("\nRefresh Process Hub status before writing.")
    return "".join(lines)


def session_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Inject a short status only for a confirmed, enabled project."""

    cwd = str(payload.get("cwd", ""))
    result = FoundationService().project_status(cwd)
    if not result.get("ok"):
        return {}
    data = result.get("data", {})
    if not isinstance(data, dict) or not data.get("effective_enabled"):
        return {}

    process_status = ProcessHubService().status(cwd)
    process_data = process_status.get("data", {}) if process_status.get("ok") else {}
    process_enabled = bool(
        isinstance(process_data, dict) and process_data.get("effective_enabled")
    )
    implementation_status = ImplementationLensService().status(cwd)
    implementation_data = (
        implementation_status.get("data", {}) if implementation_status.get("ok") else {}
    )
    implementation_enabled = bool(
        isinstance(implementation_data, dict)
        and implementation_data.get("effective_enabled")
    )
    prompt_status = PromptCopilotService().status(cwd)
    prompt_data = prompt_status.get("data", {}) if prompt_status.get("ok") else {}
    prompt_enabled = bool(
        isinstance(prompt_data, dict) and prompt_data.get("effective_enabled")
    )
    module_context = (
        " Process Hub is enabled; use $vibe-secretary-process-hub for process document work."
        if process_enabled
        else " Process Hub is not active."
    )
    if process_enabled:
        module_context += _process_usage_context(process_data)
    module_context += (
        " Implementation Lens is enabled; only a leading @lens token routes one implementation-map request through $vibe-secretary-implementation-lens."
        if implementation_enabled
        else " Implementation Lens is not active."
    )
    module_context += (
        " Prompt Copilot is enabled; use $vibe-secretary-prompt-copilot to review prompts."
        if prompt_enabled
        else " Prompt Copilot is not active."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "VibeSecretary foundation is enabled for this project and its read scope is confirmed."
                + module_context
            ),
        }
    }


def user_prompt_submit(payload: dict[str, Any]) -> dict[str, Any]:
    """Inject bounded mode-specific Prompt Copilot context for development requests."""

    cwd = str(payload.get("cwd", ""))
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        return {}
    result = ImplementationLensService().directive_hook(cwd, prompt)
    if result:
        write_audit_event(
            {
                "event": "UserPromptSubmit",
                "decision": "inject",
                "reason": "implementation_lens_directive",
                "mode": "readonly",
                "source_count": 0,
            }
        )
        return result
    result = PromptCopilotService().automatic_hook(cwd, prompt)
    if result:
        output = result.get("hookSpecificOutput", {})
        context = output.get("additionalContext", "") if isinstance(output, dict) else ""
        mode_match = re.search(r"- Mode: ([a-z]+);", context) if isinstance(context, str) else None
        write_audit_event(
            {
                "event": "UserPromptSubmit",
                "decision": "inject" if output else str(result.get("decision", "")),
                "reason": "prompt_copilot",
                "mode": mode_match.group(1) if mode_match else "",
                "source_count": context.count("\n  - [") if isinstance(context, str) else 0,
            }
        )
    return result


def pre_tool_use(payload: dict[str, Any]) -> dict[str, Any]:
    """Deny explicit out-of-scope paths while documenting opaque command gaps."""

    cwd = str(payload.get("cwd", ""))
    tool_name = str(payload.get("tool_name", ""))
    try:
        paths = ProjectPaths.from_value(cwd)
        config = load_config(paths)
        policy = ScopePolicy(paths, config)
    except FoundationError:
        return {}
    if not policy.effective_enabled:
        return {}

    tool_input = payload.get("tool_input")
    candidates = list(_extract_explicit_paths(tool_input))
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str) and tool_name == "apply_patch":
            candidates.extend(_PATCH_PATH.findall(command))

    for candidate in candidates:
        decision = policy.decide(candidate)
        if not decision.allowed:
            write_audit_event(
                {
                    "event": "PreToolUse",
                    "tool": tool_name,
                    "decision": "deny",
                    "reason": decision.reason,
                }
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "VibeSecretary denied an explicit path outside the confirmed project read scope."
                    ),
                }
            }

    reason = "checked_explicit_paths" if candidates else "opaque_or_pathless_input"
    write_audit_event(
        {
            "event": "PreToolUse",
            "tool": tool_name,
            "decision": "allow",
            "reason": reason,
        }
    )
    return {}


def _extract_explicit_paths(value: Any, key: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _extract_explicit_paths(child, str(child_key))
        return
    if isinstance(value, list):
        for child in value:
            yield from _extract_explicit_paths(child, key)
        return
    if isinstance(value, str) and key.lower() in _PATH_KEYS and value.strip():
        yield value
