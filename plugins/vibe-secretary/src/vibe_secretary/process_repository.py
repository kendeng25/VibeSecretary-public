"""Deterministic Process Hub document storage, scanning, and indexing."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from vibe_secretary.errors import FoundationError
from vibe_secretary.paths import ProjectPaths, ensure_within_root
from vibe_secretary.process_config import CollectionConfig, ProcessHubConfig
from vibe_secretary.process_models import ProcessDocument, ProcessIssue, ProcessScan
from vibe_secretary.scope import ScopePolicy

MAX_PROCESS_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_RETURNED_BODY_CHARS = 20_000
_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)(.*)\Z", re.DOTALL)
_ID_NUMBER = re.compile(r"^(?P<prefix>[A-Z][A-Z0-9_-]*)-(?P<number>[0-9]{4,})$")
_INVALID_SEGMENT = re.compile(r"[^A-Za-z0-9_-]+")
_DASHES = re.compile(r"[-_]{2,}")


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _iso_date(value: Any, field: str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise FoundationError(
                "invalid_document_metadata",
                f"Document field '{field}' must be an ISO date.",
            ) from exc
    raise FoundationError(
        "invalid_document_metadata",
        f"Document field '{field}' must be an ISO date.",
    )


def normalize_metadata(raw: Any) -> dict[str, Any]:
    """Normalize front matter while preserving supported custom scalar fields."""

    if not isinstance(raw, dict):
        raise FoundationError(
            "invalid_front_matter",
            "Process document front matter must be a YAML mapping.",
        )
    metadata = dict(raw)
    for field in ("id", "type", "title", "status"):
        value = metadata.get(field)
        if value is not None and not isinstance(value, str):
            raise FoundationError(
                "invalid_document_metadata",
                f"Document field '{field}' must be a string.",
            )
    for field in ("created_at", "updated_at"):
        if field in metadata:
            metadata[field] = _iso_date(metadata[field], field)
    for field in ("stage", "task", "slug"):
        value = metadata.get(field, "")
        if value is None:
            metadata[field] = ""
        elif not isinstance(value, str):
            raise FoundationError(
                "invalid_document_metadata",
                f"Document field '{field}' must be a string.",
            )
    for field in ("tags", "relates_to"):
        value = metadata.get(field, [])
        if value is None:
            value = []
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise FoundationError(
                "invalid_document_metadata",
                f"Document field '{field}' must be a list of non-empty strings.",
            )
        metadata[field] = list(dict.fromkeys(value))
    return metadata


def parse_process_markdown(content: str) -> tuple[dict[str, Any], str]:
    """Parse a managed Markdown document."""

    match = _FRONT_MATTER.match(content)
    if not match:
        raise FoundationError(
            "missing_front_matter",
            "Process document does not start with YAML front matter.",
        )
    try:
        raw = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise FoundationError(
            "invalid_front_matter",
            "Process document front matter is not valid YAML.",
        ) from exc
    return normalize_metadata(raw), match.group(2).lstrip("\r\n")


def render_process_markdown(metadata: dict[str, Any], body: str) -> str:
    """Render normalized metadata and body as stable UTF-8 Markdown."""

    normalized = normalize_metadata(metadata)
    ordered: dict[str, Any] = {}
    for field in (
        "id",
        "type",
        "title",
        "status",
        "stage",
        "task",
        "slug",
        "created_at",
        "updated_at",
        "tags",
        "relates_to",
    ):
        if field in normalized and normalized[field] not in ("", [], None):
            ordered[field] = normalized[field]
    for key, value in normalized.items():
        if key not in ordered and key not in {"stage", "task", "slug", "tags", "relates_to"}:
            ordered[key] = value
    front_matter = yaml.safe_dump(
        ordered,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    normalized_body = body.replace("\r\n", "\n").replace("\r", "\n").lstrip("\n")
    suffix = normalized_body.rstrip() + "\n" if normalized_body else ""
    return f"---\n{front_matter}\n---\n\n{suffix}"


def slugify(value: str, fallback: str = "document") -> str:
    """Create a safe ASCII path segment without interpreting user text as a path."""

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _INVALID_SEGMENT.sub("-", normalized).strip("-_").lower()
    slug = _DASHES.sub("-", slug)
    return slug[:80] or fallback


def _segment(value: Any, fallback: str, *, preserve_case: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    cleaned = _INVALID_SEGMENT.sub("-", text).strip("-_")
    cleaned = _DASHES.sub("-", cleaned)
    if not preserve_case:
        cleaned = cleaned.lower()
    return cleaned[:80] or fallback


def render_document_path(
    paths: ProjectPaths,
    collection: CollectionConfig,
    metadata: dict[str, Any],
    explicit_slug: str = "",
) -> Path:
    """Render and contain one configured document path."""

    created = _iso_date(metadata.get("created_at", utc_today()), "created_at")
    created_date = date.fromisoformat(created)
    document_id = str(metadata.get("id", ""))
    title = str(metadata.get("title", ""))
    values = {
        "id": _segment(document_id, "DOCUMENT", preserve_case=True),
        "slug": slugify(explicit_slug or title, fallback=document_id.lower() or "document"),
        "stage": _segment(metadata.get("stage"), "_standalone"),
        "task": _segment(metadata.get("task"), "_general"),
        "year": f"{created_date.year:04d}",
        "month": f"{created_date.month:02d}",
        "day": f"{created_date.day:02d}",
    }
    rendered = collection.path_template.format(**values)
    collection_root = ensure_within_root(paths.root, paths.root / collection.path)
    target = ensure_within_root(collection_root, collection_root / Path(rendered))
    if target.suffix.lower() != ".md":
        raise FoundationError("invalid_document_path", "Rendered process document must be Markdown.")
    return target


def _relative(paths: ProjectPaths, path: Path) -> str:
    return path.resolve(strict=False).relative_to(paths.root.resolve(strict=False)).as_posix()


def _read_document(
    paths: ProjectPaths,
    collection: CollectionConfig,
    path: Path,
) -> ProcessDocument:
    relative = _relative(paths, path)
    if path.stat().st_size > MAX_PROCESS_DOCUMENT_BYTES:
        issue = ProcessIssue(
            "document_too_large",
            "Process document exceeds the 2 MiB safety limit.",
            relative,
        )
        return ProcessDocument(path, relative, collection.id, False, None, "", [issue])
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        issue = ProcessIssue(
            "document_not_utf8",
            "Process document must be UTF-8 text.",
            relative,
        )
        return ProcessDocument(path, relative, collection.id, False, None, "", [issue])
    try:
        metadata, body = parse_process_markdown(content)
    except FoundationError as exc:
        issue = ProcessIssue(exc.code, exc.message, relative, severity="warning")
        return ProcessDocument(path, relative, collection.id, False, None, content, [issue])
    return ProcessDocument(path, relative, collection.id, True, metadata, body)


def _validate_document(
    paths: ProjectPaths,
    collection: CollectionConfig,
    document: ProcessDocument,
) -> None:
    if not document.managed or document.metadata is None:
        return
    metadata = document.metadata
    document_id = document.document_id
    for field in collection.required_fields:
        value = metadata.get(field)
        if value in (None, "", []):
            document.issues.append(
                ProcessIssue(
                    "missing_required_field",
                    f"Required metadata field '{field}' is missing.",
                    document.relative_path,
                    document_id,
                    details={"field": field},
                )
            )
    id_match = _ID_NUMBER.fullmatch(document_id)
    if not id_match or id_match.group("prefix") != collection.id_prefix:
        document.issues.append(
            ProcessIssue(
                "invalid_document_id",
                "Document id does not match the collection id_prefix and numeric format.",
                document.relative_path,
                document_id,
            )
        )
    if metadata.get("type") != collection.kind:
        document.issues.append(
            ProcessIssue(
                "collection_type_mismatch",
                "Document type does not match its collection kind.",
                document.relative_path,
                document_id,
            )
        )
    if metadata.get("status") not in collection.statuses:
        document.issues.append(
            ProcessIssue(
                "invalid_document_status",
                "Document status is not allowed by the collection lifecycle.",
                document.relative_path,
                document_id,
            )
        )
    try:
        expected = render_document_path(
            paths,
            collection,
            metadata,
            explicit_slug=str(metadata.get("slug", "")),
        )
        if _relative(paths, expected) != document.relative_path:
            document.issues.append(
                ProcessIssue(
                    "path_template_mismatch",
                    "Document path does not match the configured path_template.",
                    document.relative_path,
                    document_id,
                    severity="warning",
                    details={"expected_path": _relative(paths, expected)},
                )
            )
    except FoundationError as exc:
        document.issues.append(
            ProcessIssue(exc.code, exc.message, document.relative_path, document_id)
        )


def scan_process_documents(
    paths: ProjectPaths,
    config: ProcessHubConfig,
    policy: ScopePolicy,
) -> ProcessScan:
    """Scan configured collections without modifying consumer project files."""

    documents: list[ProcessDocument] = []
    issues: list[ProcessIssue] = []
    for collection in config.collections:
        collection_decision = policy.decide(collection.path)
        if not collection_decision.allowed:
            issues.append(
                ProcessIssue(
                    "collection_outside_scope",
                    "Collection path is excluded by the confirmed read scope.",
                    collection.path,
                    severity="error",
                    details={"collection": collection.id},
                )
            )
            continue
        root = ensure_within_root(paths.root, paths.root / collection.path)
        if not root.exists():
            continue
        if not root.is_dir():
            issues.append(
                ProcessIssue(
                    "collection_not_directory",
                    "Configured collection path is not a directory.",
                    collection.path,
                    details={"collection": collection.id},
                )
            )
            continue
        for candidate in sorted(root.rglob("*.md"), key=lambda item: item.as_posix().lower()):
            decision = policy.decide(candidate)
            if not decision.allowed:
                issues.append(
                    ProcessIssue(
                        "document_outside_scope",
                        "A collection document is excluded by the confirmed read scope.",
                        decision.relative_path,
                        severity="warning",
                    )
                )
                continue
            if not candidate.is_file():
                continue
            document = _read_document(paths, collection, candidate)
            _validate_document(paths, collection, document)
            documents.append(document)

    by_id: dict[str, list[ProcessDocument]] = {}
    for document in documents:
        if document.document_id:
            by_id.setdefault(document.document_id, []).append(document)
    for document_id, duplicates in by_id.items():
        if len(duplicates) < 2:
            continue
        paths_list = [document.relative_path for document in duplicates]
        for document in duplicates:
            document.issues.append(
                ProcessIssue(
                    "duplicate_document_id",
                    "Document id is used by more than one process document.",
                    document.relative_path,
                    document_id,
                    details={"paths": paths_list},
                )
            )
    known_ids = set(by_id)
    referenced_by_build_history: set[str] = set()
    for document in documents:
        if not document.managed or document.metadata is None:
            continue
        collection = config.collection(document.collection_id)
        if collection.kind == "build_history":
            referenced_by_build_history.update(document.metadata.get("relates_to", []))
        for target in document.metadata.get("relates_to", []):
            if target not in known_ids:
                document.issues.append(
                    ProcessIssue(
                        "unknown_relation_target",
                        "Document relation points to an unknown document id.",
                        document.relative_path,
                        document.document_id,
                        details={"target": target},
                    )
                )
    for document in documents:
        if not document.managed or document.metadata is None:
            continue
        collection = config.collection(document.collection_id)
        if (
            collection.kind == "plan"
            and document.metadata.get("status") == "completed"
            and document.document_id not in referenced_by_build_history
        ):
            document.issues.append(
                ProcessIssue(
                    "completed_plan_without_build_history",
                    "Completed plan is not referenced by a build history document.",
                    document.relative_path,
                    document.document_id,
                    severity="warning",
                )
            )
    for document in documents:
        issues.extend(document.issues)
    return ProcessScan(documents=documents, issues=issues)


def next_document_id(scan: ProcessScan, collection: CollectionConfig) -> str:
    """Return the next stable numeric id for a collection prefix."""

    highest = 0
    for document in scan.documents:
        match = _ID_NUMBER.fullmatch(document.document_id)
        if match and match.group("prefix") == collection.id_prefix:
            highest = max(highest, int(match.group("number")))
    return f"{collection.id_prefix}-{highest + 1:04d}"


def atomic_write_text(target: Path, content: str, *, overwrite: bool) -> None:
    """Write UTF-8 content atomically, optionally refusing replacement."""

    target.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        try:
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
            return
        except FileExistsError as exc:
            raise FoundationError(
                "target_exists",
                "Refusing to overwrite an existing process document.",
                {"path": str(target)},
            ) from exc
    handle, temporary_name = tempfile.mkstemp(
        prefix=f"{target.name}-",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_reverse_relations(scan: ProcessScan) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for document in scan.documents:
        if not document.managed or document.metadata is None:
            continue
        for target in document.metadata.get("relates_to", []):
            reverse.setdefault(target, []).append(document.document_id)
    return {key: sorted(set(value)) for key, value in reverse.items()}


def render_indexes(
    paths: ProjectPaths,
    config: ProcessHubConfig,
    scan: ProcessScan,
) -> tuple[str, str]:
    """Render rebuildable JSON and Markdown indexes."""

    reverse = build_reverse_relations(scan)
    documents = []
    for document in scan.documents:
        summary = document.summary()
        summary["referenced_by"] = reverse.get(document.document_id, [])
        documents.append(summary)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
        "issues": [issue.to_dict() for issue in scan.issues],
    }
    json_content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    index_path = ensure_within_root(paths.root, paths.root / config.index_markdown)
    lines = ["# Process Hub Index", "", "This file is generated and can be rebuilt.", ""]
    for collection in config.collections:
        lines.extend([f"## {collection.id}", ""])
        collection_documents = [
            document for document in scan.documents if document.collection_id == collection.id
        ]
        if not collection_documents:
            lines.extend(["No documents.", ""])
            continue
        for document in collection_documents:
            summary = document.summary()
            relative_link = os.path.relpath(document.path, index_path.parent).replace("\\", "/")
            label = summary["id"] or summary["title"]
            status = summary["status"] or "unmanaged"
            lines.append(f"- [{label}]({relative_link}) — {summary['title']} ({status})")
            if summary["relates_to"]:
                lines.append(f"  - relates to: {', '.join(summary['relates_to'])}")
            if reverse.get(document.document_id):
                lines.append(f"  - referenced by: {', '.join(reverse[document.document_id])}")
        lines.append("")
    lines.extend(["## Consistency", "", f"Issues: {len(scan.issues)}", ""])
    for issue in scan.issues:
        location = f" `{issue.path}`" if issue.path else ""
        lines.append(f"- `{issue.severity}` `{issue.code}`{location}: {issue.message}")
    markdown_content = "\n".join(lines).rstrip() + "\n"
    return json_content, markdown_content


def body_preview(document: ProcessDocument, include_body: bool) -> dict[str, Any]:
    result = document.summary()
    result["metadata"] = document.metadata
    if include_body:
        result["body"] = document.body[:MAX_RETURNED_BODY_CHARS]
        result["body_truncated"] = len(document.body) > MAX_RETURNED_BODY_CHARS
    return result
