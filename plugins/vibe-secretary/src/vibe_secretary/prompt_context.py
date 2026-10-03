"""Scope-safe context source registry for Prompt Copilot."""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from vibe_secretary.config import ProjectConfig
from vibe_secretary.implementation_service import ImplementationLensService
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.process_service import ProcessHubService
from vibe_secretary.prompt_config import PromptCopilotConfig
from vibe_secretary.prompt_models import (
    ContextSourceResult,
    EvidenceKind,
    PromptEvidence,
    PromptIntent,
)
from vibe_secretary.scope import ScopePolicy

_TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".toml", ".json", ".yaml", ".yml", ".ini", ".cfg",
    ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".sql", ".sh", ".ps1",
}
_SENSITIVE_NAMES = {
    ".env", ".env.local", ".env.production", "credentials", "credentials.json",
    "id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc",
    "secrets.toml", "secrets.yaml", "secrets.yml",
}
_SENSITIVE_DIR_NAMES = {".ssh", ".aws", ".azure", ".gnupg", "secrets", "credentials"}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_ALWAYS_USEFUL = {"agents.md", "readme.md", "pyproject.toml", "requirements.txt", "package.json"}


class ContextSource(Protocol):
    """Stable optional-context capability boundary."""

    name: str

    def collect(
        self,
        *,
        paths: ProjectPaths,
        project_config: ProjectConfig,
        policy: ScopePolicy,
        config: PromptCopilotConfig,
        intent: PromptIntent,
        hook: bool,
    ) -> ContextSourceResult:
        ...


def _is_sensitive(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name in _SENSITIVE_NAMES
        or name in _SENSITIVE_DIR_NAMES
        or path.suffix.casefold() in _SENSITIVE_SUFFIXES
    )


def _safe_text(path: Path, max_bytes: int) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r'''(?imx)(
        (?:
            ["'](?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|passwd)["']\s*:
            |
            \b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|passwd)\b\s*=
        )
        \s*
    )([^\r\n,}#]+)'''
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_PRIVATE_KEY_PATTERN = re.compile(
    r"(?s)-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----"
)


def _redact_sensitive_text(text: str) -> str:
    """Redact common embedded credential forms before returning evidence."""

    redacted = _PRIVATE_KEY_PATTERN.sub("[REDACTED PRIVATE KEY]", text)
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    return _SECRET_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", redacted)

