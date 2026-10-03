---
name: vibe-secretary-implementation-lens
description: Explain a consumer Python implementation only when the current user message begins with the complete @lens token. Build or refresh an evidence-linked reusable project model, then generate a truthful minimum-sufficient module, symbol, or detail Story as paired Markdown and static-first offline HTML. Do not invoke for ordinary code questions, process documents, or Prompt optimization.
---

# VibeSecretary Implementation Lens

Use this Skill only when the current consumer-project message starts with the complete, case-insensitive
`@lens` token followed by whitespace or end of input. Treat `@lens` as control metadata. Never target
the installed Plugin source.

## Route and prepare

1. If the remaining query is empty, ask for the implementation concern before analyzing.
2. Call `implementation_lens_status` for the consumer-project root.
3. Stop with the returned recovery action when Foundation or Lens is not effectively enabled.
4. Never initialize or enable Lens silently. The user must review the editable
   `.vibesecretary/implementation-lens.toml` before explicit confirmation.
5. Select `module`, `symbol`, or `detail` from the request; otherwise use the confirmed default.

## Preserve the read-only contract

- Treat current source and indexed evidence as authoritative. Reusable model records are derived facts,
  not a replacement for source.
- Do not use shell commands, direct file tools, imports, project entrypoints, tests, builds, formatters,
  or generators during a normal Lens analysis.
- Use only `implementation_lens_status`, `inspect_implementation_model`,
  `update_implementation_model`, `query_implementation`, and `render_implementation_map`.
- Allow these tools to write only the configured rebuildable index, reusable project model, and paired
  reports. Never edit their managed files directly.
- Preserve `certain`, `heuristic`, static-analysis limitations, partial coverage, and read-only status.
  Never present reflection, runtime dispatch, or framework magic as statically proven.

## Maintain the reusable project model

1. Call `inspect_implementation_model` before the query. It returns repository-wide indexed evidence,
   freshness, reusable records, stale record IDs, changed paths, conflicts, and coverage.
2. On the first run, examine the available evidence broadly and describe the project's real stable
   structure independently of the requested display granularity. Record responsibilities, major
   components, flows, entrypoints, and external boundaries that the evidence supports.
3. When the index is truncated or meaningful areas remain unanalyzed, set coverage to `partial` and
   state covered paths and gaps. Do not delay the requested report to claim false completeness.
4. On later runs, reuse fresh records and replace records invalidated by changed evidence. Submit the
   full desired record set to `update_implementation_model`, not only the changed records.
5. Every record must cite existing node or edge IDs. Keep interpretations distinguishable from claims.
   Source conflicts always invalidate the record.
6. If managed records were edited outside Lens, do not overwrite them silently. Report the conflict;
   use explicit replacement confirmation only after the user chooses replacement.
7. Do not store current wording, chosen granularity, temporary titles, or speculative architecture in
   the reusable model.

## Build the current Story

1. Call `query_implementation` with the query and granularity. Use the project model for stable context
   and the current evidence package for verification.
2. Select the minimum sufficient structure that answers the question. Simplicity and truth matter more
   than node or edge coverage.
3. Preserve any branch, loop, failure path, boundary, or uncertainty whose omission would change the
   explanation. Summarize irrelevant or auxiliary evidence in `omitted_summary`.
4. Give every stage and transition stable semantic IDs, action-oriented titles, responsibilities,
   `fact` or `interpretation` basis, and existing evidence references. Do not invent unsupported stages.
5. Never target a fixed number of stages, symbols, operations, or transitions for any granularity.
   Limits are safety ceilings only.
6. Use the requested cognitive level:
   - `module`: explain actual system responsibilities and concept flow. If evidence shows a ReAct loop,
     express its real Think–Act–Observe behavior; never impose that template on another project.
   - `symbol`: trace the necessary components and key symbols from entry to result.
   - `detail`: expose the necessary evidence-level calls, registrations, branches, reads/writes, and
     external boundaries without expanding unrelated neighbors.
7. If evidence cannot support a reliable Story, render the smallest evidence fallback with an explicit
   diagnostic. Never fall back to a dense whole-repository graph.

## Render and report

1. Call `render_implementation_map` with the validated Story, original query, selected granularity, and
   a concise title.
2. Confirm both report paths remain under configured output and the result contains a
   `read_only_check`. Never relabel `failed` or `unverified` as passed.
3. Return the absolute project root, selected granularity, Story stage/transition counts, reusable model
   freshness/coverage, Markdown and HTML paths, read-only result, and the most important limitation.
4. Describe HTML as a static-first semantic storyboard with native expandable evidence, not as a
   complete call graph. Do not duplicate the full report in chat.
