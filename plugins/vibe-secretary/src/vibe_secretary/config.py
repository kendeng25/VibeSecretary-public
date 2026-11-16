"""Project configuration loading, validation, and atomic persistence."""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from vibe_secretary.errors import FoundationError
from vibe_secretary.paths import (
    DEFAULT_IMPLEMENTATION_CONFIG_FILE_NAME,
    DEFAULT_PROCESS_CONFIG_FILE_NAME,
    DEFAULT_PROMPT_CONFIG_FILE_NAME,
    DEFAULT_SCOPE_FILE_NAME,
    ProjectPaths,
    ensure_within_root,
)
from vibe_secretary.providers import ProviderConfig, ProviderMode

SCHEMA_VERSION = 1
_ENV_NAME_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(frozen=True, slots=True)
class ProcessHubModuleConfig:
    """Project-level switch and config location for Process Hub."""

    enabled: bool = False
    config_file: str = DEFAULT_PROCESS_CONFIG_FILE_NAME
    config_digest: str = ""


@dataclass(frozen=True, slots=True)
class ImplementationLensModuleConfig:
    """Project-level switch and config location for Implementation Lens."""

    enabled: bool = False
    config_file: str = DEFAULT_IMPLEMENTATION_CONFIG_FILE_NAME
    config_digest: str = ""


@dataclass(frozen=True, slots=True)
class PromptCopilotModuleConfig:
    """Project-level switch and config location for Prompt Copilot."""

    enabled: bool = False
    config_file: str = DEFAULT_PROMPT_CONFIG_FILE_NAME
    config_digest: str = ""


