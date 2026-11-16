# Agent Instructions

## Project Scope

This repository develops the VibeSecretary Codex Plugin itself. It is not a consumer project.

- Do not invoke the installed or in-development VibeSecretary Skills, Hooks, MCP tools, or other
  Plugin capabilities to manage, analyze, document, or optimize work in this repository.
- Inspect and modify this repository directly with normal repository tools and the instructions in
  this file. Do not treat unavailable or disabled VibeSecretary project state as a blocker.
- Run VibeSecretary capabilities only when an explicit development or acceptance test requires
  them, and target an isolated temporary consumer project or a fixture rather than this repository.
- Treat the root `plans/`, `build_hist/`, and `memory/` directories as Plugin-development records,
  not as consumer-project business data for Process Hub.

## Project Structure

- `plugins/vibe-secretary/` is the distributable Plugin root.
  - `.codex-plugin/plugin.json` is the Plugin manifest; `.mcp.json` declares the local MCP server.
  - `src/vibe_secretary/` contains the reusable Python runtime, services, models, configuration,
    scope enforcement, Hooks logic, and MCP tool implementations.
  - `skills/` contains Codex Skill workflows; keep deterministic business logic in Python rather
    than embedding it in Skill instructions.
  - `hooks/` contains Hook declarations and thin launchers into the Python runtime.
  - `scripts/` contains development/runtime setup and entrypoint helpers.
  - `docs/` contains user-facing and consumer-agent documentation.
  - `tests/` contains the Plugin unit, integration, packaging, and acceptance tests.
  - `runtime/` contains the generated local runtime descriptor used by the development install.
- `.agents/plugins/marketplace.json` exposes the local `personal` marketplace entry for the Plugin.
- `plans/` contains Chinese development plans; `build_hist/` contains corresponding Chinese build
  histories; `memory/` contains durable project context that is not derivable from code or Git.
- `refs/` is read-only architectural reference material and must never become a runtime dependency.
- Root `requirements.txt` pins runtime dependencies; `requirements-dev.txt` adds development-only
  tooling. Root `tests/` is currently only a placeholder; active tests live under the Plugin root.
- `README.md` is the top-level installation, usage, and verification guide.

## Environment

Use a project-local Python virtual environment named `.venv`. Create it from the
repository root when it does not exist:

```powershell
py -m venv .venv
```

Activate it before running Python code or installing packages:

```powershell
.\.venv\Scripts\Activate.ps1
```

On POSIX shells, activate it with `source .venv/bin/activate`.

- Run Python commands and experiment scripts from the repository root.
- Install project dependencies with `python -m pip install -r requirements.txt`.
- Declare every direct Python dependency in the root `requirements.txt` using an
  exact version pin (`package==X.Y.Z`). Do not use unpinned dependencies or range
  specifiers such as `>=`, `~=`, or `*`.
- When code introduces, removes, or upgrades a dependency, update
  `requirements.txt` in the same change. Keep development-only tooling out of the
  runtime dependency list unless the project later adopts a separate requirements
  file for it.
- Do not install project dependencies globally or rely on packages that happen to
  exist outside `.venv`.

**GPU constraint**: The agent has no direct GPU access. Any GPU-dependent execution, including model training, must be handed off to the user. When such a task arises, prepare the code and configuration completely, then provide the exact command the user should run.

## Reference Infrastructure

The `refs/` directory contains another project whose domain and product behavior
are unrelated to this project. Treat it as read-only architectural reference
material for agent infrastructure only.

- Study the reference implementation when designing agents, provider adapters,
  message handling, tool schemas and registries, tool-call validation and
  execution, agent loops, prompts, completion protocols, error handling, and
  related tests.
- Reimplement the needed ideas inside this project's own `src/` modules, adapting
  names, interfaces, and behavior to this project's requirements and conventions.
- The project must not import modules from `refs/`, add `refs/` to `sys.path`, load
  prompts or assets from it at runtime, execute its scripts, or depend on its
  requirements, configuration, generated files, or environment.
- Do not package or deploy `refs/`. Production code and tests must continue to work
  if the entire `refs/` directory is absent.
- Do not copy domain-specific behavior from the reference project. Reuse design
  concepts deliberately, and keep the resulting implementation independently
  owned and testable in this repository.
- When adding agent or tool-calling infrastructure, include project-local tests for
  tool registration, schema generation, argument validation, execution success and
  failure payloads, allowed-tool filtering, loop termination, and step limits as
  applicable.

## Development Style

### Language

- Write all code, comments, docstrings, and filenames in **English** unless the user explicitly requests otherwise.
- Write files under `plans/` and `build_hist/` in **Chinese** by default.

### Workflow for Major Changes

Before starting any significant addition or refactor:

1. Write a plan to `plans/<topic>.md` describing the approach, affected files, and key design decisions.
2. Implement the changes.
3. Record a build history entry in `build_hist/<NNN>_<topic>.md` summarizing what was done and listing every modified file.

Minor edits, such as bug fixes and small tweaks, do not require a plan or build history entry.

### File Editing

- Do not use `apply_patch` in this repository.
- When file writes are needed, use non-sandboxed shell commands and request approval when required.

### Consistency

- Match the style, naming conventions, and abstractions of the existing code, especially under
  `plugins/vibe-secretary/src/vibe_secretary/`.
- Do not introduce new patterns or refactor surrounding code unless the task explicitly requires it.
- Prefer editing existing files over creating new ones.
- Keep user-facing configuration separate from executable entrypoints.
- Put reusable services, models, parsers, repositories, validation, analysis, and execution logic
  under `plugins/vibe-secretary/src/vibe_secretary/`.
- Keep MCP tool functions, Hook launchers, and scripts thin: validate or translate boundary inputs,
  delegate to reusable source APIs, and return stable structured results.
- Keep Skills focused on collaboration workflow, tool sequencing, output contracts, and failure
  handling. Do not duplicate deterministic Python behavior in Skill prose.
- Add or update tests under `plugins/vibe-secretary/tests/` for every changed runtime or integration
  contract.
### Plotting Conventions for 2D Meshes and Images

- For **non-negative quantities**, use `cmap="Reds"` so values range visually from white to red.
- For **signed quantities**, use `cmap="RdBu_r"` with a symmetric color range:

  ```python
  limit = abs(data).max()
  vmin = -limit
  vmax = limit
  ```

  This ensures that zero maps to white, negative values map to blue, and positive values map to red.

## Long-Term Memory

Persistent notes about the user, architectural decisions, and accumulated context are stored under `memory/` at the repository root.

- Read relevant files from `memory/` at the start of a session.
- Update them when new, durable information is learned.
- Do not duplicate information that can already be derived from the codebase or Git history.
