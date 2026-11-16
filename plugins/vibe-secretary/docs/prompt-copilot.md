# Prompt Copilot

[English](prompt-copilot.md) | [简体中文](prompt-copilot_zh.md)

Prompt Copilot improves development requests with evidence from the confirmed project scope. Its automatic Hook can clarify scope, constraints, acceptance criteria, and verification without replacing or resubmitting the user's original message.

## Initialize and enable

Foundation must already be initialized, scope-confirmed, and effectively enabled. In the consumer project, ask Codex:

```text
Use $vibe-secretary-prompt-copilot to initialize Prompt Copilot for this project. Do not enable it yet.
```

Review `.vibesecretary/prompt-copilot.toml`, then confirm:

```text
I reviewed .vibesecretary/prompt-copilot.toml. Enable Prompt Copilot for this project.
```

The Skill calls `initialize_prompt_copilot`, then `set_prompt_copilot_enabled(enabled=true, confirm_config=true)` only after review. Editing the TOML later invalidates its confirmation; review and confirm it again before continued use.

## Configuration

A new schema 2 configuration is:

```toml
schema_version = 2
default_mode = "review"
automatic_enabled = true
context_char_budget = 6000
hook_context_char_budget = 2400
per_source_char_budget = 1000
max_sources = 8
max_scan_files = 500
max_file_bytes = 262144
max_prompt_chars = 16000
```

- `default_mode` accepts `quick`, `review`, or `strict`.
- `automatic_enabled` controls ordinary development messages only. Set it to `false` for opt-in use through leading `@pc` or the explicit Skill.
- The context budgets limit evidence volume; `hook_context_char_budget` cannot exceed `context_char_budget`, and `per_source_char_budget` cannot exceed it either.
- The scan and file limits are ceilings, not promises that every matching file will be read.

A low-interruption opt-in setup is:

```toml
schema_version = 2
default_mode = "quick"
automatic_enabled = false
context_char_budget = 6000
hook_context_char_budget = 2400
per_source_char_budget = 1000
max_sources = 8
max_scan_files = 500
max_file_bytes = 262144
max_prompt_chars = 16000
```

## Modes and controls

| Mode | Automatic behavior |
|---|---|
| `quick` | Incorporates reliable additions silently and continues the task in the same turn. |
| `review` | Shows a compact optimization summary, then continues the enhanced task in the same turn. |
| `strict` | Performs a tool-free preflight and waits for the user to adopt, reject, revise, or cancel. |

A leading, case-insensitive control token applies only to the current message:

```text
@pc Fix the session-renewal race in src/auth.py and add regression tests.
@npc Apply the already-approved typo fix without Prompt Copilot.
```

- `@pc` forces Prompt Copilot even when automatic detection does not match or `automatic_enabled=false`; it does not bypass Foundation, module, configuration-confirmation, or provider checks.
- `@npc` bypasses Prompt Copilot for that message.
- The token must be complete and at the start after optional whitespace. `@pcc` and a token in the middle of a message do not control routing.
- A bare `@pc` does not arm the next message.

## Start using it

The `$vibe-secretary-prompt-copilot` name is primarily for initialization or an explicitly requested full review. With `automatic_enabled=true`, ordinary development messages use the Hook and do not need to name the Skill. Use leading `@pc` or `@npc` only to force or bypass Prompt Copilot for the current message.

With the default `review` mode, send an ordinary development request:

```text
Replace the authentication cache without changing public API behavior, and add regression tests.
```

Prompt Copilot adds a short review summary and Codex continues the work in the same turn. For a deliberate full review without automatic execution, ask:

```text
Use $vibe-secretary-prompt-copilot in strict mode to review this task: replace the authentication cache without changing public API behavior.
```

An explicit Skill review prepares and validates a sourced optimization package, shows the original and optimized interpretations, and waits for the user to adopt, revise, use the original, or cancel.

## Evidence, provider, and privacy

Repository files inside the confirmed `.vibesecretaryignore` boundary are the baseline evidence. Process Hub is optional. Implementation Lens can provide static symbol evidence during an explicit review, but the automatic Hook defers Lens analysis to keep its latency bounded. Missing optional sources are reported as degradations rather than treated as hard dependencies.

Only `codex_host` is implemented. The current Codex conversation performs the reasoning; MCP tools perform deterministic collection and validation and do not make a separate model request. `byok` is a reserved, unavailable placeholder.

Prompt Copilot does not store original prompts, evidence excerpts, or optimized prompts in project state or logs. Hook audit records contain operational metadata such as mode, decision, and source count, and all reads stay inside the confirmed project scope.

## Main tools

`prompt_copilot_status`, `initialize_prompt_copilot`, `set_prompt_copilot_enabled`, `prepare_prompt_review`, and `validate_prompt_package`.