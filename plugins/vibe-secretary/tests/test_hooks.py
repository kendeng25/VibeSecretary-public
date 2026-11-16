from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import load_config  # noqa: E402
from vibe_secretary.hooks import pre_tool_use, session_start, user_prompt_submit  # noqa: E402
from vibe_secretary.implementation_service import ImplementationLensService  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.process_service import ProcessHubService  # noqa: E402
from vibe_secretary.prompt_config import load_prompt_config, save_prompt_config  # noqa: E402
from vibe_secretary.prompt_models import PromptMode  # noqa: E402
from vibe_secretary.prompt_service import PromptCopilotService  # noqa: E402
from vibe_secretary.service import FoundationService  # noqa: E402


class HookTests(unittest.TestCase):
    def _enabled_project(self, temporary: str) -> None:
        service = FoundationService()
        service.initialize_project(temporary)
        service.set_project_enabled(True, True, temporary)

    def _active_prompt_project(
        self,
        temporary: str,
        *,
        mode: str = "review",
        automatic: bool = True,
    ) -> None:
        self._enabled_project(temporary)
        service = PromptCopilotService()
        self.assertTrue(service.initialize(temporary)["ok"])
        paths = ProjectPaths(Path(temporary).resolve())
        project_config = load_config(paths)
        config = load_prompt_config(paths, project_config)
        save_prompt_config(
            paths,
            project_config,
            replace(
                config,
                default_mode=PromptMode(mode),
                automatic_enabled=automatic,
            ),
        )
        self.assertTrue(service.set_enabled(True, True, temporary)["ok"])

    def test_session_start_is_silent_for_uninitialized_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual({}, session_start({"cwd": temporary}))

    def test_session_start_context_is_small_when_modules_are_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._enabled_project(temporary)

            result = session_start({"cwd": temporary})
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertLess(len(context), 400)
            self.assertIn("Process Hub is not active", context)
            self.assertIn("Prompt Copilot is not active", context)

    def test_session_start_names_enabled_module_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._enabled_project(temporary)
            process = ProcessHubService()
            self.assertTrue(process.initialize(temporary)["ok"])
            self.assertTrue(process.set_enabled(True, True, temporary)["ok"])
            prompt = PromptCopilotService()
            self.assertTrue(prompt.initialize(temporary)["ok"])
            self.assertTrue(prompt.set_enabled(True, True, temporary)["ok"])

            result = session_start({"cwd": temporary})
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertLess(len(context), 2200)
            self.assertIn("$vibe-secretary-process-hub", context)
            self.assertIn("$vibe-secretary-prompt-copilot", context)
            self.assertIn("Confirmed Process Hub collection guidance", context)
            self.assertIn("- plans:", context)
            self.assertIn("- build_hist:", context)

    def test_session_start_does_not_expose_unconfirmed_usage_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._enabled_project(temporary)
            process = ProcessHubService()
            self.assertTrue(process.initialize(temporary)["ok"])
            self.assertTrue(process.set_enabled(True, True, temporary)["ok"])
            config = Path(temporary) / ".vibesecretary" / "process-hub.toml"
            config.write_text(
                config.read_text(encoding="utf-8").replace(
                    "Create before major work", "UNCONFIRMED USAGE"
                ),
                encoding="utf-8",
            )

            context = session_start({"cwd": temporary})["hookSpecificOutput"]["additionalContext"]

            self.assertIn("Process Hub is not active", context)
            self.assertNotIn("UNCONFIRMED USAGE", context)

    def test_pre_tool_use_denies_explicit_excluded_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._enabled_project(temporary)

            result = pre_tool_use(
                {
                    "cwd": temporary,
                    "tool_name": "Read",
                    "tool_input": {"file_path": str(Path(temporary) / ".env")},
                }
            )

            output = result["hookSpecificOutput"]
            self.assertEqual("deny", output["permissionDecision"])
            self.assertNotIn(".env", output["permissionDecisionReason"])

    def test_pre_tool_use_does_not_claim_to_parse_opaque_shell_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._enabled_project(temporary)

            result = pre_tool_use(
                {
                    "cwd": temporary,
                    "tool_name": "Bash",
                    "tool_input": {"command": "Get-Content .env"},
                }
            )

            self.assertEqual({}, result)

    def test_lens_directive_is_complete_prefix_only_and_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._enabled_project(temporary)
            for prompt in ("@lens explain app", "  @LENS\nexplain app"):
                with self.subTest(prompt=prompt):
                    result = user_prompt_submit({"cwd": temporary, "prompt": prompt})
                    context = result["hookSpecificOutput"]["additionalContext"]
                    self.assertIn("explicit @lens route", context)
                    self.assertIn("only automatic Implementation Lens trigger", context)
            for prompt in ("@lensfoo explain app", "please use @lens explain app"):
                with self.subTest(prompt=prompt):
                    self.assertEqual(
                        {}, user_prompt_submit({"cwd": temporary, "prompt": prompt})
                    )

    def test_lens_directive_preempts_prompt_copilot_and_routes_empty_query(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary, mode="strict", automatic=True)

            result = user_prompt_submit({"cwd": temporary, "prompt": "@lens"})
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertIn("query is empty", context)
            self.assertIn("Do not send this message through Prompt Copilot", context)
            self.assertNotIn("STRICT PREFLIGHT GATE", context)

    def test_active_lens_is_named_at_session_start(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._enabled_project(temporary)
            lens = ImplementationLensService()
            self.assertTrue(lens.initialize(temporary)["ok"])
            self.assertTrue(lens.set_enabled(True, True, temporary)["ok"])

            context = session_start({"cwd": temporary})["hookSpecificOutput"]["additionalContext"]

            self.assertIn("leading @lens token", context)
            self.assertIn("$vibe-secretary-implementation-lens", context)

    def test_user_prompt_submit_is_silent_when_automatic_mode_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary, automatic=False)

            self.assertEqual(
                {},
                user_prompt_submit({"cwd": temporary, "prompt": "实现 src/app.py"}),
            )

    def test_pc_forces_current_prompt_when_automatic_mode_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary, mode="strict", automatic=False)

            result = user_prompt_submit(
                {"cwd": temporary, "prompt": "  @PC\n根据plan-001完成阶段1"}
            )
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertIn("STRICT PREFLIGHT GATE", context)
            self.assertIn("leading @pc deterministically forced", context)
            self.assertIn("Treat @pc as control metadata", context)

    def test_pc_does_not_bypass_prompt_copilot_module_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._enabled_project(temporary)
            service = PromptCopilotService()
            self.assertTrue(service.initialize(temporary)["ok"])

            result = user_prompt_submit(
                {"cwd": temporary, "prompt": "@pc 实施 src/app.py"}
            )

            self.assertEqual({}, result)

    def test_pc_forces_non_development_prompt_without_keyword_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary)

            result = user_prompt_submit(
                {"cwd": temporary, "prompt": "@pc 请处理这件事"}
            )

            self.assertIn("hookSpecificOutput", result)
            self.assertIn(
                "leading @pc deterministically forced",
                result["hookSpecificOutput"]["additionalContext"],
            )

    def test_npc_bypasses_current_development_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary, mode="strict", automatic=True)

            result = user_prompt_submit(
                {"cwd": temporary, "prompt": "@npc 实施 src/app.py 并添加测试"}
            )

            self.assertEqual({}, result)

    def test_reported_implementation_prompt_triggers_strict_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary, mode="strict")

            result = user_prompt_submit(
                {"cwd": temporary, "prompt": "根据plan-001，实施阶段1的工作"}
            )

            self.assertIn(
                "STRICT PREFLIGHT GATE",
                result["hookSpecificOutput"]["additionalContext"],
            )

    def test_user_prompt_submit_skips_non_development_chat(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary)

            self.assertEqual(
                {},
                user_prompt_submit({"cwd": temporary, "prompt": "今天天气怎么样？"}),
            )

    def test_user_prompt_submit_injects_bounded_sourced_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("def build_widget(): pass", encoding="utf-8")
            self._active_prompt_project(temporary)

            result = user_prompt_submit(
                {"cwd": temporary, "prompt": "实现 src/app.py 的 build_widget 并添加测试"}
            )
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertEqual("UserPromptSubmit", result["hookSpecificOutput"]["hookEventName"])
            self.assertIn("repo:src/app.py", context)
            self.assertLessEqual(len(context), 2400)

    def test_user_prompt_submit_strict_injects_conversational_preflight_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary, mode="strict")

            result = user_prompt_submit({"cwd": temporary, "prompt": "实现登录功能"})
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertNotIn("decision", result)
            self.assertIn("STRICT PREFLIGHT GATE", context)
            self.assertIn("do not call tools", context)
            self.assertIn("1) adopt the optimized task", context)
            self.assertIn("4) cancel", context)
            self.assertIn("Never use a tool-permission or Allow prompt", context)
            self.assertIn("- Required questions:", context)
            self.assertIn("[scope]", context)
            self.assertIn("[acceptance]", context)



    def test_user_prompt_submit_quick_executes_without_full_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary, mode="quick")

            result = user_prompt_submit({"cwd": temporary, "prompt": "实现登录功能"})
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertIn("QUICK EXECUTION", context)
            self.assertIn("continue execution in this same turn", context)
            self.assertIn("Do not stop for optional questions", context)
            self.assertIn("normal safety, permission, and tool communication", context)

    def test_user_prompt_submit_review_summarizes_then_executes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._active_prompt_project(temporary, mode="review")

            result = user_prompt_submit({"cwd": temporary, "prompt": "实现登录功能"})
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertIn("REVIEW THEN EXECUTE", context)
            self.assertIn("Prompt Copilot optimization summary", context)
            self.assertIn("without asking for adoption", context)
            self.assertIn("Required safety clarifications", context)

    def test_user_prompt_submit_audit_contains_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("Widget feature", encoding="utf-8")
            self._active_prompt_project(temporary)
            data_root = root / "plugin-data"
            previous = os.environ.get("PLUGIN_DATA")
            os.environ["PLUGIN_DATA"] = str(data_root)
            try:
                secret = "super-secret-prompt-value"
                result = user_prompt_submit(
                    {"cwd": temporary, "prompt": f"实现 Widget {secret} 并添加测试"}
                )
            finally:
                if previous is None:
                    os.environ.pop("PLUGIN_DATA", None)
                else:
                    os.environ["PLUGIN_DATA"] = previous

            self.assertIn("hookSpecificOutput", result)
            raw = (data_root / "foundation-audit.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(secret, raw)
            record = json.loads(raw.strip())
            self.assertEqual(
                {
                    "timestamp",
                    "event",
                    "tool",
                    "decision",
                    "reason",
                    "mode",
                    "source_count",
                },
                set(record),
            )
            self.assertEqual("review", record["mode"])
            self.assertGreaterEqual(record["source_count"], 1)
    def test_user_prompt_submit_completes_within_small_fixture_latency_budget(self) -> None:
        import time

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            for index in range(20):
                (root / "src" / f"module_{index}.py").write_text(
                    f"def feature_{index}(): pass",
                    encoding="utf-8",
                )
            self._active_prompt_project(temporary)
            started = time.monotonic()

            result = user_prompt_submit(
                {"cwd": temporary, "prompt": "实现 src/module_4.py 的 feature_4 并添加测试"}
            )

            self.assertIn("hookSpecificOutput", result)
            self.assertLess(time.monotonic() - started, 2.0)

if __name__ == "__main__":
    unittest.main()
