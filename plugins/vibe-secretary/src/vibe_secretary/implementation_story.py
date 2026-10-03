"""Validation and deterministic fallback stories for Implementation Lens."""

from __future__ import annotations

import re
from typing import Any

from vibe_secretary.errors import FoundationError
from vibe_secretary.implementation_config import ImplementationLensConfig
from vibe_secretary.implementation_models import (
    ConceptStage,
    EvidenceRef,
    Granularity,
    ImplementationIndex,
    ImplementationStory,
    ImplementationView,
    StoryBasis,
    StoryTransition,
)

_STAGE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ALLOWED_TRANSITIONS = {"next", "branch", "loop", "error", "complete", "dependency"}
MAX_STORY_TEXT = 8000
MAX_STAGE_DETAILS = 100
MAX_EVIDENCE_PER_ITEM = 200


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise FoundationError(
            "invalid_implementation_story", f"Story field '{field}' must be a string."
        )
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise FoundationError(
            "invalid_implementation_story", f"Story field '{field}' cannot be empty."
        )
    if len(normalized) > MAX_STORY_TEXT:
        raise FoundationError(
            "invalid_implementation_story",
            f"Story field '{field}' exceeds {MAX_STORY_TEXT} characters.",
        )
    return normalized


def _basis(value: Any, field: str) -> StoryBasis:
    try:
        return StoryBasis(str(value))
    except ValueError as exc:
        raise FoundationError(
            "invalid_implementation_story",
            f"Story field '{field}' must be 'fact' or 'interpretation'.",
        ) from exc


def _evidence(
    raw: Any,
    index: ImplementationIndex,
    field: str,
) -> tuple[EvidenceRef, ...]:
    if not isinstance(raw, list) or not raw:
        raise FoundationError(
            "invalid_implementation_story",
            f"Story field '{field}' requires at least one evidence reference.",
        )
    if len(raw) > MAX_EVIDENCE_PER_ITEM:
        raise FoundationError(
            "invalid_implementation_story",
            f"Story field '{field}' exceeds the evidence safety limit.",
        )
    node_ids = {item.node_id for item in index.nodes}
    edge_ids = {item.edge_id for item in index.edges}
    parsed: list[EvidenceRef] = []
    for position, item in enumerate(raw):
        if not isinstance(item, dict):
            raise FoundationError(
                "invalid_implementation_story",
                f"Story field '{field}[{position}]' must be an object.",
            )
        kind = str(item.get("kind", ""))
        ref_id = str(item.get("ref_id", ""))
        valid = (kind == "node" and ref_id in node_ids) or (
            kind == "edge" and ref_id in edge_ids
        )
        if not valid:
            raise FoundationError(
                "invalid_implementation_evidence",
                "Story evidence must reference an existing indexed node or edge.",
                {"kind": kind, "ref_id": ref_id},
            )
        parsed.append(
            EvidenceRef(
                kind=kind,
                ref_id=ref_id,
                claim=_text(
                    item.get("claim", ""),
                    f"{field}[{position}].claim",
                    allow_empty=True,
                ),
            )
        )
    return tuple(parsed)