def _excerpt(text: str, terms: tuple[str, ...], limit: int) -> tuple[str, int]:
    folded = text.casefold()
    positions = [folded.find(term) for term in terms if term and folded.find(term) >= 0]
    start = max(0, min(positions) - limit // 4) if positions else 0
    compact = re.sub(r"\s+", " ", _redact_sensitive_text(text[start : start + limit])).strip()
    return compact, len(positions)


class RepositoryContextSource:
    name = "repository"

    def collect(
        self,
        *,
        paths: ProjectPaths,
        project_config: ProjectConfig,
        policy: ScopePolicy,
        config: PromptCopilotConfig,
        intent: PromptIntent,
        hook: bool,
    ) -> ContextSourceResult:
        del project_config
        max_files = min(config.max_scan_files, 120) if hook else config.max_scan_files
        terms = tuple(dict.fromkeys((*intent.keywords, *intent.targets)))
        candidates: list[PromptEvidence] = []
        scanned = 0

        for root, directories, files in os.walk(paths.root):
            root_path = Path(root)
            kept: list[str] = []
            for directory in sorted(directories):
                candidate = root_path / directory
                decision = policy.decide(candidate)
                if decision.allowed and not _is_sensitive(candidate):
                    kept.append(directory)
            directories[:] = kept

            for name in sorted(files):
                if scanned >= max_files:
                    break
                path = root_path / name
                decision = policy.decide(path)
                if not decision.allowed or _is_sensitive(path):
                    continue
                if path.suffix.casefold() not in _TEXT_SUFFIXES and name.casefold() not in _ALWAYS_USEFUL:
                    continue
                scanned += 1
                text = _safe_text(path, config.max_file_bytes)
                if text is None:
                    continue
                relative = decision.relative_path
                folded_path = relative.casefold()
                path_hits = sum(1 for term in terms if term and term in folded_path)
                excerpt, content_hits = _excerpt(text, terms, config.per_source_char_budget)
                useful = name.casefold() in _ALWAYS_USEFUL
                if not path_hits and not content_hits and not useful:
                    continue
                score = path_hits * 10 + min(content_hits, 5) * 3 + (2 if useful else 0)
                reasons: list[str] = []
                if path_hits:
                    reasons.append("path_keyword_match")
                if content_hits:
                    reasons.append("content_keyword_match")
                if useful and not reasons:
                    reasons.append("project_contract")
                candidates.append(
                    PromptEvidence(
                        source_id=f"repo:{relative}",
                        source=self.name,
                        kind=EvidenceKind.REPOSITORY,
                        path=relative,
                        excerpt=excerpt,
                        score=score,
                        reasons=tuple(reasons),
                    )
                )
            if scanned >= max_files:
                break

        candidates.sort(key=lambda item: (-item.score, item.path))
        return ContextSourceResult(self.name, True, tuple(candidates))


class ProcessHubContextSource:
    name = "process_hub"

    def __init__(self, service: ProcessHubService | None = None) -> None:
        self.service = service or ProcessHubService()

    def collect(
        self,
        *,
        paths: ProjectPaths,
        project_config: ProjectConfig,
        policy: ScopePolicy,
        config: PromptCopilotConfig,
        intent: PromptIntent,
        hook: bool,
    ) -> ContextSourceResult:
        del project_config, policy, hook
        status = self.service.status(str(paths.root))
        data = status.get("data") if status.get("ok") else None
        if not isinstance(data, dict) or not data.get("effective_enabled"):
            return ContextSourceResult(self.name, False, degradation="process_hub_unavailable")

        seen: set[str] = set()
        evidence: list[PromptEvidence] = []
        terms = intent.keywords[:6] or ("",)
        for term in terms:
            result = self.service.query(
                text=term,
                limit=min(config.max_sources, 20),
                project_root=str(paths.root),
            )
            if not result.get("ok"):
                return ContextSourceResult(self.name, False, degradation="process_hub_failed")
            result_data = result.get("data", {})
            for summary in result_data.get("results", []):
                document_id = str(summary.get("id", ""))
                if not document_id or document_id in seen:
                    continue
                seen.add(document_id)
                fetched = self.service.get_document(document_id, True, str(paths.root))
                if not fetched.get("ok"):
                    continue
                document = fetched["data"]["document"]
                excerpt = re.sub(
                    r"\s+",
                    " ",
                    _redact_sensitive_text(str(document.get("body", ""))),
                ).strip()
                excerpt = excerpt[: config.per_source_char_budget]
                relative = str(document.get("path", summary.get("path", "")))
                evidence.append(
                    PromptEvidence(
                        source_id=f"process:{document_id}",
                        source=self.name,
                        kind=EvidenceKind.PROCESS_DOCUMENT,
                        path=relative,
                        document_id=document_id,
                        excerpt=excerpt or str(summary.get("title", "")),
                        score=12,
                        reasons=("process_document_match",),
                    )
                )
                if len(evidence) >= config.max_sources:
                    break
            if len(evidence) >= config.max_sources:
                break
        return ContextSourceResult(self.name, True, tuple(evidence))


class ImplementationLensContextSource:
    name = "implementation_lens"

    def __init__(self, service: ImplementationLensService | None = None) -> None:
        self.service = service or ImplementationLensService()

    def collect(
        self,
        *,
        paths: ProjectPaths,
        config: PromptCopilotConfig,
        intent: PromptIntent,
        hook: bool,
        **_: object,
    ) -> ContextSourceResult:
        if hook:
            return ContextSourceResult(
                self.name,
                False,
                degradation="implementation_lens_deferred_in_hook",
            )
        status = self.service.status(str(paths.root))
        data = status.get("data") if status.get("ok") else None
        if not isinstance(data, dict) or not data.get("effective_enabled"):
            return ContextSourceResult(
                self.name,
                False,
                degradation="implementation_lens_unavailable",
            )
        query = " ".join(intent.keywords[:8]) or intent.action
        result = self.service.query(query, "symbol", str(paths.root))
        if not result.get("ok"):
            return ContextSourceResult(
                self.name,
                False,
                degradation="implementation_lens_failed",
            )
        view = result.get("data", {}).get("view", {})
        nodes = view.get("nodes", []) if isinstance(view, dict) else []
        evidence: list[PromptEvidence] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            path = str(node.get("path", ""))
            qualified = str(node.get("qualified_name", ""))
            if not path or not qualified:
                continue
            line = int(node.get("start_line", 0))
            excerpt = f"{qualified} ({node.get('kind', 'symbol')}) at {path}:{line}"
            evidence.append(
                PromptEvidence(
                    source_id=f"implementation:{node.get('id', qualified)}",
                    source=self.name,
                    kind=EvidenceKind.IMPLEMENTATION,
                    path=path,
                    excerpt=excerpt[: config.per_source_char_budget],
                    score=14 if node.get("entrypoint") else 10,
                    reasons=("implementation_symbol_match",),
                )
            )
            if len(evidence) >= config.max_sources:
                break
        return ContextSourceResult(self.name, True, tuple(evidence))


def default_context_sources() -> tuple[ContextSource, ...]:
    return (
        RepositoryContextSource(),
        ProcessHubContextSource(),
        ImplementationLensContextSource(),
    )


def collect_context(
    *,
    paths: ProjectPaths,
    project_config: ProjectConfig,
    policy: ScopePolicy,
    config: PromptCopilotConfig,
    intent: PromptIntent,
    hook: bool,
    sources: tuple[ContextSource, ...] | None = None,
) -> tuple[tuple[ContextSourceResult, ...], tuple[PromptEvidence, ...], dict[str, int | str | bool]]:
    results: list[ContextSourceResult] = []
    for source in sources or default_context_sources():
        try:
            result = source.collect(
                paths=paths,
                project_config=project_config,
                policy=policy,
                config=config,
                intent=intent,
                hook=hook,
            )
        except Exception:
            result = ContextSourceResult(source.name, False, degradation=f"{source.name}_failed")
        results.append(result)

    budget = config.hook_context_char_budget if hook else config.context_char_budget
    ordered = sorted(
        (evidence for result in results for evidence in result.evidence),
        key=lambda item: (-item.score, item.source, item.path),
    )
    selected: list[PromptEvidence] = []
    used = 0
    for evidence in ordered:
        if len(selected) >= config.max_sources or used >= budget:
            break
        remaining = budget - used
        excerpt = evidence.excerpt[:remaining]
        if not excerpt:
            continue
        selected.append(replace(evidence, excerpt=excerpt))
        used += len(excerpt)

    return (
        tuple(results),
        tuple(selected),
        {
            "character_budget": budget,
            "characters_used": used,
            "source_limit": config.max_sources,
            "sources_selected": len(selected),
            "approximate_tokens": (used + 3) // 4,
            "token_estimate_is_approximate": True,
        },
    )
