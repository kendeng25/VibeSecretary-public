"""Bundled stdio MCP server for VibeSecretary foundation and business modules."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from vibe_secretary.service import FoundationService
from vibe_secretary.process_service import ProcessHubService
from vibe_secretary.implementation_service import ImplementationLensService
from vibe_secretary.prompt_service import PromptCopilotService
from vibe_secretary.version import PLUGIN_VERSION

service = FoundationService()
process_hub = ProcessHubService()
implementation_lens = ImplementationLensService()
prompt_copilot = PromptCopilotService()
server = MCPServer(
    name="vibe-secretary-foundation",
    title="VibeSecretary",
    description="Project foundation, process documents, implementation maps, and Prompt review.",
    instructions="Use foundation tools for setup, Process Hub for documents, Implementation Lens for @lens code maps, and Prompt Copilot for sourced Prompt review.",
    version=PLUGIN_VERSION,
    log_level="WARNING",
)


@server.tool(description="Return the VibeSecretary foundation server health and version.", structured_output=True)
def foundation_health() -> dict[str, Any]:
    return service.health()


@server.tool(description="Inspect VibeSecretary initialization, scope, and enablement state.", structured_output=True)
def project_status(project_root: str = "") -> dict[str, Any]:
    return service.project_status(project_root)


@server.tool(description="Create disabled VibeSecretary config and read-scope templates without overwriting files.", structured_output=True)
def initialize_project(project_root: str = "") -> dict[str, Any]:
    return service.initialize_project(project_root)


@server.tool(description="Enable or disable VibeSecretary after explicit read-scope confirmation.", structured_output=True)
def set_project_enabled(
    enabled: bool,
    confirm_scope: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return service.set_project_enabled(
        enabled=enabled,
        confirm_scope=confirm_scope,
        project_root=project_root,
    )


@server.tool(description="Check whether one explicit path is allowed by the confirmed project scope.", structured_output=True)
def scope_decision(candidate: str, project_root: str = "") -> dict[str, Any]:
    return service.scope_decision(candidate=candidate, project_root=project_root)


@server.tool(description="Inspect Process Hub configuration, confirmation, and enablement state.", structured_output=True)
def process_hub_status(project_root: str = "") -> dict[str, Any]:
    return process_hub.status(project_root)


@server.tool(description="Create default Process Hub configuration and missing collection directories without enabling it.", structured_output=True)
def initialize_process_hub(project_root: str = "") -> dict[str, Any]:
    return process_hub.initialize(project_root)


@server.tool(description="Enable or disable Process Hub after explicit configuration review.", structured_output=True)
def set_process_hub_enabled(
    enabled: bool,
    confirm_config: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return process_hub.set_enabled(enabled, confirm_config, project_root)


@server.tool(description="Validate Process Hub configuration and all process-document consistency rules without changes.", structured_output=True)
def validate_process_hub(project_root: str = "") -> dict[str, Any]:
    return process_hub.validate(project_root)


@server.tool(description="Scan configured process collections and return managed, unmanaged, and issue summaries.", structured_output=True)
def scan_process_documents(project_root: str = "") -> dict[str, Any]:
    return process_hub.scan(project_root)


@server.tool(description="Query process documents by structured metadata or deterministic text matching.", structured_output=True)
def query_process_documents(
    project_root: str = "",
    collection: str = "",
    document_type: str = "",
    status: str = "",
    stage: str = "",
    task: str = "",
    tag: str = "",
    text: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    return process_hub.query(
        project_root=project_root,
        collection=collection,
        document_type=document_type,
        status=status,
        stage=stage,
        task=task,
        tag=tag,
        text=text,
        limit=limit,
    )


@server.tool(description="Return one process document by stable id, including derived reverse relations.", structured_output=True)
def get_process_document(
    document_id: str,
    include_body: bool = True,
    project_root: str = "",
) -> dict[str, Any]:
    return process_hub.get_document(document_id, include_body, project_root)


@server.tool(description="Preview the exact id, path, metadata, and Markdown for a new process document without writing.", structured_output=True)
def preview_process_document(
    collection: str,
    title: str,
    body: str = "",
    stage: str = "",
    task: str = "",
    status: str = "",
    tags: list[str] | None = None,
    relates_to: list[str] | None = None,
    slug: str = "",
    document_id: str = "",
    metadata: dict[str, Any] | None = None,
    project_root: str = "",
) -> dict[str, Any]:
    return process_hub.preview_document(
        collection=collection,
        title=title,
        body=body,
        stage=stage,
        task=task,
        status=status,
        tags=tags,
        relates_to=relates_to,
        slug=slug,
        document_id=document_id,
        metadata=metadata,
        project_root=project_root,
    )


@server.tool(description="Preview or explicitly create one process document without overwriting existing files.", structured_output=True)
def create_process_document(
    collection: str,
    title: str,
    body: str = "",
    stage: str = "",
    task: str = "",
    status: str = "",
    tags: list[str] | None = None,
    relates_to: list[str] | None = None,
    slug: str = "",
    document_id: str = "",
    metadata: dict[str, Any] | None = None,
    apply: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return process_hub.create_document(
        collection=collection,
        title=title,
        body=body,
        stage=stage,
        task=task,
        status=status,
        tags=tags,
        relates_to=relates_to,
        slug=slug,
        document_id=document_id,
        metadata=metadata,
        apply=apply,
        project_root=project_root,
    )


@server.tool(description="Preview or apply a lifecycle status change for one managed process document.", structured_output=True)
def transition_process_document(
    document_id: str,
    new_status: str,
    apply: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return process_hub.transition_document(document_id, new_status, apply, project_root)


@server.tool(description="Preview or apply safe moves of managed documents to configured template paths.", structured_output=True)
def organize_process_documents(
    apply: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return process_hub.organize(apply, project_root)


@server.tool(description="Preview or rebuild the derived JSON and Markdown Process Hub indexes.", structured_output=True)
def rebuild_process_index(
    apply: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return process_hub.rebuild_index(apply, project_root)




@server.tool(description="Inspect Implementation Lens configuration, output, and enablement state.", structured_output=True)
def implementation_lens_status(project_root: str = "") -> dict[str, Any]:
    return implementation_lens.status(project_root)


@server.tool(description="Create the default Implementation Lens config without enabling the module.", structured_output=True)
def initialize_implementation_lens(project_root: str = "") -> dict[str, Any]:
    return implementation_lens.initialize(project_root)


@server.tool(description="Enable or disable Implementation Lens after explicit config review.", structured_output=True)
def set_implementation_lens_enabled(
    enabled: bool,
    confirm_config: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return implementation_lens.set_enabled(enabled, confirm_config, project_root)


@server.tool(description="Incrementally rebuild the scope-safe static implementation index.", structured_output=True)
def refresh_implementation_index(project_root: str = "") -> dict[str, Any]:
    return implementation_lens.refresh(project_root)


@server.tool(description="Inspect reusable project-model freshness and repository-wide static evidence without writing.", structured_output=True)
def inspect_implementation_model(project_root: str = "") -> dict[str, Any]:
    return implementation_lens.inspect_model(project_root)


@server.tool(description="Validate and update the reusable, granularity-independent project model from indexed evidence.", structured_output=True)
def update_implementation_model(
    records: list[dict[str, Any]],
    coverage: str,
    covered_paths: list[str] | None = None,
    diagnostics: list[str] | None = None,
    expected_model_digest: str = "",
    confirm_replace_modified: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return implementation_lens.update_model(
        records,
        coverage,
        covered_paths,
        diagnostics,
        expected_model_digest,
        confirm_replace_modified,
        project_root,
    )


@server.tool(description="Query a read-only Python implementation subgraph without writing reports.", structured_output=True)
def query_implementation(
    query: str,
    granularity: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    return implementation_lens.query(query, granularity, project_root)


@server.tool(description="Render a validated minimum-sufficient semantic Story as paired Markdown and static-first offline HTML.", structured_output=True)
def render_implementation_map(
    query: str,
    granularity: str = "",
    title: str = "",
    story: dict[str, Any] | None = None,
    project_root: str = "",
) -> dict[str, Any]:
    return implementation_lens.render(
        query, granularity, title, project_root=project_root, story=story
    )


@server.tool(description="Inspect Prompt Copilot configuration, confirmation, provider, and enablement state.", structured_output=True)
def prompt_copilot_status(project_root: str = "") -> dict[str, Any]:
    return prompt_copilot.status(project_root)


@server.tool(description="Create the default Prompt Copilot configuration without enabling it.", structured_output=True)
def initialize_prompt_copilot(project_root: str = "") -> dict[str, Any]:
    return prompt_copilot.initialize(project_root)


@server.tool(description="Enable or disable Codex Host Prompt Copilot after explicit configuration review.", structured_output=True)
def set_prompt_copilot_enabled(
    enabled: bool,
    confirm_config: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    return prompt_copilot.set_enabled(enabled, confirm_config, project_root)


@server.tool(description="Prepare a scope-safe, sourced Prompt review package for the current Codex Host.", structured_output=True)
def prepare_prompt_review(
    prompt: str,
    mode: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    return prompt_copilot.prepare_review(prompt, mode, project_root)


@server.tool(description="Validate a structured Prompt package generated by the current Codex Host.", structured_output=True)
def validate_prompt_package(
    original_prompt: str,
    package: dict[str, Any],
    mode: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    return prompt_copilot.validate_package(original_prompt, package, mode, project_root)


def main() -> None:
    """Run until the Codex MCP client closes stdio."""

    server.run("stdio")
