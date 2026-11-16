"""Implementation Lens configuration and deterministic TOML persistence."""

from __future__ import annotations

import hashlib
import os
import string
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from vibe_secretary.config import ProjectConfig
from vibe_secretary.errors import FoundationError
from vibe_secretary.implementation_models import Granularity
from vibe_secretary.paths import ProjectPaths, ensure_within_root

IMPLEMENTATION_SCHEMA_VERSION = 2
LEGACY_IMPLEMENTATION_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_PATH = "ImplementationLens"
DEFAULT_PATH_TEMPLATE = "reports/{granularity}/{slug}_{timestamp}.{ext}"
LEGACY_PATH_TEMPLATE = "{slug}_{timestamp}.{ext}"
DEFAULT_PROJECT_MODEL_PATH = "_project_model"
DEFAULT_INDEX_JSON = ".vibesecretary/implementation-lens-index.json"
ALLOWED_TEMPLATE_FIELDS = {
    "slug",
    "timestamp",
    "granularity",
    "language",
    "year",
    "month",
    "day",
    "ext",
}
MAX_CONFIG_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ImplementationLensConfig:
    """Validated settings for static implementation analysis."""

    schema_version: int = IMPLEMENTATION_SCHEMA_VERSION
    default_granularity: Granularity = Granularity.SYMBOL
    output_path: str = DEFAULT_OUTPUT_PATH
    path_template: str = DEFAULT_PATH_TEMPLATE
    project_model_path: str = DEFAULT_PROJECT_MODEL_PATH
    index_json: str = DEFAULT_INDEX_JSON
    max_files: int = 2000
    max_file_bytes: int = 1024 * 1024
    max_nodes: int = 500
    max_edges: int = 1000
    max_audit_files: int = 5000

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_granularity": self.default_granularity.value,
            "index_json": self.index_json,
            "output": {
                "path": self.output_path,
                "path_template": self.path_template,
                "project_model_path": self.project_model_path,
            },
            "limits": {
                "max_files": self.max_files,
                "max_file_bytes": self.max_file_bytes,
                "max_nodes": self.max_nodes,
                "max_edges": self.max_edges,
                "max_audit_files": self.max_audit_files,
            },
        }


def default_implementation_config() -> ImplementationLensConfig:
    return ImplementationLensConfig()


def _expect(raw: dict[str, Any], key: str, expected: type, default: Any) -> Any:
    value = raw.get(key, default)
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise FoundationError(
            "invalid_implementation_config",
            f"Implementation Lens field '{key}' has an invalid type.",
        )
    return value


def _positive_integer(raw: dict[str, Any], key: str, default: int, maximum: int) -> int:
    value = _expect(raw, key, int, default)
    if value < 1 or value > maximum:
        raise FoundationError(
            "invalid_implementation_config",
            f"Implementation Lens field '{key}' must be between 1 and {maximum}.",
        )
    return value


def _relative_path(paths: ProjectPaths, value: str, field: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or normalized == "."
        or pure.is_absolute()
        or Path(value).is_absolute()
        or ".." in pure.parts
    ):
        raise FoundationError(
            "invalid_implementation_path",
            f"Implementation Lens {field} must be a non-empty project-relative path without '..'.",
        )
    ensure_within_root(paths.root, paths.root / Path(normalized))
    return normalized


def _render_template(value: str, *, ext: str) -> str:
    return value.format(
        slug="sample",
        timestamp="20260820T120000000000Z",
        granularity="symbol",
        language="python",
        year="2026",
        month="08",
        day="20",
        ext=ext,
    )


def validate_output_template(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    pure = PurePosixPath(normalized)
    if not normalized or pure.is_absolute() or Path(value).is_absolute() or ".." in pure.parts:
        raise FoundationError(
            "invalid_implementation_template",
            "Implementation Lens path_template must be project-relative without '..'.",
        )
    try:
        fields = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(normalized)
            if field_name
        }
    except ValueError as exc:
        raise FoundationError(
            "invalid_implementation_template",
            "Implementation Lens path_template has invalid braces.",
        ) from exc
    unknown = fields - ALLOWED_TEMPLATE_FIELDS
    if unknown or not {"slug", "ext"}.issubset(fields):
        raise FoundationError(
            "invalid_implementation_template",
            "Implementation Lens path_template requires '{slug}' and '{ext}' and contains only supported fields.",
            {"unsupported_fields": sorted(unknown)},
        )
    try:
        rendered = _render_template(normalized, ext="md")
    except (KeyError, ValueError) as exc:
        raise FoundationError(
            "invalid_implementation_template",
            "Implementation Lens path_template cannot be rendered.",
        ) from exc
    if PurePosixPath(rendered).suffix not in {".md", ".html"}:
        raise FoundationError(
            "invalid_implementation_template",
            "Implementation Lens path_template must place '{ext}' as the file extension.",
        )
    return normalized


