from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.service import FoundationService  # noqa: E402


class FoundationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FoundationService()

    def test_initialize_is_non_destructive_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = self.service.initialize_project(temporary)
            scope = Path(temporary) / ".vibesecretaryignore"
            scope.write_text("custom-secret/\n", encoding="utf-8")

            second = self.service.initialize_project(temporary)

            self.assertTrue(first["ok"])
            self.assertEqual([], second["data"]["created"])
            self.assertEqual("custom-secret/\n", scope.read_text(encoding="utf-8"))

    def test_reinitializing_enabled_project_preserves_effective_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.service.initialize_project(temporary)
            self.service.set_project_enabled(True, True, temporary)

            result = self.service.initialize_project(temporary)

            self.assertTrue(result["data"]["effective_enabled"])

    def test_enable_requires_explicit_scope_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.service.initialize_project(temporary)

            denied = self.service.set_project_enabled(True, False, temporary)
            enabled = self.service.set_project_enabled(True, True, temporary)

            self.assertFalse(denied["ok"])
            self.assertEqual("scope_confirmation_required", denied["error"]["code"])
            self.assertTrue(enabled["ok"])
            self.assertTrue(self.service.project_status(temporary)["data"]["effective_enabled"])

    def test_scope_change_disables_effective_state_until_reconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.service.initialize_project(temporary)
            self.service.set_project_enabled(True, True, temporary)
            scope = Path(temporary) / ".vibesecretaryignore"
            scope.write_text(scope.read_text(encoding="utf-8") + "private/\n", encoding="utf-8")

            status = self.service.project_status(temporary)

            self.assertTrue(status["data"]["configured_enabled"])
            self.assertFalse(status["data"]["effective_enabled"])
            self.assertFalse(status["data"]["scope_confirmed"])

    def test_disable_does_not_require_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.service.initialize_project(temporary)
            self.service.set_project_enabled(True, True, temporary)

            disabled = self.service.set_project_enabled(False, False, temporary)

            self.assertTrue(disabled["ok"])
            self.assertFalse(disabled["data"]["effective_enabled"])
            self.assertFalse(self.service.project_status(temporary)["data"]["effective_enabled"])

    def test_expected_errors_use_stable_envelope_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.service.set_project_enabled(True, True, temporary)

            self.assertEqual({"ok", "data", "error"}, set(result))
            self.assertFalse(result["ok"])
            self.assertNotIn("traceback", str(result).lower())

    def test_health_declares_business_modules(self) -> None:
        result = self.service.health()

        self.assertTrue(result["ok"])
        self.assertEqual(
            ["process_hub", "implementation_lens", "prompt_copilot"],
            result["data"]["business_modules"],
        )


if __name__ == "__main__":
    unittest.main()
