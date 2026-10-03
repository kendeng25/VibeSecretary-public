"""Stable domain models for deterministic Prompt Copilot preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PromptMode(StrEnum):
    """Supported Prompt Copilot interaction modes."""

    QUICK = "quick"
    REVIEW = "review"
    STRICT = "strict"


class EvidenceKind(StrEnum):
    """Kinds of source evidence exposed to the Codex host."""

    REPOSITORY = "repository"
    PROCESS_DOCUMENT = "process_document"
    IMPLEMENTATION = "implementation"


@dataclass(frozen=True, slots=True)
class PromptEvidence:
    source_id: str
    source: str
    kind: EvidenceKind
    path: str
    excerpt: str
    score: int
    reasons: tuple[str, ...]
    document_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source": self.source,
            "kind": self.kind.value,
            "path": self.path,
            "document_id": self.document_id,
            "excerpt": self.excerpt,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class PromptFinding:
    code: str
    message: str
    severity: str
    blocking: bool = False
    source_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "blocking": self.blocking,
            "source_ids": list(self.source_ids),
        }


@dataclass(frozen=True, slots=True)
class PromptQuestion:
    question_id: str
    text: str
    required: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "required": self.required,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PromptIntent:
    action: str
    targets: tuple[str, ...]
    keywords: tuple[str, ...]
    risk_flags: tuple[str, ...]
    development_request: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "targets": list(self.targets),
            "keywords": list(self.keywords),
            "risk_flags": list(self.risk_flags),
            "development_request": self.development_request,
        }


@dataclass(frozen=True, slots=True)
class ContextSourceResult:
    source: str
    available: bool
    evidence: tuple[PromptEvidence, ...] = ()
    degradation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "available": self.available,
            "evidence_count": len(self.evidence),
            "degradation": self.degradation,
        }


@dataclass(frozen=True, slots=True)
class PromptContextPackage:
    original_prompt: str
    mode: PromptMode
    intent: PromptIntent
    evidence: tuple[PromptEvidence, ...]
    gaps: tuple[PromptFinding, ...]
    conflicts: tuple[PromptFinding, ...]
    questions: tuple[PromptQuestion, ...]
    acceptance_suggestions: tuple[str, ...]
    verification_suggestions: tuple[str, ...]
    source_results: tuple[ContextSourceResult, ...]
    budget: dict[str, int | str | bool]
    host_instructions: str

    @property
    def blocking_questions(self) -> tuple[PromptQuestion, ...]:
        return tuple(item for item in self.questions if item.required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_prompt": self.original_prompt,
            "mode": self.mode.value,
            "intent": self.intent.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "gaps": [item.to_dict() for item in self.gaps],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "questions": [item.to_dict() for item in self.questions],
            "acceptance_suggestions": list(self.acceptance_suggestions),
            "verification_suggestions": list(self.verification_suggestions),
            "sources": [item.to_dict() for item in self.source_results],
            "degradations": [
                {"source": item.source, "code": item.degradation}
                for item in self.source_results
                if item.degradation
            ],
            "budget": self.budget,
            "host_instructions": self.host_instructions,
        }
