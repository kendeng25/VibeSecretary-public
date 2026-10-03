"""Domain models for deterministic implementation analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Granularity(StrEnum):
    """Supported implementation-map detail levels."""

    MODULE = "module"
    SYMBOL = "symbol"
    DETAIL = "detail"


class Confidence(StrEnum):
    """Evidence confidence for one static relationship."""

    CERTAIN = "certain"
    HEURISTIC = "heuristic"
    INFERRED = "inferred"


@dataclass(frozen=True, slots=True)
class CodeEvidence:
    """Source location supporting a node or edge."""

    path: str
    start_line: int
    end_line: int
    method: str
    excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "method": self.method,
            "excerpt": self.excerpt,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CodeEvidence":
        return cls(
            path=str(raw["path"]),
            start_line=int(raw["start_line"]),
            end_line=int(raw["end_line"]),
            method=str(raw["method"]),
            excerpt=str(raw.get("excerpt", "")),
        )


@dataclass(frozen=True, slots=True)
class CodeNode:
    """One stable code entity in an implementation graph."""

    node_id: str
    kind: str
    language: str
    label: str
    qualified_name: str
    path: str
    start_line: int
    end_line: int
    module: str
    parent_id: str = ""
    decorators: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    entrypoint: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "kind": self.kind,
            "language": self.language,
            "label": self.label,
            "qualified_name": self.qualified_name,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "module": self.module,
            "parent_id": self.parent_id,
            "decorators": list(self.decorators),
            "keywords": list(self.keywords),
            "entrypoint": self.entrypoint,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CodeNode":
        return cls(
            node_id=str(raw["id"]),
            kind=str(raw["kind"]),
            language=str(raw["language"]),
            label=str(raw["label"]),
            qualified_name=str(raw["qualified_name"]),
            path=str(raw["path"]),
            start_line=int(raw["start_line"]),
            end_line=int(raw["end_line"]),
            module=str(raw["module"]),
            parent_id=str(raw.get("parent_id", "")),
            decorators=tuple(str(item) for item in raw.get("decorators", [])),
            keywords=tuple(str(item) for item in raw.get("keywords", [])),
            entrypoint=bool(raw.get("entrypoint", False)),
        )


@dataclass(frozen=True, slots=True)
class CodeReference:
    """An unresolved per-file relationship used to rebuild cross-file edges."""

    source_id: str
    kind: str
    expression: str
    evidence: CodeEvidence
    detail: str = ""
    confidence: Confidence = Confidence.CERTAIN

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "expression": self.expression,
            "evidence": self.evidence.to_dict(),
            "detail": self.detail,
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CodeReference":
        return cls(
            source_id=str(raw["source_id"]),
            kind=str(raw["kind"]),
            expression=str(raw["expression"]),
            evidence=CodeEvidence.from_dict(raw["evidence"]),
            detail=str(raw.get("detail", "")),
            confidence=Confidence(str(raw.get("confidence", Confidence.CERTAIN.value))),
        )


@dataclass(frozen=True, slots=True)
class CodeEdge:
    """One directed implementation relationship."""

    edge_id: str
    source_id: str
    target_id: str
    kind: str
    confidence: Confidence
    evidence: CodeEvidence
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.edge_id,
            "source": self.source_id,
            "target": self.target_id,
            "kind": self.kind,
            "confidence": self.confidence.value,
            "evidence": self.evidence.to_dict(),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AnalysisDiagnostic:
    """Non-fatal analysis limitation or parse issue."""

    code: str
    message: str
    path: str = ""
    line: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "line": self.line,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AnalysisDiagnostic":
        return cls(
            code=str(raw["code"]),
            message=str(raw["message"]),
            path=str(raw.get("path", "")),
            line=int(raw.get("line", 0)),
        )


@dataclass(frozen=True, slots=True)
class FileAnalysis:
    """Cacheable analysis result for one Python file."""

    path: str
    digest: str
    module: str
    nodes: tuple[CodeNode, ...] = ()
    references: tuple[CodeReference, ...] = ()
    diagnostics: tuple[AnalysisDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "digest": self.digest,
            "module": self.module,
            "nodes": [item.to_dict() for item in self.nodes],
            "references": [item.to_dict() for item in self.references],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FileAnalysis":
        return cls(
            path=str(raw["path"]),
            digest=str(raw["digest"]),
            module=str(raw["module"]),
            nodes=tuple(CodeNode.from_dict(item) for item in raw.get("nodes", [])),
            references=tuple(
                CodeReference.from_dict(item) for item in raw.get("references", [])
            ),
            diagnostics=tuple(
                AnalysisDiagnostic.from_dict(item) for item in raw.get("diagnostics", [])
            ),
        )


@dataclass(frozen=True, slots=True)
class ImplementationIndex:
    """Rebuildable repository analysis state."""

    schema_version: int
    analyzer_version: str
    generated_at: str
    config_digest: str
    files: tuple[FileAnalysis, ...]
    nodes: tuple[CodeNode, ...]
    edges: tuple[CodeEdge, ...]
    diagnostics: tuple[AnalysisDiagnostic, ...] = ()
    scanned_files: int = 0
    reused_files: int = 0
    changed_files: int = 0
    deleted_files: int = 0
    truncated: bool = False

    def to_dict(self, *, include_cache: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "analyzer_version": self.analyzer_version,
            "generated_at": self.generated_at,
            "config_digest": self.config_digest,
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "stats": {
                "scanned_files": self.scanned_files,
                "reused_files": self.reused_files,
                "changed_files": self.changed_files,
                "deleted_files": self.deleted_files,
                "nodes": len(self.nodes),
                "edges": len(self.edges),
                "truncated": self.truncated,
            },
        }
        if include_cache:
            payload["files"] = [item.to_dict() for item in self.files]
        return payload


@dataclass(frozen=True, slots=True)
class ImplementationView:
    """A bounded subgraph selected for one user question."""

    query: str
    granularity: Granularity
    nodes: tuple[CodeNode, ...]
    edges: tuple[CodeEdge, ...]
    seed_ids: tuple[str, ...]
    diagnostics: tuple[AnalysisDiagnostic, ...] = ()
    limitations: tuple[str, ...] = ()
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "granularity": self.granularity.value,
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "seed_ids": list(self.seed_ids),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "limitations": list(self.limitations),
            "truncated": self.truncated,
            "stats": {"nodes": len(self.nodes), "edges": len(self.edges)},
        }


class StoryBasis(StrEnum):
    """Whether one presentation claim is direct evidence or sourced interpretation."""

    FACT = "fact"
    INTERPRETATION = "interpretation"


class ProjectRecordKind(StrEnum):
    """Stable categories in the reusable project model."""

    OVERVIEW = "overview"
    COMPONENT = "component"
    FLOW = "flow"
    BOUNDARY = "boundary"


class ModelCoverage(StrEnum):
    """Declared semantic coverage of the reusable project model."""

    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """A claim-level reference to one indexed node or edge."""

    kind: str
    ref_id: str
    claim: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref_id": self.ref_id, "claim": self.claim}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvidenceRef":
        return cls(kind=str(raw["kind"]), ref_id=str(raw["ref_id"]), claim=str(raw.get("claim", "")))


@dataclass(frozen=True, slots=True)
class ConceptStage:
    """One minimum-sufficient semantic stage in a query-specific story."""

    stage_id: str
    title: str
    summary: str
    role: str
    basis: StoryBasis
    evidence: tuple[EvidenceRef, ...]
    details: tuple[str, ...] = ()
    lane: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.stage_id,
            "title": self.title,
            "summary": self.summary,
            "role": self.role,
            "basis": self.basis.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "details": list(self.details),
            "lane": self.lane,
        }


@dataclass(frozen=True, slots=True)
class StoryTransition:
    """One sourced relationship between semantic stages."""

    source_id: str
    target_id: str
    kind: str
    label: str
    basis: StoryBasis
    evidence: tuple[EvidenceRef, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "kind": self.kind,
            "label": self.label,
            "basis": self.basis.value,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class ImplementationStory:
    """A validated, query-specific semantic presentation over indexed evidence."""

    query: str
    granularity: Granularity
    title: str
    stages: tuple[ConceptStage, ...]
    transitions: tuple[StoryTransition, ...]
    omitted_summary: str = ""
    limitations: tuple[str, ...] = ()
    fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "granularity": self.granularity.value,
            "title": self.title,
            "stages": [item.to_dict() for item in self.stages],
            "transitions": [item.to_dict() for item in self.transitions],
            "omitted_summary": self.omitted_summary,
            "limitations": list(self.limitations),
            "fallback": self.fallback,
            "stats": {"stages": len(self.stages), "transitions": len(self.transitions)},
        }


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    """One reusable, granularity-independent project-model record."""

    record_id: str
    kind: ProjectRecordKind
    title: str
    summary: str
    evidence: tuple[EvidenceRef, ...]
    details: tuple[str, ...] = ()
    related_records: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.record_id,
            "kind": self.kind.value,
            "title": self.title,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "details": list(self.details),
            "related_records": list(self.related_records),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProjectRecord":
        return cls(
            record_id=str(raw["id"]),
            kind=ProjectRecordKind(str(raw["kind"])),
            title=str(raw["title"]),
            summary=str(raw["summary"]),
            evidence=tuple(EvidenceRef.from_dict(item) for item in raw.get("evidence", [])),
            details=tuple(str(item) for item in raw.get("details", [])),
            related_records=tuple(str(item) for item in raw.get("related_records", [])),
        )


@dataclass(frozen=True, slots=True)
class ProjectModelManifest:
    """Authoritative metadata and records for one reusable project model."""

    schema_version: int
    generated_at: str
    analyzer_version: str
    config_digest: str
    scope_digest: str
    source_digest: str
    model_digest: str
    coverage: ModelCoverage
    file_digests: dict[str, str]
    covered_paths: tuple[str, ...]
    diagnostics: tuple[str, ...]
    managed_files: dict[str, str]
    records: tuple[ProjectRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "analyzer_version": self.analyzer_version,
            "config_digest": self.config_digest,
            "scope_digest": self.scope_digest,
            "source_digest": self.source_digest,
            "model_digest": self.model_digest,
            "coverage": self.coverage.value,
            "file_digests": dict(sorted(self.file_digests.items())),
            "covered_paths": list(self.covered_paths),
            "diagnostics": list(self.diagnostics),
            "managed_files": dict(sorted(self.managed_files.items())),
            "records": [item.to_dict() for item in self.records],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProjectModelManifest":
        return cls(
            schema_version=int(raw["schema_version"]),
            generated_at=str(raw["generated_at"]),
            analyzer_version=str(raw["analyzer_version"]),
            config_digest=str(raw["config_digest"]),
            scope_digest=str(raw["scope_digest"]),
            source_digest=str(raw["source_digest"]),
            model_digest=str(raw["model_digest"]),
            coverage=ModelCoverage(str(raw["coverage"])),
            file_digests={str(key): str(value) for key, value in raw.get("file_digests", {}).items()},
            covered_paths=tuple(str(item) for item in raw.get("covered_paths", [])),
            diagnostics=tuple(str(item) for item in raw.get("diagnostics", [])),
            managed_files={str(key): str(value) for key, value in raw.get("managed_files", {}).items()},
            records=tuple(ProjectRecord.from_dict(item) for item in raw.get("records", [])),
        )

@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    """Content baseline for a bounded read-only inspection."""

    files: dict[str, str] = field(default_factory=dict)
    complete: bool = True
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadOnlyCheck:
    """Auditable result for source mutation detection."""

    status: str
    method: str
    files_checked: int
    allowed_writes: tuple[str, ...]
    unexpected_changes: tuple[str, ...] = ()
    boundaries: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method": self.method,
            "files_checked": self.files_checked,
            "allowed_writes": list(self.allowed_writes),
            "unexpected_changes": list(self.unexpected_changes),
            "boundaries": list(self.boundaries),
        }
