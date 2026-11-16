from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import load_config, save_config  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.implementation_service import ImplementationLensService  # noqa: E402
from vibe_secretary.process_service import ProcessHubService  # noqa: E402
from vibe_secretary.prompt_config import load_prompt_config, save_prompt_config  # noqa: E402
from vibe_secretary.prompt_models import PromptMode  # noqa: E402
from vibe_secretary.prompt_service import PromptCopilotService  # noqa: E402
from vibe_secretary.providers import ProviderConfig, ProviderMode  # noqa: E402
from vibe_secretary.service import FoundationService  # noqa: E402


class PromptCopilotServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.foundation = FoundationService()
        self.prompt = PromptCopilotService()

    def _foundation_project(self, root: str) -> None:
        self.assertTrue(self.foundation.initialize_project(root)["ok"])
        self.assertTrue(self.foundation.set_project_enabled(True, True, root)["ok"])

    def _active_project(self, root: str) -> None:
        self._foundation_project(root)
        self.assertTrue(self.prompt.initialize(root)["ok"])
        self.assertTrue(self.prompt.set_enabled(True, True, root)["ok"])

    def test_status_returns_project_root_before_foundation_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.prompt.status(temporary)

            self.assertTrue(result["ok"])
            self.assertEqual(str(Path(temporary).resolve()), result["data"]["project_root"])
            self.assertFalse(result["data"]["foundation_initialized"])
            self.assertFalse(result["data"]["foundation_effective_enabled"])
            self.assertFalse(result["data"]["effective_enabled"])

    def test_initialize_enable_and_config_change_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._foundation_project(temporary)
            initialized = self.prompt.initialize(temporary)
            denied = self.prompt.set_enabled(True, False, temporary)
            enabled = self.prompt.set_enabled(True, True, temporary)
            path = Path(temporary) / ".vibesecretary" / "prompt-copilot.toml"
            path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
            changed = self.prompt.status(temporary)

            self.assertTrue(initialized["ok"])
            self.assertEqual("prompt_config_confirmation_required", denied["error"]["code"])
            self.assertTrue(enabled["data"]["effective_enabled"])
            self.assertFalse(changed["data"]["effective_enabled"])
            self.assertFalse(changed["data"]["config_confirmed"])

    def test_prepare_review_works_without_other_business_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "service.py").write_text(
                "def create_report():\n    return 'report'\n",
                encoding="utf-8",
            )
            self._active_project(temporary)

            result = self.prompt.prepare_review(
                "请实现 src/service.py 的 create_report，并添加测试。",
                "review",
                temporary,
            )

            self.assertTrue(result["ok"])
            data = result["data"]
            self.assertEqual("review", data["mode"])
            self.assertTrue(any(item["path"] == "src/service.py" for item in data["evidence"]))
            degradations = {item["source"]: item["code"] for item in data["degradations"]}
            self.assertEqual("process_hub_unavailable", degradations["process_hub"])
            self.assertEqual(
                "implementation_lens_unavailable",
                degradations["implementation_lens"],
            )
            self.assertIn("Codex Host", data["host_instructions"])

    def test_implementation_lens_is_optional_non_hook_enhancement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "service.py").write_text(
                "def create_report():\n    return 'report'\n", encoding="utf-8"
            )
            self._active_project(temporary)
            lens = ImplementationLensService()
            self.assertTrue(lens.initialize(temporary)["ok"])
            self.assertTrue(lens.set_enabled(True, True, temporary)["ok"])

            result = self.prompt.prepare_review(
                "实现 create_report 并添加验证", "review", temporary
            )

            self.assertTrue(result["ok"], result)
            implementation = [
                item for item in result["data"]["evidence"]
                if item["source"] == "implementation_lens"
            ]
            self.assertTrue(implementation)
            self.assertTrue(
                all(item["kind"] == "implementation" for item in implementation)
            )

    def test_process_hub_is_optional_enhancement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)
            process = ProcessHubService()
            process.initialize(temporary)
            process.set_enabled(True, True, temporary)
            created = process.create_document(
                collection="plans",
                title="Authentication plan",
                body="Implement authentication with session validation.",
                tags=["authentication"],
                apply=True,
                project_root=temporary,
            )
            self.assertTrue(created["ok"])

            result = self.prompt.prepare_review(
                "实现 authentication session 验证并添加测试",
                "review",
                temporary,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(
                any(item["source"] == "process_hub" for item in result["data"]["evidence"])
            )

    def test_strict_mode_marks_required_questions_and_scope_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)

            result = self.prompt.prepare_review(
                "删除 ../outside/data.txt",
                "strict",
                temporary,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(any(item["required"] for item in result["data"]["questions"]))
            self.assertTrue(any(item["code"] == "target_outside_scope" for item in result["data"]["conflicts"]))

    def test_validate_host_package_checks_sources_and_required_answers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)
            package = {
                "summary": "Implement login",
                "optimized_prompt": "实现登录并运行测试",
                "changes": ["Added acceptance criteria"],
                "source_ids": ["repo:not-real"],
                "source_links": {"login behavior": ["repo:not-real"]},
                "assumptions": [],
                "acceptance_criteria": ["Tests pass"],
                "verification_commands": [
                    {
                        "command": "python -m unittest",
                        "source_ids": [],
                        "suggested": True,
                    }
                ],
                "unresolved_questions": [],
                "answers": {},
            }

            result = self.prompt.validate_package(
                "实现登录功能",
                package,
                "strict",
                temporary,
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["data"]["valid"])
            codes = {item["code"] for item in result["data"]["errors"]}
            self.assertIn("unknown_source_id", codes)
            self.assertIn("unanswered_required_question", codes)

    def test_byok_is_explicitly_unimplemented_and_never_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._foundation_project(temporary)
            self.prompt.initialize(temporary)
            paths = ProjectPaths(Path(temporary).resolve())
            config = load_config(paths)
            config = replace(
                config,
                provider=ProviderConfig(
                    mode=ProviderMode.BYOK,
                    name="placeholder",
                    api_key_env="PLACEHOLDER_API_KEY",
                ),
            )
            save_config(paths, config)

            result = self.prompt.set_enabled(True, True, temporary)

            self.assertFalse(result["ok"])
            self.assertEqual("provider_not_implemented", result["error"]["code"])

    def test_disable_succeeds_when_prompt_config_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_project(temporary)
            config = Path(temporary) / ".vibesecretary" / "prompt-copilot.toml"
            config.write_text("invalid = [", encoding="utf-8")

            result = self.prompt.set_enabled(False, False, temporary)

            self.assertTrue(result["ok"])
            self.assertFalse(result["data"]["effective_enabled"])



    def test_sourced_constraint_is_reported_as_potential_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "AGENTS.md").write_text(
                "Do not modify authentication behavior without an approved migration.",
                encoding="utf-8",
            )
            self._active_project(temporary)

            result = self.prompt.prepare_review(
                "重构 authentication behavior 并添加测试",
                "review",
                temporary,
            )

            self.assertTrue(result["ok"])
            conflict = next(
                item for item in result["data"]["conflicts"]
                if item["code"] == "potential_constraint_conflict"
            )
            self.assertTrue(conflict["source_ids"])


    def test_optional_context_source_failure_degrades_without_blocking(self) -> None:
        from vibe_secretary.prompt_context import RepositoryContextSource

        class ExplodingSource:
            name = "optional_fixture"

            def collect(self, **kwargs):
                del kwargs
                raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("Widget implementation", encoding="utf-8")
            self._foundation_project(temporary)
            service = PromptCopilotService(
                sources=(RepositoryContextSource(), ExplodingSource())
            )
            service.initialize(temporary)
            service.set_enabled(True, True, temporary)

            result = service.prepare_review("实现 Widget 并添加测试", "review", temporary)

            self.assertTrue(result["ok"])
            self.assertIn(
                {"source": "optional_fixture", "code": "optional_fixture_failed"},
                result["data"]["degradations"],
            )

    def test_validator_enforces_exact_schema_and_preserves_intent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "auth.py").write_text(
                "def authenticate(token: str) -> bool:\n    return bool(token)\n",
                encoding="utf-8",
            )
            self._active_project(temporary)
            prepared = self.prompt.prepare_review(
                "修复 src/auth.py 的 token 认证安全问题",
                "review",
                temporary,
            )
            source_ids = [item["source_id"] for item in prepared["data"]["evidence"]]
            package = {
                "summary": "Unrelated change",
                "optimized_prompt": "实现 reports.py 报表功能",
                "changes": [],
                "source_ids": source_ids,
                "source_links": {"Authentication code exists": source_ids},
                "assumptions": [],
                "acceptance_criteria": [],
                "verification_commands": [
                    {
                        "command": "python -m unittest",
                        "source_ids": [],
                        "suggested": False,
                    }
                ],
                "unresolved_questions": [],
                "answers": {},
                "extra": "not allowed",
            }

            result = self.prompt.validate_package(
                "修复 src/auth.py 的 token 认证安全问题",
                package,
                "review",
                temporary,
            )

            codes = {item["code"] for item in result["data"]["errors"]}
            self.assertIn("unexpected_field", codes)
            self.assertIn("intent_action_changed", codes)
            self.assertIn("intent_target_lost", codes)
            self.assertIn("intent_risk_lost", codes)
            self.assertIn("unsupported_verification_command", codes)

    def test_validator_requires_sources_and_claim_links_when_evidence_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("Widget feature", encoding="utf-8")
            self._active_project(temporary)
            package = {
                "summary": "Implement Widget",
                "optimized_prompt": "实现 Widget 功能并添加测试",
                "changes": [],
                "source_ids": [],
                "source_links": {},
                "assumptions": [],
                "acceptance_criteria": [],
                "verification_commands": [],
                "unresolved_questions": [],
                "answers": {},
            }

            result = self.prompt.validate_package(
                "实现 Widget 功能并添加测试",
                package,
                "review",
                temporary,
            )

            codes = {item["code"] for item in result["data"]["errors"]}
            self.assertIn("missing_source_ids", codes)
            self.assertIn("missing_source_links", codes)
    def test_valid_host_package_passes_deterministic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("Widget feature", encoding="utf-8")
            self._active_project(temporary)
            prepared = self.prompt.prepare_review(
                "实现 Widget 功能并添加测试和验证步骤",
                "review",
                temporary,
            )
            source_ids = [item["source_id"] for item in prepared["data"]["evidence"]]
            package = {
                "summary": "Implement Widget",
                "optimized_prompt": "实现 Widget 功能，添加测试并运行验证。",
                "changes": ["Added acceptance and verification"],
                "source_ids": source_ids,
                "source_links": {"Widget feature exists": source_ids},
                "assumptions": [],
                "acceptance_criteria": ["Widget tests pass"],
                "verification_commands": [
                    {
                        "command": "python -m unittest",
                        "source_ids": [],
                        "suggested": True,
                    }
                ],
                "unresolved_questions": [],
                "answers": {},
            }

            result = self.prompt.validate_package(
                "实现 Widget 功能并添加测试和验证步骤",
                package,
                "review",
                temporary,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["data"]["valid"])
            self.assertEqual([], result["data"]["errors"])

if __name__ == "__main__":
    unittest.main()
