"""Foundation service used by MCP tools and lifecycle hooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from vibe_secretary.config import default_config, load_config, save_config
from vibe_secretary.errors import FoundationError, failure, internal_failure, success
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.scope import DEFAULT_SCOPE_TEMPLATE, ScopePolicy
from vibe_secretary.version import PLUGIN_VERSION


class FoundationService:
    """Provide safe project lifecycle operations without business-module logic."""

    def health(self) -> dict[str, Any]:
        return success(
            {
                "service": "vibe-secretary-foundation",
                "plugin_version": PLUGIN_VERSION,
                "transport": "stdio",
                "status": "healthy",
                "business_modules": ["process_hub", "implementation_lens", "prompt_copilot"],
            }
        )

    def project_status(self, project_root: str = "") -> dict[str, Any]:
        return self._guard(lambda: self._project_status(ProjectPaths.from_value(project_root or None)))

    def initialize_project(self, project_root: str = "") -> dict[str, Any]:
        return self._guard(lambda: self._initialize(ProjectPaths.from_value(project_root or None)))

    def set_project_enabled(
        self,
        enabled: bool,
        confirm_scope: bool = False,
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._set_enabled(
                ProjectPaths.from_value(project_root or None),
                enabled=enabled,
                confirm_scope=confirm_scope,
            )
        )

    def scope_decision(self, candidate: str, project_root: str = "") -> dict[str, Any]:
        return self._guard(
            lambda: self._scope_decision(ProjectPaths.from_value(project_root or None), candidate)
        )

    @staticmethod
    def _guard(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return operation()
        except FoundationError as exc:
            return failure(exc)
        except Exception:
            return internal_failure()

    @staticmethod
    def _module_status(config: Any) -> dict[str, Any]:
        return {
            "process_hub": {
                "configured_enabled": config.modules.process_hub.enabled,
                "config_file": config.modules.process_hub.config_file,
            },
            "implementation_lens": {
                "configured_enabled": config.modules.implementation_lens.enabled,
                "config_file": config.modules.implementation_lens.config_file,
            },
            "prompt_copilot": {
                "configured_enabled": config.modules.prompt_copilot.enabled,
                "config_file": config.modules.prompt_copilot.config_file,
            },
        }

    @staticmethod
    def _project_status(paths: ProjectPaths) -> dict[str, Any]:
        config_exists = paths.config_file.is_file()
        if not config_exists:
            return success(
                {
                    "project_root": str(paths.root),
                    "initialized": False,
                    "configured_enabled": False,
                    "effective_enabled": False,
                    "scope_file_exists": False,
                    "scope_confirmed": False,
                    "provider_mode": "codex_host",
                    "modules": {
                        "process_hub": {"configured_enabled": False},
                        "implementation_lens": {"configured_enabled": False},
                        "prompt_copilot": {"configured_enabled": False},
                    },
                    "diagnostics": ["Run initialize_project before enabling VibeSecretary."],
                }
            )

        config = load_config(paths)
        scope_path = paths.scope_file(config.scope_file)
        if not scope_path.is_file():
            return success(
                {
                    "project_root": str(paths.root),
                    "initialized": True,
                    "configured_enabled": config.enabled,
                    "effective_enabled": False,
                    "scope_file_exists": False,
                    "scope_confirmed": False,
                    "provider_mode": config.provider.mode.value,
                    "modules": FoundationService._module_status(config),
                    "diagnostics": ["The configured scope file is missing."],
                }
            )

        policy = ScopePolicy(paths, config)
        diagnostics: list[str] = []
        if not policy.confirmed:
            diagnostics.append("Review and confirm the scope file before enabling the project.")
        if config.enabled and not policy.confirmed:
            diagnostics.append("The scope file changed after confirmation; effective enablement is disabled.")
        if not config.enabled:
            diagnostics.append("VibeSecretary is configured but disabled for this project.")
        return success(
            {
                "project_root": str(paths.root),
                "initialized": True,
                "configured_enabled": config.enabled,
                "effective_enabled": policy.effective_enabled,
                "scope_file": config.scope_file,
                "scope_file_exists": True,
                "scope_confirmed": policy.confirmed,
                "provider_mode": config.provider.mode.value,
                "modules": FoundationService._module_status(config),
                "diagnostics": diagnostics,
            }
        )

    @staticmethod
    def _initialize(paths: ProjectPaths) -> dict[str, Any]:
        created: list[str] = []
        existing: list[str] = []
        paths.state_dir.mkdir(parents=True, exist_ok=True)

        if paths.config_file.exists():
            existing.append(str(paths.config_file.relative_to(paths.root).as_posix()))
        else:
            save_config(paths, default_config())
            created.append(str(paths.config_file.relative_to(paths.root).as_posix()))

        scope_file = paths.scope_file()
        if scope_file.exists():
            existing.append(str(scope_file.relative_to(paths.root).as_posix()))
        else:
            scope_file.write_text(DEFAULT_SCOPE_TEMPLATE, encoding="utf-8", newline="\n")
            created.append(str(scope_file.relative_to(paths.root).as_posix()))

        status = FoundationService._project_status(paths)["data"]
        return success(
            {
                "project_root": str(paths.root),
                "created": created,
                "preserved": existing,
                "effective_enabled": status["effective_enabled"],
                "next_step": "Review the scope file, then enable with confirm_scope=true.",
            }
        )

    @staticmethod
    def _set_enabled(paths: ProjectPaths, *, enabled: bool, confirm_scope: bool) -> dict[str, Any]:
        config = load_config(paths)
        policy = ScopePolicy(paths, config)
        if enabled and not confirm_scope:
            raise FoundationError(
                code="scope_confirmation_required",
                message="Set confirm_scope=true after reviewing the scope file.",
            )

        digest = policy.digest if enabled else config.scope_digest
        updated = config.with_enabled(enabled, scope_digest=digest)
        save_config(paths, updated)
        updated_policy = ScopePolicy(paths, updated)
        return success(
            {
                "project_root": str(paths.root),
                "configured_enabled": enabled,
                "effective_enabled": updated_policy.effective_enabled,
                "scope_confirmed": updated_policy.confirmed,
            }
        )

    @staticmethod
    def _scope_decision(paths: ProjectPaths, candidate: str) -> dict[str, Any]:
        config = load_config(paths)
        policy = ScopePolicy(paths, config)
        return success(
            {
                "effective_enabled": policy.effective_enabled,
                "decision": policy.decide(Path(candidate)).to_dict(),
            }
        )
