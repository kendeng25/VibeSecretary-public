"""Project-root discovery and path containment helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from vibe_secretary.errors import FoundationError

PROJECT_DIR_NAME = ".vibesecretary"
CONFIG_FILE_NAME = "config.toml"
DEFAULT_SCOPE_FILE_NAME = ".vibesecretaryignore"
DEFAULT_PROCESS_CONFIG_FILE_NAME = "process-hub.toml"
DEFAULT_PROMPT_CONFIG_FILE_NAME = "prompt-copilot.toml"
DEFAULT_IMPLEMENTATION_CONFIG_FILE_NAME = "implementation-lens.toml"


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def ensure_within_root(root: Path, candidate: Path) -> Path:
    """Resolve a path and reject traversal or symlink escape from the root."""

    resolved_root = _resolved(root)
    resolved_candidate = _resolved(candidate)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise FoundationError(
            code="path_outside_project",
            message="The requested path is outside the project root.",
        ) from exc
    return resolved_candidate


def validate_project_root(value: str | Path | None = None) -> Path:
    """Return an existing project directory from an explicit value or cwd."""

    raw = Path(value) if value else Path.cwd()
    root = _resolved(raw)
    if not root.exists():
        raise FoundationError(
            code="project_root_missing",
            message="The project root does not exist.",
        )
    if not root.is_dir():
        raise FoundationError(
            code="project_root_not_directory",
            message="The project root is not a directory.",
        )
    return root


def discover_project_root(start: str | Path | None = None) -> Path:
    """Find the nearest configured or Git project, falling back to cwd."""

    override = os.environ.get("VIBESECRETARY_PROJECT_ROOT")
    if override:
        return validate_project_root(override)

    current = validate_project_root(start)
    fallback = current
    for candidate in (current, *current.parents):
        if (candidate / PROJECT_DIR_NAME / CONFIG_FILE_NAME).is_file():
            return candidate
        if (candidate / ".git").exists():
            return candidate
    return fallback


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Canonical locations for one VibeSecretary-enabled project."""

    root: Path

    @classmethod
    def from_value(cls, value: str | Path | None = None) -> "ProjectPaths":
        return cls(root=discover_project_root(value))

    @property
    def state_dir(self) -> Path:
        return self.root / PROJECT_DIR_NAME

    @property
    def config_file(self) -> Path:
        return self.state_dir / CONFIG_FILE_NAME

    def process_config_file(
        self,
        relative_name: str = DEFAULT_PROCESS_CONFIG_FILE_NAME,
    ) -> Path:
        """Return a Process Hub config path contained by the state directory."""

        return ensure_within_root(self.state_dir, self.state_dir / relative_name)

    def prompt_config_file(
        self,
        relative_name: str = DEFAULT_PROMPT_CONFIG_FILE_NAME,
    ) -> Path:
        """Return a Prompt Copilot config path contained by the state directory."""

        return ensure_within_root(self.state_dir, self.state_dir / relative_name)

    def implementation_config_file(
        self,
        relative_name: str = DEFAULT_IMPLEMENTATION_CONFIG_FILE_NAME,
    ) -> Path:
        """Return an Implementation Lens config path contained by the state directory."""

        return ensure_within_root(self.state_dir, self.state_dir / relative_name)

    def scope_file(self, relative_name: str = DEFAULT_SCOPE_FILE_NAME) -> Path:
        candidate = self.root / relative_name
        return ensure_within_root(self.root, candidate)
