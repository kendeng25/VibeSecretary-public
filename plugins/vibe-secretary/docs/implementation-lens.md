# Implementation Lens

[English](implementation-lens.md) | [简体中文](implementation-lens_zh.md)

Implementation Lens explains a requested Python implementation with static, evidence-linked analysis. Its goal is the smallest truthful view that answers the question, not the largest graph it can produce.

## Initialize and enable

Foundation must already be initialized, scope-confirmed, and effectively enabled. In the consumer project, ask Codex:

```text
Use $vibe-secretary-implementation-lens to initialize Implementation Lens for this project. Do not enable it yet.
```

Review `.vibesecretary/implementation-lens.toml`, then confirm:

```text
I reviewed .vibesecretary/implementation-lens.toml. Enable Implementation Lens for this project.
```

The Skill calls `initialize_implementation_lens`, then `set_implementation_lens_enabled(enabled=true, confirm_config=true)` only after review. Editing the TOML later invalidates its confirmation; review and confirm it again before continued use.

## Configuration

A new schema 2 configuration is:

```toml
schema_version = 2
default_granularity = "symbol"
index_json = ".vibesecretary/implementation-lens-index.json"

[output]
path = "ImplementationLens"
path_template = "reports/{granularity}/{slug}_{timestamp}.{ext}"
project_model_path = "_project_model"

[limits]
max_files = 2000
max_file_bytes = 1048576
max_nodes = 500
max_edges = 1000
max_audit_files = 5000
```

Users retain control of the generated file structure:

- `output.path` selects the project-relative output root.
- `output.path_template` controls paired query-report paths and must contain `{slug}` and `{ext}`. It can also use `timestamp`, `granularity`, `language`, `year`, `month`, and `day`.
- `output.project_model_path` selects the stable reusable-model directory below `output.path`; it is independent of query granularity.
- `index_json` selects the rebuildable static index path.

For example:

```toml
[output]
path = "docs/implementation"
path_template = "reports/{year}/{month}/{granularity}/{slug}_{timestamp}.{ext}"
project_model_path = "project-model"
```

Paths must remain project-relative and cannot contain `..`. Reports cannot live inside the reusable-model directory. Changing templates does not move existing reports.

## Start using it

The explicit `$vibe-secretary-implementation-lens` name is for initialization and configuration management. A normal analysis does not need to name the Skill; the current message only needs to begin with the complete, case-insensitive `@lens` token after optional whitespace. Ask for the cognitive level explicitly when the default is not suitable:

```text
@lens Explain how this agent plans, calls tools, observes results, and stops. Use module granularity.
@lens Trace session renewal from the HTTP handler to persistence. Use symbol granularity.
@lens Show the branches and concrete reads and writes involved in token rotation. Use detail granularity.
```

`@lensfoo` and a token in the middle of a message do not trigger Lens. A bare `@lens` asks for an implementation concern before analysis. Lens routing takes precedence over Prompt Copilot for that message.

## Granularity is cognitive, not numeric

- `module` explains actual system responsibilities and the concept flow between them. If the implementation really uses ReAct, the report can express its real Think–Act–Observe loop; Lens never imposes that template on a different agent or project.
- `symbol` traces the necessary components and key symbols from entry to result.
- `detail` exposes the necessary calls, registrations, branches, reads, writes, and external boundaries.

No level targets a fixed number of stages, symbols, or transitions. Node and edge limits are safety ceilings only. A branch, loop, failure path, boundary, or uncertainty is retained when omitting it would change the explanation; irrelevant neighbors are summarized or omitted.

## Reusable project model and reports

Before answering a query, Lens inspects or refreshes a long-lived model under `output.path/project_model_path`. It records evidence-linked responsibilities, components, flows, entrypoints, and external boundaries independently of the requested report granularity. On later runs, fresh records are reused and records invalidated by changed source evidence are replaced.

Large or only partly analyzed projects are marked `partial` with covered paths and gaps. Source code remains authoritative. If a managed model file was edited outside Lens, the conflict is reported and the file is not silently overwritten.

Each query produces paired Markdown and offline HTML from the same validated semantic Story. Markdown contains the concise flow, boundaries, evidence appendix, and read-only check. HTML is a static-first storyboard with native expandable evidence; JavaScript only enhances expansion and filtering. It is not presented as a complete call graph.

## Static and read-only boundaries

The analyzer uses Python AST evidence and does not import or execute consumer code. It can identify Python modules, classes, functions, methods, entrypoints, imports, common direct calls, decorators, and registrations. Reflection, dynamic dispatch, dependency injection, string-based imports, and framework magic may remain heuristic or unknown.

A normal `@lens` workflow does not edit source or run project entrypoints, tests, builds, formatters, or generators. Its tools may write only the configured rebuildable index, reusable project model, and paired reports. Source digests are compared before and after analysis; `failed` and `unverified` read-only checks are never relabeled as passed.

## Main tools

`implementation_lens_status`, `initialize_implementation_lens`, `set_implementation_lens_enabled`, `refresh_implementation_index`, `inspect_implementation_model`, `update_implementation_model`, `query_implementation`, and `render_implementation_map`.