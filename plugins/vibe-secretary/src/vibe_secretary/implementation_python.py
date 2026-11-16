"""Static Python analyzer for Implementation Lens."""

from __future__ import annotations

import ast
import hashlib
import io
import re
import tokenize
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Protocol

from vibe_secretary.implementation_models import (
    AnalysisDiagnostic,
    CodeEvidence,
    CodeNode,
    CodeReference,
    Confidence,
    FileAnalysis,
)

class LanguageAnalyzer(Protocol):
    """Boundary for future language-specific static analyzers."""

    language: str
    version: str
    suffixes: tuple[str, ...]

    def analyze(self, path: Path, relative: str, raw: bytes) -> FileAnalysis:
        """Return a cacheable analysis without executing consumer code."""


class PythonLanguageAdapter:
    """Standard-library AST implementation of the language analyzer boundary."""

    language = "python"
    version = "python-ast-1"
    suffixes = (".py",)

    def analyze(self, path: Path, relative: str, raw: bytes) -> FileAnalysis:
        return analyze_python_file(path, relative, raw)


ANALYZER_VERSION = "python-ast-1"
_ENTRY_DECORATORS = {"tool", "route", "get", "post", "put", "patch", "delete", "command", "callback"}
_READ_CALLS = {"get", "load", "read", "find", "fetch", "query", "select", "list"}
_WRITE_CALLS = {"save", "write", "create", "update", "delete", "insert", "remove", "commit"}
_WORDS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")


def module_name_for_path(relative: str) -> str:
    """Derive a stable import-like module name from one project-relative path."""

    parts = list(PurePosixPath(relative).with_suffix("").parts)
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or PurePosixPath(relative).stem


def node_id(relative: str, qualified_name: str) -> str:
    return f"python:{relative}:{qualified_name}"


