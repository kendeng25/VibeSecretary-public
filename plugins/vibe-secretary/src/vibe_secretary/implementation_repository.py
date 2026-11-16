"""Repository scanning, incremental indexing, querying, and read-only baselines."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import tomllib
from collections import defaultdict, deque
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from vibe_secretary.errors import FoundationError
from vibe_secretary.implementation_config import ImplementationLensConfig
from vibe_secretary.implementation_models import (
    AnalysisDiagnostic,
    CodeEdge,
    CodeEvidence,
    CodeNode,
    CodeReference,
    Confidence,
    FileAnalysis,
    Granularity,
    ImplementationIndex,
    ImplementationView,
    ProjectSnapshot,
    ReadOnlyCheck,
)
from vibe_secretary.implementation_python import (
    ANALYZER_VERSION,
    PYTHON_LANGUAGE_ADAPTER,
    external_node_id,
    mark_entrypoint,
)
from vibe_secretary.paths import ProjectPaths, ensure_within_root
from vibe_secretary.scope import ScopePolicy

INDEX_SCHEMA_VERSION = 1
_QUERY_TERMS = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*|[\u4e00-\u9fff]{2,}")
_INCOMING_MARKERS = ("caller", "called by", "impact", "who calls", "谁调用", "影响", "上游")
_ENTRY_MARKERS = ("entry", "start", "route", "入口", "进入", "起点")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _edge_id(kind: str, source: str, target: str, evidence: CodeEvidence) -> str:
    raw = f"{kind}\0{source}\0{target}\0{evidence.path}\0{evidence.start_line}"
    return "edge:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _external_node(expression: str, evidence: CodeEvidence) -> CodeNode:
    label = expression or "external"
    return CodeNode(
        node_id=external_node_id(label),
        kind="external",
        language="external",
        label=label,
        qualified_name=label,
        path=evidence.path,
        start_line=evidence.start_line,
        end_line=evidence.end_line,
        module="external",
        keywords=tuple(part for part in re.split(r"[^A-Za-z0-9_]+", label) if part),
    )


def _load_cached_index(path: Path, config_digest: str) -> tuple[FileAnalysis, ...]:
    if not path.is_file() or path.stat().st_size > 100 * 1024 * 1024:
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if (
            raw.get("schema_version") != INDEX_SCHEMA_VERSION
            or raw.get("analyzer_version") != ANALYZER_VERSION
            or raw.get("config_digest") != config_digest
        ):
            return ()
        return tuple(FileAnalysis.from_dict(item) for item in raw.get("files", []))
    except (OSError, ValueError, TypeError, KeyError):
        return ()


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    ensure_within_root(path.parents[1] if path.parent.name == ".vibesecretary" else path.parent, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix="implementation-index-", suffix=".json.tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _scan_python_sources(
    paths: ProjectPaths,
    policy: ScopePolicy,
    config: ImplementationLensConfig,
) -> tuple[list[tuple[Path, str, bytes]], list[AnalysisDiagnostic], bool]:
    sources: list[tuple[Path, str, bytes]] = []
    diagnostics: list[AnalysisDiagnostic] = []
    truncated = False
    for candidate in sorted(paths.root.rglob("*.py"), key=lambda item: item.as_posix().casefold()):
        if not candidate.is_file():
            continue
        decision = policy.decide(candidate)
        if not decision.allowed:
            continue
        if len(sources) >= config.max_files:
            truncated = True
            diagnostics.append(
                AnalysisDiagnostic(
                    "source_file_limit",
                    "Python source scan stopped at the configured max_files limit.",
                )
            )
            break
        try:
            if candidate.stat().st_size > config.max_file_bytes:
                diagnostics.append(
                    AnalysisDiagnostic(
                        "source_file_too_large",
                        "Python source exceeds the configured max_file_bytes limit.",
                        decision.relative_path,
                    )
                )
                continue
            sources.append((candidate, decision.relative_path, candidate.read_bytes()))
        except OSError:
            diagnostics.append(
                AnalysisDiagnostic(
                    "source_file_unreadable",
                    "Python source could not be read during static analysis.",
                    decision.relative_path,
                )
            )
    return sources, diagnostics, truncated


def _script_targets(paths: ProjectPaths, policy: ScopePolicy) -> tuple[set[str], list[AnalysisDiagnostic]]:
    target = paths.root / "pyproject.toml"
    decision = policy.decide(target)
    if not target.is_file() or not decision.allowed:
        return set(), []
    try:
        with target.open("rb") as stream:
            raw = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError):
        return set(), [
            AnalysisDiagnostic(
                "pyproject_unreadable", "pyproject.toml could not be parsed for script entrypoints.",
                "pyproject.toml",
            )
        ]
    scripts = raw.get("project", {}).get("scripts", {})
    if not isinstance(scripts, dict):
        return set(), []
    values = {
        str(value).split("[", 1)[0].strip()
        for value in scripts.values()
        if isinstance(value, str) and ":" in value
    }
    return values, []


def _module_aliases(nodes: Iterable[CodeNode]) -> dict[str, CodeNode]:
    aliases: dict[str, CodeNode] = {}
    for node in nodes:
        if node.kind != "module":
            continue
        aliases[node.module] = node
        path_module = node.path.removesuffix(".py").replace("/", ".")
        if path_module.endswith(".__init__"):
            path_module = path_module[: -len(".__init__")]
        aliases.setdefault(path_module, node)
    return aliases


def _resolve_graph(
    analyses: tuple[FileAnalysis, ...],
    script_targets: set[str],
) -> tuple[tuple[FileAnalysis, ...], tuple[CodeNode, ...], tuple[CodeEdge, ...]]:
    all_nodes = [node for analysis in analyses for node in analysis.nodes]
    by_id = {node.node_id: node for node in all_nodes}
    by_qualified: dict[str, list[CodeNode]] = defaultdict(list)
    by_label: dict[str, list[CodeNode]] = defaultdict(list)
    for node in all_nodes:
        by_qualified[node.qualified_name].append(node)
        by_label[node.label].append(node)
    module_aliases = _module_aliases(all_nodes)

    entry_ids: set[str] = set()
    for target in script_targets:
        module_name, symbol_name = target.split(":", 1)
        qualified = f"{module_name}.{symbol_name}"
        for node in by_qualified.get(qualified, []):
            entry_ids.add(node.node_id)
    if entry_ids:
        analyses = tuple(
            replace(
                analysis,
                nodes=tuple(
                    mark_entrypoint(node) if node.node_id in entry_ids else node
                    for node in analysis.nodes
                ),
            )
            for analysis in analyses
        )
        all_nodes = [node for analysis in analyses for node in analysis.nodes]
        by_id = {node.node_id: node for node in all_nodes}
        by_qualified = defaultdict(list)
        by_label = defaultdict(list)
        for node in all_nodes:
            by_qualified[node.qualified_name].append(node)
            by_label[node.label].append(node)

    aliases_by_path: dict[str, dict[str, str]] = defaultdict(dict)
    for analysis in analyses:
        for reference in analysis.references:
            if reference.kind == "imports" and "=" in reference.detail:
                local, target = reference.detail.split("=", 1)
                aliases_by_path[analysis.path][local] = target

    external_nodes: dict[str, CodeNode] = {}
    edges: dict[str, CodeEdge] = {}

    def target_for_import(expression: str) -> CodeNode | None:
        if expression in module_aliases:
            return module_aliases[expression]
        exact = by_qualified.get(expression, [])
        if len(exact) == 1:
            return exact[0]
        parts = expression.split(".")
        for stop in range(len(parts) - 1, 0, -1):
            module = ".".join(parts[:stop])
            if module in module_aliases:
                return module_aliases[module]
        return None

    def target_for_call(reference: CodeReference, source: CodeNode) -> tuple[CodeNode | None, Confidence]:
        expression = reference.expression
        candidates: list[CodeNode] = []
        constructed_method = re.fullmatch(
            r"(?P<class>[A-Za-z_][A-Za-z0-9_]*)\(.*\)\.(?P<method>[A-Za-z_][A-Za-z0-9_]*)",
            expression,
        )
        if constructed_method:
            class_name = constructed_method.group("class")
            method_name = constructed_method.group("method")
            classes = [
                item for item in by_label.get(class_name, []) if item.kind == "class"
            ]
            if len(classes) == 1:
                candidates = by_qualified.get(
                    f"{classes[0].qualified_name}.{method_name}", []
                )
        elif expression.startswith("self."):
            method = expression.split(".", 1)[1]
            parent = by_id.get(source.parent_id)
            if parent and parent.kind == "class":
                candidates = by_qualified.get(f"{parent.qualified_name}.{method}", [])
        elif "." not in expression:
            if source.kind == "method":
                parent = by_id.get(source.parent_id)
                if parent:
                    candidates = by_qualified.get(f"{parent.qualified_name}.{expression}", [])
            if not candidates:
                candidates = by_qualified.get(f"{source.module}.{expression}", [])
            if not candidates:
                candidates = by_label.get(expression, [])
        else:
            first, rest = expression.split(".", 1)
            imported = aliases_by_path[source.path].get(first)
            qualified = f"{imported}.{rest}" if imported else expression
            candidates = by_qualified.get(qualified, [])
            if not candidates and imported:
                candidates = by_qualified.get(imported, [])
        unique = {item.node_id: item for item in candidates}
        if len(unique) == 1:
            confidence = (
                Confidence.CERTAIN
                if expression.startswith("self.") or expression in by_label
                else Confidence.HEURISTIC
            )
            return next(iter(unique.values())), confidence
        return None, Confidence.HEURISTIC

    for analysis in analyses:
        for reference in analysis.references:
            source = by_id.get(reference.source_id)
            target: CodeNode | None = None
            confidence = reference.confidence
            if reference.kind in {"contains", "registers"}:
                target = by_id.get(reference.expression)
                if reference.kind == "registers":
                    source = external_nodes.setdefault(
                        reference.source_id,
                        _external_node(reference.detail or reference.source_id, reference.evidence),
                    )
            elif source and reference.kind == "imports":
                target = target_for_import(reference.expression)
                if target is None:
                    target = external_nodes.setdefault(
                        external_node_id(reference.expression),
                        _external_node(reference.expression, reference.evidence),
                    )
            elif source and reference.kind in {"calls", "reads", "writes"}:
                target, confidence = target_for_call(reference, source)
                if target is None:
                    first = reference.expression.split(".", 1)[0]
                    imported = aliases_by_path[source.path].get(first)
                    if imported:
                        external_expression = (
                            f"{imported}.{reference.expression.split('.', 1)[1]}"
                            if "." in reference.expression
                            else imported
                        )
                        target = external_nodes.setdefault(
                            external_node_id(external_expression),
                            _external_node(external_expression, reference.evidence),
                        )
            if source is None or target is None or source.node_id == target.node_id:
                continue
            identifier = _edge_id(
                reference.kind, source.node_id, target.node_id, reference.evidence
            )
            edges.setdefault(
                identifier,
                CodeEdge(
                    edge_id=identifier,
                    source_id=source.node_id,
                    target_id=target.node_id,
                    kind=reference.kind,
                    confidence=confidence,
                    evidence=reference.evidence,
                    detail=reference.detail or reference.expression,
                ),
            )

    nodes = tuple(sorted((*all_nodes, *external_nodes.values()), key=lambda item: item.node_id))
    return analyses, nodes, tuple(sorted(edges.values(), key=lambda item: item.edge_id))


def build_implementation_index(
    paths: ProjectPaths,
    policy: ScopePolicy,
    config: ImplementationLensConfig,
    config_digest: str,
    *,
    persist: bool,
) -> ImplementationIndex:
    """Build or incrementally refresh one repository index."""

    index_path = ensure_within_root(paths.root, paths.root / config.index_json)
    if persist and not policy.decide(index_path).allowed:
        raise FoundationError(
            "implementation_index_outside_scope",
            "The configured Implementation Lens index is excluded by project scope.",
        )
    cached = {
        item.path: item for item in _load_cached_index(index_path, config_digest)
    }
    sources, diagnostics, truncated = _scan_python_sources(paths, policy, config)
    analyses: list[FileAnalysis] = []
    reused = 0
    changed = 0
    current_paths: set[str] = set()
    for candidate, relative, raw in sources:
        current_paths.add(relative)
        digest = hashlib.sha256(raw).hexdigest()
        previous = cached.get(relative)
        if previous is not None and previous.digest == digest:
            analyses.append(previous)
            reused += 1
        else:
            analyses.append(PYTHON_LANGUAGE_ADAPTER.analyze(candidate, relative, raw))
            changed += 1
    deleted = len(set(cached) - current_paths)
    script_targets, script_diagnostics = _script_targets(paths, policy)
    diagnostics.extend(script_diagnostics)
    resolved_analyses, nodes, edges = _resolve_graph(tuple(analyses), script_targets)
    all_diagnostics = tuple(
        (*diagnostics, *(item for analysis in resolved_analyses for item in analysis.diagnostics))
    )
    index = ImplementationIndex(
        schema_version=INDEX_SCHEMA_VERSION,
        analyzer_version=ANALYZER_VERSION,
        generated_at=_utc_now(),
        config_digest=config_digest,
        files=resolved_analyses,
        nodes=nodes,
        edges=edges,
        diagnostics=all_diagnostics,
        scanned_files=len(sources),
        reused_files=reused,
        changed_files=changed,
        deleted_files=deleted,
        truncated=truncated,
    )
    if persist:
        _atomic_write_json(index_path, index.to_dict(include_cache=True))
    return index


def _query_terms(query: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.casefold() for item in _QUERY_TERMS.findall(query)))


def _node_score(node: CodeNode, terms: tuple[str, ...], query: str) -> int:
    haystack = " ".join(
        (
            node.label,
            node.qualified_name,
            node.path,
            node.module,
            *node.decorators,
            *node.keywords,
        )
    ).casefold()
    score = sum(4 if term == node.label.casefold() else 1 for term in terms if term in haystack)
    folded = query.casefold()
    if node.entrypoint and any(marker in folded for marker in _ENTRY_MARKERS):
        score += 8
    if node.kind == "external" and score:
        score -= 1
    return score


def select_implementation_view(
    index: ImplementationIndex,
    query: str,
    granularity: Granularity,
    config: ImplementationLensConfig,
) -> ImplementationView:
    """Select a bounded directed subgraph for one natural-language query."""

    if not isinstance(query, str) or not query.strip():
        raise FoundationError("implementation_query_empty", "Implementation query cannot be empty.")
    terms = _query_terms(query)
    scored = sorted(
        ((score, node) for node in index.nodes if (score := _node_score(node, terms, query)) > 0),
        key=lambda item: (-item[0], not item[1].entrypoint, item[1].node_id),
    )
    if scored:
        seeds = [item[1] for item in scored[: min(8, config.max_nodes)]]
    else:
        seeds = [node for node in index.nodes if node.entrypoint][:8]
        if not seeds:
            seeds = [node for node in index.nodes if node.kind == "module"][:8]

    node_by_id = {node.node_id: node for node in index.nodes}
    outgoing: dict[str, list[CodeEdge]] = defaultdict(list)
    incoming: dict[str, list[CodeEdge]] = defaultdict(list)
    for edge in index.edges:
        outgoing[edge.source_id].append(edge)
        incoming[edge.target_id].append(edge)

    if granularity is Granularity.MODULE:
        module_seed_ids = {
            next(
                (
                    candidate.node_id
                    for candidate in index.nodes
                    if candidate.kind == "module" and candidate.module == seed.module
                ),
                seed.node_id,
            )
            for seed in seeds
        }
        allowed_kinds = {"module", "external"}
        selected_ids = set(module_seed_ids)
        for edge in index.edges:
            source = node_by_id.get(edge.source_id)
            target = node_by_id.get(edge.target_id)
            if (
                edge.kind == "imports"
                and source is not None
                and target is not None
                and source.kind in allowed_kinds
                and target.kind in allowed_kinds
                and (source.node_id in selected_ids or target.node_id in selected_ids)
            ):
                selected_ids.update((source.node_id, target.node_id))
        selected_edges = [
            edge
            for edge in index.edges
            if edge.kind == "imports"
            and edge.source_id in selected_ids
            and edge.target_id in selected_ids
        ]
    else:
        depth = 2 if granularity is Granularity.SYMBOL else 4
        prefer_incoming = any(marker in query.casefold() for marker in _INCOMING_MARKERS)
        selected_ids = {seed.node_id for seed in seeds}
        queue = deque((seed.node_id, 0) for seed in seeds)
        while queue and len(selected_ids) < config.max_nodes:
            current, level = queue.popleft()
            if level >= depth:
                continue
            candidates = (
                (*incoming[current], *outgoing[current])
                if prefer_incoming
                else (*outgoing[current], *incoming[current])
            )
            for edge in candidates:
                other = edge.source_id if edge.target_id == current else edge.target_id
                if other not in selected_ids:
                    selected_ids.add(other)
                    queue.append((other, level + 1))
                    if len(selected_ids) >= config.max_nodes:
                        break
        selected_edges = [
            edge
            for edge in index.edges
            if edge.source_id in selected_ids and edge.target_id in selected_ids
        ]

    selected_nodes = [node_by_id[item] for item in selected_ids if item in node_by_id]
    selected_nodes.sort(key=lambda item: (not item.entrypoint, item.kind, item.path, item.start_line))
    selected_edges.sort(key=lambda item: (item.kind, item.source_id, item.target_id))
    truncated = len(selected_nodes) > config.max_nodes or len(selected_edges) > config.max_edges
    selected_nodes = selected_nodes[: config.max_nodes]
    retained = {node.node_id for node in selected_nodes}
    selected_edges = [
        edge
        for edge in selected_edges
        if edge.source_id in retained and edge.target_id in retained
    ][: config.max_edges]
    limitations = [
        "Python static analysis cannot prove dynamic dispatch, reflection, monkey-patching, or runtime framework wiring.",
        "Call relationships are complete only for the syntactic and import patterns recognized by the analyzer.",
    ]
    diagnostics = list(index.diagnostics)
    if not scored:
        diagnostics.append(
            AnalysisDiagnostic(
                "query_no_direct_match",
                "No code identifier directly matched the query; the view starts from detected entrypoints or modules.",
            )
        )
    if truncated or index.truncated:
        limitations.append("The configured node, edge, or source-file budget truncated this view.")
    return ImplementationView(
        query=query.strip(),
        granularity=granularity,
        nodes=tuple(selected_nodes),
        edges=tuple(selected_edges),
        seed_ids=tuple(seed.node_id for seed in seeds),
        diagnostics=tuple(diagnostics),
        limitations=tuple(limitations),
        truncated=truncated or index.truncated,
    )


def snapshot_project(
    paths: ProjectPaths,
    policy: ScopePolicy,
    config: ImplementationLensConfig,
) -> ProjectSnapshot:
    """Hash current in-scope project files excluding declared Lens outputs and index."""

    output_prefix = config.output_path.rstrip("/") + "/"
    excluded = {config.index_json}
    files: dict[str, str] = {}
    issues: list[str] = []
    complete = True
    for candidate in sorted(paths.root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not candidate.is_file():
            continue
        decision = policy.decide(candidate)
        if not decision.allowed:
            continue
        relative = decision.relative_path
        if relative in excluded or relative == config.output_path or relative.startswith(output_prefix):
            continue
        if len(files) >= config.max_audit_files:
            complete = False
            issues.append("The read-only baseline exceeded max_audit_files.")
            break
        try:
            files[relative] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except OSError:
            complete = False
            issues.append(f"Could not hash {relative} during the read-only baseline.")
    return ProjectSnapshot(files=files, complete=complete, issues=tuple(issues))


def compare_snapshots(
    before: ProjectSnapshot,
    after: ProjectSnapshot,
    allowed_writes: tuple[str, ...],
) -> ReadOnlyCheck:
    changed = sorted(
        path
        for path in set(before.files) | set(after.files)
        if before.files.get(path) != after.files.get(path)
    )
    boundaries = tuple((*before.issues, *after.issues))
    if changed:
        status = "failed"
    elif before.complete and after.complete:
        status = "passed"
    else:
        status = "unverified"
    return ReadOnlyCheck(
        status=status,
        method="SHA-256 comparison of in-scope project files before and after static analysis",
        files_checked=max(len(before.files), len(after.files)),
        allowed_writes=allowed_writes,
        unexpected_changes=tuple(changed),
        boundaries=boundaries,
    )