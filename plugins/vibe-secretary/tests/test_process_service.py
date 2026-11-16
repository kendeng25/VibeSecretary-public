from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.process_service import ProcessHubService  # noqa: E402
from vibe_secretary.config import load_config  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.process_config import (  # noqa: E402
    CollectionConfig,
    CORE_REQUIRED_FIELDS,
    ProcessHubConfig,
    save_process_config,
)
from vibe_secretary.service import FoundationService  # noqa: E402


class ProcessHubServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.foundation = FoundationService()
        self.process = ProcessHubService()

    def _foundation_project(self, root: str) -> None:
        self.assertTrue(self.foundation.initialize_project(root)["ok"])
        self.assertTrue(self.foundation.set_project_enabled(True, True, root)["ok"])

    def _active_project(self, root: str) -> None:
        self._foundation_project(root)
        self.assertTrue(self.process.initialize(root)["ok"])
        self.assertTrue(self.process.set_enabled(True, True, root)["ok"])

    def _create_plan(self, root: str, *, apply: bool = True) -> dict:
        return self.process.create_document(
            collection="plans",
            title="Configuration model",
            body="# Plan\n",
            stage="stage-2",
            task="task-1",
            tags=["config"],
            apply=apply,
            project_root=root,
        )

    def test_initialize_adopts_existing_directories_without_touching_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._foundation_project(temporary)
            legacy = Path(temporary) / "plans" / "legacy.md"
            legacy.parent.mkdir()
            legacy.write_text("legacy", encoding="utf-8")

            result = self.process.initialize(temporary)

            self.assertTrue(result["ok"])
            self.assertIn("plans", result["data"]["preserved"])
            self.assertEqual("legacy", legacy.read_text(encoding="utf-8"))
            self.assertFalse(result["data"]["effective_enabled"])

    def test_repeated_initialization_preserves_enabled_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)

            result = self.process.initialize(temporary)

            self.assertTrue(result["ok"])
            self.assertTrue(result["data"]["configured_enabled"])
            self.assertTrue(result["data"]["effective_enabled"])

    def test_enable_requires_confirmation_and_config_changes_invalidate_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._foundation_project(temporary)
            self.process.initialize(temporary)

            denied = self.process.set_enabled(True, False, temporary)
            enabled = self.process.set_enabled(True, True, temporary)
            config = Path(temporary) / ".vibesecretary" / "process-hub.toml"
            config.write_text(config.read_text(encoding="utf-8") + "\n# reviewed change\n", encoding="utf-8")
            changed = self.process.status(temporary)

            self.assertEqual("process_config_confirmation_required", denied["error"]["code"])
            self.assertTrue(enabled["data"]["effective_enabled"])
            self.assertFalse(changed["data"]["effective_enabled"])
            self.assertFalse(changed["data"]["config_confirmed"])

    def test_preview_does_not_write_and_create_requires_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)

            preview = self._create_plan(temporary, apply=False)
            target = Path(temporary) / preview["data"]["target_path"]
            self.assertFalse(target.exists())
            created = self.process.create_document(
                collection="plans",
                title="Configuration model",
                body="# Plan\n",
                stage="stage-2",
                task="task-1",
                tags=["config"],
                document_id=preview["data"]["document_id"],
                apply=True,
                project_root=temporary,
            )

            self.assertTrue(created["ok"])
            self.assertTrue(target.exists())
            self.assertIn("PLAN-0001", target.read_text(encoding="utf-8"))

            duplicate = self.process.create_document(
                collection="plans",
                title="Duplicate configuration model",
                document_id=preview["data"]["document_id"],
                apply=True,
                project_root=temporary,
            )
            self.assertFalse(duplicate["ok"])
            self.assertEqual("document_id_exists", duplicate["error"]["code"])
            self.assertIn("Configuration model", target.read_text(encoding="utf-8"))

    def test_default_documents_use_creation_date_directories(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)
            with patch("vibe_secretary.process_service.utc_today", return_value="2026-10-03"):
                plan = self._create_plan(temporary)
                build = self.process.create_document(
                    collection="build_hist",
                    title="Configuration implementation",
                    relates_to=[plan["data"]["document_id"]],
                    apply=True,
                    project_root=temporary,
                )
            self.assertTrue(plan["ok"])
            self.assertTrue(build["ok"])
            self.assertEqual(
                "plans/2026-10-03/PLAN-0001_configuration-model.md",
                plan["data"]["target_path"],
            )
            self.assertEqual(
                "build_hist/2026-10-03/BUILD-0001_configuration-implementation.md",
                build["data"]["target_path"],
            )
            for result in (plan, build):
                self.assertTrue((Path(temporary) / result["data"]["target_path"]).is_file())
            query = self.process.query(project_root=temporary)
            self.assertTrue(query["ok"])
            self.assertEqual(2, query["data"]["result_count"])

    def test_relationship_query_transition_and_index_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)
            plan = self._create_plan(temporary)
            plan_id = plan["data"]["document_id"]
            build = self.process.create_document(
                collection="build_hist",
                title="Configuration implementation",
                body="# Build\n",
                stage="stage-2",
                task="task-1",
                relates_to=[plan_id],
                apply=True,
                project_root=temporary,
            )

            query = self.process.query(tag="config", project_root=temporary)
            fetched = self.process.get_document(plan_id, True, temporary)
            transition_preview = self.process.transition_document(
                plan_id, "completed", False, temporary
            )
            transition = self.process.transition_document(plan_id, "completed", True, temporary)
            index_preview = self.process.rebuild_index(False, temporary)
            index_result = self.process.rebuild_index(True, temporary)

            self.assertTrue(build["ok"])
            self.assertEqual(1, query["data"]["result_count"])
            self.assertEqual([build["data"]["document_id"]], fetched["data"]["document"]["referenced_by"])
            self.assertFalse(transition_preview["data"]["applied"])
            self.assertTrue(transition["data"]["terminal"])
            self.assertIn(plan_id, index_preview["data"]["markdown_preview"])
            self.assertTrue(index_result["data"]["applied"])
            self.assertTrue((Path(temporary) / ".vibesecretary" / "process-index.json").is_file())

    def test_organize_previews_and_moves_only_managed_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)
            created = self._create_plan(temporary)
            original = Path(temporary) / created["data"]["target_path"]
            misplaced = Path(temporary) / "plans" / "legacy-location.md"
            original.replace(misplaced)
            unmanaged = Path(temporary) / "plans" / "notes.md"
            unmanaged.write_text("plain markdown", encoding="utf-8")

            preview = self.process.organize(False, temporary)
            applied = self.process.organize(True, temporary)

            self.assertEqual(1, preview["data"]["move_count"])
            self.assertFalse(preview["data"]["applied"])
            self.assertTrue(applied["data"]["applied"])
            self.assertTrue(original.exists())
            self.assertTrue(unmanaged.exists())

    def test_collection_excluded_by_scope_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.foundation.initialize_project(temporary)
            scope = Path(temporary) / ".vibesecretaryignore"
            scope.write_text(scope.read_text(encoding="utf-8") + "plans/\n", encoding="utf-8")
            self.foundation.set_project_enabled(True, True, temporary)

            result = self.process.initialize(temporary)

            self.assertFalse(result["ok"])
            self.assertEqual("process_path_outside_scope", result["error"]["code"])

    def test_custom_collection_can_be_configured_and_used(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._foundation_project(temporary)
            self.process.initialize(temporary)
            paths = ProjectPaths(Path(temporary).resolve())
            project_config = load_config(paths)
            custom = ProcessHubConfig(
                collections=(
                    CollectionConfig(
                        id="adr",
                        kind="decision",
                        path="docs/adr",
                        id_prefix="ADR",
                        path_template="{year}/{id}_{slug}.md",
                        usage="Record durable architecture decisions.",
                        required_fields=(*CORE_REQUIRED_FIELDS, "owner"),
                        initial_status="active",
                    ),
                )
            )
            save_process_config(paths, project_config, custom)
            enabled = self.process.set_enabled(True, True, temporary)
            preview = self.process.preview_document(
                collection="adr",
                title="Choose local storage",
                body="# Decision\n",
                metadata={"owner": "personal"},
                project_root=temporary,
            )

            self.assertTrue(enabled["ok"])
            self.assertTrue(preview["ok"])
            self.assertEqual("ADR-0001", preview["data"]["document_id"])
            self.assertIn("docs/adr/", preview["data"]["target_path"])
            self.assertEqual("personal", preview["data"]["metadata"]["owner"])

    def test_status_exposes_usage_without_internal_kind_or_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)

            status = self.process.status(temporary)
            plans = status["data"]["collections"][0]

            self.assertIn("usage", plans)
            self.assertNotIn("kind", plans)
            self.assertNotIn("id_prefix", plans)

    def test_disable_succeeds_even_when_process_config_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)
            config = Path(temporary) / ".vibesecretary" / "process-hub.toml"
            config.write_text("not valid toml = [", encoding="utf-8")

            result = self.process.set_enabled(False, False, temporary)

            self.assertTrue(result["ok"])
            self.assertFalse(result["data"]["effective_enabled"])


if __name__ == "__main__":
    unittest.main()