def external_node_id(expression: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", expression).strip("-") or "unknown"
    return f"external:{normalized}"


def _expression(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return node.__class__.__name__


def _excerpt(lines: list[str], start: int, end: int) -> str:
    if start < 1 or start > len(lines):
        return ""
    selected = " ".join(line.strip() for line in lines[start - 1 : min(end, start + 2)])
    return re.sub(r"\s+", " ", selected).strip()[:240]


class _Visitor(ast.NodeVisitor):
    def __init__(self, relative: str, module: str, lines: list[str]) -> None:
        self.relative = relative
        self.module = module
        self.lines = lines
        self.nodes: list[CodeNode] = []
        self.references: list[CodeReference] = []
        self.scope: list[tuple[str, str, str]] = []
        self.module_id = node_id(relative, module)
        self.nodes.append(
            CodeNode(
                node_id=self.module_id,
                kind="module",
                language="python",
                label=module,
                qualified_name=module,
                path=relative,
                start_line=1,
                end_line=max(1, len(lines)),
                module=module,
                keywords=tuple(part for part in module.split(".") if part),
            )
        )

    @property
    def current_id(self) -> str:
        return self.scope[-1][1] if self.scope else self.module_id

    @property
    def current_qualname(self) -> str:
        return self.scope[-1][0] if self.scope else self.module

    def evidence(self, node: ast.AST, method: str) -> CodeEvidence:
        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start))
        return CodeEvidence(
            path=self.relative,
            start_line=start,
            end_line=end,
            method=method,
            excerpt=_excerpt(self.lines, start, end),
        )

    def _qualified(self, name: str) -> str:
        return f"{self.current_qualname}.{name}"

    def _add_symbol(self, node: ast.AST, name: str, kind: str, decorators: tuple[str, ...]) -> str:
        qualified = self._qualified(name)
        identifier = node_id(self.relative, qualified)
        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start))
        entrypoint = name == "main" or any(
            decorator.rsplit(".", 1)[-1].split("(", 1)[0] in _ENTRY_DECORATORS
            for decorator in decorators
        )
        keywords = tuple(dict.fromkeys(_WORDS.findall(" ".join((name, qualified, *decorators)))))
        parent_id = self.current_id
        self.nodes.append(
            CodeNode(
                node_id=identifier,
                kind=kind,
                language="python",
                label=name,
                qualified_name=qualified,
                path=self.relative,
                start_line=start,
                end_line=end,
                module=self.module,
                parent_id=parent_id,
                decorators=decorators,
                keywords=keywords,
                entrypoint=entrypoint,
            )
        )
        self.references.append(
            CodeReference(
                source_id=parent_id,
                kind="contains",
                expression=identifier,
                evidence=self.evidence(node, "ast_parent_scope"),
            )
        )
        for decorator in decorators:
            self.references.append(
                CodeReference(
                    source_id=external_node_id(decorator),
                    kind="registers",
                    expression=identifier,
                    evidence=self.evidence(node, "ast_decorator"),
                    detail=decorator,
                    confidence=Confidence.HEURISTIC,
                )
            )
        return identifier

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        decorators = tuple(_expression(item) for item in node.decorator_list)
        identifier = self._add_symbol(node, node.name, "class", decorators)
        qualified = self._qualified(node.name)
        self.scope.append((qualified, identifier, "class"))
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        decorators = tuple(_expression(item) for item in node.decorator_list)
        kind = "method" if self.scope and self.scope[-1][2] == "class" else "function"
        identifier = self._add_symbol(node, node.name, kind, decorators)
        qualified = self._qualified(node.name)
        self.scope.append((qualified, identifier, kind))
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.references.append(
                CodeReference(
                    source_id=self.current_id,
                    kind="imports",
                    expression=alias.name,
                    evidence=self.evidence(node, "ast_import"),
                    detail=f"{local}={alias.name}",
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        prefix = "." * node.level + (node.module or "")
        for alias in node.names:
            target = f"{prefix}.{alias.name}".strip(".")
            local = alias.asname or alias.name
            self.references.append(
                CodeReference(
                    source_id=self.current_id,
                    kind="imports",
                    expression=target,
                    evidence=self.evidence(node, "ast_import_from"),
                    detail=f"{local}={target}",
                )
            )

    def visit_Call(self, node: ast.Call) -> None:
        expression = _expression(node.func)
        evidence = self.evidence(node, "ast_call")
        self.references.append(
            CodeReference(
                source_id=self.current_id,
                kind="calls",
                expression=expression,
                evidence=evidence,
                confidence=Confidence.CERTAIN,
            )
        )
        call_name = expression.rsplit(".", 1)[-1].casefold()
        access_kind = "reads" if call_name in _READ_CALLS else "writes" if call_name in _WRITE_CALLS else ""
        if access_kind:
            self.references.append(
                CodeReference(
                    source_id=self.current_id,
                    kind=access_kind,
                    expression=expression,
                    evidence=evidence,
                    detail=f"heuristic_{access_kind}_call:{expression}",
                    confidence=Confidence.HEURISTIC,
                )
            )
        self.generic_visit(node)


def analyze_python_file(path: Path, relative: str, raw: bytes) -> FileAnalysis:
    """Analyze one Python source file without importing or executing it."""

    digest = hashlib.sha256(raw).hexdigest()
    module = module_name_for_path(relative)
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        text = raw.decode(encoding)
    except (SyntaxError, UnicodeDecodeError, LookupError):
        return FileAnalysis(
            path=relative,
            digest=digest,
            module=module,
            diagnostics=(
                AnalysisDiagnostic(
                    "python_encoding_error",
                    "Python source encoding could not be decoded safely and was skipped.",
                    relative,
                ),
            ),
        )
    lines = text.splitlines()
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return FileAnalysis(
            path=relative,
            digest=digest,
            module=module,
            diagnostics=(
                AnalysisDiagnostic(
                    "python_syntax_error",
                    "Python source could not be parsed statically.",
                    relative,
                    int(exc.lineno or 0),
                ),
            ),
        )
    visitor = _Visitor(relative, module, lines)
    visitor.visit(tree)
    return FileAnalysis(
        path=relative,
        digest=digest,
        module=module,
        nodes=tuple(visitor.nodes),
        references=tuple(visitor.references),
    )


def mark_entrypoint(node: CodeNode) -> CodeNode:
    return node if node.entrypoint else replace(node, entrypoint=True)

PYTHON_LANGUAGE_ADAPTER: LanguageAnalyzer = PythonLanguageAdapter()
