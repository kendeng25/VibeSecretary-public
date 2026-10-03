from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import (  # noqa: E402
    ProjectConfig,
    load_config,
    parse_config,
    save_config,
)
from vibe_secretary.errors import FoundationError  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.providers import ProviderConfig, ProviderMode  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_config_round_trip_preserves_non_secret_provider_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            config = ProjectConfig(
                enabled=True,
                scope_digest="a" * 64,
                provider=ProviderConfig(
                    mode=ProviderMode.BYOK,
                    name="example",
                    api_key_env="EXAMPLE_API_KEY",
                ),
            )
            save_config(paths, config)

            loaded = load_config(paths)

            self.assertEqual(config, loaded)
            self.assertNotIn("secret-value", paths.config_file.read_text(encoding="utf-8"))

    def test_byok_requires_provider_name_and_api_key_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            with self.assertRaises(FoundationError) as caught:
                parse_config(
                    {
                        "schema_version": 1,
                        "provider": {"mode": "byok", "name": "", "api_key_env": ""},
                    },
                    paths,
                )

            self.assertEqual("incomplete_byok_config", caught.exception.code)

    def test_scope_file_cannot_escape_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            with self.assertRaises(FoundationError) as caught:
                parse_config(
                    {"schema_version": 1, "scope_file": "../outside.ignore"},
                    paths,
                )

            self.assertEqual("path_outside_project", caught.exception.code)

    def test_boolean_schema_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            with self.assertRaises(FoundationError) as caught:
                parse_config({"schema_version": True}, paths)

            self.assertEqual("invalid_config", caught.exception.code)

    def test_invalid_environment_variable_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = ProjectPaths(Path(temporary).resolve())
            with self.assertRaises(FoundationError) as caught:
                parse_config(
                    {
                        "schema_version": 1,
                        "provider": {
                            "mode": "byok",
                            "name": "example",
                            "api_key_env": "not-a-safe-name",
                        },
                    },
                    paths,
                )

            self.assertEqual("invalid_api_key_env", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