def parse_story(
    raw: Any,
    index: ImplementationIndex,
    config: ImplementationLensConfig,
    *,
    query: str,
    granularity: Granularity,
    title: str,
) -> ImplementationStory:
    """Parse one model-authored story while keeping evidence validation deterministic."""

    if not isinstance(raw, dict):
        raise FoundationError(
            "invalid_implementation_story", "story must be an object."
        )
    stages_raw = raw.get("stages", [])
    transitions_raw = raw.get("transitions", [])
    if not isinstance(stages_raw, list) or not stages_raw:
        raise FoundationError(
            "invalid_implementation_story", "story.stages must be a non-empty list."
        )
    if len(stages_raw) > config.max_nodes:
        raise FoundationError(
            "invalid_implementation_story",
            "Story stages exceed the configured node safety limit.",
        )
    if not isinstance(transitions_raw, list) or len(transitions_raw) > config.max_edges:
        raise FoundationError(
            "invalid_implementation_story",
            "Story transitions must be a list within the configured edge safety limit.",
        )
    stages: list[ConceptStage] = []
    stage_ids: set[str] = set()
    for position, item in enumerate(stages_raw):
        if not isinstance(item, dict):
            raise FoundationError(
                "invalid_implementation_story",
                f"story.stages[{position}] must be an object.",
            )
        stage_id = str(item.get("id", ""))
        if not _STAGE_ID.fullmatch(stage_id) or stage_id in stage_ids:
            raise FoundationError(
                "invalid_implementation_story",
                "Story stage IDs must be unique lower-case hyphen identifiers.",
                {"stage_id": stage_id},
            )
        stage_ids.add(stage_id)
        details_raw = item.get("details", [])
        if not isinstance(details_raw, list) or len(details_raw) > MAX_STAGE_DETAILS:
            raise FoundationError(
                "invalid_implementation_story",
                "Story stage details must be a bounded list.",
            )
        stages.append(
            ConceptStage(
                stage_id=stage_id,
                title=_text(item.get("title", ""), f"stages[{position}].title"),
                summary=_text(item.get("summary", ""), f"stages[{position}].summary"),
                role=_text(
                    item.get("role", "stage"), f"stages[{position}].role"
                ),
                basis=_basis(
                    item.get("basis", StoryBasis.INTERPRETATION.value),
                    f"stages[{position}].basis",
                ),
                evidence=_evidence(
                    item.get("evidence", []), index, f"stages[{position}].evidence"
                ),
                details=tuple(
                    _text(value, f"stages[{position}].details")
                    for value in details_raw
                ),
                lane=_text(
                    item.get("lane", ""),
                    f"stages[{position}].lane",
                    allow_empty=True,
                ),
            )
        )
    transitions: list[StoryTransition] = []
    for position, item in enumerate(transitions_raw):
        if not isinstance(item, dict):
            raise FoundationError(
                "invalid_implementation_story",
                f"story.transitions[{position}] must be an object.",
            )
        source = str(item.get("source", ""))
        target = str(item.get("target", ""))
        kind = str(item.get("kind", "next"))
        if source not in stage_ids or target not in stage_ids:
            raise FoundationError(
                "invalid_implementation_story",
                "Story transitions must connect existing stages.",
                {"source": source, "target": target},
            )
        if kind not in _ALLOWED_TRANSITIONS:
            raise FoundationError(
                "invalid_implementation_story",
                "Story transition kind is unsupported.",
                {"kind": kind},
            )
        basis = _basis(
            item.get("basis", StoryBasis.INTERPRETATION.value),
            f"transitions[{position}].basis",
        )
        evidence = _evidence(
            item.get("evidence", []), index, f"transitions[{position}].evidence"
        )
        if basis is StoryBasis.FACT and not any(ref.kind == "edge" for ref in evidence):
            raise FoundationError(
                "invalid_implementation_story",
                "A fact transition requires at least one indexed edge reference.",
            )
        transitions.append(
            StoryTransition(
                source_id=source,
                target_id=target,
                kind=kind,
                label=_text(
                    item.get("label", kind), f"transitions[{position}].label"
                ),
                basis=basis,
                evidence=evidence,
            )
        )
    limitations_raw = raw.get("limitations", [])
    if not isinstance(limitations_raw, list):
        raise FoundationError(
            "invalid_implementation_story", "story.limitations must be a list."
        )
    return ImplementationStory(
        query=query.strip(),
        granularity=granularity,
        title=title.strip(),
        stages=tuple(stages),
        transitions=tuple(transitions),
        omitted_summary=_text(
            raw.get("omitted_summary", ""), "omitted_summary", allow_empty=True
        ),
        limitations=tuple(_text(item, "limitations") for item in limitations_raw),
    )


