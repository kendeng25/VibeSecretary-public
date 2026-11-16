from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from vibe_secretary.config import load_config
from vibe_secretary.implementation_config import (
    load_implementation_config,
    save_implementation_config,
)
from vibe_secretary.implementation_service import ImplementationLensService
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.service import FoundationService


class ImplementationProjectModelTests(unittest.TestCase):
    def _active_project(self, temporary: str) -> tuple[Path, ImplementationLensService]:
        root = Path(temporary)
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text(
            "def save_widget(value):\n    return value\n\n"
            "def main():\n    return save_widget('x')\n",
            encoding="utf-8",
        )
        foundation = FoundationService()
        self.assertTrue(foundation.initialize_project(temporary)["ok"])
        self.assertTrue(foundation.set_project_enabled(True, True, temporary)["ok"])
        service = ImplementationLensService()
        self.assertTrue(service.initialize(temporary)["ok"])
        self.assertTrue(service.set_enabled(True, True, temporary)["ok"])
        return root, service

    @staticmethod
    def _records(inspected: dict, summary: str = "Widget request implementation.") -> list[dict]:
        nodes = {
            item["qualified_name"]: item
            for item in inspected["data"]["evidence_package"]["nodes"]
        }
        return [
            {
                "id": "overview",
                "kind": "overview",
                "title": "Project implementation overview",
                "summary": summary,
                "details": ["main delegates widget persistence to save_widget."],
                "evidence": [
                    {
                        "kind": "node",
                        "ref_id": nodes["app.main"]["id"],
                        "claim": "Detected project entrypoint.",
                    }
                ],
                "related_records": ["widget-component"],
            },
            {
                "id": "widget-component",
                "kind": "component",
                "title": "Widget component",
                "summary": "The component accepts and returns the widget value.",
                "evidence": [
                    {
                        "kind": "node",
                        "ref_id": nodes["app.save_widget"]["id"],
                        "claim": "Static function definition.",
                    }
                ],
                "related_records": ["overview"],
            },
        ]

    def test_first_build_reuse_and_source_change_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            inspected = service.inspect_model(temporary)
            self.assertTrue(inspected["ok"], inspected)
            self.assertEqual("missing", inspected["data"]["project_model"]["status"])
            self.assertEqual([], inspected["data"]["writes"])
            records = self._records(inspected)

            updated = service.update_model(
                records,
                "complete",
                expected_model_digest="",
                project_root=temporary,
            )
            self.assertTrue(updated["ok"], updated)
            self.assertEqual("passed", updated["data"]["read_only_check"]["status"])
            model = updated["data"]["project_model"]
            self.assertTrue((root / model["manifest"]).is_file())
            self.assertTrue((root / "ImplementationLens/_project_model/overview.md").is_file())
            self.assertTrue(
                (root / "ImplementationLens/_project_model/components/widget-component.md").is_file()
            )

            fresh = service.inspect_model(temporary)
            self.assertEqual("fresh", fresh["data"]["project_model"]["status"])
            self.assertFalse(fresh["data"]["project_model"]["update_required"])
            self.assertEqual(2, len(fresh["data"]["project_model"]["records"]))

            reused = service.update_model(
                records,
                "complete",
                expected_model_digest=model["model_digest"],
                project_root=temporary,
            )
            self.assertTrue(reused["ok"], reused)
            self.assertEqual(
                ["ImplementationLens/_project_model/manifest.json"],
                reused["data"]["writes"],
            )

            (root / "src/app.py").write_text(
                "def save_widget(value):\n    return {'saved': value}\n\n"
                "def main():\n    return save_widget('x')\n",
                encoding="utf-8",
            )
            stale = service.inspect_model(temporary)["data"]["project_model"]
            self.assertEqual("stale", stale["status"])
            self.assertEqual(["src/app.py"], stale["changed_paths"])
            self.assertEqual(["overview", "widget-component"], stale["stale_record_ids"])
            self.assertEqual([], stale["records"])

    def test_deleted_source_and_config_change_invalidate_affected_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            inspected = service.inspect_model(temporary)
            records = self._records(inspected)
            updated = service.update_model(records, "complete", project_root=temporary)
            self.assertTrue(updated["ok"], updated)

            (root / "src/app.py").unlink()
            deleted = service.inspect_model(temporary)["data"]["project_model"]
            self.assertEqual("stale", deleted["status"])
            self.assertEqual(["src/app.py"], deleted["changed_paths"])
            self.assertEqual(["overview", "widget-component"], deleted["stale_record_ids"])

        with tempfile.TemporaryDirectory() as temporary:
            _, service = self._active_project(temporary)
            inspected = service.inspect_model(temporary)
            records = self._records(inspected)
            updated = service.update_model(records, "complete", project_root=temporary)
            self.assertTrue(updated["ok"], updated)
            paths = ProjectPaths.from_value(temporary)
            project_config = load_config(paths)
            config = load_implementation_config(paths, project_config)
            save_implementation_config(
                paths,
                project_config,
                replace(config, default_granularity=config.default_granularity.__class__("module")),
            )
            self.assertTrue(service.set_enabled(True, True, temporary)["ok"])

            stale = service.inspect_model(temporary)["data"]["project_model"]
            self.assertEqual("stale", stale["status"])
            self.assertEqual(["overview", "widget-component"], stale["stale_record_ids"])
            self.assertIn(
                "Analyzer, Lens configuration, or read scope changed",
                " ".join(stale["diagnostics"]),
            )
    def test_managed_file_conflict_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            inspected = service.inspect_model(temporary)
            records = self._records(inspected)
            updated = service.update_model(records, "complete", project_root=temporary)
            digest = updated["data"]["project_model"]["model_digest"]
            overview = root / "ImplementationLens/_project_model/overview.md"
            overview.write_text("manual edit\n", encoding="utf-8")

            conflict = service.inspect_model(temporary)["data"]["project_model"]
            self.assertEqual("conflict", conflict["status"])
            rejected = service.update_model(
                records,
                "complete",
                expected_model_digest=digest,
                project_root=temporary,
            )
            self.assertFalse(rejected["ok"])
            self.assertEqual("implementation_model_conflict", rejected["error"]["code"])
            confirmed = service.update_model(
                records,
                "complete",
                expected_model_digest=digest,
                confirm_replace_modified=True,
                project_root=temporary,
            )
            self.assertTrue(confirmed["ok"], confirmed)
            self.assertIn("Project implementation overview", overview.read_text(encoding="utf-8"))

    def test_complete_coverage_rejects_a_truncated_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            (root / "src/extra.py").write_text("def extra():\n    return 1\n", encoding="utf-8")
            paths = ProjectPaths(root.resolve())
            project_config = load_config(paths)
            config = load_implementation_config(paths, project_config)
            save_implementation_config(paths, project_config, replace(config, max_files=1))
            self.assertTrue(service.set_enabled(True, True, temporary)["ok"])
            inspected = service.inspect_model(temporary)
            self.assertTrue(inspected["data"]["evidence_package"]["stats"]["truncated"])
            records = self._records(inspected)

            rejected = service.update_model(records, "complete", project_root=temporary)
            self.assertFalse(rejected["ok"])
            self.assertEqual(
                "invalid_implementation_model_coverage", rejected["error"]["code"]
            )
            covered = sorted(
                {
                    item["path"]
                    for item in inspected["data"]["evidence_package"]["nodes"]
                }
            )
            partial = service.update_model(
                records,
                "partial",
                covered_paths=covered,
                diagnostics=["Source-file budget left part of the project unmodeled."],
                project_root=temporary,
            )
            self.assertTrue(partial["ok"], partial)
            self.assertEqual("partial", partial["data"]["project_model"]["coverage"])

    def test_obsolete_record_deletion_is_audited_and_rolled_back_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            inspected = service.inspect_model(temporary)
            records = self._records(inspected)
            updated = service.update_model(records, "complete", project_root=temporary)
            digest = updated["data"]["project_model"]["model_digest"]
            component = root / "ImplementationLens/_project_model/components/widget-component.md"
            manifest = root / "ImplementationLens/_project_model/manifest.json"
            before_component = component.read_bytes()
            before_manifest = manifest.read_bytes()
            overview_only = [{**records[0], "related_records": []}]
            from vibe_secretary import implementation_project_model as module

            original = module._atomic_write

            def fail_manifest(path: Path, raw: bytes) -> None:
                if path.name == "manifest.json":
                    raise OSError("simulated manifest failure")
                original(path, raw)

            with patch.object(module, "_atomic_write", side_effect=fail_manifest):
                failed = service.update_model(
                    overview_only,
                    "complete",
                    expected_model_digest=digest,
                    project_root=temporary,
                )
            self.assertFalse(failed["ok"])
            self.assertEqual(before_manifest, manifest.read_bytes())
            self.assertEqual(before_component, component.read_bytes())

            removed = service.update_model(
                overview_only,
                "complete",
                expected_model_digest=digest,
                project_root=temporary,
            )
            self.assertTrue(removed["ok"], removed)
            self.assertFalse(component.exists())
            self.assertIn(
                "ImplementationLens/_project_model/components/widget-component.md",
                removed["data"]["writes"],
            )
            self.assertEqual("passed", removed["data"]["read_only_check"]["status"])
    def test_failed_manifest_commit_rolls_back_record_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            inspected = service.inspect_model(temporary)
            records = self._records(inspected)
            updated = service.update_model(records, "complete", project_root=temporary)
            digest = updated["data"]["project_model"]["model_digest"]
            manifest = root / "ImplementationLens/_project_model/manifest.json"
            overview = root / "ImplementationLens/_project_model/overview.md"
            before_manifest = manifest.read_bytes()
            before_overview = overview.read_bytes()
            revised = self._records(inspected, "Revised project summary.")
            from vibe_secretary import implementation_project_model as module

            original = module._atomic_write

            def fail_manifest(path: Path, raw: bytes) -> None:
                if path.name == "manifest.json":
                    raise OSError("simulated manifest failure")
                original(path, raw)

            with patch.object(module, "_atomic_write", side_effect=fail_manifest):
                failed = service.update_model(
                    revised,
                    "complete",
                    expected_model_digest=digest,
                    project_root=temporary,
                )

            self.assertFalse(failed["ok"])
            self.assertEqual(before_manifest, manifest.read_bytes())
            self.assertEqual(before_overview, overview.read_bytes())
            self.assertEqual("fresh", service.inspect_model(temporary)["data"]["project_model"]["status"])


if __name__ == "__main__":
    unittest.main()
