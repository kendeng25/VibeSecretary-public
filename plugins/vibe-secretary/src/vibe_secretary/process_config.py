"""Process Hub collection configuration and deterministic TOML persistence."""

from __future__ import annotations

import hashlib
import os
import re
import string
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from vibe_secretary.config import ProjectConfig
from vibe_secretary.errors import FoundationError
from vibe_secretary.paths import ProjectPaths, ensure_within_root

PROCESS_HUB_SCHEMA_VERSION = 2
LEGACY_PROCESS_HUB_SCHEMA_VERSION = 1
DEFAULT_INDEX_JSON = ".vibesecretary/process-index.json"
DEFAULT_INDEX_MARKDOWN = ".vibesecretary/process-index.md"
CORE_REQUIRED_FIELDS = ("id", "type", "title", "status", "created_at", "updated_at")
DEFAULT_STATUSES = ("draft", "active", "blocked", "completed", "superseded", "archived")
DEFAULT_TERMINAL_STATUSES = ("completed", "superseded", "archived")
ALLOWED_TEMPLATE_FIELDS = {"id", "slug", "stage", "task", "year", "month", "day"}
MAX_PROCESS_CONFIG_BYTES = 1024 * 1024
MAX_COLLECTION_USAGE_CHARS = 2000
_COLLECTION_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_TYPE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_LEGACY_ID_PREFIX = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")
_DERIVED_ID_PREFIX = re.compile(r"^[A-Z][A-Z0-9_-]{0,63}$")

DEFAULT_COLLECTION_USAGE = {
    "plans": (
        "Create before major work to record goals, scope, design choices, and acceptance criteria; "
        "maintain it as implementation facts change."
    ),
    "build_hist": (
        "Create after implementation and verification to record actual changes, checks, and "
        "remaining work; relate it to the source plan when one exists."
    ),
}


@dataclass(frozen=True, slots=True)
class CollectionConfig:
    """Validated storage, metadata, and lifecycle rules for one document collection."""

    id: str
    kind: str
    path: str
    id_prefix: str
    path_template: str
    usage: str = ""
    required_fields: tuple[str, ...] = CORE_REQUIRED_FIELDS
    statuses: tuple[str, ...] = DEFAULT_STATUSES
    initial_status: str = "draft"
    terminal_statuses: tuple[str, ...] = DEFAULT_TERMINAL_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "usage": self.usage,
            "path": self.path,
            "path_template": self.path_template,
            "required_metadata": [
                field for field in self.required_fields if field not in CORE_REQUIRED_FIELDS
            ],
            "statuses": list(self.statuses),
            "initial_status": self.initial_status,
            "terminal_statuses": list(self.terminal_statuses),
        }


@dataclass(frozen=True, slots=True)
class ProcessHubConfig:
    """Validated Process Hub module configuration."""

    schema_version: int = PROCESS_HUB_SCHEMA_VERSION
    index_json: str = DEFAULT_INDEX_JSON
    index_markdown: str = DEFAULT_INDEX_MARKDOWN
    collections: tuple[CollectionConfig, ...] = ()

    def collection(self, collection_id: str) -> CollectionConfig:
        for collection in self.collections:
            if collection.id == collection_id:
                return collection
        raise FoundationError(
            "unknown_collection",
            f"Unknown Process Hub collection: {collection_id}.",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "index_json": self.index_json,
            "index_markdown": self.index_markdown,
            "collections": [collection.to_dict() for collection in self.collections],
        }


def default_process_config() -> ProcessHubConfig:
    """Return the opinionated but editable default collection layout."""

    return ProcessHubConfig(
        collections=(
            CollectionConfig(
                id="plans",
                kind="plan",
                path="plans",
                id_prefix="PLAN",
                path_template="{year}-{month}-{day}/{id}_{slug}.md",
                usage=DEFAULT_COLLECTION_USAGE["plans"],
            ),
            CollectionConfig(
                id="build_hist",
                kind="build_history",
                path="build_hist",
                id_prefix="BUILD",
                path_template="{year}-{month}-{day}/{id}_{slug}.md",
                usage=DEFAULT_COLLECTION_USAGE["build_hist"],
                initial_status="completed",
            ),
        )
    )