def fallback_story(
    view: ImplementationView,
    *,
    title: str,
) -> ImplementationStory:
    """Create an explicit evidence fallback for legacy callers without a semantic story."""

    node_by_id = {item.node_id: item for item in view.nodes}
    seed_nodes = [node_by_id[item] for item in view.seed_ids if item in node_by_id]
    if not seed_nodes:
        seed_nodes = list(view.nodes[:1])
    stages: list[ConceptStage] = []
    stage_by_node: dict[str, str] = {}
    for position, node in enumerate(seed_nodes):
        stage_id = f"evidence-{position + 1}"
        stage_by_node[node.node_id] = stage_id
        stages.append(
            ConceptStage(
                stage_id=stage_id,
                title=node.label or node.qualified_name,
                summary=(
                    "Direct static evidence fallback. Supply a semantic Story through the "
                    "Implementation Lens Skill for an architecture-level explanation."
                ),
                role=node.kind,
                basis=StoryBasis.FACT,
                evidence=(EvidenceRef("node", node.node_id, "Matched query seed."),),
                details=(f"{node.qualified_name} — {node.path}:{node.start_line}",),
            )
        )
    transitions: list[StoryTransition] = []
    for edge in view.edges:
        source = stage_by_node.get(edge.source_id)
        target = stage_by_node.get(edge.target_id)
        if source and target:
            transitions.append(
                StoryTransition(
                    source_id=source,
                    target_id=target,
                    kind="dependency",
                    label=edge.kind,
                    basis=StoryBasis.FACT,
                    evidence=(EvidenceRef("edge", edge.edge_id, "Indexed relation."),),
                )
            )
    if not stages:
        stages.append(
            ConceptStage(
                stage_id="no-evidence",
                title="No matching evidence",
                summary="The current query did not select an indexed code entity.",
                role="diagnostic",
                basis=StoryBasis.FACT,
                evidence=(),
            )
        )
    return ImplementationStory(
        query=view.query,
        granularity=view.granularity,
        title=title,
        stages=tuple(stages),
        transitions=tuple(transitions),
        omitted_summary=(
            "This compatibility result intentionally shows only query seeds; it is not a "
            "semantic or complete implementation map."
        ),
        limitations=(
            "No semantic Story was supplied, so the renderer used a labeled evidence fallback.",
            *view.limitations,
        ),
        fallback=True,
    )
def expand_view_for_story(
    view: ImplementationView,
    index: ImplementationIndex,
    story: ImplementationStory,
) -> ImplementationView:
    """Include every cited node, edge, and edge endpoint in the report appendix."""

    node_ids = {item.node_id for item in view.nodes}
    edge_ids = {item.edge_id for item in view.edges}
    index_nodes = {item.node_id: item for item in index.nodes}
    index_edges = {item.edge_id: item for item in index.edges}
    evidence = [
        ref
        for stage in story.stages
        for ref in stage.evidence
    ] + [
        ref
        for transition in story.transitions
        for ref in transition.evidence
    ]
    for ref in evidence:
        if ref.kind == "node":
            node_ids.add(ref.ref_id)
        else:
            edge = index_edges.get(ref.ref_id)
            if edge is not None:
                edge_ids.add(ref.ref_id)
                node_ids.update((edge.source_id, edge.target_id))
    nodes = tuple(
        sorted(
            (index_nodes[item] for item in node_ids if item in index_nodes),
            key=lambda item: (not item.entrypoint, item.kind, item.path, item.start_line),
        )
    )
    edges = tuple(
        sorted(
            (
                index_edges[item]
                for item in edge_ids
                if item in index_edges
                and index_edges[item].source_id in node_ids
                and index_edges[item].target_id in node_ids
            ),
            key=lambda item: (item.kind, item.source_id, item.target_id),
        )
    )
    return ImplementationView(
        query=view.query,
        granularity=view.granularity,
        nodes=nodes,
        edges=edges,
        seed_ids=view.seed_ids,
        diagnostics=view.diagnostics,
        limitations=view.limitations,
        truncated=view.truncated,
    )