@dataclass(frozen=True, slots=True)
class ModuleConfig:
    """Independent business-module settings."""

    process_hub: ProcessHubModuleConfig = ProcessHubModuleConfig()
    implementation_lens: ImplementationLensModuleConfig = ImplementationLensModuleConfig()
    prompt_copilot: PromptCopilotModuleConfig = PromptCopilotModuleConfig()


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Validated project-level foundation configuration."""

    schema_version: int = SCHEMA_VERSION
    enabled: bool = False
    scope_file: str = DEFAULT_SCOPE_FILE_NAME
    scope_digest: str = ""
    provider: ProviderConfig = ProviderConfig()
    modules: ModuleConfig = ModuleConfig()

    def with_enabled(self, enabled: bool, scope_digest: str | None = None) -> "ProjectConfig":
        return replace(
            self,
            enabled=enabled,
            scope_digest=self.scope_digest if scope_digest is None else scope_digest,
        )

    def with_process_hub_enabled(
        self,
        enabled: bool,
        config_digest: str | None = None,
    ) -> "ProjectConfig":
        return replace(
            self,
            modules=replace(
                self.modules,
                process_hub=replace(
                    self.modules.process_hub,
                    enabled=enabled,
                    config_digest=(
                        self.modules.process_hub.config_digest
                        if config_digest is None
                        else config_digest
                    ),
                ),
            ),
        )

    def with_implementation_lens_enabled(
        self,
        enabled: bool,
        config_digest: str | None = None,
    ) -> "ProjectConfig":
        return replace(
            self,
            modules=replace(
                self.modules,
                implementation_lens=replace(
                    self.modules.implementation_lens,
                    enabled=enabled,
                    config_digest=(
                        self.modules.implementation_lens.config_digest
                        if config_digest is None
                        else config_digest
                    ),
                ),
            ),
        )

    def with_prompt_copilot_enabled(
        self,
        enabled: bool,
        config_digest: str | None = None,
    ) -> "ProjectConfig":
        return replace(
            self,
            modules=replace(
                self.modules,
                prompt_copilot=replace(
                    self.modules.prompt_copilot,
                    enabled=enabled,
                    config_digest=(
                        self.modules.prompt_copilot.config_digest
                        if config_digest is None
                        else config_digest
                    ),
                ),
            ),
        )


def default_config() -> ProjectConfig:
    """Return the safe disabled default configuration."""

    return ProjectConfig()


def _expect_type(mapping: dict[str, Any], key: str, expected: type, default: Any) -> Any:
    value = mapping.get(key, default)
    invalid_boolean_integer = expected is int and isinstance(value, bool)
    if not isinstance(value, expected) or invalid_boolean_integer:
        raise FoundationError(
            code="invalid_config",
            message=f"Configuration field '{key}' has an invalid type.",
        )
    return value


def _parse_provider(raw: Any) -> ProviderConfig:
    if raw is None:
        return ProviderConfig()
    if not isinstance(raw, dict):
        raise FoundationError("invalid_config", "Configuration section 'provider' must be a table.")

    mode_raw = _expect_type(raw, "mode", str, ProviderMode.CODEX_HOST.value)
    try:
        mode = ProviderMode(mode_raw)
    except ValueError as exc:
        raise FoundationError(
            code="invalid_provider_mode",
            message="Provider mode must be 'codex_host' or 'byok'.",
        ) from exc

    name = _expect_type(raw, "name", str, "")
    api_key_env = _expect_type(raw, "api_key_env", str, "")
    if api_key_env and not _ENV_NAME_PATTERN.fullmatch(api_key_env):
        raise FoundationError(
            code="invalid_api_key_env",
            message="Provider api_key_env must be an uppercase environment-variable name.",
        )
    if mode is ProviderMode.BYOK and (not name or not api_key_env):
        raise FoundationError(
            code="incomplete_byok_config",
            message="BYOK mode requires provider.name and provider.api_key_env.",
        )
    return ProviderConfig(mode=mode, name=name, api_key_env=api_key_env)


def _module_file(
    raw: dict[str, Any],
    *,
    default: str,
    paths: ProjectPaths,
    kind: str,
) -> tuple[bool, str, str]:
    enabled = _expect_type(raw, "enabled", bool, False)
    config_file = _expect_type(raw, "config_file", str, default)
    config_digest = _expect_type(raw, "config_digest", str, "")
    if not config_file.strip() or Path(config_file).is_absolute():
        raise FoundationError(
            f"invalid_{kind}_config_file",
            f"{kind.replace('_', ' ').title()} config_file must be a non-empty state-directory-relative path.",
        )
    if kind == "process_hub":
        paths.process_config_file(config_file)
    elif kind == "implementation_lens":
        paths.implementation_config_file(config_file)
    else:
        paths.prompt_config_file(config_file)
    return enabled, config_file.replace("\\", "/"), config_digest


def _parse_modules(raw: Any, paths: ProjectPaths) -> ModuleConfig:
    if raw is None:
        return ModuleConfig()
    if not isinstance(raw, dict):
        raise FoundationError("invalid_config", "Configuration section 'modules' must be a table.")

    process = ProcessHubModuleConfig()
    process_raw = raw.get("process_hub")
    if process_raw is not None:
        if not isinstance(process_raw, dict):
            raise FoundationError(
                "invalid_config",
                "Configuration section 'modules.process_hub' must be a table.",
            )
        enabled, config_file, digest = _module_file(
            process_raw,
            default=DEFAULT_PROCESS_CONFIG_FILE_NAME,
            paths=paths,
            kind="process_hub",
        )
        process = ProcessHubModuleConfig(enabled, config_file, digest)

    implementation = ImplementationLensModuleConfig()
    implementation_raw = raw.get("implementation_lens")
    if implementation_raw is not None:
        if not isinstance(implementation_raw, dict):
            raise FoundationError(
                "invalid_config",
                "Configuration section 'modules.implementation_lens' must be a table.",
            )
        enabled, config_file, digest = _module_file(
            implementation_raw,
            default=DEFAULT_IMPLEMENTATION_CONFIG_FILE_NAME,
            paths=paths,
            kind="implementation_lens",
        )
        implementation = ImplementationLensModuleConfig(enabled, config_file, digest)

    prompt = PromptCopilotModuleConfig()
    prompt_raw = raw.get("prompt_copilot")
    if prompt_raw is not None:
        if not isinstance(prompt_raw, dict):
            raise FoundationError(
                "invalid_config",
                "Configuration section 'modules.prompt_copilot' must be a table.",
            )
        enabled, config_file, digest = _module_file(
            prompt_raw,
            default=DEFAULT_PROMPT_CONFIG_FILE_NAME,
            paths=paths,
            kind="prompt_copilot",
        )
        prompt = PromptCopilotModuleConfig(enabled, config_file, digest)

    return ModuleConfig(
        process_hub=process,
        implementation_lens=implementation,
        prompt_copilot=prompt,
    )


def parse_config(data: dict[str, Any], paths: ProjectPaths) -> ProjectConfig:
    """Validate a decoded TOML mapping."""

    schema_version = _expect_type(data, "schema_version", int, SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        raise FoundationError(
            code="unsupported_schema_version",
            message=f"Unsupported configuration schema version: {schema_version}.",
        )

    enabled = _expect_type(data, "enabled", bool, False)
    scope_file = _expect_type(data, "scope_file", str, DEFAULT_SCOPE_FILE_NAME)
    scope_digest = _expect_type(data, "scope_digest", str, "")
    if not scope_file.strip():
        raise FoundationError("invalid_scope_file", "scope_file cannot be empty.")
    scope_path = Path(scope_file)
    if scope_path.is_absolute():
        raise FoundationError("invalid_scope_file", "scope_file must be project-relative.")
    ensure_within_root(paths.root, paths.root / scope_path)

    return ProjectConfig(
        schema_version=schema_version,
        enabled=enabled,
        scope_file=scope_file.replace("\\", "/"),
        scope_digest=scope_digest,
        provider=_parse_provider(data.get("provider")),
        modules=_parse_modules(data.get("modules"), paths),
    )


def load_config(paths: ProjectPaths) -> ProjectConfig:
    """Load and validate the project config."""

    if not paths.config_file.is_file():
        raise FoundationError(
            code="project_not_initialized",
            message="VibeSecretary is not initialized for this project.",
        )
    try:
        with paths.config_file.open("rb") as stream:
            raw = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise FoundationError("invalid_config_toml", "The VibeSecretary config is not valid TOML.") from exc
    return parse_config(raw, paths)


def render_config(config: ProjectConfig) -> str:
    """Render the small supported TOML schema deterministically."""

    lines = [
        f"schema_version = {config.schema_version}",
        f"enabled = {'true' if config.enabled else 'false'}",
        f'scope_file = "{config.scope_file}"',
    ]
    if config.scope_digest:
        lines.append(f'scope_digest = "{config.scope_digest}"')
    lines.extend(
        [
            "",
            "[provider]",
            f'mode = "{config.provider.mode.value}"',
            f'name = "{config.provider.name}"',
            f'api_key_env = "{config.provider.api_key_env}"',
            "",
            "[modules.process_hub]",
            f"enabled = {'true' if config.modules.process_hub.enabled else 'false'}",
            f'config_file = "{config.modules.process_hub.config_file}"',
            *(
                [f'config_digest = "{config.modules.process_hub.config_digest}"']
                if config.modules.process_hub.config_digest
                else []
            ),
            "",
            "[modules.implementation_lens]",
            f"enabled = {'true' if config.modules.implementation_lens.enabled else 'false'}",
            f'config_file = "{config.modules.implementation_lens.config_file}"',
            *(
                [f'config_digest = "{config.modules.implementation_lens.config_digest}"']
                if config.modules.implementation_lens.config_digest
                else []
            ),
            "",
            "[modules.prompt_copilot]",
            f"enabled = {'true' if config.modules.prompt_copilot.enabled else 'false'}",
            f'config_file = "{config.modules.prompt_copilot.config_file}"',
            *(
                [f'config_digest = "{config.modules.prompt_copilot.config_digest}"']
                if config.modules.prompt_copilot.config_digest
                else []
            ),
            "",
        ]
    )
    return "\n".join(lines)


def save_config(paths: ProjectPaths, config: ProjectConfig) -> None:
    """Atomically persist validated configuration."""

    paths.state_dir.mkdir(parents=True, exist_ok=True)
    content = render_config(config)
    handle, temporary_name = tempfile.mkstemp(
        prefix="config-",
        suffix=".toml.tmp",
        dir=paths.state_dir,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, paths.config_file)
    finally:
        if temporary.exists():
            temporary.unlink()
