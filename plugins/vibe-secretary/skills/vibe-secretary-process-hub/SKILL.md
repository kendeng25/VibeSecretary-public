---
name: vibe-secretary-process-hub
description: Configure, create, find, review, organize, relate, transition, archive, or index plans, build histories, ADRs, research notes, reviews, and other Process Hub documents in the current consumer project. Use whenever development, research, decisions, reviews, or project instructions require a process record before, during, or after the work, including a build history after implementation and verification. Do not use for source-code implementation mapping or prompt optimization.
---

# VibeSecretary Process Hub

Use the bundled deterministic Process Hub MCP tools. Treat the current consumer project as the only
project root; never infer document targets from the installed Plugin source directory.

## Start every workflow

1. Call `process_hub_status`.
2. State the returned absolute `project_root` before a mutation.
3. Treat the returned collection catalog as the current project's runtime extension of this Skill.
   Select collections by their `usage`, not only by their IDs or paths.
4. If Foundation is not effectively enabled, stop and use the foundation workflow first.
5. If Process Hub is not initialized, call `initialize_process_hub` only when the user asked to set
   it up. Tell the user to review `.vibesecretary/process-hub.toml`.
6. Enable only after explicit review by calling `set_process_hub_enabled` with
   `enabled=true` and `confirm_config=true`.

## Create a document

When the current request, consumer-project instructions, or confirmed collection `usage` requires
one process document, create it directly with `create_process_document` and `apply=true`. This
applies to plans, build histories, ADRs, research notes, reviews, and custom collections.

- Resolve collection, title, stage, task, status, tags, relations, and body from facts already
  available. Ask only when missing information changes the result materially.
- Use `preview_process_document` instead when the user requests read-only work, a preview, no
  record, or waiting for confirmation.
- Report the created document ID and path. Never overwrite an existing document.
- After implementation and verification, create a build history when its confirmed `usage` calls
  for one, and relate it to the source plan when one exists.
- Creating a document does not authorize closing, archiving, or moving an existing plan. Record
  partial or blocked work honestly.

## Find and review

- Use `query_process_documents` for collection, type, status, stage, task, tag, or text searches.
- Use `get_process_document` for one stable ID and its forward and reverse relations.
- Use `validate_process_hub` for configuration and consistency review. Report issues by code and
  path; do not silently fix unmanaged or invalid documents.
- Use `scan_process_documents` when the user needs the complete managed/unmanaged inventory.

## Change lifecycle or archive

- If the user explicitly requests one unambiguous status transition, call
  `transition_process_document` with `apply=true` and report the old and new status.
- Use `apply=false` when the user requests a preview or when the intended status is materially
  ambiguous.
- Archive by transitioning to the collection's configured `archived` status. Do not move a file
  merely because its status changed.

## Organize and index

- For `organize_process_documents`, always call with `apply=false` first and show every proposed
  source and target path. Apply only after explicit confirmation. Never adopt or move unmanaged
  files without that review.
- Rebuild derived indexes directly with `rebuild_process_index` and `apply=true`, unless the user
  requested a preview.

## Boundaries

- Configuration, scope, unmanaged-file adoption, migration, and batch moves retain their explicit
  review or confirmation boundary.
- Never scan or mutate the VibeSecretary Plugin development repository unless it is intentionally
  the current consumer project and the user explicitly enabled it there.
- Never bypass `.vibesecretaryignore`, Foundation enablement, or Process Hub config confirmation.
- Keep Markdown documents as facts; treat generated JSON and Markdown indexes as rebuildable.
- Do not implement or simulate Implementation Lens or Prompt Copilot behavior.
- Return structured tool errors with a concise recovery step; do not expose tracebacks.
