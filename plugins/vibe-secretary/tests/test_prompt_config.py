from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import load_config  # noqa: E402
from vibe_secretary.errors import FoundationError  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.prompt_config import (  # noqa: E402
    PROMPT_CONFIG_SCHEMA_VERSION,
    default_prompt_config,
    load_prompt_config,
    parse_prompt_config,
    render_prompt_config,
    save_prompt_config,
)
from vibe_secretary.prompt_models import PromptMode  # noqa: E402
from vibe_secretary.service import FoundationService  # noqa: E402


class PromptConfigTests(unittest.TestCase):
    def test_default_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            foundation = FoundationService()
            foundation.initialize_project(temporary)
            paths = ProjectPaths(Path(temporary).resolve())
            project_config = load_config(paths)
            expected = replace(
                default_prompt_config(),
                default_mode=PromptMode.STRICT,
                automatic_enabled=True,
            )

            save_prompt_config(paths, project_config, expected)

            self.assertEqual(expected, load_prompt_config(paths, project_config))

    def test_schema_two_defaults_to_automatic_review_without_strict_blocking(self) -> None:
        config = default_prompt_config()
        rendered = render_prompt_config(config)

        self.assertEqual(2, PROMPT_CONFIG_SCHEMA_VERSION)
        self.assertEqual(PromptMode.REVIEW, config.default_mode)
        self.assertTrue(config.automatic_enabled)
        self.assertFalse(hasattr(config, "strict_blocking"))
        self.assertIn("schema_version = 2", rendered)
        self.assertIn("automatic_enabled = true", rendered)
        self.assertNotIn("strict_blocking", rendered)

    def test_schema_one_is_loaded_as_schema_two_without_changing_automatic_choice(self) -> None:
        migrated = parse_prompt_config(
            {
                "schema_version": 1,
                "default_mode": "strict",
                "automatic_enabled": False,
                "strict_blocking": True,
            }
        )

        self.assertEqual(2, migrated.schema_version)
        self.assertEqual(PromptMode.STRICT, migrated.default_mode)
        self.assertFalse(migrated.automatic_enabled)
        self.assertFalse(hasattr(migrated, "strict_blocking"))
        self.assertNotIn("strict_blocking", render_prompt_config(migrated))

    def test_schema_two_rejects_removed_strict_blocking_field(self) -> None:
        with self.assertRaises(FoundationError) as caught:
            parse_prompt_config(
                {
                    "schema_version": 2,
                    "strict_blocking": True,
                }
            )

        self.assertEqual("removed_prompt_config_field", caught.exception.code)

    def test_invalid_budget_relationship_is_rejected(self) -> None:
        with self.assertRaises(FoundationError) as caught:
            parse_prompt_config(
                {
                    "context_char_budget": 1000,
                    "hook_context_char_budget": 1500,
                }
            )

        self.assertEqual("invalid_prompt_config", caught.exception.code)

    def test_hook_budget_must_preserve_mode_protocol_capacity(self) -> None:
        with self.assertRaises(FoundationError) as caught:
            parse_prompt_config({"hook_context_char_budget": 1399})

        self.assertEqual("invalid_prompt_config", caught.exception.code)

    def test_invalid_mode_is_rejected(self) -> None:
        with self.assertRaises(FoundationError) as caught:
            parse_prompt_config({"default_mode": "automatic"})

        self.assertEqual("invalid_prompt_mode", caught.exception.code)

    def test_foundation_config_without_prompt_module_is_backward_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            paths.state_dir.mkdir()
            paths.config_file.write_text(
                'schema_version = 1\nenabled = false\nscope_file = ".vibesecretaryignore"\n',
                encoding="utf-8",
            )

            config = load_config(paths)

            self.assertFalse(config.modules.prompt_copilot.enabled)
            self.assertEqual("prompt-copilot.toml", config.modules.prompt_copilot.config_file)



    def test_prompt_module_config_path_cannot_escape_state_directory(self) -> None:
        from vibe_secretary.config import parse_config

        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            with self.assertRaises(FoundationError) as caught:
                parse_config(
                    {
                        "schema_version": 1,
                        "modules": {
                            "prompt_copilot": {
                                "config_file": "../outside.toml",
                            }
                        },
                    },
                    paths,
                )

            self.assertEqual("path_outside_project", caught.exception.code)

if __name__ == "__main__":
    unittest.main()
