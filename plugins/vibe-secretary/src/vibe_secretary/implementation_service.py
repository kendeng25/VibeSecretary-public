"""Application service for Implementation Lens lifecycle and analysis tools."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from vibe_secretary.config import ProjectConfig, load_config, save_config
from vibe_secretary.errors import FoundationError, failure, internal_failure, success
from vibe_secretary.implementation_config import (
    ImplementationLensConfig,
    default_implementation_config,
    implementation_config_digest,
    load_implementation_config,
    save_implementation_config,
)
from vibe_secretary.implementation_models import Granularity, ImplementationIndex, ImplementationStory
from vibe_secretary.implementation_project_model import (
    inspect_project_model,
    update_project_model,
)
from vibe_secretary.implementation_render import render_html_graph, render_markdown
from vibe_secretary.implementation_repository import (
    build_implementation_index,
    compare_snapshots,
    select_implementation_view,
    snapshot_project,
)
from vibe_secretary.implementation_story import (
    expand_view_for_story,
    fallback_story,
    parse_story,
)
from vibe_secretary.paths import ProjectPaths, ensure_within_root
from vibe_secretary.scope import ScopePolicy

_SLUG_TOKEN = re.compile(r"[A-Za-z0-9]+")
_LENS_DIRECTIVE = re.compile(r"^\s*@lens(?=$|\s)", re.IGNORECASE)


class ImplementationLensService:
    """Provide independent static implementation-map workflows."""

    def directive_hook(self, project_root: str, prompt: str) -> dict[str, Any]:
        """Route only an explicit leading @lens token without analyzing the repository."""

        if not isinstance(prompt, str):
            return {}
        match = _LENS_DIRECTIVE.match(prompt)
        if match is None:
            return {}
        query = prompt[match.end() :].lstrip()
        status = self.status(project_root)
        data = status.get("data") if status.get("ok") else None
        active = bool(isinstance(data, dict) and data.get("effective_enabled"))
        lines = [
            "VibeSecretary Implementation Lens explicit @lens route:",
            "- Treat the leading @lens token as one-turn control metadata, not query content.",
            "- This is the only automatic Implementation Lens trigger. Do not send this message through Prompt Copilot.",
            "- Use $vibe-secretary-implementation-lens and only its prescribed MCP tools.",
            "- Inspect consumer code statically and read-only: do not edit, import, execute, test, build, format, or generate project code.",
            "- The only permitted analysis writes are the configured derived index, reusable project model, and paired Markdown/HTML reports.",
        ]
        if query:
            lines.append(f"- User implementation query: {query[:1200]}")
        else:
            lines.append(
                "- The query is empty. Ask the user for the implementation target and desired granularity before analysis."
            )
        if active:
            lines.append(
                "- Implementation Lens is active. Check status, inspect/update the reusable project model, then query and render the requested story."
            )
        else:
            diagnostics = data.get("diagnostics", []) if isinstance(data, dict) else []
            lines.append(
                "- Implementation Lens is not active. Do not analyze or initialize silently; report status and the explicit setup/reconfirmation step."
            )
            if isinstance(diagnostics, list) and diagnostics:
                lines.append("- Status diagnostics: " + "; ".join(str(item) for item in diagnostics[:3]))
        context = "\n".join(lines)
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context[:2200],
            }
        }

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

    def refresh(self, project_root: str = "") -> dict[str, Any]:
        return self._guard(lambda: self._refresh(ProjectPaths.from_value(project_root or None)))

    def inspect_model(self, project_root: str = "") -> dict[str, Any]:
        return self._guard(
            lambda: self._inspect_model(ProjectPaths.from_value(project_root or None))
        )

    def update_model(
        self,
        records: list[dict[str, Any]],
        coverage: str,
        covered_paths: list[str] | None = None,
        diagnostics: list[str] | None = None,
        expected_model_digest: str = "",
        confirm_replace_modified: bool = False,
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._update_model(
                ProjectPaths.from_value(project_root or None),
                records=records,
                coverage=coverage,
                covered_paths=covered_paths or [],
                diagnostics=diagnostics or [],
                expected_model_digest=expected_model_digest,
                confirm_replace_modified=confirm_replace_modified,
            )
        )

    def query(
        self,
        query: str,
        granularity: str = "",
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._query(
                ProjectPaths.from_value(project_root or None),
                query=query,
                granularity=granularity,
            )
        )

    def render(
        self,
        query: str,
        granularity: str = "",
        title: str = "",
        project_root: str = "",
        story: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._render(
                ProjectPaths.from_value(project_root or None),
                query=query,
                granularity=granularity,
                title=title,
                story=story,
            )
        )

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
    def _assert_config_in_scope(
        paths: ProjectPaths,
        project_config: ProjectConfig,
        policy: ScopePolicy,
    ) -> Path:
        path = paths.implementation_config_file(
            project_config.modules.implementation_lens.config_file
        )
        decision = policy.decide(path)
        if not decision.allowed:
            raise FoundationError(
                "implementation_config_outside_scope",
                "The configured Implementation Lens file is excluded by project scope.",
            )
        return path

    @classmethod
    def _configured_context(
        cls,
        paths: ProjectPaths,
        *,
        require_enabled: bool,
    ) -> tuple[ProjectConfig, ScopePolicy, ImplementationLensConfig, str]:
        project_config, policy = cls._foundation_context(paths)
        cls._assert_config_in_scope(paths, project_config, policy)
        config = load_implementation_config(paths, project_config)
        digest = implementation_config_digest(paths, project_config)
        module = project_config.modules.implementation_lens
        if require_enabled and (
            not module.enabled or not module.config_digest or module.config_digest != digest
        ):
            raise FoundationError(
                "implementation_lens_not_enabled",
                "Implementation Lens must be enabled with the current confirmed configuration.",
            )
        return project_config, policy, config, digest

    @classmethod
    def _status(cls, paths: ProjectPaths) -> dict[str, Any]:
        if not paths.config_file.is_file():
            return success(
                {
                    "project_root": str(paths.root),
                    "initialized": False,
                    "configured_enabled": False,
                    "effective_enabled": False,
                    "config_confirmed": False,
                    "trigger": "@lens",
                    "languages": ["python"],
                    "diagnostics": ["Enable the VibeSecretary foundation first."],
                }
            )
        project_config = load_config(paths)
        module = project_config.modules.implementation_lens
        config_path = paths.implementation_config_file(module.config_file)
        if not config_path.is_file():
            return success(
                {
                    "project_root": str(paths.root),
                    "initialized": False,
                    "configured_enabled": module.enabled,
                    "effective_enabled": False,
                    "config_confirmed": False,
                    "config_file": module.config_file,
                    "trigger": "@lens",
                    "languages": ["python"],
                    "diagnostics": ["Initialize Implementation Lens before enabling it."],
                }
            )
        policy = ScopePolicy(paths, project_config)
        decision = policy.decide(config_path)
        config = load_implementation_config(paths, project_config)
        digest = implementation_config_digest(paths, project_config)
        confirmed = bool(module.config_digest) and module.config_digest == digest
        effective = bool(
            policy.effective_enabled and decision.allowed and module.enabled and confirmed
        )
        diagnostics: list[str] = []
        if not policy.effective_enabled:
            diagnostics.append("Foundation scope is not effectively enabled.")
        if not decision.allowed:
            diagnostics.append("Implementation Lens config is excluded by project scope.")
        if not module.enabled:
            diagnostics.append("Implementation Lens is configured but disabled.")
        if module.enabled and not confirmed:
            diagnostics.append("Implementation Lens config changed after confirmation.")
        return success(
            {
                "project_root": str(paths.root),
                "initialized": True,
                "configured_enabled": module.enabled,
                "effective_enabled": effective,
                "config_confirmed": confirmed,
                "config_file": module.config_file,
                "trigger": "@lens",
                "languages": ["python"],
                "default_granularity": config.default_granularity.value,
                "output": {
                    "path": config.output_path,
                    "path_template": config.path_template,
                    "project_model_path": config.project_model_path,
                },
                "index_json": config.index_json,
                "diagnostics": diagnostics,
            }
        )

    @classmethod
    def _initialize(cls, paths: ProjectPaths) -> dict[str, Any]:
        project_config = load_config(paths)
        target = paths.implementation_config_file(
            project_config.modules.implementation_lens.config_file
        )
        created: list[str] = []
        preserved: list[str] = []
        relative = target.relative_to(paths.root).as_posix()
        if target.exists():
            preserved.append(relative)
        else:
            save_implementation_config(paths, project_config, default_implementation_config())
            created.append(relative)
        status = cls._status(paths)["data"]
        return success(
            {
                "project_root": str(paths.root),
                "created": created,
                "preserved": preserved,
                "configured_enabled": status["configured_enabled"],
                "effective_enabled": status["effective_enabled"],
                "next_step": "Review the Implementation Lens config, then enable with confirm_config=true.",
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
            updated = project_config.with_implementation_lens_enabled(False)
            save_config(paths, updated)
            return success(
                {
                    "project_root": str(paths.root),
                    "configured_enabled": False,
                    "effective_enabled": False,
                    "config_confirmed": bool(updated.modules.implementation_lens.config_digest),
                }
            )
        policy = ScopePolicy(paths, project_config)
        if not policy.effective_enabled:
            raise FoundationError(
                "foundation_not_enabled",
                "VibeSecretary foundation must be effectively enabled first.",
            )
        cls._assert_config_in_scope(paths, project_config, policy)
        load_implementation_config(paths, project_config)
        if not confirm_config:
            raise FoundationError(
                "implementation_config_confirmation_required",
                "Set confirm_config=true after reviewing the Implementation Lens configuration.",
            )
        digest = implementation_config_digest(paths, project_config)
        updated = project_config.with_implementation_lens_enabled(True, digest)
        save_config(paths, updated)
        return success(
            {
                "project_root": str(paths.root),
                "configured_enabled": True,
                "effective_enabled": True,
                "config_confirmed": True,
            }
        )

    @staticmethod
    def _granularity(value: str, config: ImplementationLensConfig) -> Granularity:
        if not value:
            return config.default_granularity
        if not isinstance(value, str):
            raise FoundationError(
                "invalid_implementation_granularity", "granularity must be a string."
            )
        try:
            return Granularity(value.casefold())
        except ValueError as exc:
            raise FoundationError(
                "invalid_implementation_granularity",
                "granularity must be 'module', 'symbol', or 'detail'.",
            ) from exc

    @classmethod
    def _refresh(cls, paths: ProjectPaths) -> dict[str, Any]:
        _, policy, config, digest = cls._configured_context(paths, require_enabled=True)
        index = build_implementation_index(
            paths, policy, config, digest, persist=True
        )
        return success(
            {
                "project_root": str(paths.root),
                "index_json": config.index_json,
                "index": index.to_dict(include_cache=False),
            }
        )

    @staticmethod
    def _evidence_package(index: ImplementationIndex) -> dict[str, Any]:
        payload = index.to_dict(include_cache=False)
        nodes = payload["nodes"]
        edges = payload["edges"]
        return {
            "stats": payload["stats"],
            "modules": [item for item in nodes if item["kind"] == "module"],
            "entrypoints": [item for item in nodes if item["entrypoint"]],
            "nodes": nodes,
            "edges": edges,
            "diagnostics": payload["diagnostics"],
            "coverage": "partial" if index.truncated else "complete",
        }

    @classmethod
    def _inspect_model(cls, paths: ProjectPaths) -> dict[str, Any]:
        _, policy, config, digest = cls._configured_context(paths, require_enabled=True)
        index = build_implementation_index(paths, policy, config, digest, persist=False)
        model = inspect_project_model(paths, policy, config, digest, index)
        return success(
            {
                "project_root": str(paths.root),
                "project_model": model,
                "evidence_package": cls._evidence_package(index),
                "read_only": True,
                "writes": [],
            }
        )

    @classmethod
    def _update_model(
        cls,
        paths: ProjectPaths,
        *,
        records: list[dict[str, Any]],
        coverage: str,
        covered_paths: list[str],
        diagnostics: list[str],
        expected_model_digest: str,
        confirm_replace_modified: bool,
    ) -> dict[str, Any]:
        _, policy, config, digest = cls._configured_context(paths, require_enabled=True)
        before = snapshot_project(paths, policy, config)
        index = build_implementation_index(paths, policy, config, digest, persist=True)
        manifest, written = update_project_model(
            paths,
            policy,
            config,
            digest,
            index,
            raw_records=records,
            coverage=coverage,
            covered_paths=covered_paths,
            diagnostics=diagnostics,
            expected_model_digest=expected_model_digest,
            confirm_replace_modified=confirm_replace_modified,
        )
        allowed_writes = tuple(dict.fromkeys((config.index_json, *written)))
        after = snapshot_project(paths, policy, config)
        read_only = compare_snapshots(before, after, allowed_writes)
        return success(
            {
                "project_root": str(paths.root),
                "project_model": {
                    "path": (
                        Path(config.output_path) / config.project_model_path
                    ).as_posix(),
                    "manifest": (
                        Path(config.output_path)
                        / config.project_model_path
                        / "manifest.json"
                    ).as_posix(),
                    "model_digest": manifest.model_digest,
                    "coverage": manifest.coverage.value,
                    "records": [item.to_dict() for item in manifest.records],
                    "covered_paths": list(manifest.covered_paths),
                    "diagnostics": list(manifest.diagnostics),
                },
                "writes": list(written),
                "read_only_check": read_only.to_dict(),
            }
        )

    @classmethod
    def _query(
        cls,
        paths: ProjectPaths,
        *,
        query: str,
        granularity: str,
    ) -> dict[str, Any]:
        _, policy, config, digest = cls._configured_context(paths, require_enabled=True)
        selected = cls._granularity(granularity, config)
        index = build_implementation_index(
            paths, policy, config, digest, persist=False
        )
        view = select_implementation_view(index, query, selected, config)
        model = inspect_project_model(paths, policy, config, digest, index)
        return success(
            {
                "project_root": str(paths.root),
                "view": view.to_dict(),
                "project_model": model,
                "index_stats": index.to_dict(include_cache=False)["stats"],
                "read_only": True,
                "writes": [],
            }
        )

    @staticmethod
    def _slug(value: str) -> str:
        tokens = _SLUG_TOKEN.findall(value.casefold())[:8]
        return "-".join(tokens)[:80] or "implementation-map"

    @classmethod
    def _output_targets(
        cls,
        paths: ProjectPaths,
        policy: ScopePolicy,
        config: ImplementationLensConfig,
        query: str,
        granularity: Granularity,
    ) -> tuple[Path, Path, str, str]:
        generated_at = datetime.now(UTC)
        timestamp = generated_at.strftime("%Y%m%dT%H%M%S%fZ")
        values = {
            "slug": cls._slug(query),
            "timestamp": timestamp,
            "granularity": granularity.value,
            "language": "python",
            "year": generated_at.strftime("%Y"),
            "month": generated_at.strftime("%m"),
            "day": generated_at.strftime("%d"),
        }
        rendered_md = config.path_template.format(**values, ext="md")
        rendered_html = config.path_template.format(**values, ext="html")
        root = ensure_within_root(paths.root, paths.root / config.output_path)
        model_root = ensure_within_root(root, root / config.project_model_path)
        markdown = ensure_within_root(root, root / Path(rendered_md))
        html = ensure_within_root(root, root / Path(rendered_html))
        for target in (markdown, html):
            if target == model_root or model_root in target.parents:
                raise FoundationError(
                    "implementation_output_inside_model",
                    "Query reports cannot be stored inside the reusable project-model directory.",
                )
            decision = policy.decide(target)
            if not decision.allowed:
                raise FoundationError(
                    "implementation_output_outside_scope",
                    "The configured Implementation Lens output is excluded by project scope.",
                )
            if target.exists():
                raise FoundationError(
                    "implementation_output_exists",
                    "Implementation Lens refuses to overwrite an existing report.",
                    {"path": decision.relative_path},
                )
        return (
            markdown,
            html,
            markdown.relative_to(paths.root).as_posix(),
            html.relative_to(paths.root).as_posix(),
        )

    @classmethod
    def _render(
        cls,
        paths: ProjectPaths,
        *,
        query: str,
        granularity: str,
        title: str,
        story: dict[str, Any] | None,
    ) -> dict[str, Any]:
        _, policy, config, digest = cls._configured_context(paths, require_enabled=True)
        selected = cls._granularity(granularity, config)
        if not isinstance(query, str) or not query.strip():
            raise FoundationError(
                "implementation_query_empty", "Implementation query cannot be empty."
            )
        before = snapshot_project(paths, policy, config)
        index = build_implementation_index(paths, policy, config, digest, persist=True)
        view = select_implementation_view(index, query, selected, config)
        report_title = title.strip() if isinstance(title, str) and title.strip() else query.strip()
        selected_story: ImplementationStory = (
            parse_story(
                story,
                index,
                config,
                query=query,
                granularity=selected,
                title=report_title,
            )
            if story is not None
            else fallback_story(view, title=report_title)
        )
        report_view = expand_view_for_story(view, index, selected_story)
        markdown_path, html_path, markdown_relative, html_relative = cls._output_targets(
            paths, policy, config, query, selected
        )
        model = inspect_project_model(paths, policy, config, digest, index)
        html_content = render_html_graph(
            title=report_title,
            view=report_view,
            html_path=html_path,
            project_root=paths.root,
            story=selected_story,
            project_model=model,
        )
        html_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with html_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(html_content)
        except FileExistsError as exc:
            raise FoundationError(
                "implementation_output_exists",
                "Implementation Lens refuses to overwrite an existing report.",
                {"path": html_relative},
            ) from exc
        allowed_writes = (config.index_json, markdown_relative, html_relative)
        after = snapshot_project(paths, policy, config)
        read_only = compare_snapshots(before, after, allowed_writes)
        markdown_content = render_markdown(
            title=report_title,
            view=report_view,
            read_only=read_only,
            markdown_path=markdown_path,
            html_path=html_path,
            project_root=paths.root,
            story=selected_story,
            project_model=model,
        )
        try:
            with markdown_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(markdown_content)
        except Exception:
            html_path.unlink(missing_ok=True)
            raise
        limitations = list(
            dict.fromkeys((*selected_story.limitations, *report_view.limitations))
        )
        return success(
            {
                "project_root": str(paths.root),
                "query": report_view.query,
                "granularity": report_view.granularity.value,
                "markdown": markdown_relative,
                "html": html_relative,
                "index_json": config.index_json,
                "story": selected_story.to_dict(),
                "storyboard": {
                    "stages": len(selected_story.stages),
                    "transitions": len(selected_story.transitions),
                    "fallback": selected_story.fallback,
                },
                "graph": {"nodes": len(report_view.nodes), "edges": len(report_view.edges)},
                "project_model": {
                    "status": model["status"],
                    "coverage": model["coverage"],
                    "path": model["path"],
                    "model_digest": model["model_digest"],
                    "update_required": model["update_required"],
                },
                "diagnostics": [item.to_dict() for item in report_view.diagnostics],
                "limitations": limitations,
                "read_only_check": read_only.to_dict(),
            }
        )
