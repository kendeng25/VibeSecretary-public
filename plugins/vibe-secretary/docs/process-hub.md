# Process Hub

[English](process-hub.md) | [简体中文](process-hub_zh.md)

Process Hub stores plans, build histories, ADRs, research notes, reviews, and custom process records as repository-native Markdown. Markdown is the source of truth; JSON and Markdown indexes are derived and rebuildable.

## Initialize and enable

Foundation must already be initialized, scope-confirmed, and effectively enabled. In the consumer project, ask Codex:

```text
Use $vibe-secretary-process-hub to initialize Process Hub for this project. Do not enable it yet.
```

Review `.vibesecretary/process-hub.toml`, then confirm:

```text
I reviewed .vibesecretary/process-hub.toml. Enable Process Hub for this project.
```

The Skill calls `initialize_process_hub`, then `set_process_hub_enabled(enabled=true, confirm_config=true)` only after review. Editing the TOML later invalidates its confirmation; review and confirm it again before continued use.

## Configuration

A new schema 2 configuration exposes only the fields users need:

```toml
schema_version = 2

[[collections]]
id = "plans"
usage = "Create before major work to record goals, scope, design choices, and acceptance criteria; maintain it as implementation facts change."
path = "plans"
path_template = "{year}-{month}-{day}/{id}_{slug}.md"

[[collections]]
id = "build_hist"
usage = "Create after implementation and verification to record actual changes, checks, and remaining work; relate it to the source plan when one exists."
path = "build_hist"
path_template = "{year}-{month}-{day}/{id}_{slug}.md"
```

- `id` is the stable collection selector.
- `usage` tells Codex what belongs in the collection and when to create or maintain it.
- `path` is relative to the consumer-project root.
- `path_template` controls new document paths and must contain `{id}` and end in `.md`.

Supported template variables are `id`, `slug`, `stage`, `task`, `year`, `month`, and `day`:

```toml
path_template = "{year}-{month}-{day}/{id}_{slug}.md"
path_template = "{year}/{month}/{id}_{slug}.md"
path_template = "{stage}/{task}/{id}_{slug}.md"
```

Collection directories cannot overlap or live inside `.vibesecretary/`. Existing documents are never moved just because a template changes. Internal document type, ID prefix, core front matter, default lifecycle, and default index paths are derived by Process Hub.

Add a custom collection by adding another table:

```toml
[[collections]]
id = "adr"
usage = "Create when a durable architecture decision affects multiple modules; record alternatives, tradeoffs, and consequences."
path = "docs/adr"
path_template = "{year}/{id}_{slug}.md"
required_metadata = ["owner"]
statuses = ["proposed", "accepted", "superseded", "archived"]
initial_status = "proposed"
terminal_statuses = ["accepted", "superseded", "archived"]
```

`required_metadata` contains only additional fields; Process Hub already manages the core fields.

## Start using it

The explicit `$vibe-secretary-process-hub` form below is useful for setup, demonstrations, and forcing an unambiguous workflow. It is not required for every daily request. After the consumer [AGENTS.md template](agent/AGENTS.md) is adapted, Codex can use Process Hub when project instructions and the confirmed collection `usage` require a plan, decision, review, or build history.

Create a plan before major work:

```text
Use $vibe-secretary-process-hub to create a plan for replacing the authentication cache. Include scope, design decisions, risks, acceptance criteria, and verification.
```

Record the completed implementation and relate it to the plan:

```text
Use $vibe-secretary-process-hub to create the build history for the authentication cache work and relate it to PLAN-0001. Include every modified file, checks run, and remaining limitations.
```

Find or review records:

```text
Use $vibe-secretary-process-hub to find active plans related to authentication.
Use $vibe-secretary-process-hub to validate Process Hub and report inconsistent metadata or broken relations.
Show PLAN-0001 and all forward and reverse relations.
```

When the consumer [AGENTS.md template](agent/AGENTS.md) is installed and adapted, ordinary development work can also invoke Process Hub automatically when the confirmed collection `usage` requires a plan, decision, review, or build history.

## Behavior and safety

- One clearly required document is created directly; an extra preview confirmation is not required.
- Read-only requests, explicit previews, ambiguous collection choices, unmanaged-file adoption, configuration changes, and batch organization retain review boundaries.
- `organize_process_documents` always previews all moves before application.
- Creating a build history does not automatically close, archive, or move its source plan.
- Documents are never overwritten; duplicate IDs, invalid front matter, path escape, and overlapping collections are rejected.
- All reads and writes remain inside the project and the confirmed `.vibesecretaryignore` scope.

## Main tools

`process_hub_status`, `initialize_process_hub`, `set_process_hub_enabled`, `scan_process_documents`, `query_process_documents`, `get_process_document`, `preview_process_document`, `create_process_document`, `transition_process_document`, `organize_process_documents`, `validate_process_hub`, and `rebuild_process_index`.
