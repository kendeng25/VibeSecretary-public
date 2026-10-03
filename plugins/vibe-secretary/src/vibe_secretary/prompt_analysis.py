"""Deterministic intent, risk, gap, and suggestion analysis for Prompt Copilot."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from vibe_secretary.errors import FoundationError
from vibe_secretary.prompt_models import (
    PromptFinding,
    PromptIntent,
    PromptMode,
    PromptQuestion,
)

_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,}|[\u4e00-\u9fff]{2,}")
_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/]|\.?\.?[\\/])?[A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_.-]+)+"
)
_CONTROL_DIRECTIVE_PATTERN = re.compile(
    r"^\s*@(?P<directive>npc|pc)(?=$|\s)",
    re.IGNORECASE,
)
_ACTIONS = {
    "implement": (
        "implement", "add", "create", "build", "实现", "实施", "新增", "添加", "开发", "构建",
    ),
    "fix": ("fix", "bug", "repair", "修复", "排查", "解决"),
    "refactor": ("refactor", "rename", "move", "重构", "重命名", "迁移"),
    "test": ("test", "verify", "validate", "测试", "验证", "验收"),
    "document": ("document", "readme", "docs", "文档", "说明"),
    "inspect": ("inspect", "review", "analyze", "explain", "查看", "审查", "分析", "解释"),
}
_DEVELOPMENT_MARKERS = tuple(word for words in _ACTIONS.values() for word in words) + (
    "code",
    "file",
    "module",
    "api",
    "cli",
    "代码",
    "文件",
    "模块",
    "接口",
    "项目",
)
_STOPWORDS = {
    "please", "this", "that", "with", "from", "into", "current", "project",
    "帮我", "一下", "当前", "这个", "项目", "进行", "需要", "暂时", "实现",
}
_DESTRUCTIVE = ("delete", "remove", "drop", "reset", "overwrite", "删除", "移除", "清空", "覆盖")
_SECURITY = ("auth", "token", "secret", "password", "permission", "安全", "认证", "密钥", "密码", "权限")
_DEPENDENCY = ("dependency", "package", "pip", "npm", "upgrade", "依赖", "升级", "安装")
_ACCEPTANCE = ("acceptance", "done when", "must pass", "verify", "test", "验收", "通过", "验证", "测试")
_SCOPE = ("scope", "only", "file", "module", "directory", "范围", "仅", "文件", "模块", "目录")
_CONFIRMATION = ("confirm", "confirmed", "backup", "确认", "已备份", "同意")


class PromptDirective(str, Enum):
    """Deterministic one-turn control applied before automatic classification."""

    AUTOMATIC = "automatic"
    FORCE = "force"
    BYPASS = "bypass"


def parse_prompt_directive(prompt: str) -> tuple[PromptDirective, str]:
    """Return a leading control directive and the task text that follows it."""

    match = _CONTROL_DIRECTIVE_PATTERN.match(prompt)
    if match is None:
        return PromptDirective.AUTOMATIC, prompt
    directive = (
        PromptDirective.FORCE
        if match.group("directive").casefold() == "pc"
        else PromptDirective.BYPASS
    )
    return directive, prompt[match.end():].lstrip()


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(marker.casefold() in folded for marker in markers)


def analyze_intent(prompt: str, max_prompt_chars: int) -> PromptIntent:
    """Parse a bounded prompt into deterministic, explainable features."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise FoundationError("prompt_empty", "Prompt cannot be empty.")
    if "\x00" in prompt:
        raise FoundationError("prompt_invalid", "Prompt cannot contain NUL characters.")
    if len(prompt) > max_prompt_chars:
        raise FoundationError(
            "prompt_too_large",
            f"Prompt exceeds the configured {max_prompt_chars}-character limit.",
        )

    folded = prompt.casefold()
    action = "unspecified"
    for candidate, markers in _ACTIONS.items():
        if any(marker.casefold() in folded for marker in markers):
            action = candidate
            break

    targets = tuple(dict.fromkeys(match.group(0).replace("\\", "/") for match in _PATH_PATTERN.finditer(prompt)))
    raw_keywords = [token.casefold() for token in _TOKEN_PATTERN.findall(prompt)]
    keywords = tuple(
        dict.fromkeys(
            token for token in raw_keywords
            if token not in _STOPWORDS and len(token) > 1
        )
    )[:20]

    risks: list[str] = []
    if _contains(prompt, _DESTRUCTIVE):
        risks.append("destructive_change")
    if _contains(prompt, _SECURITY):
        risks.append("security_sensitive")
    if _contains(prompt, _DEPENDENCY):
        risks.append("dependency_change")

    development_request = _contains(prompt, _DEVELOPMENT_MARKERS) or bool(targets)
    return PromptIntent(
        action=action,
        targets=targets,
        keywords=keywords,
        risk_flags=tuple(risks),
        development_request=development_request,
    )


