---
name: vibe-secretary-foundation
description: Initialize, enable, disable, inspect, or diagnose the VibeSecretary Codex plugin foundation for the current local project. Use only for foundation management, not process documents, implementation maps, or prompt optimization.
---

# VibeSecretary Foundation

Use the bundled VibeSecretary foundation MCP tools for project setup and diagnostics.

## Workflow

1. Call `project_status` for the current project before changing foundation state.
2. If the project is not initialized and the user asks to initialize it, call `initialize_project`.
3. Tell the user to review `.vibesecretaryignore` before enabling the project.
4. Enable only after the user explicitly confirms the scope; then call `set_project_enabled` with
   `enabled=true` and `confirm_scope=true`.
5. To disable, call `set_project_enabled` with `enabled=false`.
6. Use `foundation_health` for server or version diagnostics.
7. Use `scope_decision` only for a specific path the user asks about.

## Boundaries

- Do not overwrite an existing config or scope file.
- Do not claim the scope file can fully constrain opaque shell commands or every native Codex read.
- Do not read excluded paths to explain why they are excluded.
- Do not manage process documents in this foundation skill; use
  `$vibe-secretary-process-hub` for Process Hub workflows.
- Do not implement or simulate Implementation Lens or Prompt Copilot behavior.
- Return the MCP tool's structured error and a concise recovery step when an operation fails.
