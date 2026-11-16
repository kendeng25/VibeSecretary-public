# Agent Instructions

> Reusable template for a project that consumes the VibeSecretary Plugin. Copy it to the consumer
> project root as `AGENTS.md`, review it, and add project-specific commands. This documentation
> copy is not loaded automatically by other projects.

## General project rules

### Scope and language

- Treat the directory containing this file as the consumer project root.
- The current user request overrides defaults here; use a closer nested `AGENTS.md` for
  subtree-specific exceptions.
- Write code, comments, docstrings, configuration keys, and filenames in English unless requested
  otherwise.

### Environment

Use a project-local Python virtual environment named `.venv`. Create and activate it from the
project root when needed:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On POSIX shells, activate it with `source .venv/bin/activate`.

- Pin every direct runtime dependency in `requirements.txt` as `package==X.Y.Z`.
- Update dependency declarations in the same change as the code that needs them.
- Keep development-only dependencies separate and never rely on global Python packages.
- Run Python commands and project scripts from the project root unless documented otherwise.

### Development and file editing

- Match existing style, naming, and abstractions; keep changes focused.
- Prefer existing files and reusable source APIs over parallel or one-off implementations.
- Keep user-facing configuration separate from executable entrypoints.
- Put reusable project code—including application logic, components, models, data encoding,
  training loops, and evaluation utilities—under `src/`.
- By default, put project entrypoints and executable scripts in `experiments/`. Treat them as a
  thin orchestration layer above `src/`: load configuration, instantiate components from `src/`,
  and call a small number of high-level APIs.
- Test files may live under `tests/`; keep reusable runtime implementation in `src/` rather than
  embedding it in tests or entrypoints.
- Preserve unrelated changes and avoid destructive Git or filesystem commands.
- Do not use `apply_patch`; use non-sandboxed shell writes and request approval when required.

### Verification

- Run the smallest relevant checks first and broaden verification in proportion to risk.
- Distinguish passed, failed, and skipped checks. Never infer success from intent or partial output.
- The agent has no direct GPU access. Prepare GPU work completely and give the user the exact
  command to run; do not claim unexecuted GPU results.

### Plotting conventions for 2D meshes and images

- For non-negative quantities, use `cmap="Reds"` so values range from white to red.
- For signed quantities, use `cmap="RdBu_r"` with a symmetric range:

  ```python
  limit = abs(data).max()
  vmin = -limit
  vmax = limit
  ```

  Zero must map to white, negative values to blue, and positive values to red.

### Long-term memory

- Read relevant files under `memory/` at the start of a session.
- Update them only for durable user preferences or architectural decisions.
- Do not duplicate facts already derivable from code, configuration, managed documents, or Git.

## VibeSecretary

This consumer project uses the installed VibeSecretary Codex Plugin. Use the Plugin for matching
project workflow and Prompt-improvement tasks instead of manually recreating Plugin-managed results.

### Plugin entry points

- Use `$vibe-secretary-foundation` for VibeSecretary project setup, scope, enablement, status,
  and diagnostics.
- Use `$vibe-secretary-process-hub` for configured process collections and process-document
  operations.
- Use `$vibe-secretary-implementation-lens` only when the current message begins with the complete
  `@lens` token. Keep consumer source read-only, maintain the evidence-linked reusable project model,
  and generate the configured Markdown and static-first offline HTML semantic storyboard.
- Use `$vibe-secretary-prompt-copilot` when the user explicitly asks to optimize, review,
  clarify, or prepare a development Prompt. Automatic Prompt handling is provided separately by
  the Plugin's configured Hook.
- Foundation and Process Hub allow implicit Skill invocation. Implementation Lens does not: ordinary
  code questions must not activate it, and `@lens` takes routing priority over Prompt Copilot.
- Invoke the appropriate Foundation or Process Hub Skill for a
  matching request even when the user does not name it explicitly.
- Follow the selected Skill as the authoritative workflow and use the VibeSecretary MCP tools it
  prescribes.
- Treat the consumer project's VibeSecretary configuration as the source of truth. Do not assume
  collection names, directory layouts, document types, or development workflows in this file.
- At the start of matching work, read Process Hub status and use each collection's confirmed
  `usage` as runtime guidance. When that guidance or the project workflow clearly requires one
  process document, create it directly without asking for an extra business confirmation.
- After implementation and verification, create the applicable factual record (normally the
  configured build-history collection) and relate it to its source plan when one exists. Do not
  close, archive, or move the whole plan merely because one implementation increment finished.
- Preserve previews and confirmation for explicit read-only/preview requests, material ambiguity,
  configuration or scope changes, unmanaged-file adoption, migration, and batch organization.
- Report the VibeSecretary Skill and MCP tools used. If a required capability is unavailable, say
  so instead of simulating a Plugin-managed result.
