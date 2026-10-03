"""Process Hub application service exposed through bundled MCP tools."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from vibe_secretary.config import ProjectConfig, load_config, save_config
from vibe_secretary.errors import FoundationError, failure, internal_failure, success
from vibe_secretary.paths import ProjectPaths, ensure_within_root
from vibe_secretary.process_config import (
    ProcessHubConfig,
    default_process_config,
    load_process_config,
    process_config_digest,
    save_process_config,
)
from vibe_secretary.process_models import ProcessDocument, ProcessScan
from vibe_secretary.process_repository import (
    MAX_PROCESS_DOCUMENT_BYTES,
    atomic_write_text,
    body_preview,
    build_reverse_relations,
    next_document_id,
    render_document_path,
    render_indexes,
    render_process_markdown,
    scan_process_documents,
    slugify,
    utc_today,
)
from vibe_secretary.scope import ScopePolicy
from vibe_secretary.service import FoundationService


class ProcessHubService:
    """Manage process documents inside one explicitly enabled consumer project."""

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

    def validate(self, project_root: str = "") -> dict[str, Any]:
        return self._guard(lambda: self._validate(ProjectPaths.from_value(project_root or None)))

    def scan(self, project_root: str = "") -> dict[str, Any]:
        return self._guard(lambda: self._scan(ProjectPaths.from_value(project_root or None)))

    def query(
        self,
        project_root: str = "",
        collection: str = "",
        document_type: str = "",
        status: str = "",
        stage: str = "",
        task: str = "",
        tag: str = "",
        text: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._query(
                ProjectPaths.from_value(project_root or None),
                collection=collection,
                document_type=document_type,
                status=status,
                stage=stage,
                task=task,
                tag=tag,
                text=text,
                limit=limit,
            )
        )

    def get_document(
        self,
        document_id: str,
        include_body: bool = True,
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._get_document(
                ProjectPaths.from_value(project_root or None),
                document_id=document_id,
                include_body=include_body,
            )
        )

    def preview_document(
        self,
        collection: str,
        title: str,
        body: str = "",
        stage: str = "",
        task: str = "",
        status: str = "",
        tags: list[str] | None = None,
        relates_to: list[str] | None = None,
        slug: str = "",
        document_id: str = "",
        metadata: dict[str, Any] | None = None,
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: success(
                self._prepare_document(
                    ProjectPaths.from_value(project_root or None),
                    collection_id=collection,
                    title=title,
                    body=body,
                    stage=stage,
                    task=task,
                    status=status,
                    tags=tags or [],
                    relates_to=relates_to or [],
                    slug=slug,
                    document_id=document_id,
                    extra_metadata=metadata or {},
                )
            )
        )

    def create_document(
        self,
        collection: str,
        title: str,
        body: str = "",
        stage: str = "",
        task: str = "",
        status: str = "",
        tags: list[str] | None = None,
        relates_to: list[str] | None = None,
        slug: str = "",
        document_id: str = "",
        metadata: dict[str, Any] | None = None,
        apply: bool = False,
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._create_document(
                ProjectPaths.from_value(project_root or None),
                collection_id=collection,
                title=title,
                body=body,
                stage=stage,
                task=task,
                status=status,
                tags=tags or [],
                relates_to=relates_to or [],
                slug=slug,
                document_id=document_id,
                extra_metadata=metadata or {},
                apply=apply,
            )
        )

    def transition_document(
        self,
        document_id: str,
        new_status: str,
        apply: bool = False,
        project_root: str = "",
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._transition_document(
                ProjectPaths.from_value(project_root or None),
                document_id=document_id,
                new_status=new_status,
                apply=apply,
            )
        )

    def organize(self, apply: bool = False, project_root: str = "") -> dict[str, Any]:
        return self._guard(
            lambda: self._organize(
                ProjectPaths.from_value(project_root or None),
                apply=apply,
            )
        )

    def rebuild_index(self, apply: bool = False, project_root: str = "") -> dict[str, Any]:
        return self._guard(
            lambda: self._rebuild_index(
                ProjectPaths.from_value(project_root or None),
                apply=apply,
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
                "Enable VibeSecretary and confirm its read scope before using Process Hub.",
            )
        return project_config, policy

    @staticmethod
    def _assert_config_in_scope(
        config: ProcessHubConfig,
        policy: ScopePolicy,
    ) -> None:
        denied = [
            candidate
            for candidate in (config.index_json, config.index_markdown)
            if not policy.decide(candidate).allowed
        ]
        for collection in config.collections:
            root_allowed = policy.decide(collection.path).allowed
            child_allowed = policy.decide(
                f"{collection.path}/.vibesecretary-scope-probe"
            ).allowed
            if not root_allowed or not child_allowed:
                denied.append(collection.path)
        if denied:
            raise FoundationError(
                "process_path_outside_scope",
                "Process Hub configuration contains paths excluded by the confirmed read scope.",
                {"paths": denied},
            )

    @classmethod
    def _configured_context(
        cls,
        paths: ProjectPaths,
        *,
        require_enabled: bool,
    ) -> tuple[ProjectConfig, ProcessHubConfig, ScopePolicy, str]:
        project_config, policy = cls._foundation_context(paths)
        process_config = load_process_config(paths, project_config)
        cls._assert_config_in_scope(process_config, policy)
        for collection in process_config.collections:
            collection_path = ensure_within_root(paths.root, paths.root / collection.path)
            if collection_path.exists() and not collection_path.is_dir():
                raise FoundationError(
                    "collection_not_directory",
                    "A configured collection path exists but is not a directory.",
                    {"path": collection.path},
                )
        digest = process_config_digest(paths, project_config)
        module = project_config.modules.process_hub
        confirmed = bool(module.config_digest) and module.config_digest == digest
        if require_enabled and (not module.enabled or not confirmed):
            raise FoundationError(
                "process_hub_not_enabled",
                "Process Hub is disabled or its configuration changed after confirmation.",
            )
        return project_config, process_config, policy, digest

    @classmethod
    def _status(cls, paths: ProjectPaths) -> dict[str, Any]:
        foundation = FoundationService().project_status(str(paths.root))
        foundation_data = foundation.get("data") if foundation.get("ok") else None
        foundation_enabled = bool(
            isinstance(foundation_data, dict) and foundation_data.get("effective_enabled")
        )
        diagnostics: list[str] = []
        if not foundation_enabled:
            diagnostics.append("Enable the VibeSecretary foundation before using Process Hub.")
        try:
            project_config = load_config(paths)
        except FoundationError:
            return success(
                {
                    "project_root": str(paths.root),
                    "initialized": False,
                    "configured_enabled": False,
                    "effective_enabled": False,
                    "config_confirmed": False,
                    "collections": [],
                    "diagnostics": diagnostics,
                }
            )
        module = project_config.modules.process_hub
        config_path = paths.process_config_file(module.config_file)
        if not config_path.is_file():
            diagnostics.append("Run initialize_process_hub to create the module configuration.")
            return success(
                {
                    "project_root": str(paths.root),
                    "initialized": False,
                    "configured_enabled": module.enabled,
                    "effective_enabled": False,
                    "config_file": module.config_file,
                    "config_confirmed": False,
                    "collections": [],
                    "diagnostics": diagnostics,
                }
            )
        try:
            process_config = load_process_config(paths, project_config)
            digest = process_config_digest(paths, project_config)
            confirmed = bool(module.config_digest) and module.config_digest == digest
            policy = ScopePolicy(paths, project_config)
            cls._assert_config_in_scope(process_config, policy)
        except FoundationError as exc:
            diagnostics.append(exc.message)
            return success(
                {
                    "project_root": str(paths.root),
                    "initialized": True,
                    "configured_enabled": module.enabled,
                    "effective_enabled": False,
                    "config_file": module.config_file,
                    "config_confirmed": False,
                    "collections": [],
                    "diagnostics": diagnostics,
                }
            )
        if not confirmed:
            diagnostics.append("Review and confirm the Process Hub configuration before enabling it.")
        if not module.enabled:
            diagnostics.append("Process Hub is configured but disabled.")
        return success(
            {
                "project_root": str(paths.root),
                "initialized": True,
                "configured_enabled": module.enabled,
                "effective_enabled": foundation_enabled and module.enabled and confirmed,
                "config_file": module.config_file,
                "config_confirmed": confirmed,
                "collections": [collection.to_dict() for collection in process_config.collections],
                "index_json": process_config.index_json,
                "index_markdown": process_config.index_markdown,
                "diagnostics": diagnostics,
            }
        )

    @classmethod
    def _initialize(cls, paths: ProjectPaths) -> dict[str, Any]:
        project_config, policy = cls._foundation_context(paths)
        config_path = paths.process_config_file(project_config.modules.process_hub.config_file)
        created: list[str] = []
        preserved: list[str] = []
        config_created = False
        if config_path.exists():
            preserved.append(config_path.relative_to(paths.root).as_posix())
            process_config = load_process_config(paths, project_config)
        else:
            process_config = default_process_config()
            cls._assert_config_in_scope(process_config, policy)
            save_process_config(paths, project_config, process_config)
            created.append(config_path.relative_to(paths.root).as_posix())
            config_created = True
        cls._assert_config_in_scope(process_config, policy)
        for collection in process_config.collections:
            target = ensure_within_root(paths.root, paths.root / collection.path)
            if target.exists():
                if not target.is_dir():
                    raise FoundationError(
                        "collection_not_directory",
                        "A configured collection path exists but is not a directory.",
                        {"path": collection.path},
                    )
                preserved.append(collection.path)
            else:
                target.mkdir(parents=True, exist_ok=False)
                created.append(collection.path)
        updated_project_config = (
            project_config.with_process_hub_enabled(False, config_digest="")
            if config_created
            else project_config
        )
        save_config(paths, updated_project_config)
        digest = process_config_digest(paths, updated_project_config)
        module = updated_project_config.modules.process_hub
        confirmed = bool(module.config_digest) and module.config_digest == digest
        effective = module.enabled and confirmed
        return success(
            {
                "project_root": str(paths.root),
                "created": created,
                "preserved": preserved,
                "configured_enabled": module.enabled,
                "effective_enabled": effective,
                "config_file": config_path.relative_to(paths.root).as_posix(),
                "next_step": "Review process-hub.toml, validate it, then enable with confirm_config=true.",
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
        if not enabled:
            project_config, _ = cls._foundation_context(paths)
            updated = project_config.with_process_hub_enabled(False)
            save_config(paths, updated)
            return success(
                {
                    "project_root": str(paths.root),
                    "configured_enabled": False,
                    "effective_enabled": False,
                    "config_confirmed": bool(updated.modules.process_hub.config_digest),
                    "collection_count": 0,
                }
            )
        project_config, process_config, policy, digest = cls._configured_context(
            paths,
            require_enabled=False,
        )
        if not confirm_config:
            raise FoundationError(
                "process_config_confirmation_required",
                "Set confirm_config=true after reviewing process-hub.toml.",
            )
        cls._assert_config_in_scope(process_config, policy)
        updated = project_config.with_process_hub_enabled(
            True,
            config_digest=digest,
        )
        save_config(paths, updated)
        return success(
            {
                "project_root": str(paths.root),
                "configured_enabled": True,
                "effective_enabled": True,
                "config_confirmed": bool(digest),
                "collection_count": len(process_config.collections),
            }
        )

    @classmethod
    def _validate(cls, paths: ProjectPaths) -> dict[str, Any]:
        project_config, process_config, policy, digest = cls._configured_context(
            paths,
            require_enabled=False,
        )
        scan = scan_process_documents(paths, process_config, policy)
        module = project_config.modules.process_hub
        return success(
            {
                "project_root": str(paths.root),
                "config_valid": True,
                "config_confirmed": bool(module.config_digest) and module.config_digest == digest,
                "config_digest": digest,
                "collections": [collection.to_dict() for collection in process_config.collections],
                **scan.to_dict(),
            }
        )

    @classmethod
    def _scan(cls, paths: ProjectPaths) -> dict[str, Any]:
        _, config, policy, _ = cls._configured_context(paths, require_enabled=True)
        scan = scan_process_documents(paths, config, policy)
        return success({"project_root": str(paths.root), **scan.to_dict()})

    @classmethod
    def _active_scan(
        cls,
        paths: ProjectPaths,
    ) -> tuple[ProcessHubConfig, ScopePolicy, ProcessScan]:
        _, config, policy, _ = cls._configured_context(paths, require_enabled=True)
        return config, policy, scan_process_documents(paths, config, policy)

    @staticmethod
    def _find_unique(scan: ProcessScan, document_id: str) -> ProcessDocument:
        matches = [document for document in scan.documents if document.document_id == document_id]
        if not matches:
            raise FoundationError("document_not_found", f"Process document not found: {document_id}.")
        if len(matches) > 1:
            raise FoundationError(
                "duplicate_document_id",
                "Cannot select a process document because its id is duplicated.",
                {"document_id": document_id, "paths": [item.relative_path for item in matches]},
            )
        document = matches[0]
        if not document.managed or document.metadata is None:
            raise FoundationError("document_unmanaged", "The selected process document is unmanaged.")
        return document

    @classmethod
    def _query(
        cls,
        paths: ProjectPaths,
        *,
        collection: str,
        document_type: str,
        status: str,
        stage: str,
        task: str,
        tag: str,
        text: str,
        limit: int,
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or limit < 1 or limit > 100:
            raise FoundationError("invalid_query_limit", "Query limit must be between 1 and 100.")
        _, _, scan = cls._active_scan(paths)
        needle = text.casefold().strip()
        results: list[dict[str, Any]] = []
        for document in scan.documents:
            summary = document.summary()
            if collection and summary["collection"] != collection:
                continue
            if document_type and summary["type"] != document_type:
                continue
            if status and summary["status"] != status:
                continue
            if stage and summary["stage"] != stage:
                continue
            if task and summary["task"] != task:
                continue
            if tag and tag not in summary["tags"]:
                continue
            haystack = "\n".join(
                [summary["id"], summary["title"], summary["path"], document.body]
            ).casefold()
            if needle and needle not in haystack:
                continue
            results.append(summary)
            if len(results) >= limit:
                break
        return success(
            {
                "project_root": str(paths.root),
                "result_count": len(results),
                "results": results,
            }
        )

    @classmethod
    def _get_document(
        cls,
        paths: ProjectPaths,
        *,
        document_id: str,
        include_body: bool,
    ) -> dict[str, Any]:
        _, _, scan = cls._active_scan(paths)
        document = cls._find_unique(scan, document_id)
        result = body_preview(document, include_body)
        result["referenced_by"] = build_reverse_relations(scan).get(document_id, [])
        result["issues"] = [issue.to_dict() for issue in document.issues]
        return success({"project_root": str(paths.root), "document": result})

    @classmethod
    def _prepare_document(
        cls,
        paths: ProjectPaths,
        *,
        collection_id: str,
        title: str,
        body: str,
        stage: str,
        task: str,
        status: str,
        tags: list[str],
        relates_to: list[str],
        slug: str,
        document_id: str,
        extra_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not title.strip():
            raise FoundationError("invalid_document_title", "Process document title cannot be empty.")
        if len(body.encode("utf-8")) > MAX_PROCESS_DOCUMENT_BYTES:
            raise FoundationError("document_too_large", "Process document exceeds the 2 MiB limit.")
        if not all(isinstance(item, str) and item for item in tags + relates_to):
            raise FoundationError(
                "invalid_document_metadata",
                "tags and relates_to must contain non-empty strings.",
            )
        config, policy, scan = cls._active_scan(paths)
        collection = config.collection(collection_id)
        selected_id = document_id or next_document_id(scan, collection)
        if not re.fullmatch(rf"{re.escape(collection.id_prefix)}-[0-9]{{4,}}", selected_id):
            raise FoundationError(
                "invalid_document_id",
                "Document id must match the collection id_prefix and numeric format.",
                {"document_id": selected_id},
            )
        if any(document.document_id == selected_id for document in scan.documents):
            raise FoundationError(
                "document_id_exists",
                "A process document already uses the requested id.",
                {"document_id": selected_id},
            )
        selected_status = status or collection.initial_status
        if selected_status not in collection.statuses:
            raise FoundationError(
                "invalid_document_status",
                "Requested status is not allowed by the collection lifecycle.",
                {"status": selected_status},
            )
        known_ids = {document.document_id for document in scan.documents if document.document_id}
        unknown_relations = sorted(set(relates_to) - known_ids)
        if unknown_relations:
            raise FoundationError(
                "unknown_relation_target",
                "Cannot create a relation to an unknown process document.",
                {"document_ids": unknown_relations},
            )
        today = utc_today()
        metadata: dict[str, Any] = {
            "id": selected_id,
            "type": collection.kind,
            "title": title.strip(),
            "status": selected_status,
            "stage": stage.strip(),
            "task": task.strip(),
            "created_at": today,
            "updated_at": today,
            "tags": list(dict.fromkeys(tags)),
            "relates_to": list(dict.fromkeys(relates_to)),
        }
        reserved = set(metadata) | {"slug"}
        reserved_overrides = sorted(reserved & set(extra_metadata))
        if reserved_overrides:
            raise FoundationError(
                "reserved_metadata_field",
                "Custom metadata cannot override Process Hub core fields.",
                {"fields": reserved_overrides},
            )
        if not _is_safe_metadata_value(extra_metadata):
            raise FoundationError(
                "invalid_custom_metadata",
                "Custom metadata must contain JSON-compatible values and string keys.",
            )
        metadata.update(extra_metadata)
        if slug.strip():
            metadata["slug"] = slugify(slug)
        missing_required = [
            field for field in collection.required_fields if metadata.get(field) in (None, "", [])
        ]
        if missing_required:
            raise FoundationError(
                "missing_required_field",
                "Required collection metadata is missing from the new document.",
                {"fields": missing_required},
            )
        target = render_document_path(
            paths,
            collection,
            metadata,
            explicit_slug=str(metadata.get("slug", "")),
        )
        decision = policy.decide(target)
        if not decision.allowed:
            raise FoundationError(
                "document_path_outside_scope",
                "The configured document target is outside the confirmed read scope.",
                {"path": decision.relative_path, "reason": decision.reason},
            )
        markdown = render_process_markdown(metadata, body)
        return {
            "project_root": str(paths.root),
            "collection": collection.id,
            "document_id": selected_id,
            "target_path": target.relative_to(paths.root).as_posix(),
            "metadata": metadata,
            "markdown_preview": markdown,
            "will_overwrite": target.exists(),
        }

    @classmethod
    def _create_document(cls, paths: ProjectPaths, *, apply: bool, **kwargs: Any) -> dict[str, Any]:
        prepared = cls._prepare_document(paths, **kwargs)
        if not apply:
            return success({**prepared, "applied": False})
        target = ensure_within_root(paths.root, paths.root / prepared["target_path"])
        atomic_write_text(target, prepared["markdown_preview"], overwrite=False)
        return success(
            {
                **prepared,
                "applied": True,
                "next_step": "Rebuild the Process Hub index after completing related changes.",
            }
        )

    @classmethod
    def _transition_document(
        cls,
        paths: ProjectPaths,
        *,
        document_id: str,
        new_status: str,
        apply: bool,
    ) -> dict[str, Any]:
        config, policy, scan = cls._active_scan(paths)
        document = cls._find_unique(scan, document_id)
        collection = config.collection(document.collection_id)
        if new_status not in collection.statuses:
            raise FoundationError(
                "invalid_document_status",
                "Requested status is not allowed by the collection lifecycle.",
                {"status": new_status, "allowed": list(collection.statuses)},
            )
        metadata = dict(document.metadata or {})
        old_status = str(metadata.get("status", ""))
        metadata["status"] = new_status
        metadata["updated_at"] = utc_today()
        markdown = render_process_markdown(metadata, document.body)
        decision = policy.decide(document.path)
        if not decision.allowed:
            raise FoundationError("document_path_outside_scope", "Document path is outside scope.")
        if apply:
            atomic_write_text(document.path, markdown, overwrite=True)
        return success(
            {
                "project_root": str(paths.root),
                "document_id": document_id,
                "path": document.relative_path,
                "old_status": old_status,
                "new_status": new_status,
                "terminal": new_status in collection.terminal_statuses,
                "markdown_preview": markdown,
                "applied": apply,
            }
        )

    @classmethod
    def _organize(cls, paths: ProjectPaths, *, apply: bool) -> dict[str, Any]:
        config, policy, scan = cls._active_scan(paths)
        moves: list[dict[str, str]] = []
        skipped: list[dict[str, Any]] = []
        destinations: set[Path] = set()
        for document in scan.documents:
            if not document.managed or document.metadata is None:
                continue
            blocking_issues = [
                issue
                for issue in document.issues
                if issue.severity == "error" and issue.code != "path_template_mismatch"
            ]
            if blocking_issues:
                skipped.append(
                    {
                        "document_id": document.document_id,
                        "path": document.relative_path,
                        "issue_codes": [issue.code for issue in blocking_issues],
                    }
                )
                continue
            collection = config.collection(document.collection_id)
            target = render_document_path(
                paths,
                collection,
                document.metadata,
                explicit_slug=str(document.metadata.get("slug", "")),
            )
            if target == document.path.resolve(strict=False):
                continue
            decision = policy.decide(target)
            if not decision.allowed:
                raise FoundationError(
                    "organization_target_outside_scope",
                    "An organization target is outside the confirmed read scope.",
                    {"path": str(target)},
                )
            if target in destinations or target.exists():
                raise FoundationError(
                    "organization_target_exists",
                    "Cannot organize documents because a target path already exists.",
                    {"path": target.relative_to(paths.root).as_posix()},
                )
            destinations.add(target)
            moves.append(
                {
                    "document_id": document.document_id,
                    "from": document.relative_path,
                    "to": target.relative_to(paths.root).as_posix(),
                }
            )
        if apply:
            for move in moves:
                source = ensure_within_root(paths.root, paths.root / move["from"])
                target = ensure_within_root(paths.root, paths.root / move["to"])
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
        return success(
            {
                "project_root": str(paths.root),
                "move_count": len(moves),
                "moves": moves,
                "skipped": skipped,
                "applied": apply,
                "unmanaged_files_unchanged": sum(not document.managed for document in scan.documents),
            }
        )

    @classmethod
    def _rebuild_index(cls, paths: ProjectPaths, *, apply: bool) -> dict[str, Any]:
        config, policy, scan = cls._active_scan(paths)
        json_content, markdown_content = render_indexes(paths, config, scan)
        targets = {
            "json": ensure_within_root(paths.root, paths.root / config.index_json),
            "markdown": ensure_within_root(paths.root, paths.root / config.index_markdown),
        }
        for target in targets.values():
            decision = policy.decide(target)
            if not decision.allowed:
                raise FoundationError(
                    "index_path_outside_scope",
                    "A Process Hub index path is outside the confirmed read scope.",
                )
        if apply:
            atomic_write_text(targets["json"], json_content, overwrite=True)
            atomic_write_text(targets["markdown"], markdown_content, overwrite=True)
        return success(
            {
                "project_root": str(paths.root),
                "json_path": config.index_json,
                "markdown_path": config.index_markdown,
                "document_count": len(scan.documents),
                "issue_count": len(scan.issues),
                "json_preview": json_content if not apply else "",
                "markdown_preview": markdown_content if not apply else "",
                "applied": apply,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        )


def _is_safe_metadata_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_safe_metadata_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and key and _is_safe_metadata_value(item)
            for key, item in value.items()
        )
    return False
