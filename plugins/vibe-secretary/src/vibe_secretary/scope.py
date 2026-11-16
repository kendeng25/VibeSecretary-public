"""Gitignore-style project read-scope policy."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pathspec import PathSpec

from vibe_secretary.config import ProjectConfig
from vibe_secretary.errors import FoundationError
from vibe_secretary.paths import ProjectPaths, ensure_within_root

MAX_SCOPE_FILE_BYTES = 1024 * 1024

DEFAULT_SCOPE_TEMPLATE = """# VibeSecretary read exclusions (gitignore syntax).
# Review this file, then explicitly confirm it when enabling the project.
.git/
.venv/
.env
refs/
.vibesecretary/cache/
.vibesecretary/logs/
__pycache__/
*.py[cod]
"""


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """A path authorization decision without exposing file contents."""

    allowed: bool
    relative_path: str
    reason: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "allowed": self.allowed,
            "relative_path": self.relative_path,
            "reason": self.reason,
        }


class ScopePolicy:
    """Compiled project scope shared by all plugin modules."""

    def __init__(self, paths: ProjectPaths, config: ProjectConfig) -> None:
        self.paths = paths
        self.config = config
        self.file = paths.scope_file(config.scope_file)
        raw = _read_scope_bytes(self.file)
        self.digest = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8-sig")
        self._spec = PathSpec.from_lines("gitignore", text.splitlines())

    @property
    def confirmed(self) -> bool:
        return bool(self.config.scope_digest) and self.config.scope_digest == self.digest

    @property
    def effective_enabled(self) -> bool:
        return self.config.enabled and self.confirmed

    def decide(self, candidate: str | Path) -> ScopeDecision:
        raw = Path(candidate)
        absolute = raw if raw.is_absolute() else self.paths.root / raw
        try:
            resolved = ensure_within_root(self.paths.root, absolute)
        except FoundationError:
            return ScopeDecision(False, "", "outside_project")

        relative = resolved.relative_to(self.paths.root.resolve(strict=False)).as_posix()
        if not relative:
            return ScopeDecision(True, ".", "project_root")
        if self._spec.match_file(relative):
            return ScopeDecision(False, relative, "excluded_by_scope")
        return ScopeDecision(True, relative, "allowed_by_scope")


def _read_scope_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise FoundationError(
            code="scope_file_missing",
            message="The configured VibeSecretary scope file does not exist.",
        )
    size = path.stat().st_size
    if size > MAX_SCOPE_FILE_BYTES:
        raise FoundationError(
            code="scope_file_too_large",
            message="The VibeSecretary scope file exceeds the 1 MiB safety limit.",
        )
    raw = path.read_bytes()
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FoundationError(
            code="scope_file_not_utf8",
            message="The VibeSecretary scope file must be UTF-8 text.",
        ) from exc
    return raw