def _expect(raw: dict[str, Any], key: str, expected: type, default: Any) -> Any:
    value = raw.get(key, default)
    invalid_boolean_integer = expected is int and isinstance(value, bool)
    if not isinstance(value, expected) or invalid_boolean_integer:
        raise FoundationError(
            "invalid_process_config",
            f"Process Hub field '{key}' has an invalid type.",
        )
    return value


def _string_list(raw: dict[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = raw.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise FoundationError(
            "invalid_process_config",
            f"Process Hub field '{key}' must be a list of non-empty strings.",
        )
    if len(value) != len(set(value)):
        raise FoundationError(
            "invalid_process_config",
            f"Process Hub field '{key}' cannot contain duplicates.",
        )
    return tuple(value)


def _validate_relative_path(paths: ProjectPaths, value: str, field: str) -> str:
    raw = value.replace("\\", "/")
    raw_path = PurePosixPath(raw)
    if raw_path.is_absolute() or Path(value).is_absolute():
        raise FoundationError(
            "invalid_process_path",
            f"Process Hub {field} must be project-relative.",
        )
    normalized = raw.strip("/")
    pure = PurePosixPath(normalized)
    if not normalized or normalized == "." or pure.is_absolute() or ".." in pure.parts:
        raise FoundationError(
            "invalid_process_path",
            f"Process Hub {field} must be a non-empty project-relative path without '..'.",
        )
    ensure_within_root(paths.root, paths.root / Path(normalized))
    return normalized


def validate_path_template(value: str) -> str:
    """Validate a safe relative Markdown path template."""

    raw = value.replace("\\", "/")
    if PurePosixPath(raw).is_absolute() or Path(value).is_absolute():
        raise FoundationError(
            "invalid_path_template",
            "path_template must be relative.",
        )
    normalized = raw.strip("/")
    pure = PurePosixPath(normalized)
    if not normalized or pure.is_absolute() or ".." in pure.parts or not normalized.endswith(".md"):
        raise FoundationError(
            "invalid_path_template",
            "path_template must be a relative Markdown path without '..'.",
        )
    try:
        fields = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(normalized)
            if field_name
        }
    except ValueError as exc:
        raise FoundationError("invalid_path_template", "path_template has invalid braces.") from exc
    unknown = fields - ALLOWED_TEMPLATE_FIELDS
    if unknown:
        raise FoundationError(
            "invalid_path_template",
            "path_template contains unsupported fields.",
            {"unsupported_fields": sorted(unknown)},
        )
    if "id" not in fields:
        raise FoundationError("invalid_path_template", "path_template must contain '{id}'.")
    try:
        rendered = normalized.format(**{field: "sample" for field in ALLOWED_TEMPLATE_FIELDS})
    except (KeyError, ValueError) as exc:
        raise FoundationError("invalid_path_template", "path_template cannot be rendered.") from exc
    rendered_path = PurePosixPath(rendered)
    if rendered_path.is_absolute() or ".." in rendered_path.parts:
        raise FoundationError("invalid_path_template", "path_template renders outside its collection.")
    return normalized


def _default_usage(collection_id: str) -> str:
    return DEFAULT_COLLECTION_USAGE.get(
        collection_id,
        f"Store and maintain process documents belonging to the '{collection_id}' collection.",
    )


def _derived_kind(collection_id: str) -> str:
    return {"plans": "plan", "build_hist": "build_history"}.get(
        collection_id, collection_id
    )


def _derived_prefix(collection_id: str) -> str:
    prefix = {"plans": "PLAN", "build_hist": "BUILD"}.get(
        collection_id, collection_id.upper()
    )
    if not _DERIVED_ID_PREFIX.fullmatch(prefix):
        raise FoundationError("invalid_id_prefix", "Derived collection ID prefix is invalid.")
    return prefix


def _parse_collection(raw: Any, paths: ProjectPaths, schema_version: int) -> CollectionConfig:
    if not isinstance(raw, dict):
        raise FoundationError("invalid_process_config", "Each collection must be a TOML table.")
    collection_id = _expect(raw, "id", str, "")
    path = _validate_relative_path(paths, _expect(raw, "path", str, ""), "collection path")
    template = validate_path_template(_expect(raw, "path_template", str, ""))
    if not _COLLECTION_ID.fullmatch(collection_id):
        raise FoundationError("invalid_collection_id", "Collection id has an invalid format.")
    if schema_version == LEGACY_PROCESS_HUB_SCHEMA_VERSION:
        kind = _expect(raw, "kind", str, "")
        id_prefix = _expect(raw, "id_prefix", str, "")
        usage = _expect(raw, "usage", str, _default_usage(collection_id)).strip()
        if not _TYPE_NAME.fullmatch(kind):
            raise FoundationError("invalid_collection_kind", "Collection kind has an invalid format.")
        if not _LEGACY_ID_PREFIX.fullmatch(id_prefix):
            raise FoundationError("invalid_id_prefix", "Collection id_prefix has an invalid format.")
        required = _string_list(raw, "required_fields", CORE_REQUIRED_FIELDS)
    else:
        unsupported = sorted(
            key for key in ("description", "kind", "id_prefix", "required_fields") if key in raw
        )
        if unsupported:
            raise FoundationError(
                "unsupported_collection_fields",
                "Schema 2 collection configuration contains internal or obsolete fields.",
                {"fields": unsupported},
            )
        kind = _derived_kind(collection_id)
        id_prefix = _derived_prefix(collection_id)
        usage = _expect(raw, "usage", str, "").strip()
        if not usage:
            raise FoundationError(
                "invalid_collection_usage", "Collection usage must be a non-empty string."
            )
        if len(usage) > MAX_COLLECTION_USAGE_CHARS:
            raise FoundationError(
                "invalid_collection_usage",
                f"Collection usage cannot exceed {MAX_COLLECTION_USAGE_CHARS} characters.",
            )
        extra_required = _string_list(raw, "required_metadata", ())
        repeated_core = sorted(set(extra_required) & set(CORE_REQUIRED_FIELDS))
        if repeated_core:
            raise FoundationError(
                "invalid_required_metadata",
                "required_metadata cannot repeat core document fields.",
                {"core_fields": repeated_core},
            )
        required = (*CORE_REQUIRED_FIELDS, *extra_required)
    if path == ".vibesecretary" or path.startswith(".vibesecretary/"):
        raise FoundationError(
            "invalid_collection_path",
            "Process collections cannot be stored inside .vibesecretary.",
        )
    missing_core = sorted(set(CORE_REQUIRED_FIELDS) - set(required))
    if missing_core:
        raise FoundationError(
            "invalid_required_fields",
            "Collection required_fields must include the core document fields.",
            {"missing_fields": missing_core},
        )
    statuses = _string_list(raw, "statuses", DEFAULT_STATUSES)
    default_initial_status = (
        "completed"
        if schema_version == PROCESS_HUB_SCHEMA_VERSION and collection_id == "build_hist"
        else "draft"
    )
    initial_status = _expect(raw, "initial_status", str, default_initial_status)
    terminal = _string_list(raw, "terminal_statuses", DEFAULT_TERMINAL_STATUSES)
    if initial_status not in statuses or not set(terminal).issubset(statuses):
        raise FoundationError(
            "invalid_lifecycle",
            "initial_status and terminal_statuses must belong to statuses.",
        )
    return CollectionConfig(
        id=collection_id,
        kind=kind,
        path=path,
        id_prefix=id_prefix,
        path_template=template,
        usage=usage,
        required_fields=required,
        statuses=statuses,
        initial_status=initial_status,
        terminal_statuses=terminal,
    )


def parse_process_config(data: dict[str, Any], paths: ProjectPaths) -> ProcessHubConfig:
    """Validate decoded Process Hub TOML."""

    schema_version = _expect(data, "schema_version", int, LEGACY_PROCESS_HUB_SCHEMA_VERSION)
    if schema_version not in {LEGACY_PROCESS_HUB_SCHEMA_VERSION, PROCESS_HUB_SCHEMA_VERSION}:
        raise FoundationError(
            "unsupported_process_schema_version",
            f"Unsupported Process Hub schema version: {schema_version}.",
        )
    index_json = _validate_relative_path(
        paths,
        _expect(data, "index_json", str, DEFAULT_INDEX_JSON),
        "index_json",
    )
    index_markdown = _validate_relative_path(
        paths,
        _expect(data, "index_markdown", str, DEFAULT_INDEX_MARKDOWN),
        "index_markdown",
    )
    if not index_json.endswith(".json") or not index_markdown.endswith(".md"):
        raise FoundationError(
            "invalid_index_path",
            "Process Hub index paths must end in .json and .md respectively.",
        )
    raw_collections = data.get("collections")
    if not isinstance(raw_collections, list) or not raw_collections:
        raise FoundationError(
            "invalid_process_config",
            "Process Hub requires at least one [[collections]] table.",
        )
    collections = tuple(_parse_collection(raw, paths, schema_version) for raw in raw_collections)
    ids = [collection.id for collection in collections]
    if len(ids) != len(set(ids)):
        raise FoundationError("duplicate_collection", "Collection ids must be unique.")
    prefixes = [collection.id_prefix for collection in collections]
    if len(prefixes) != len(set(prefixes)):
        raise FoundationError("duplicate_id_prefix", "Collection id_prefix values must be unique.")
    resolved_paths = [
        (collection.id, ensure_within_root(paths.root, paths.root / collection.path))
        for collection in collections
    ]
    for index, (left_id, left) in enumerate(resolved_paths):
        for right_id, right in resolved_paths[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                raise FoundationError(
                    "overlapping_collections",
                    "Process Hub collection paths cannot overlap.",
                    {"collections": [left_id, right_id]},
                )
    return ProcessHubConfig(
        schema_version=schema_version,
        index_json=index_json,
        index_markdown=index_markdown,
        collections=collections,
    )


def load_process_config(paths: ProjectPaths, project_config: ProjectConfig) -> ProcessHubConfig:
    """Load Process Hub config from the project state directory."""

    config_path = paths.process_config_file(project_config.modules.process_hub.config_file)
    if not config_path.is_file():
        raise FoundationError(
            "process_hub_not_initialized",
            "Process Hub is not initialized for this project.",
        )
    if config_path.stat().st_size > MAX_PROCESS_CONFIG_BYTES:
        raise FoundationError(
            "process_config_too_large",
            "The Process Hub config exceeds the 1 MiB safety limit.",
        )
    try:
        with config_path.open("rb") as stream:
            raw = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise FoundationError(
            "invalid_process_config_toml",
            "The Process Hub config is not valid TOML.",
        ) from exc
    return parse_process_config(raw, paths)


def process_config_digest(paths: ProjectPaths, project_config: ProjectConfig) -> str:
    """Return the SHA-256 digest of the configured Process Hub TOML bytes."""

    target = paths.process_config_file(project_config.modules.process_hub.config_file)
    if not target.is_file():
        raise FoundationError(
            "process_hub_not_initialized",
            "Process Hub is not initialized for this project.",
        )
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_list(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def render_process_config(config: ProcessHubConfig) -> str:
    """Render Process Hub config in a stable, human-editable form."""

    if config.schema_version == LEGACY_PROCESS_HUB_SCHEMA_VERSION:
        return _render_legacy_process_config(config)
    if config.schema_version != PROCESS_HUB_SCHEMA_VERSION:
        raise FoundationError(
            "unsupported_process_schema_version",
            f"Unsupported Process Hub schema version: {config.schema_version}.",
        )
    lines = [
        "# Each collection needs only id, usage, path, and path_template.",
        "# Internal type, document ID prefix, core metadata, and default lifecycle are managed by Process Hub.",
        "#",
        "# path_template examples:",
        '#   Flat:          "{id}_{slug}.md"',
        '#   By date:       "{year}-{month}-{day}/{id}_{slug}.md"',
        '#   By year/month: "{year}/{month}/{id}_{slug}.md"',
        '#   By stage:      "{stage}/{id}_{slug}.md"',
        '#   By stage/task: "{stage}/{task}/{id}_{slug}.md"',
        "# Available variables: id, slug, stage, task, year, month, day.",
        "# Editing this file invalidates confirmation. Existing files are never moved automatically.",
        "",
        f"schema_version = {config.schema_version}",
        "",
    ]
    if config.index_json != DEFAULT_INDEX_JSON:
        lines.insert(-1, f"index_json = {_toml_string(config.index_json)}")
    if config.index_markdown != DEFAULT_INDEX_MARKDOWN:
        lines.insert(-1, f"index_markdown = {_toml_string(config.index_markdown)}")
    for collection in config.collections:
        if not collection.usage.strip():
            raise FoundationError(
                "invalid_collection_usage", "Collection usage must be a non-empty string."
            )
        lines.extend([
            "[[collections]]",
            f"id = {_toml_string(collection.id)}",
            f"usage = {_toml_string(collection.usage)}",
            f"path = {_toml_string(collection.path)}",
            f"path_template = {_toml_string(collection.path_template)}",
        ])
        extra_required = tuple(
            field for field in collection.required_fields if field not in CORE_REQUIRED_FIELDS
        )
        if extra_required:
            lines.append(f"required_metadata = {_toml_list(extra_required)}")
        default_initial = "completed" if collection.id == "build_hist" else "draft"
        if collection.statuses != DEFAULT_STATUSES:
            lines.append(f"statuses = {_toml_list(collection.statuses)}")
        if collection.initial_status != default_initial:
            lines.append(f"initial_status = {_toml_string(collection.initial_status)}")
        if collection.terminal_statuses != DEFAULT_TERMINAL_STATUSES:
            lines.append(f"terminal_statuses = {_toml_list(collection.terminal_statuses)}")
        lines.append("")
    return "\n".join(lines)


def _render_legacy_process_config(config: ProcessHubConfig) -> str:
    lines = [
        f"schema_version = {config.schema_version}",
        f"index_json = {_toml_string(config.index_json)}",
        f"index_markdown = {_toml_string(config.index_markdown)}",
        "",
    ]
    for collection in config.collections:
        lines.extend([
            "[[collections]]",
            f"id = {_toml_string(collection.id)}",
            f"kind = {_toml_string(collection.kind)}",
            f"path = {_toml_string(collection.path)}",
            f"id_prefix = {_toml_string(collection.id_prefix)}",
            f"path_template = {_toml_string(collection.path_template)}",
            f"required_fields = {_toml_list(collection.required_fields)}",
            f"statuses = {_toml_list(collection.statuses)}",
            f"initial_status = {_toml_string(collection.initial_status)}",
            f"terminal_statuses = {_toml_list(collection.terminal_statuses)}",
            "",
        ])
    return "\n".join(lines)


def save_process_config(
    paths: ProjectPaths,
    project_config: ProjectConfig,
    config: ProcessHubConfig,
) -> Path:
    """Atomically persist Process Hub config."""

    target = paths.process_config_file(project_config.modules.process_hub.config_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix="process-hub-",
        suffix=".toml.tmp",
        dir=target.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(render_process_config(config))
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
