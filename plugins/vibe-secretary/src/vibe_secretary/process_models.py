"""Data models shared by Process Hub scanning, indexing, and tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ProcessIssue:
    """One deterministic configuration or document consistency issue."""

    code: str
    message: str
    path: str = ""
    document_id: str = ""
    severity: str = "error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "document_id": self.document_id,
            "severity": self.severity,
            "details": self.details,
        }


@dataclass(slots=True)
class ProcessDocument:
    """One scanned Markdown document and its normalized metadata."""

    path: Path
    relative_path: str
    collection_id: str
    managed: bool
    metadata: dict[str, Any] | None
    body: str
    issues: list[ProcessIssue] = field(default_factory=list)

    @property
    def document_id(self) -> str:
        if not self.metadata:
            return ""
        value = self.metadata.get("id")
        return value if isinstance(value, str) else ""

    def summary(self) -> dict[str, Any]:
        metadata = self.metadata or {}
        return {
            "id": self.document_id,
            "collection": self.collection_id,
            "type": metadata.get("type", ""),
            "title": metadata.get("title", self.path.stem),
            "status": metadata.get("status", ""),
            "stage": metadata.get("stage", ""),
            "task": metadata.get("task", ""),
            "tags": metadata.get("tags", []),
            "relates_to": metadata.get("relates_to", []),
            "created_at": metadata.get("created_at", ""),
            "updated_at": metadata.get("updated_at", ""),
            "path": self.relative_path,
            "managed": self.managed,
            "issue_codes": [issue.code for issue in self.issues],
        }


@dataclass(slots=True)
class ProcessScan:
    """Complete deterministic scan result for one consumer project."""

    documents: list[ProcessDocument]
    issues: list[ProcessIssue]

    def to_dict(self) -> dict[str, Any]:
        managed = sum(document.managed for document in self.documents)
        return {
            "document_count": len(self.documents),
            "managed_count": managed,
            "unmanaged_count": len(self.documents) - managed,
            "issue_count": len(self.issues),
            "documents": [document.summary() for document in self.documents],
            "issues": [issue.to_dict() for issue in self.issues],
        }
