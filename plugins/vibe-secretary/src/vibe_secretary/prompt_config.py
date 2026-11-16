"""Prompt Copilot module configuration and confirmation digest."""

from __future__ import annotations

import hashlib
import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibe_secretary.config import ProjectConfig
from vibe_secretary.errors import FoundationError
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.prompt_models import PromptMode

PROMPT_CONFIG_SCHEMA_VERSION = 2
LEGACY_PROMPT_CONFIG_SCHEMA_VERSION = 1
MAX_CONFIG_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PromptCopilotConfig:
    schema_version: int = PROMPT_CONFIG_SCHEMA_VERSION
    default_mode: PromptMode = PromptMode.REVIEW
    automatic_enabled: bool = True
    context_char_budget: int = 6000
    hook_context_char_budget: int = 2400
    per_source_char_budget: int = 1000
    max_sources: int = 8
    max_scan_files: int = 500
    max_file_bytes: int = 262_144
    max_prompt_chars: int = 16_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_mode": self.default_mode.value,
            "automatic_enabled": self.automatic_enabled,
            "context_char_budget": self.context_char_budget,
            "hook_context_char_budget": self.hook_context_char_budget,
            "per_source_char_budget": self.per_source_char_budget,
            "max_sources": self.max_sources,
            "max_scan_files": self.max_scan_files,
            "max_file_bytes": self.max_file_bytes,
            "max_prompt_chars": self.max_prompt_chars,
        }


def default_prompt_config() -> PromptCopilotConfig:
    return PromptCopilotConfig()


def _integer(raw: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise FoundationError(
            "invalid_prompt_config",
            f"Prompt Copilot field '{key}' must be an integer from {minimum} to {maximum}.",
        )
    return value


def _boolean(raw: dict[str, Any], key: str, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise FoundationError(
            "invalid_prompt_config",
            f"Prompt Copilot field '{key}' must be a boolean.",
        )
    return value


def parse_prompt_config(raw: dict[str, Any]) -> PromptCopilotConfig:
    source_schema = _integer(
        raw,
        "schema_version",
        PROMPT_CONFIG_SCHEMA_VERSION,
        LEGACY_PROMPT_CONFIG_SCHEMA_VERSION,
        PROMPT_CONFIG_SCHEMA_VERSION,
    )
    if source_schema == PROMPT_CONFIG_SCHEMA_VERSION and "strict_blocking" in raw:
        raise FoundationError(
            "removed_prompt_config_field",
            "Prompt Copilot field 'strict_blocking' was removed in schema 2. "
            "Delete it; Strict mode now uses a conversational preflight gate.",
        )

    mode_raw = raw.get("default_mode", PromptMode.REVIEW.value)
    if not isinstance(mode_raw, str):
        raise FoundationError("invalid_prompt_config", "default_mode must be a string.")
    try:
        mode = PromptMode(mode_raw.lower())
    except ValueError as exc:
        raise FoundationError(
            "invalid_prompt_mode",
            "Prompt mode must be 'quick', 'review', or 'strict'.",
        ) from exc

    automatic_default = (
        False
        if source_schema == LEGACY_PROMPT_CONFIG_SCHEMA_VERSION
        else True
    )
    config = PromptCopilotConfig(
        schema_version=PROMPT_CONFIG_SCHEMA_VERSION,
        default_mode=mode,
        automatic_enabled=_boolean(raw, "automatic_enabled", automatic_default),
        context_char_budget=_integer(raw, "context_char_budget", 6000, 500, 40_000),
        hook_context_char_budget=_integer(raw, "hook_context_char_budget", 2400, 1400, 8_000),
        per_source_char_budget=_integer(raw, "per_source_char_budget", 1000, 100, 8_000),
        max_sources=_integer(raw, "max_sources", 8, 1, 30),
        max_scan_files=_integer(raw, "max_scan_files", 500, 10, 10_000),
        max_file_bytes=_integer(raw, "max_file_bytes", 262_144, 1024, 5_000_000),
        max_prompt_chars=_integer(raw, "max_prompt_chars", 16_000, 100, 100_000),
    )
    if config.hook_context_char_budget > config.context_char_budget:
        raise FoundationError(
            "invalid_prompt_config",
            "hook_context_char_budget cannot exceed context_char_budget.",
        )
    if config.per_source_char_budget > config.context_char_budget:
        raise FoundationError(
            "invalid_prompt_config",
            "per_source_char_budget cannot exceed context_char_budget.",
        )
    return config


def render_prompt_config(config: PromptCopilotConfig) -> str:
    return "\n".join(
        [
            f"schema_version = {PROMPT_CONFIG_SCHEMA_VERSION}",
            f'default_mode = "{config.default_mode.value}"',
            f"automatic_enabled = {'true' if config.automatic_enabled else 'false'}",
            f"context_char_budget = {config.context_char_budget}",
            f"hook_context_char_budget = {config.hook_context_char_budget}",
            f"per_source_char_budget = {config.per_source_char_budget}",
            f"max_sources = {config.max_sources}",
            f"max_scan_files = {config.max_scan_files}",
            f"max_file_bytes = {config.max_file_bytes}",
            f"max_prompt_chars = {config.max_prompt_chars}",
            "",
        ]
    )


def _config_path(paths: ProjectPaths, project_config: ProjectConfig) -> Path:
    return paths.prompt_config_file(project_config.modules.prompt_copilot.config_file)


def load_prompt_config(
    paths: ProjectPaths,
    project_config: ProjectConfig,
) -> PromptCopilotConfig:
    path = _config_path(paths, project_config)
    if not path.is_file():
        raise FoundationError(
            "prompt_copilot_not_initialized",
            "Prompt Copilot is not initialized for this project.",
        )
    if path.stat().st_size > MAX_CONFIG_BYTES:
        raise FoundationError("prompt_config_too_large", "Prompt Copilot config exceeds 1 MiB.")
    try:
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise FoundationError(
            "invalid_prompt_config_toml",
            "The Prompt Copilot config is not valid TOML.",
        ) from exc
    return parse_prompt_config(raw)


def prompt_config_digest(paths: ProjectPaths, project_config: ProjectConfig) -> str:
    path = _config_path(paths, project_config)
    if not path.is_file():
        raise FoundationError(
            "prompt_copilot_not_initialized",
            "Prompt Copilot is not initialized for this project.",
        )
    raw = path.read_bytes()
    if len(raw) > MAX_CONFIG_BYTES:
        raise FoundationError("prompt_config_too_large", "Prompt Copilot config exceeds 1 MiB.")
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FoundationError(
            "prompt_config_not_utf8",
            "Prompt Copilot config must be UTF-8.",
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def save_prompt_config(
    paths: ProjectPaths,
    project_config: ProjectConfig,
    config: PromptCopilotConfig,
) -> None:
    path = _config_path(paths, project_config)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        prefix="prompt-copilot-",
        suffix=".toml.tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(render_prompt_config(config))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
