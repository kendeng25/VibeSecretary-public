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
from vibe_secretary.implementation_models import Granularity, ImplementationView
from vibe_secretary.implementation_render import render_html_graph
from vibe_secretary.implementation_service import ImplementationLensService
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.service import FoundationService


class ImplementationServiceTests(unittest.TestCase):
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

    def test_status_initialize_enable_query_and_render_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            status = service.status(temporary)
            self.assertTrue(status["data"]["effective_enabled"])
            self.assertEqual("@lens", status["data"]["trigger"])

            query = service.query("main save_widget", "symbol", temporary)
            self.assertTrue(query["ok"], query)
            self.assertEqual([], query["data"]["writes"])
            self.assertFalse((root / ".vibesecretary" / "implementation-lens-index.json").exists())

            rendered = service.render("main save_widget", "symbol", "Widget flow", temporary)
            self.assertTrue(rendered["ok"], rendered)
            data = rendered["data"]
            self.assertEqual("passed", data["read_only_check"]["status"])
            markdown = root / data["markdown"]
            html = root / data["html"]
            self.assertTrue(markdown.is_file())
            self.assertTrue(html.is_file())
            self.assertTrue((root / data["index_json"]).is_file())
            markdown_text = markdown.read_text(encoding="utf-8")
            html_text = html.read_text(encoding="utf-8")
            self.assertEqual("## 只读检查", [line for line in markdown_text.splitlines() if line.startswith("## ")][-1])
            self.assertIn("**通过**", markdown_text)
            self.assertIn("Implementation semantic storyboard", html_text)
            self.assertIn('<details class="stage"', html_text)
            self.assertIn('id="expand-all"', html_text)
            self.assertIn('id="selection-status"', html_text)
            self.assertIn("最小充分实现流程", html_text)
            self.assertNotIn("<svg", html_text)
            self.assertNotIn("pointermove", html_text)
            self.assertNotIn("<script src=", html_text)
            self.assertNotIn("fetch(", html_text)

    def test_config_change_invalidates_enablement_and_custom_output_layout_applies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            paths = ProjectPaths(root.resolve())
            project_config = load_config(paths)
            config = load_implementation_config(paths, project_config)
            save_implementation_config(
                paths,
                project_config,
                replace(
                    config,
                    output_path="docs/implementation",
                    path_template="{year}/{month}/{granularity}/{slug}_{day}.{ext}",
                ),
            )
            self.assertFalse(service.status(temporary)["data"]["effective_enabled"])
            self.assertTrue(service.set_enabled(True, True, temporary)["ok"])

            rendered = service.render("main", "detail", "Main", temporary)

            self.assertTrue(rendered["ok"], rendered)
            markdown_path = Path(rendered["data"]["markdown"])
            html_path = Path(rendered["data"]["html"])
            self.assertEqual("docs", markdown_path.parts[0])
            self.assertEqual("implementation", markdown_path.parts[1])
            self.assertRegex(markdown_path.parts[2], r"^\d{4}$")
            self.assertRegex(markdown_path.parts[3], r"^\d{2}$")
            self.assertEqual("detail", markdown_path.parts[4])
            self.assertEqual(markdown_path.parent, html_path.parent)
            self.assertTrue((root / html_path).is_file())

    def test_empty_html_graph_shows_diagnostic_instead_of_blank_canvas(self) -> None:
        view = ImplementationView(
            query="missing feature",
            granularity=Granularity.SYMBOL,
            nodes=(),
            edges=(),
            seed_ids=(),
        )

        rendered = render_html_graph(
            title="Empty graph",
            view=view,
            html_path=Path("ImplementationLens/empty.html"),
            project_root=Path("."),
        )

        self.assertIn('id="stage-no-evidence"', rendered)
        self.assertIn("No matching evidence", rendered)
        self.assertIn("证据回退，不是语义全图", rendered)
        self.assertNotIn("<svg", rendered)

    def test_scope_excluded_index_and_output_are_rejected(self) -> None:
        for exclusion, operation, expected in (
            (
                ".vibesecretary/implementation-lens-index.json\n",
                "refresh",
                "implementation_index_outside_scope",
            ),
            (
                "ImplementationLens/\n",
                "render",
                "implementation_output_outside_scope",
            ),
        ):
            with self.subTest(exclusion=exclusion), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "src").mkdir()
                (root / "src" / "app.py").write_text(
                    "def main():\n    return 1\n", encoding="utf-8"
                )
                foundation = FoundationService()
                foundation.initialize_project(temporary)
                scope = root / ".vibesecretaryignore"
                scope.write_text(
                    scope.read_text(encoding="utf-8") + exclusion, encoding="utf-8"
                )
                foundation.set_project_enabled(True, True, temporary)
                service = ImplementationLensService()
                service.initialize(temporary)
                service.set_enabled(True, True, temporary)

                result = (
                    service.refresh(temporary)
                    if operation == "refresh"
                    else service.render("main", "symbol", "Main", temporary)
                )

                self.assertFalse(result["ok"])
                self.assertEqual(expected, result["error"]["code"])

    def test_disable_succeeds_when_module_config_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            config = root / ".vibesecretary" / "implementation-lens.toml"
            config.write_text("invalid = [", encoding="utf-8")

            result = service.set_enabled(False, False, temporary)

            self.assertTrue(result["ok"])
            self.assertFalse(result["data"]["effective_enabled"])

    def test_read_only_check_fails_when_source_changes_during_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            from vibe_secretary import implementation_service as module

            original = module.build_implementation_index

            def mutating_build(*args, **kwargs):
                result = original(*args, **kwargs)
                (root / "src" / "app.py").write_text(
                    "def changed():\n    return 2\n", encoding="utf-8"
                )
                return result

            with patch.object(module, "build_implementation_index", side_effect=mutating_build):
                rendered = service.render("main", "symbol", "Concurrent change", temporary)

            self.assertTrue(rendered["ok"], rendered)
            self.assertEqual("failed", rendered["data"]["read_only_check"]["status"])
            self.assertIn("src/app.py", rendered["data"]["read_only_check"]["unexpected_changes"])
            markdown = (root / rendered["data"]["markdown"]).read_text(encoding="utf-8")
            self.assertIn("**失败**", markdown)

    def test_read_only_check_is_unverified_when_audit_budget_is_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service = self._active_project(temporary)
            (root / "extra.txt").write_text("extra", encoding="utf-8")
            paths = ProjectPaths(root.resolve())
            project_config = load_config(paths)
            config = load_implementation_config(paths, project_config)
            save_implementation_config(
                paths, project_config, replace(config, max_audit_files=1)
            )
            self.assertTrue(service.set_enabled(True, True, temporary)["ok"])

            rendered = service.render("main", "symbol", "Budget", temporary)

            self.assertTrue(rendered["ok"], rendered)
            self.assertEqual("unverified", rendered["data"]["read_only_check"]["status"])
            self.assertTrue(rendered["data"]["read_only_check"]["boundaries"])


if __name__ == "__main__":
    unittest.main()
