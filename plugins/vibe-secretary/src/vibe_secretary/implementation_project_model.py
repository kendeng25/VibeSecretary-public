"""Reusable, evidence-linked project model for Implementation Lens."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from vibe_secretary.errors import FoundationError
from vibe_secretary.implementation_config import ImplementationLensConfig
from vibe_secretary.implementation_models import (
    EvidenceRef,
    ImplementationIndex,
    ModelCoverage,
    ProjectModelManifest,
    ProjectRecord,
    ProjectRecordKind,
)
from vibe_secretary.paths import ProjectPaths, ensure_within_root
from vibe_secretary.scope import ScopePolicy

PROJECT_MODEL_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 500
MAX_RECORD_TEXT = 8000
MAX_RECORD_DETAILS = 100
MAX_RECORD_EVIDENCE = 200
_RECORD_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_digest(payload: object) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256(raw)


def source_file_digests(index: ImplementationIndex) -> dict[str, str]:
    return {item.path: item.digest for item in sorted(index.files, key=lambda item: item.path)}


def source_digest(index: ImplementationIndex) -> str:
    return _canonical_digest(source_file_digests(index))


def project_model_root(
    paths: ProjectPaths, config: ImplementationLensConfig
) -> Path:
    output_root = ensure_within_root(paths.root, paths.root / config.output_path)
    return ensure_within_root(output_root, output_root / config.project_model_path)


def _relative(paths: ProjectPaths, value: Path) -> str:
    return value.relative_to(paths.root).as_posix()


def _assert_scope(policy: ScopePolicy, value: Path) -> str:
    decision = policy.decide(value)
    if not decision.allowed:
        raise FoundationError(
            "implementation_model_outside_scope",
            "The configured Implementation Lens project model is excluded by project scope.",
            {"path": decision.relative_path},
        )
    return decision.relative_path


def _manifest_path(paths: ProjectPaths, config: ImplementationLensConfig) -> Path:
    return ensure_within_root(
        project_model_root(paths, config),
        project_model_root(paths, config) / "manifest.json",
    )


def _load_manifest(path: Path) -> tuple[ProjectModelManifest | None, str]:
    if not path.is_file():
        return None, ""
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        return None, "Project-model manifest exceeds the 10 MiB safety limit."
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("manifest root must be an object")
        manifest = ProjectModelManifest.from_dict(raw)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return None, f"Project-model manifest is invalid: {exc}"
    if manifest.schema_version != PROJECT_MODEL_SCHEMA_VERSION:
        return None, (
            "Project-model schema is unsupported: "
            f"{manifest.schema_version}."
        )
    return manifest, ""


def _evidence_maps(index: ImplementationIndex) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {item.node_id: item for item in index.nodes},
        {item.edge_id: item for item in index.edges},
    )


def _evidence_path(
    evidence: EvidenceRef,
    node_by_id: dict[str, Any],
    edge_by_id: dict[str, Any],
) -> str:
    if evidence.kind == "node":
        node = node_by_id.get(evidence.ref_id)
        return "" if node is None else str(node.path)
    edge = edge_by_id.get(evidence.ref_id)
    return "" if edge is None else str(edge.evidence.path)


def inspect_project_model(
    paths: ProjectPaths,
    policy: ScopePolicy,
    config: ImplementationLensConfig,
    config_digest: str,
    index: ImplementationIndex,
) -> dict[str, Any]:
    """Inspect freshness and return only currently reusable records."""

    root = project_model_root(paths, config)
    manifest_path = _manifest_path(paths, config)
    relative_root = _assert_scope(policy, root)
    _assert_scope(policy, manifest_path)
    manifest, load_error = _load_manifest(manifest_path)
    current_files = source_file_digests(index)
    current_source_digest = source_digest(index)
    base: dict[str, Any] = {
        "path": relative_root,
        "manifest": _relative(paths, manifest_path),
        "source_digest": current_source_digest,
        "file_digests": current_files,
        "index_truncated": index.truncated,
    }
    if load_error:
        return {
            **base,
            "status": "invalid",
            "usable": False,
            "update_required": True,
            "model_digest": "",
            "coverage": ModelCoverage.PARTIAL.value,
            "records": [],
            "changed_paths": sorted(current_files),
            "stale_record_ids": [],
            "conflict_paths": [],
            "diagnostics": [load_error],
        }
    if manifest is None:
        return {
            **base,
            "status": "missing",
            "usable": False,
            "update_required": True,
            "model_digest": "",
            "coverage": ModelCoverage.PARTIAL.value,
            "records": [],
            "changed_paths": sorted(current_files),
            "stale_record_ids": [],
            "conflict_paths": [],
            "diagnostics": ["Create the reusable project model before rendering a semantic report."],
        }

    conflict_paths: list[str] = []
    for relative, expected in manifest.managed_files.items():
        target = ensure_within_root(paths.root, paths.root / relative)
        if not target.is_file() or _sha256(target.read_bytes()) != expected:
            conflict_paths.append(relative)

    old_files = manifest.file_digests
    changed_paths = sorted(
        path
        for path in set(old_files) | set(current_files)
        if old_files.get(path) != current_files.get(path)
    )
    incompatible = (
        manifest.analyzer_version != index.analyzer_version
        or manifest.config_digest != config_digest
        or manifest.scope_digest != policy.digest
    )
    node_by_id, edge_by_id = _evidence_maps(index)
    stale_ids: list[str] = []
    reusable: list[ProjectRecord] = []
    for record in manifest.records:
        record_paths = {
            _evidence_path(item, node_by_id, edge_by_id) for item in record.evidence
        }
        invalid_ref = "" in record_paths
        if incompatible or invalid_ref or record_paths.intersection(changed_paths):
            stale_ids.append(record.record_id)
        else:
            reusable.append(record)

    fresh = (
        not incompatible
        and not conflict_paths
        and not changed_paths
        and manifest.source_digest == current_source_digest
    )
    usable = not conflict_paths and not incompatible
    status = "fresh" if fresh else "conflict" if conflict_paths else "stale"
    diagnostics = list(manifest.diagnostics)
    if incompatible:
        diagnostics.append(
            "Analyzer, Lens configuration, or read scope changed; rebuild affected project records."
        )
    if conflict_paths:
        diagnostics.append(
            "Managed project-model files changed outside Implementation Lens; explicit replacement confirmation is required."
        )
    if manifest.coverage is ModelCoverage.PARTIAL:
        diagnostics.append("The reusable project model declares partial coverage.")
    return {
        **base,
        "status": status,
        "usable": usable,
        "update_required": not fresh or manifest.coverage is ModelCoverage.PARTIAL,
        "model_digest": manifest.model_digest,
        "coverage": manifest.coverage.value,
        "covered_paths": list(manifest.covered_paths),
        "records": [item.to_dict() for item in reusable],
        "all_records": [item.to_dict() for item in manifest.records],
        "changed_paths": changed_paths,
        "stale_record_ids": sorted(stale_ids),
        "conflict_paths": sorted(conflict_paths),
        "diagnostics": list(dict.fromkeys(diagnostics)),
    }


def _bounded_text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise FoundationError(
            "invalid_implementation_model",
            f"Project-model field '{field}' must be a string.",
        )
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise FoundationError(
            "invalid_implementation_model",
            f"Project-model field '{field}' cannot be empty.",
        )
    if len(normalized) > MAX_RECORD_TEXT:
        raise FoundationError(
            "invalid_implementation_model",
            f"Project-model field '{field}' exceeds {MAX_RECORD_TEXT} characters.",
        )
    return normalized


def _parse_evidence(
    raw: Any,
    node_by_id: dict[str, Any],
    edge_by_id: dict[str, Any],
    field: str,
) -> tuple[EvidenceRef, ...]:
    if not isinstance(raw, list) or not raw:
        raise FoundationError(
            "invalid_implementation_evidence",
            f"'{field}' requires at least one evidence reference.",
        )
    if len(raw) > MAX_RECORD_EVIDENCE:
        raise FoundationError(
            "invalid_implementation_evidence",
            f"'{field}' exceeds the evidence safety limit.",
        )
    parsed: list[EvidenceRef] = []
    for position, item in enumerate(raw):
        if not isinstance(item, dict):
            raise FoundationError(
                "invalid_implementation_evidence",
                f"'{field}[{position}]' must be an object.",
            )
        kind = str(item.get("kind", ""))
        ref_id = str(item.get("ref_id", ""))
        if kind == "node":
            exists = ref_id in node_by_id
        elif kind == "edge":
            exists = ref_id in edge_by_id
        else:
            exists = False
        if not exists:
            raise FoundationError(
                "invalid_implementation_evidence",
                "Evidence must reference an existing indexed node or edge.",
                {"kind": kind, "ref_id": ref_id},
            )
        parsed.append(
            EvidenceRef(
                kind=kind,
                ref_id=ref_id,
                claim=_bounded_text(
                    item.get("claim", ""),
                    f"{field}[{position}].claim",
                    allow_empty=True,
                ),
            )
        )
    return tuple(parsed)


def parse_project_records(
    raw_records: Any,
    index: ImplementationIndex,
) -> tuple[ProjectRecord, ...]:
    if not isinstance(raw_records, list):
        raise FoundationError(
            "invalid_implementation_model",
            "Project-model records must be a list.",
        )
    if len(raw_records) > MAX_RECORDS:
        raise FoundationError(
            "invalid_implementation_model",
            "Project-model records exceed the safety limit.",
        )
    node_by_id, edge_by_id = _evidence_maps(index)
    records: list[ProjectRecord] = []
    seen: set[str] = set()
    for position, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            raise FoundationError(
                "invalid_implementation_model",
                f"Project-model record {position} must be an object.",
            )
        record_id = str(raw.get("id", ""))
        if not _RECORD_ID.fullmatch(record_id) or record_id in seen:
            raise FoundationError(
                "invalid_implementation_model",
                "Project-model record IDs must be unique lower-case hyphen identifiers.",
                {"record_id": record_id},
            )
        seen.add(record_id)
        try:
            kind = ProjectRecordKind(str(raw.get("kind", "")))
        except ValueError as exc:
            raise FoundationError(
                "invalid_implementation_model",
                "Project-model record kind must be overview, component, flow, or boundary.",
            ) from exc
        details_raw = raw.get("details", [])
        related_raw = raw.get("related_records", [])
        if not isinstance(details_raw, list) or len(details_raw) > MAX_RECORD_DETAILS:
            raise FoundationError(
                "invalid_implementation_model",
                "Project-model record details must be a bounded list.",
            )
        if not isinstance(related_raw, list):
            raise FoundationError(
                "invalid_implementation_model",
                "Project-model related_records must be a list.",
            )
        records.append(
            ProjectRecord(
                record_id=record_id,
                kind=kind,
                title=_bounded_text(raw.get("title", ""), f"records[{position}].title"),
                summary=_bounded_text(raw.get("summary", ""), f"records[{position}].summary"),
                evidence=_parse_evidence(
                    raw.get("evidence", []),
                    node_by_id,
                    edge_by_id,
                    f"records[{position}].evidence",
                ),
                details=tuple(
                    _bounded_text(item, f"records[{position}].details", allow_empty=False)
                    for item in details_raw
                ),
                related_records=tuple(str(item) for item in related_raw),
            )
        )
    identifiers = {item.record_id for item in records}
    for record in records:
        unknown = set(record.related_records) - identifiers
        if unknown:
            raise FoundationError(
                "invalid_implementation_model",
                "Project-model related_records contain unknown IDs.",
                {"record_id": record.record_id, "unknown": sorted(unknown)},
            )
    if records and not any(item.kind is ProjectRecordKind.OVERVIEW for item in records):
        raise FoundationError(
            "invalid_implementation_model",
            "A non-empty project model requires at least one overview record.",
        )
    return tuple(sorted(records, key=lambda item: (item.kind.value, item.record_id)))


def _evidence_label(
    evidence: EvidenceRef,
    node_by_id: dict[str, Any],
    edge_by_id: dict[str, Any],
) -> str:
    if evidence.kind == "node":
        node = node_by_id[evidence.ref_id]
        location = f"{node.path}:{node.start_line}"
        label = node.qualified_name
    else:
        edge = edge_by_id[evidence.ref_id]
        location = f"{edge.evidence.path}:{edge.evidence.start_line}"
        label = f"{edge.kind} ({edge.confidence.value})"
    claim = f" — {evidence.claim}" if evidence.claim else ""
    return f"`{evidence.kind}:{evidence.ref_id}` — {label} — `{location}`{claim}"


def _record_relative_path(record: ProjectRecord) -> str:
    if record.kind is ProjectRecordKind.OVERVIEW:
        return "overview.md"
    return f"{record.kind.value}s/{record.record_id}.md"


def _render_record(
    record: ProjectRecord,
    node_by_id: dict[str, Any],
    edge_by_id: dict[str, Any],
) -> str:
    lines = [
        "<!-- Generated and managed by VibeSecretary Implementation Lens. -->",
        f"# {record.title}",
        "",
        f"- Record ID: `{record.record_id}`",
        f"- Kind: `{record.kind.value}`",
        "",
        record.summary,
    ]
    if record.details:
        lines.extend(["", "## Structure", ""])
        lines.extend(f"- {item}" for item in record.details)
    lines.extend(["", "## Evidence", ""])
    lines.extend(
        f"- {_evidence_label(item, node_by_id, edge_by_id)}"
        for item in record.evidence
    )
    if record.related_records:
        lines.extend(["", "## Related records", ""])
        lines.extend(f"- `{item}`" for item in record.related_records)
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def update_project_model(
    paths: ProjectPaths,
    policy: ScopePolicy,
    config: ImplementationLensConfig,
    config_digest: str,
    index: ImplementationIndex,
    *,
    raw_records: Any,
    coverage: str,
    covered_paths: Iterable[str],
    diagnostics: Iterable[str],
    expected_model_digest: str,
    confirm_replace_modified: bool,
) -> tuple[ProjectModelManifest, tuple[str, ...]]:
    """Validate and atomically publish a reusable project model."""

    inspection = inspect_project_model(paths, policy, config, config_digest, index)
    current_digest = str(inspection.get("model_digest", ""))
    if current_digest and expected_model_digest != current_digest:
        raise FoundationError(
            "implementation_model_changed",
            "The reusable project model changed after it was inspected.",
            {"expected": expected_model_digest, "current": current_digest},
        )
    conflicts = list(inspection.get("conflict_paths", []))
    if conflicts and not confirm_replace_modified:
        raise FoundationError(
            "implementation_model_conflict",
            "Managed project-model files changed outside Implementation Lens.",
            {"paths": conflicts, "next_step": "Confirm replacement explicitly after reviewing the files."},
        )
    try:
        coverage_value = ModelCoverage(coverage)
    except ValueError as exc:
        raise FoundationError(
            "invalid_implementation_model",
            "Project-model coverage must be 'complete' or 'partial'.",
        ) from exc
    if coverage_value is ModelCoverage.COMPLETE and index.truncated:
        raise FoundationError(
            "invalid_implementation_model_coverage",
            "A truncated index cannot support complete project-model coverage.",
        )
    records = parse_project_records(raw_records, index)
    if not records:
        raise FoundationError(
            "invalid_implementation_model",
            "The reusable project model cannot be empty.",
        )
    all_paths = set(source_file_digests(index))
    if coverage_value is ModelCoverage.COMPLETE:
        covered = tuple(sorted(all_paths))
    else:
        covered_values = {str(item).replace("\\", "/") for item in covered_paths}
        unknown = covered_values - all_paths
        if unknown:
            raise FoundationError(
                "invalid_implementation_model_coverage",
                "covered_paths contains files outside the current implementation index.",
                {"paths": sorted(unknown)},
            )
        covered = tuple(sorted(covered_values))
    clean_diagnostics = tuple(
        dict.fromkeys(
            _bounded_text(item, "diagnostics", allow_empty=False)
            for item in diagnostics
        )
    )
    root = project_model_root(paths, config)
    manifest_path = _manifest_path(paths, config)
    _assert_scope(policy, root)
    _assert_scope(policy, manifest_path)
    node_by_id, edge_by_id = _evidence_maps(index)
    rendered: dict[str, bytes] = {}
    for record in records:
        relative_inside = _record_relative_path(record)
        target = ensure_within_root(root, root / relative_inside)
        _assert_scope(policy, target)
        rendered[_relative(paths, target)] = _render_record(
            record, node_by_id, edge_by_id
        ).encode("utf-8")
    managed_files = {relative: _sha256(raw) for relative, raw in rendered.items()}
    source_hash = source_digest(index)
    model_payload = {
        "source_digest": source_hash,
        "coverage": coverage_value.value,
        "covered_paths": list(covered),
        "diagnostics": list(clean_diagnostics),
        "records": [item.to_dict() for item in records],
    }
    model_hash = _canonical_digest(model_payload)
    manifest = ProjectModelManifest(
        schema_version=PROJECT_MODEL_SCHEMA_VERSION,
        generated_at=_utc_now(),
        analyzer_version=index.analyzer_version,
        config_digest=config_digest,
        scope_digest=policy.digest,
        source_digest=source_hash,
        model_digest=model_hash,
        coverage=coverage_value,
        file_digests=source_file_digests(index),
        covered_paths=covered,
        diagnostics=clean_diagnostics,
        managed_files=managed_files,
        records=records,
    )
    previous, _ = _load_manifest(manifest_path)
    obsolete = (
        set(previous.managed_files) - set(managed_files)
        if previous is not None
        else set()
    )
    written: list[str] = []
    originals: dict[str, bytes | None] = {}
    manifest_relative = _relative(paths, manifest_path)
    try:
        for relative, raw in sorted(rendered.items()):
            target = ensure_within_root(paths.root, paths.root / relative)
            if target.is_file() and _sha256(target.read_bytes()) == _sha256(raw):
                continue
            originals[relative] = target.read_bytes() if target.is_file() else None
            _atomic_write(target, raw)
            written.append(relative)
        for relative in sorted(obsolete):
            target = ensure_within_root(root, paths.root / relative)
            if not target.is_file():
                continue
            originals[relative] = target.read_bytes()
            target.unlink()
            written.append(relative)
        manifest_raw = (
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        originals[manifest_relative] = (
            manifest_path.read_bytes() if manifest_path.is_file() else None
        )
        _atomic_write(manifest_path, manifest_raw)
        written.append(manifest_relative)
    except Exception:
        for relative in reversed(written):
            target = ensure_within_root(paths.root, paths.root / relative)
            original = originals[relative]
            if original is None:
                target.unlink(missing_ok=True)
            else:
                _atomic_write(target, original)
        raise
    return manifest, tuple(written)
