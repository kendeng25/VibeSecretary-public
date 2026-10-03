"""Configure a local plugin installation to use the repository virtual environment."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class LocalRuntimeConfigurationError(ValueError):
    """Raised when a safe local runtime configuration cannot be generated."""


_HOOK_LAUNCH_NAMES = {
    "SessionStart": "session-start",
    "PreToolUse": "pre-tool-use",
    "UserPromptSubmit": "user-prompt-submit",
}
_RUNTIME_SCHEMA_VERSION = 1


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_file(path: Path, label: str) -> Path:
    candidate = _absolute_path(path)
    if not candidate.is_file():
        raise LocalRuntimeConfigurationError(f"{label} does not exist: {candidate}")
    return candidate


def _require_project_python(repository_root: Path, python_executable: Path) -> Path:
    expected_environment = _absolute_path(repository_root / ".venv")
    executable = _require_file(python_executable, "Python executable")
    try:
        executable.relative_to(expected_environment)
    except ValueError as error:
        raise LocalRuntimeConfigurationError(
            f"Python executable must be inside {expected_environment}: {executable}"
        ) from error
    return executable


def _project_mcp_entrypoint(repository_root: Path) -> Path:
    if os.name == "nt":
        return repository_root / ".venv" / "Scripts" / "vibe-secretary-mcp.exe"
    return repository_root / ".venv" / "bin" / "vibe-secretary-mcp"


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LocalRuntimeConfigurationError(f"Cannot read {label}: {path}") from error
    if not isinstance(payload, dict):
        raise LocalRuntimeConfigurationError(f"{label} must contain a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(rendered, encoding="utf-8")


def _windows_hook_command(launch_name: str) -> str:
    return (
        'cmd.exe /d /c call "%PLUGIN_ROOT%\\scripts\\run_hook.cmd" '
        f"{launch_name}"
    )


def _configure_runtime_descriptor(plugin_root: Path, python_executable: Path) -> Path:
    config_path = plugin_root / "runtime" / "runtime.json"
    _write_json(
        config_path,
        {
            "schema_version": _RUNTIME_SCHEMA_VERSION,
            "python_executable": str(python_executable),
        },
    )
    return config_path


def _configure_mcp(plugin_root: Path, mcp_entrypoint: Path) -> Path:
    config_path = plugin_root / ".mcp.json"
    payload = _read_json_object(config_path, "MCP configuration")
    try:
        foundation = payload["mcpServers"]["foundation"]
    except (KeyError, TypeError) as error:
        raise LocalRuntimeConfigurationError(
            "MCP configuration must define mcpServers.foundation"
        ) from error
    if not isinstance(foundation, dict):
        raise LocalRuntimeConfigurationError("mcpServers.foundation must be a JSON object")
    foundation["command"] = str(mcp_entrypoint)
    foundation["args"] = []
    _write_json(config_path, payload)
    return config_path


def _configure_hooks(plugin_root: Path) -> Path:
    config_path = plugin_root / "hooks" / "hooks.json"
    payload = _read_json_object(config_path, "Hook configuration")
    hooks = payload.get("hooks")
    if not isinstance(hooks, dict):
        raise LocalRuntimeConfigurationError("Hook configuration must define a hooks object")

    for event, launch_name in _HOOK_LAUNCH_NAMES.items():
        event_groups = hooks.get(event)
        if not isinstance(event_groups, list):
            raise LocalRuntimeConfigurationError(f"Hook configuration is missing {event}")
        command_handlers: list[dict[str, Any]] = []
        for group in event_groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            for handler in group["hooks"]:
                if isinstance(handler, dict) and handler.get("type") == "command":
                    command_handlers.append(handler)
        if len(command_handlers) != 1:
            raise LocalRuntimeConfigurationError(
                f"Expected exactly one {event} command handler, found {len(command_handlers)}"
            )
        command_handlers[0]["commandWindows"] = _windows_hook_command(launch_name)

    _write_json(config_path, payload)
    return config_path


def configure_local_runtime(
    repository_root: Path,
    python_executable: Path,
) -> dict[str, str]:
    """Pin MCP and Windows Hooks to one project-local runtime description."""

    repository_root = _absolute_path(repository_root)
    plugin_root = repository_root / "plugins" / "vibe-secretary"
    if not plugin_root.is_dir():
        raise LocalRuntimeConfigurationError(f"Plugin root does not exist: {plugin_root}")

    python_executable = _require_project_python(repository_root, python_executable)
    mcp_entrypoint = _require_file(
        _project_mcp_entrypoint(repository_root),
        "MCP console entrypoint",
    )
    _require_file(plugin_root / "scripts" / "run_hook.cmd", "Windows Hook launcher")
    _require_file(
        plugin_root / "scripts" / "run_hook.ps1",
        "PowerShell Hook launcher",
    )

    runtime_config = _configure_runtime_descriptor(plugin_root, python_executable)
    mcp_config = _configure_mcp(plugin_root, mcp_entrypoint)
    hook_config = _configure_hooks(plugin_root)
    return {
        "repository_root": str(repository_root),
        "python_executable": str(python_executable),
        "mcp_entrypoint": str(mcp_entrypoint),
        "runtime_config": str(runtime_config),
        "mcp_config": str(mcp_config),
        "hook_config": str(hook_config),
    }