def analyze_gaps(
    prompt: str,
    intent: PromptIntent,
    mode: PromptMode,
) -> tuple[tuple[PromptFinding, ...], tuple[PromptQuestion, ...]]:
    """Find missing task-contract elements without using model inference."""

    strict = mode is PromptMode.STRICT
    quick = mode is PromptMode.QUICK
    gaps: list[PromptFinding] = []
    questions: list[PromptQuestion] = []

    if intent.action == "unspecified":
        gaps.append(PromptFinding("missing_action", "The requested action is not explicit.", "warning", strict))
        if not quick:
            questions.append(
                PromptQuestion("action", "What concrete change or investigation should Codex perform?", strict, "The action is ambiguous.")
            )

    has_scope = bool(intent.targets) or _contains(prompt, _SCOPE)
    if not has_scope:
        gaps.append(PromptFinding("missing_scope", "No concrete file, module, or boundary is stated.", "warning", strict))
        if not quick:
            questions.append(
                PromptQuestion("scope", "Which files, modules, or behaviors are in scope and out of scope?", strict, "A bounded scope reduces unintended changes.")
            )

    if not _contains(prompt, _ACCEPTANCE):
        blocking = strict and intent.action in {"implement", "fix", "refactor"}
        gaps.append(PromptFinding("missing_acceptance", "No explicit acceptance or verification condition was found.", "warning", blocking))
        if not quick:
            questions.append(
                PromptQuestion("acceptance", "What observable result and verification command define completion?", blocking, "Completion needs an auditable condition.")
            )

    if "destructive_change" in intent.risk_flags and not _contains(prompt, _CONFIRMATION):
        gaps.append(PromptFinding("missing_destructive_confirmation", "A destructive action appears unconfirmed.", "error", strict))
        if not quick:
            questions.append(
                PromptQuestion("destructive_confirmation", "Do you explicitly approve the destructive action, and is recovery available?", strict, "Destructive changes require explicit intent.")
            )

    return tuple(gaps), tuple(questions)


def acceptance_suggestions(intent: PromptIntent) -> tuple[str, ...]:
    suggestions = ["The requested behavior is observable from the stated user entry point."]
    if intent.action in {"implement", "fix", "refactor"}:
        suggestions.append("Relevant existing tests pass and focused regression coverage is added.")
    if "dependency_change" in intent.risk_flags:
        suggestions.append("Dependency metadata and exact version pins are updated consistently.")
    if "security_sensitive" in intent.risk_flags:
        suggestions.append("Sensitive values are not written to source, logs, or generated context.")
    suggestions.append("No files outside the confirmed scope are read or changed by VibeSecretary.")
    return tuple(suggestions)


def verification_suggestions(paths: tuple[str, ...]) -> tuple[str, ...]:
    suggestions = ["Run the project's documented test command from the repository root."]
    suffixes = {Path(path).suffix.casefold() for path in paths}
    if ".py" in suffixes or not suffixes:
        suggestions.append("Run the focused Python unit tests for affected modules.")
    suggestions.append("Review the final diff and confirm every change maps to an acceptance criterion.")
    return tuple(suggestions)
