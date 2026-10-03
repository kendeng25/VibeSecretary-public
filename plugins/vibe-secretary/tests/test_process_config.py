from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import parse_config, render_config  # noqa: E402
from vibe_secretary.errors import FoundationError  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.process_config import (  # noqa: E402
    CORE_REQUIRED_FIELDS,
    default_process_config,
    parse_process_config,
    render_process_config,
)


class ProcessConfigTests(unittest.TestCase):
    def test_foundation_config_without_modules_is_backward_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())

            config = parse_config({"schema_version": 1}, paths)

            self.assertFalse(config.modules.process_hub.enabled)
            self.assertEqual("process-hub.toml", config.modules.process_hub.config_file)
            self.assertIn("[modules.process_hub]", render_config(config))

    def test_default_process_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            original = default_process_config()
            import tomllib

            parsed = parse_process_config(
                tomllib.loads(render_process_config(original)),
                paths,
            )

            self.assertEqual(original, parsed)
            self.assertEqual(["plans", "build_hist"], [item.id for item in parsed.collections])
            rendered = render_process_config(original)
            self.assertIn("schema_version = 2", rendered)
            self.assertIn("# path_template examples:", rendered)
            self.assertNotIn("kind =", rendered)
            self.assertNotIn("id_prefix =", rendered)
            self.assertNotIn("required_fields =", rendered)
            for collection_id in ("plans", "build_hist"):
                self.assertEqual(
                    "{year}-{month}-{day}/{id}_{slug}.md",
                    parsed.collection(collection_id).path_template,
                )

    def test_schema_two_derives_internal_fields_and_accepts_advanced_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            parsed = parse_process_config(
                {
                    "schema_version": 2,
                    "collections": [{
                        "id": "architecture_decisions",
                        "usage": "Record durable architecture decisions.",
                        "path": "docs/adr",
                        "path_template": "{year}/{id}_{slug}.md",
                        "required_metadata": ["owner"],
                        "statuses": ["proposed", "accepted", "archived"],
                        "initial_status": "proposed",
                        "terminal_statuses": ["accepted", "archived"],
                    }],
                },
                paths,
            )

            collection = parsed.collections[0]
            self.assertEqual("architecture_decisions", collection.kind)
            self.assertEqual("ARCHITECTURE_DECISIONS", collection.id_prefix)
            self.assertEqual((*CORE_REQUIRED_FIELDS, "owner"), collection.required_fields)

    def test_schema_one_keeps_legacy_kind_prefix_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            legacy = {
                "schema_version": 1,
                "collections": [{
                    "id": "plans",
                    "kind": "legacy_plan",
                    "path": "plans",
                    "id_prefix": "OLDPLAN",
                    "path_template": "{stage}/{id}_{slug}.md",
                }],
            }
            parsed = parse_process_config(legacy, paths)
            rendered = render_process_config(parsed)

            self.assertEqual("legacy_plan", parsed.collections[0].kind)
            self.assertEqual("OLDPLAN", parsed.collections[0].id_prefix)
            self.assertEqual("{stage}/{id}_{slug}.md", parsed.collections[0].path_template)
            self.assertIn('kind = "legacy_plan"', rendered)
            self.assertIn('id_prefix = "OLDPLAN"', rendered)

    def test_schema_two_rejects_obsolete_description_and_internal_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            raw = {
                "schema_version": 2,
                "collections": [{
                    "id": "reviews",
                    "usage": "Record review findings.",
                    "description": "This field is obsolete.",
                    "path": "reviews",
                    "path_template": "{id}_{slug}.md",
                    "kind": "review",
                }],
            }

            with self.assertRaises(FoundationError) as caught:
                parse_process_config(raw, paths)

            self.assertEqual("unsupported_collection_fields", caught.exception.code)
            self.assertEqual(
                ["description", "kind"], caught.exception.details["fields"]
            )

    def test_unknown_template_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            raw = {
                "schema_version": 1,
                "collections": [
                    {
                        "id": "plans",
                        "kind": "plan",
                        "path": "plans",
                        "id_prefix": "PLAN",
                        "path_template": "{unknown}/{id}.md",
                    }
                ]
            }

            with self.assertRaises(FoundationError) as caught:
                parse_process_config(raw, paths)

            self.assertEqual("invalid_path_template", caught.exception.code)

    def test_overlapping_collection_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            raw = {
                "schema_version": 1,
                "collections": [
                    {
                        "id": "docs",
                        "kind": "note",
                        "path": "docs",
                        "id_prefix": "DOC",
                        "path_template": "{id}_{slug}.md",
                    },
                    {
                        "id": "adr",
                        "kind": "decision",
                        "path": "docs/adr",
                        "id_prefix": "ADR",
                        "path_template": "{id}_{slug}.md",
                    },
                ]
            }

            with self.assertRaises(FoundationError) as caught:
                parse_process_config(raw, paths)

            self.assertEqual("overlapping_collections", caught.exception.code)

    def test_absolute_and_project_root_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            for invalid_path in (".", str(Path(temporary) / "plans")):
                raw = {
                    "schema_version": 1,
                    "collections": [
                        {
                            "id": "plans",
                            "kind": "plan",
                            "path": invalid_path,
                            "id_prefix": "PLAN",
                            "path_template": "{id}_{slug}.md",
                        }
                    ]
                }
                with self.subTest(path=invalid_path), self.assertRaises(FoundationError):
                    parse_process_config(raw, paths)


if __name__ == "__main__":
    unittest.main()
