---
name: vibe-secretary-prompt-copilot
description: Improve a development Prompt with project-scoped evidence in Quick, Review, or Strict mode. Use when the user explicitly asks VibeSecretary Prompt Copilot to optimize, review, clarify, or prepare a coding task. Ordinary automatic Prompt handling is supplied by the bundled UserPromptSubmit Hook.
---

# VibeSecretary Prompt Copilot

Use the bundled deterministic tools and the current Codex conversation as the reasoning host. BYOK
is not implemented.

## Follow automatic Hook context first

When the current turn contains `VibeSecretary Prompt Copilot automatic context`, that context is the
automatic workflow contract. Do not call the explicit review tools again unless the context or user
requires more evidence. This exception never applies during the current Strict preflight turn.

- `QUICK EXECUTION`: silently incorporate reliable additions and execute in the same turn. Silent
  means no separate Prompt Copilot review; normal safety, permission, and tool communication still
  applies. Do not stop for optional questions.
- `REVIEW THEN EXECUTE`: start with a compact Prompt Copilot optimization summary, then execute
  the enhanced interpretation in the same turn without asking for adoption. Required safety
  clarifications and real tool permissions still apply.
- `STRICT PREFLIGHT GATE`: do not call tools, run commands, edit files, or start implementation in
  that turn. Show the complete preflight supported by the supplied bounded context and end with four
  conversational choices:
  1. adopt the optimized task and execute;
  2. reject optimization and execute the original task;
  3. provide feedback and continue optimizing;
  4. cancel.

Accept a number or natural-language answer on the next turn. These are product choices, not tool
permissions: never trigger or imitate an Allow/permission prompt for them. Do not silently replace,
rewrite, or resubmit the original Prompt.

## Start an explicit workflow

1. Preserve the user's original Prompt exactly.
2. Call `prompt_copilot_status` for the current consumer project.
3. State the returned absolute `project_root`.
4. If `foundation_effective_enabled=false`, stop and use `$vibe-secretary-foundation`.
5. If Prompt Copilot is not initialized, call `initialize_prompt_copilot` only when the user asked
   to set it up. Ask the user to review `.vibesecretary/prompt-copilot.toml`.
6. Enable only after explicit review by calling `set_prompt_copilot_enabled` with `enabled=true`
   and `confirm_config=true`.
7. If status reports `provider_mode=byok`, explain that BYOK is a reserved placeholder. There is no
   provider-setting MCP tool. Only after the user requests the change, edit the consumer project's
   `.vibesecretary/config.toml` `[provider]` table to `mode = "codex_host"`, `name = ""`, and
   `api_key_env = ""`; confirm status reports `provider_available=true`.

## Review an explicit Prompt

1. Resolve the user-selected mode; otherwise use the configured default.
2. Call `prepare_prompt_review` with the exact original Prompt and selected mode.
3. Treat `evidence` as bounded facts, `gaps` and `conflicts` as deterministic findings, and
   `host_instructions` as the output contract.
4. Never cite a path or document absent from the returned evidence.
5. For explicit Strict review, ask every required question and wait before finalizing.
6. Generate a package with exactly:
   - `summary`;
   - `optimized_prompt`;
   - `changes`;
   - `source_ids`;
   - `source_links`;
   - `assumptions`;
   - `acceptance_criteria`;
   - `verification_commands`, whose items contain exactly `command`, `source_ids`, and
     `suggested`;
   - `unresolved_questions`;
   - `answers`.
7. Call `validate_prompt_package` with the exact original Prompt, mode, and package. Correct every
   schema, intent, target, risk, provenance, and unanswered-required-question error.
8. Show the original Prompt, interpretation, gaps/conflicts, readable diff, optimized Prompt,
   evidence/assumptions, acceptance criteria, verification, and unresolved questions.
9. Ask whether to adopt, revise, use the original, or cancel. Execute only after the user chooses
   execution.

## Explicit mode behavior

- **Quick**: concise improvement with explicit safe assumptions; no optional-question interruption.
- **Review**: full analysis, evidence, questions, and diff.
- **Strict**: resolve every required question before finalizing, then offer the four conversational
  choices. There is no `strict_blocking` setting.

## Boundaries

- Respect `.vibesecretaryignore`; never reconstruct excluded content.
- Do not describe repository text search as a symbol graph or call-path analysis.
- Process Hub is optional. Report its absence or failure as a degradation.
- Implementation Lens is an optional evidence source for explicit review. Automatic Hook collection defers Lens analysis; report its absence, failure, or deferral as a degradation.
- Do not make model/API requests from MCP tools or claim BYOK works.
- Do not store original Prompts, excerpts, or optimized Prompts in logs or project state.
- Return structured tool errors with concise recovery steps; never expose tracebacks.
