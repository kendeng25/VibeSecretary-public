"""Prompt Copilot lifecycle, preparation, and Host package validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from vibe_secretary.config import ProjectConfig, load_config, save_config
from vibe_secretary.errors import FoundationError, failure, internal_failure, success
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.prompt_analysis import (
    PromptDirective,
    acceptance_suggestions,
    analyze_gaps,
    analyze_intent,
    parse_prompt_directive,
    verification_suggestions,
)
from vibe_secretary.prompt_config import (
    PromptCopilotConfig,
    default_prompt_config,
    load_prompt_config,
    prompt_config_digest,
    save_prompt_config,
)
from vibe_secretary.prompt_context import ContextSource, collect_context
from vibe_secretary.prompt_models import (
    PromptContextPackage,
    PromptFinding,
    PromptMode,
)
from vibe_secretary.providers import ProviderMode
from vibe_secretary.scope import ScopePolicy


class PromptCopilotService:
    """Provide deterministic Prompt Copilot preparation for the current Codex host."""

    def __init__(self, sources: tuple[ContextSource, ...] | None = None) -> None:
        self.sources = sources

    def status(self, project_root: str = "") -> dict[str, Any]:
        return self._guard(lambda: self._status(ProjectPaths.from_value(project_root or None)))

    def initialize(self, project_root: str = "") -> dict[str, Any]:
        return self._guard(lambda: self._initialize(ProjectPaths.from_value(project_root or None)))

    def set_enabled(
        self,
        enabled: bool,
        confirm_config: bool = False,
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._set_enabled(
                ProjectPaths.from_value(project_root or None),
                enabled=enabled,
                confirm_config=confirm_config,
            )
        )

    def prepare_review(
        self,
        prompt: str,
        mode: str = "",
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: success(
                self._prepare(
                    ProjectPaths.from_value(project_root or None),
                    prompt=prompt,
                    mode=mode,
                    hook=False,
                ).to_dict()
            )
        )

    def validate_package(
        self,
        original_prompt: str,
        package: dict[str, Any],
        mode: str = "",
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._validate_package(
                ProjectPaths.from_value(project_root or None),
                original_prompt=original_prompt,
                package=package,
                mode=mode,
            )
        )

    def automatic_hook(self, project_root: str, prompt: str) -> dict[str, Any]:
        """Return a UserPromptSubmit response or remain silent on any recoverable failure."""

        try:
            directive, task_prompt = parse_prompt_directive(prompt)
            if directive is PromptDirective.BYPASS:
                return {}
            paths = ProjectPaths.from_value(project_root or None)
            project_config, policy, config = self._configured_context(paths, require_enabled=True)
            if directive is PromptDirective.AUTOMATIC and not config.automatic_enabled:
                return {}
            package = self._prepare_with_context(
                paths,
                project_config,
                policy,
                config,
                prompt=task_prompt,
                mode=config.default_mode,
                hook=True,
            )
            if (
                directive is PromptDirective.AUTOMATIC
                and not package.intent.development_request
            ):
                return {}
            context = self._render_hook_context(
                package,
                config.hook_context_char_budget,
                forced=directive is PromptDirective.FORCE,
            )
            if not context:
                return {}
            return {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            }
        except Exception:
            return {}

    @staticmethod
    def _guard(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return operation()
        except FoundationError as exc:
            return failure(exc)
        except Exception:
            return internal_failure()

    @staticmethod
    def _foundation_context(paths: ProjectPaths) -> tuple[ProjectConfig, ScopePolicy]:
        project_config = load_config(paths)
        policy = ScopePolicy(paths, project_config)
        if not policy.effective_enabled:
            raise FoundationError(
                "foundation_not_enabled",
                "VibeSecretary foundation must be effectively enabled first.",
            )
        return project_config, policy

    @staticmethod
    def _assert_codex_host(project_config: ProjectConfig) -> None:
        if project_config.provider.mode is not ProviderMode.CODEX_HOST:
            raise FoundationError(
                "provider_not_implemented",
                "Prompt Copilot currently supports codex_host only; BYOK is reserved but not implemented.",
            )

    @staticmethod
    def _assert_config_in_scope(
        paths: ProjectPaths,
        project_config: ProjectConfig,
        policy: ScopePolicy,
    ) -> Path:
        path = paths.prompt_config_file(project_config.modules.prompt_copilot.config_file)
        decision = policy.decide(path)
        if not decision.allowed:
            raise FoundationError(
                "prompt_config_outside_scope",
                "Prompt Copilot configuration is excluded by the confirmed read scope.",
                {"path": decision.relative_path, "reason": decision.reason},
            )
        return path

    @classmethod
    def _configured_context(
        cls,
        paths: ProjectPaths,
        *,
        require_enabled: bool,
    ) -> tuple[ProjectConfig, ScopePolicy, PromptCopilotConfig]:
        project_config, policy = cls._foundation_context(paths)
        cls._assert_codex_host(project_config)
        cls._assert_config_in_scope(paths, project_config, policy)
        config = load_prompt_config(paths, project_config)
        digest = prompt_config_digest(paths, project_config)
        module = project_config.modules.prompt_copilot
        confirmed = bool(module.config_digest) and module.config_digest == digest
        if require_enabled and (not module.enabled or not confirmed):
            raise FoundationError(
                "prompt_copilot_not_enabled",
                "Prompt Copilot must be enabled with its current configuration confirmed.",
            )
        return project_config, policy, config

    @classmethod
    def _status(cls, paths: ProjectPaths) -> dict[str, Any]:
        if not paths.config_file.is_file():
            return success(
                {
                    "project_root": str(paths.root),
                    "foundation_initialized": False,
                    "foundation_effective_enabled": False,
                    "initialized": False,
                    "configured_enabled": False,
                    "effective_enabled": False,
                    "config_file": ".vibesecretary/prompt-copilot.toml",
                    "config_confirmed": False,
                    "provider_mode": ProviderMode.CODEX_HOST.value,
                    "provider_available": True,
                    "byok_implemented": False,
                    "diagnostics": ["Initialize and enable VibeSecretary Foundation first."],
                }
            )

        project_config = load_config(paths)
        module = project_config.modules.prompt_copilot
        provider_available = project_config.provider.mode is ProviderMode.CODEX_HOST
        diagnostics: list[str] = []
        try:
            policy = ScopePolicy(paths, project_config)
            foundation_effective = policy.effective_enabled
        except FoundationError as exc:
            policy = None
            foundation_effective = False
            diagnostics.append(f"Foundation is inactive: {exc.code}.")

        if not foundation_effective:
            diagnostics.append("Enable Foundation and confirm its current read scope first.")
        path = paths.prompt_config_file(module.config_file)
        if not path.is_file():
            diagnostics.append("Run initialize_prompt_copilot after Foundation is active.")
            return success(
                {
                    "project_root": str(paths.root),
                    "foundation_initialized": True,
                    "foundation_effective_enabled": foundation_effective,
                    "initialized": False,
                    "configured_enabled": module.enabled,
                    "effective_enabled": False,
                    "config_file": module.config_file,
                    "config_confirmed": False,
                    "provider_mode": project_config.provider.mode.value,
                    "provider_available": provider_available,
                    "byok_implemented": False,
                    "diagnostics": diagnostics,
                }
            )

        if policy is None:
            return success(
                {
                    "project_root": str(paths.root),
                    "foundation_initialized": True,
                    "foundation_effective_enabled": False,
                    "initialized": True,
                    "configured_enabled": module.enabled,
                    "effective_enabled": False,
                    "config_file": module.config_file,
                    "config_confirmed": False,
                    "provider_mode": project_config.provider.mode.value,
                    "provider_available": provider_available,
                    "byok_implemented": False,
                    "diagnostics": diagnostics,
                }
            )

        cls._assert_config_in_scope(paths, project_config, policy)
        config = load_prompt_config(paths, project_config)
        digest = prompt_config_digest(paths, project_config)
        confirmed = bool(module.config_digest) and module.config_digest == digest
        effective = foundation_effective and module.enabled and confirmed and provider_available
        if not confirmed:
            diagnostics.append("Review and confirm the current Prompt Copilot configuration.")
        if not module.enabled:
            diagnostics.append("Prompt Copilot is configured but disabled.")
        if not provider_available:
            diagnostics.append("BYOK is a reserved placeholder and is not implemented.")
        return success(
            {
                "project_root": str(paths.root),
                "foundation_initialized": True,
                "foundation_effective_enabled": foundation_effective,
                "initialized": True,
                "configured_enabled": module.enabled,
                "effective_enabled": effective,
                "config_file": module.config_file,
                "config_confirmed": confirmed,
                "provider_mode": project_config.provider.mode.value,
                "provider_available": provider_available,
                "byok_implemented": False,
                "config": config.to_dict(),
                "diagnostics": diagnostics,
            }
        )
    @classmethod
    def _initialize(cls, paths: ProjectPaths) -> dict[str, Any]:
        project_config, policy = cls._foundation_context(paths)
        cls._assert_config_in_scope(paths, project_config, policy)
        path = paths.prompt_config_file(project_config.modules.prompt_copilot.config_file)
        created: list[str] = []
        preserved: list[str] = []
        relative = path.relative_to(paths.root).as_posix()
        if path.exists():
            preserved.append(relative)
        else:
            save_prompt_config(paths, project_config, default_prompt_config())
            created.append(relative)
        status = cls._status(paths)["data"]
        return success(
            {
                "project_root": str(paths.root),
                "created": created,
                "preserved": preserved,
                "configured_enabled": status["configured_enabled"],
                "effective_enabled": status["effective_enabled"],
                "next_step": "Review the Prompt Copilot config, then enable with confirm_config=true.",
            }
        )

    @classmethod
    def _set_enabled(
        cls,
        paths: ProjectPaths,
        *,
        enabled: bool,
        confirm_config: bool,
    ) -> dict[str, Any]:
        project_config = load_config(paths)
        if not enabled:
            updated = project_config.with_prompt_copilot_enabled(False)
            save_config(paths, updated)
            return success(
                {
                    "project_root": str(paths.root),
                    "configured_enabled": False,
                    "effective_enabled": False,
                    "config_confirmed": bool(updated.modules.prompt_copilot.config_digest),
                }
            )

        policy = ScopePolicy(paths, project_config)
        if not policy.effective_enabled:
            raise FoundationError(
                "foundation_not_enabled",
                "VibeSecretary foundation must be effectively enabled first.",
            )
        cls._assert_codex_host(project_config)
        cls._assert_config_in_scope(paths, project_config, policy)
        load_prompt_config(paths, project_config)
        if not confirm_config:
            raise FoundationError(
                "prompt_config_confirmation_required",
                "Set confirm_config=true after reviewing the Prompt Copilot configuration.",
            )
        digest = prompt_config_digest(paths, project_config)
        updated = project_config.with_prompt_copilot_enabled(True, digest)
        save_config(paths, updated)
        return success(
            {
                "project_root": str(paths.root),
                "configured_enabled": True,
                "effective_enabled": True,
                "config_confirmed": True,
            }
        )

    def _prepare(
        self,
        paths: ProjectPaths,
        *,
        prompt: str,
        mode: str,
        hook: bool,
    ) -> PromptContextPackage:
        project_config, policy, config = self._configured_context(paths, require_enabled=True)
        selected_mode = self._mode(mode, config)
        return self._prepare_with_context(
            paths,
            project_config,
            policy,
            config,
            prompt=prompt,
            mode=selected_mode,
            hook=hook,
        )

    @staticmethod
    def _mode(value: str, config: PromptCopilotConfig) -> PromptMode:
        if not value:
            return config.default_mode
        if not isinstance(value, str):
            raise FoundationError("invalid_prompt_mode", "Prompt mode must be a string.")
        try:
            return PromptMode(value.casefold())
        except ValueError as exc:
            raise FoundationError(
                "invalid_prompt_mode",
                "Prompt mode must be 'quick', 'review', or 'strict'.",
            ) from exc

    def _prepare_with_context(
        self,
        paths: ProjectPaths,
        project_config: ProjectConfig,
        policy: ScopePolicy,
        config: PromptCopilotConfig,
        *,
        prompt: str,
        mode: PromptMode,
        hook: bool,
    ) -> PromptContextPackage:
        intent = analyze_intent(prompt, config.max_prompt_chars)
        gaps, questions = analyze_gaps(prompt, intent, mode)
        source_results, evidence, budget = collect_context(
            paths=paths,
            project_config=project_config,
            policy=policy,
            config=config,
            intent=intent,
            hook=hook,
            sources=self.sources,
        )

        conflicts: list[PromptFinding] = []
        for target in intent.targets:
            decision = policy.decide(target)
            if not decision.allowed:
                conflicts.append(
                    PromptFinding(
                        code="target_outside_scope",
                        message="A requested target is outside the confirmed VibeSecretary scope.",
                        severity="error",
                        blocking=mode is PromptMode.STRICT,
                    )
                )

        constraint_markers = ("do not", "must not", "forbidden", "禁止", "不得", "不要", "不允许")
        for item in evidence:
            excerpt = item.excerpt.casefold()
            if not any(marker in excerpt for marker in constraint_markers):
                continue
            matching_terms = [
                keyword for keyword in intent.keywords
                if len(keyword) >= 4 and keyword in excerpt
            ]
            if matching_terms:
                conflicts.append(
                    PromptFinding(
                        code="potential_constraint_conflict",
                        message="A sourced project constraint may conflict with the requested change.",
                        severity="warning",
                        blocking=False,
                        source_ids=(item.source_id,),
                    )
                )
                break

        host_instructions = self._host_instructions(mode)
        return PromptContextPackage(
            original_prompt=prompt,
            mode=mode,
            intent=intent,
            evidence=evidence,
            gaps=gaps,
            conflicts=tuple(conflicts),
            questions=questions,
            acceptance_suggestions=acceptance_suggestions(intent),
            verification_suggestions=verification_suggestions(intent.targets),
            source_results=source_results,
            budget=budget,
            host_instructions=host_instructions,
        )

    @staticmethod
    def _host_instructions(mode: PromptMode) -> str:
        return (
            "Act as the Codex Host reasoning layer. Preserve the user's intent and never claim "
            "that evidence proves more than its excerpt. Produce a review with: summary, "
            "optimized_prompt, changes, source_ids, source_links, assumptions, acceptance_criteria, "
            "verification_commands, unresolved_questions, and answers. In strict mode, ask all "
            "required questions before finalizing optimized_prompt. Show a readable diff in the "
            f"conversation. Active mode: {mode.value}."
        )

    def _validate_package(
        self,
        paths: ProjectPaths,
        *,
        original_prompt: str,
        package: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        context = self._prepare(paths, prompt=original_prompt, mode=mode, hook=False)
        if not isinstance(package, dict):
            raise FoundationError("invalid_prompt_package", "Prompt package must be an object.")

        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        expected_fields = {
            "summary",
            "optimized_prompt",
            "changes",
            "source_ids",
            "source_links",
            "assumptions",
            "acceptance_criteria",
            "verification_commands",
            "unresolved_questions",
            "answers",
        }
        for field in sorted(expected_fields - set(package)):
            errors.append({"code": "missing_field", "field": field})
        for field in sorted(set(package) - expected_fields):
            errors.append({"code": "unexpected_field", "field": field})

        for field in ("summary", "optimized_prompt"):
            value = package.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append({"code": "invalid_field", "field": field})
        for field in (
            "changes",
            "source_ids",
            "assumptions",
            "acceptance_criteria",
            "unresolved_questions",
        ):
            value = package.get(field)
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                errors.append({"code": "invalid_field", "field": field})

        known_sources = {item.source_id for item in context.evidence}
        source_ids = package.get("source_ids")
        valid_source_ids = source_ids if isinstance(source_ids, list) else []
        for source_id in valid_source_ids:
            if isinstance(source_id, str) and source_id not in known_sources:
                errors.append({"code": "unknown_source_id", "field": source_id})
        if known_sources and not valid_source_ids:
            errors.append({"code": "missing_source_ids", "field": "source_ids"})

        source_links = package.get("source_links")
        linked_sources: set[str] = set()
        if not isinstance(source_links, dict):
            errors.append({"code": "invalid_field", "field": "source_links"})
        else:
            for claim, links in source_links.items():
                if not isinstance(claim, str) or not claim.strip() or not isinstance(links, list):
                    errors.append({"code": "invalid_source_link", "field": str(claim)})
                    continue
                if not links or any(not isinstance(item, str) for item in links):
                    errors.append({"code": "invalid_source_link", "field": claim})
                    continue
                for source_id in links:
                    linked_sources.add(source_id)
                    if source_id not in known_sources:
                        errors.append({"code": "unknown_source_id", "field": source_id})
            if known_sources and not source_links:
                errors.append({"code": "missing_source_links", "field": "source_links"})
        declared_sources = {item for item in valid_source_ids if isinstance(item, str)}
        if linked_sources - declared_sources:
            errors.append({"code": "undeclared_linked_source", "field": "source_links"})
        if declared_sources - linked_sources:
            warnings.append({"code": "unlinked_source_id", "field": "source_ids"})

        verification_commands = package.get("verification_commands")
        if not isinstance(verification_commands, list):
            errors.append({"code": "invalid_field", "field": "verification_commands"})
        else:
            verification_fields = {"command", "source_ids", "suggested"}
            for index, item in enumerate(verification_commands):
                field = f"verification_commands[{index}]"
                if not isinstance(item, dict) or set(item) != verification_fields:
                    errors.append({"code": "invalid_verification_command", "field": field})
                    continue
                command = item.get("command")
                command_sources = item.get("source_ids")
                suggested = item.get("suggested")
                if not isinstance(command, str) or not command.strip():
                    errors.append({"code": "invalid_verification_command", "field": field})
                if not isinstance(command_sources, list) or any(
                    not isinstance(source_id, str) for source_id in command_sources
                ):
                    errors.append({"code": "invalid_verification_command", "field": field})
                    command_sources = []
                if not isinstance(suggested, bool):
                    errors.append({"code": "invalid_verification_command", "field": field})
                for source_id in command_sources:
                    if source_id not in known_sources:
                        errors.append({"code": "unknown_source_id", "field": source_id})
                if suggested is False and not command_sources:
                    errors.append({"code": "unsupported_verification_command", "field": field})

        answers = package.get("answers")
        if not isinstance(answers, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in answers.items()
        ):
            errors.append({"code": "invalid_field", "field": "answers"})
            answers = {}
        for question in context.blocking_questions:
            answer = answers.get(question.question_id)
            if not isinstance(answer, str) or not answer.strip():
                errors.append({"code": "unanswered_required_question", "field": question.question_id})

        optimized = package.get("optimized_prompt", "")
        if isinstance(optimized, str) and len(optimized) > 50_000:
            errors.append({"code": "optimized_prompt_too_large", "field": "optimized_prompt"})
        if isinstance(optimized, str) and optimized.strip():
            folded = optimized.casefold().replace("\\", "/")
            if context.intent.action != "unspecified":
                action_markers = {
                    "implement": ("implement", "add", "create", "实现", "新增", "添加"),
                    "fix": ("fix", "repair", "修复", "解决"),
                    "refactor": ("refactor", "重构"),
                    "test": ("test", "verify", "测试", "验证"),
                    "document": ("document", "readme", "文档"),
                    "inspect": ("inspect", "review", "analyze", "查看", "审查", "分析"),
                }[context.intent.action]
                if not any(marker.casefold() in folded for marker in action_markers):
                    errors.append({"code": "intent_action_changed", "field": "optimized_prompt"})
            for target in context.intent.targets:
                if target.casefold().replace("\\", "/") not in folded:
                    errors.append({"code": "intent_target_lost", "field": target})
            optimized_intent = analyze_intent(optimized, 50_000)
            for risk in context.intent.risk_flags:
                if risk not in optimized_intent.risk_flags:
                    errors.append({"code": "intent_risk_lost", "field": risk})
            generic_keywords = {
                "implement", "create", "build", "change", "update", "please", "with",
                "tests", "test", "verify", "file", "module", "project",
            }
            meaningful = tuple(
                keyword for keyword in context.intent.keywords
                if keyword.isascii() and len(keyword) >= 4 and keyword not in generic_keywords
            )
            if meaningful and not any(keyword in folded for keyword in meaningful):
                errors.append({"code": "intent_keywords_lost", "field": "optimized_prompt"})

        return success(
            {
                "project_root": str(paths.root),
                "valid": not errors,
                "errors": errors,
                "warnings": warnings,
                "known_source_ids": sorted(known_sources),
                "required_question_ids": [
                    item.question_id for item in context.blocking_questions
                ],
            }
        )
    @staticmethod
    def _render_hook_context(
        package: PromptContextPackage,
        limit: int,
        *,
        forced: bool = False,
    ) -> str:
        protocols = {
            PromptMode.QUICK: (
                "- Automatic behavior: QUICK EXECUTION. Silently incorporate reliable evidence, "
                "constraints, acceptance criteria, and verification suggestions into the current "
                "task, then continue execution in this same turn. Silent means no separate Prompt "
                "Copilot review; normal safety, permission, and tool communication still applies. "
                "Do not stop for optional questions or claim the user prompt was rewritten."
            ),
            PromptMode.REVIEW: (
                "- Automatic behavior: REVIEW THEN EXECUTE. Start the response with a compact "
                "'Prompt Copilot optimization summary' of 1-4 bullets describing material scope, "
                "constraint, acceptance, or verification improvements. Then continue executing "
                "the enhanced task in this same turn without asking for adoption. Required safety "
                "clarifications and real tool permissions still apply. Do not claim the user "
                "prompt was rewritten or resubmitted."
            ),
            PromptMode.STRICT: (
                "- Automatic behavior: STRICT PREFLIGHT GATE. In this turn, do not call tools, "
                "execute commands, edit files, or begin task implementation. Show the interpreted "
                "intent, gaps and conflicts, a complete proposed optimized task from the supplied "
                "bounded context, evidence and assumptions, acceptance criteria, verification, "
                "and unresolved questions. End with four conversational choices and wait: "
                "1) adopt the optimized task and "
                "execute; 2) reject optimization and execute the original task; 3) provide "
                "feedback and continue optimizing; 4) cancel. Accept numbers or natural language "
                "on the next turn. Never use a tool-permission or Allow prompt for these choices."
            ),
        }
        lines = [
            "VibeSecretary Prompt Copilot automatic context "
            "(deterministic evidence; preserve the original prompt):",
            f"- Mode: {package.mode.value}; action: {package.intent.action}",
            protocols[package.mode],
        ]
        if forced:
            lines.append(
                "- Control directive: the leading @pc deterministically forced this one-turn "
                "workflow. Treat @pc as control metadata, not as task content."
            )
        if package.mode is PromptMode.STRICT and package.blocking_questions:
            lines.append("- Required questions:")
            for item in package.blocking_questions:
                lines.append(f"  - [{item.question_id}] {item.text}")
        lines.append(
            "- Evidence rule: treat excerpts as bounded evidence, make assumptions explicit, "
            "and never infer excluded content."
        )
        if package.gaps:
            lines.append("- Gaps: " + "; ".join(item.message for item in package.gaps[:3]))
            if len(package.gaps) > 3:
                lines.append(f"- Gaps omitted by item cap: {len(package.gaps) - 3}")
        if package.conflicts:
            lines.append("- Conflicts: " + "; ".join(item.message for item in package.conflicts[:2]))
            if len(package.conflicts) > 2:
                lines.append(f"- Conflicts omitted by item cap: {len(package.conflicts) - 2}")
        if package.acceptance_suggestions:
            lines.append(
                "- Acceptance suggestions: "
                + "; ".join(package.acceptance_suggestions[:2])
            )
        if package.verification_suggestions:
            lines.append(
                "- Verification suggestions: "
                + "; ".join(package.verification_suggestions[:2])
            )
        if package.evidence:
            lines.append(f"- Evidence ({len(package.evidence)} items):")
            for item in package.evidence:
                lines.append(f"  - [{item.source_id}] {item.path}: {item.excerpt}")
        text = "\n".join(lines)
        if len(text) <= limit:
            return text
        suffix = "\n- Context truncated to the configured Hook budget."
        return text[: max(0, limit - len(suffix))].rstrip() + suffix