def parse_implementation_config(
    raw: dict[str, Any], paths: ProjectPaths
) -> ImplementationLensConfig:
    schema = _expect(raw, "schema_version", int, IMPLEMENTATION_SCHEMA_VERSION)
    if schema not in {LEGACY_IMPLEMENTATION_SCHEMA_VERSION, IMPLEMENTATION_SCHEMA_VERSION}:
        raise FoundationError(
            "unsupported_implementation_schema_version",
            f"Unsupported Implementation Lens schema version: {schema}.",
        )
    granularity_raw = _expect(raw, "default_granularity", str, Granularity.SYMBOL.value)
    try:
        granularity = Granularity(granularity_raw.casefold())
    except ValueError as exc:
        raise FoundationError(
            "invalid_implementation_granularity",
            "default_granularity must be 'module', 'symbol', or 'detail'.",
        ) from exc
    output = raw.get("output", {})
    limits = raw.get("limits", {})
    if not isinstance(output, dict) or not isinstance(limits, dict):
        raise FoundationError(
            "invalid_implementation_config",
            "Implementation Lens output and limits must be tables.",
        )
    defaults = default_implementation_config()
    output_path = _relative_path(
        paths, _expect(output, "path", str, defaults.output_path), "output.path"
    )
    if output_path == ".vibesecretary" or output_path.startswith(".vibesecretary/"):
        raise FoundationError(
            "invalid_implementation_path",
            "Implementation Lens reports cannot be stored inside .vibesecretary.",
        )
    default_template = (
        LEGACY_PATH_TEMPLATE
        if schema == LEGACY_IMPLEMENTATION_SCHEMA_VERSION
        else defaults.path_template
    )
    template = validate_output_template(
        _expect(output, "path_template", str, default_template)
    )
    project_model_path = _relative_path(
        paths,
        _expect(output, "project_model_path", str, defaults.project_model_path),
        "output.project_model_path",
    )
    sample_report = _render_template(template, ext="md")
    if sample_report == project_model_path or sample_report.startswith(project_model_path + "/"):
        raise FoundationError(
            "invalid_implementation_path",
            "Implementation Lens reports cannot be stored inside the project-model directory.",
        )
    index_json = _relative_path(
        paths, _expect(raw, "index_json", str, defaults.index_json), "index_json"
    )
    if not index_json.endswith(".json"):
        raise FoundationError(
            "invalid_implementation_path",
            "Implementation Lens index_json must end with '.json'.",
        )
    return ImplementationLensConfig(
        schema_version=schema,
        default_granularity=granularity,
        output_path=output_path,
        path_template=template,
        project_model_path=project_model_path,
        index_json=index_json,
        max_files=_positive_integer(limits, "max_files", defaults.max_files, 100_000),
        max_file_bytes=_positive_integer(
            limits, "max_file_bytes", defaults.max_file_bytes, 20 * 1024 * 1024
        ),
        max_nodes=_positive_integer(limits, "max_nodes", defaults.max_nodes, 20_000),
        max_edges=_positive_integer(limits, "max_edges", defaults.max_edges, 50_000),
        max_audit_files=_positive_integer(
            limits, "max_audit_files", defaults.max_audit_files, 100_000
        ),
    )


def load_implementation_config(
    paths: ProjectPaths, project_config: ProjectConfig
) -> ImplementationLensConfig:
    path = paths.implementation_config_file(project_config.modules.implementation_lens.config_file)
    if not path.is_file():
        raise FoundationError(
            "implementation_config_missing",
            "The configured Implementation Lens file is missing.",
        )
    if path.stat().st_size > MAX_CONFIG_BYTES:
        raise FoundationError(
            "implementation_config_too_large",
            "Implementation Lens config exceeds 1 MiB.",
        )
    try:
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise FoundationError(
            "invalid_implementation_config_toml",
            "Implementation Lens config is not valid TOML.",
        ) from exc
    return parse_implementation_config(raw, paths)


def implementation_config_digest(paths: ProjectPaths, project_config: ProjectConfig) -> str:
    path = paths.implementation_config_file(project_config.modules.implementation_lens.config_file)
    if not path.is_file():
        raise FoundationError(
            "implementation_config_missing",
            "The configured Implementation Lens file is missing.",
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_implementation_config(config: ImplementationLensConfig) -> str:
    return "\n".join(
        [
            "# path_template examples:",
            '#   Default:       "reports/{granularity}/{slug}_{timestamp}.{ext}"',
            '#   Flat:          "{slug}_{timestamp}.{ext}"',
            '#   By year/month: "reports/{year}/{month}/{slug}_{timestamp}.{ext}"',
            "# Available variables: slug, timestamp, granularity, language, year, month, day, ext.",
            "# project_model_path is stable and independent from query-report granularity.",
            "# Editing this file invalidates confirmation. Existing reports are never moved automatically.",
            "",
            f"schema_version = {config.schema_version}",
            f'default_granularity = "{config.default_granularity.value}"',
            f'index_json = "{config.index_json}"',
            "",
            "[output]",
            f'path = "{config.output_path}"',
            f'path_template = "{config.path_template}"',
            f'project_model_path = "{config.project_model_path}"',
            "",
            "[limits]",
            f"max_files = {config.max_files}",
            f"max_file_bytes = {config.max_file_bytes}",
            f"max_nodes = {config.max_nodes}",
            f"max_edges = {config.max_edges}",
            f"max_audit_files = {config.max_audit_files}",
            "",
        ]
    )


def save_implementation_config(
    paths: ProjectPaths,
    project_config: ProjectConfig,
    config: ImplementationLensConfig,
) -> None:
    target = paths.implementation_config_file(project_config.modules.implementation_lens.config_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix="implementation-lens-", suffix=".toml.tmp", dir=target.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(render_implementation_config(config))
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
