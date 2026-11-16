from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vibe_secretary.config import load_config
from vibe_secretary.errors import FoundationError
from vibe_secretary.implementation_config import (
    default_implementation_config,
    load_implementation_config,
    parse_implementation_config,
    render_implementation_config,
)
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.service import FoundationService


class ImplementationConfigTests(unittest.TestCase):
    def test_default_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            FoundationService().initialize_project(temporary)
            project_config = load_config(paths)
            rendered = render_implementation_config(default_implementation_config())
            import tomllib

            parsed = parse_implementation_config(tomllib.loads(rendered), paths)
            self.assertEqual(default_implementation_config(), parsed)
            self.assertEqual("ImplementationLens", parsed.output_path)
            self.assertEqual(2, parsed.schema_version)
            self.assertIn("reports/{granularity}/", parsed.path_template)
            self.assertEqual("_project_model", parsed.project_model_path)
            self.assertIn("By year/month", rendered)
            nested = parse_implementation_config(
                {
                    "schema_version": 1,
                    "output": {
                        "path": "ImplementationLens",
                        "path_template": "{year}/{month}/{granularity}/{slug}_{day}.{ext}",
                    },
                },
                paths,
            )
            self.assertEqual(
                "{year}/{month}/{granularity}/{slug}_{day}.{ext}", nested.path_template
            )

    def test_output_and_index_paths_cannot_escape_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            with self.assertRaises(FoundationError):
                parse_implementation_config(
                    {
                        "schema_version": 1,
                        "output": {"path": "../outside", "path_template": "{slug}.{ext}"},
                    },
                    paths,
                )
            with self.assertRaises(FoundationError):
                parse_implementation_config(
                    {"schema_version": 1, "index_json": "../index.json"}, paths
                )

    def test_template_requires_slug_and_extension_and_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            for template in ("fixed.{ext}", "{slug}.md", "{slug}_{unknown}.{ext}"):
                with self.subTest(template=template), self.assertRaises(FoundationError):
                    parse_implementation_config(
                        {
                            "schema_version": 1,
                            "output": {
                                "path": "ImplementationLens",
                                "path_template": template,
                            },
                        },
                        paths,
                    )

    def test_schema_one_preserves_flat_report_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())

            parsed = parse_implementation_config({"schema_version": 1}, paths)

            self.assertEqual("{slug}_{timestamp}.{ext}", parsed.path_template)
            self.assertEqual("_project_model", parsed.project_model_path)

    def test_project_model_path_is_customizable_and_cannot_contain_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            parsed = parse_implementation_config(
                {
                    "schema_version": 2,
                    "output": {
                        "path": "docs/lens",
                        "path_template": "reports/{granularity}/{slug}.{ext}",
                        "project_model_path": "knowledge/implementation",
                    },
                },
                paths,
            )
            self.assertEqual("knowledge/implementation", parsed.project_model_path)
            with self.assertRaises(FoundationError):
                parse_implementation_config(
                    {
                        "schema_version": 2,
                        "output": {
                            "path": "ImplementationLens",
                            "path_template": "_project_model/{slug}.{ext}",
                            "project_model_path": "_project_model",
                        },
                    },
                    paths,
                )
    def test_foundation_config_without_lens_module_is_backward_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            FoundationService().initialize_project(temporary)
            config_path = root / ".vibesecretary" / "config.toml"
            content = config_path.read_text(encoding="utf-8")
            start = content.index("[modules.implementation_lens]")
            end = content.index("[modules.prompt_copilot]")
            config_path.write_text(content[:start] + content[end:], encoding="utf-8")

            config = load_config(ProjectPaths(root.resolve()))

            self.assertFalse(config.modules.implementation_lens.enabled)
            self.assertEqual("implementation-lens.toml", config.modules.implementation_lens.config_file)


if __name__ == "__main__":
    unittest.main()
