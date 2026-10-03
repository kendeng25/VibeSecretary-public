from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import load_config, save_config  # noqa: E402
from vibe_secretary.hooks import user_prompt_submit  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.process_service import ProcessHubService  # noqa: E402
from vibe_secretary.prompt_config import load_prompt_config, save_prompt_config  # noqa: E402
from vibe_secretary.prompt_models import PromptMode  # noqa: E402
from vibe_secretary.prompt_service import PromptCopilotService  # noqa: E402
from vibe_secretary.providers import ProviderConfig, ProviderMode  # noqa: E402
from vibe_secretary.service import FoundationService  # noqa: E402


class StageFourConsumerAcceptanceTests(unittest.TestCase):
    def test_host_only_prompt_copilot_consumer_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "src" / "auth.py"
            source.parent.mkdir()
            source.write_text(
                "def validate_session(token: str) -> bool:\n    return bool(token)\n",
                encoding="utf-8",
            )
            secret = root / ".env"
            secret.write_text("API_TOKEN=must-not-leak", encoding="utf-8")
            original_source = source.read_bytes()
            original_secret = secret.read_bytes()

            foundation = FoundationService()
            prompt = PromptCopilotService()
            process = ProcessHubService()

            self.assertTrue(foundation.initialize_project(temporary)["ok"])
            self.assertTrue(foundation.set_project_enabled(True, True, temporary)["ok"])
            self.assertTrue(prompt.initialize(temporary)["ok"])
            self.assertTrue(prompt.set_enabled(True, True, temporary)["ok"])

            raw_prompt = "修复 src/auth.py 的 validate_session，并添加测试"
            mode_prompt = "实现登录功能"
            quick = prompt.prepare_review(mode_prompt, "quick", temporary)
            review_modes = prompt.prepare_review(mode_prompt, "review", temporary)
            review = prompt.prepare_review(raw_prompt, "review", temporary)
            strict = prompt.prepare_review(mode_prompt, "strict", temporary)

            self.assertTrue(quick["ok"])
            self.assertEqual([], quick["data"]["questions"])
            self.assertTrue(review_modes["data"]["questions"])
            self.assertTrue(any(item["required"] for item in strict["data"]["questions"]))
            self.assertTrue(any(item["path"] == "src/auth.py" for item in review["data"]["evidence"]))
            serialized_review = str(review["data"])
            self.assertNotIn("must-not-leak", serialized_review)
            self.assertEqual(raw_prompt, review["data"]["original_prompt"])

            self.assertTrue(process.initialize(temporary)["ok"])
            self.assertTrue(process.set_enabled(True, True, temporary)["ok"])
            plan = process.create_document(
                collection="plans",
                title="Session validation plan",
                body="Keep validate_session behavior and add regression tests.",
                tags=["validate_session"],
                apply=True,
                project_root=temporary,
            )
            self.assertTrue(plan["ok"])
            enhanced = prompt.prepare_review(raw_prompt, "review", temporary)
            self.assertTrue(
                any(item["source"] == "process_hub" for item in enhanced["data"]["evidence"])
            )

            paths = ProjectPaths(root.resolve())
            project_config = load_config(paths)
            prompt_config = load_prompt_config(paths, project_config)
            save_prompt_config(
                paths,
                project_config,
                replace(prompt_config, automatic_enabled=True),
            )
            self.assertTrue(prompt.set_enabled(True, True, temporary)["ok"])
            injected = user_prompt_submit({"cwd": temporary, "prompt": raw_prompt})
            self.assertIn("hookSpecificOutput", injected)
            self.assertNotIn("must-not-leak", str(injected))

            project_config = load_config(paths)
            prompt_config = load_prompt_config(paths, project_config)
            save_prompt_config(
                paths,
                project_config,
                replace(
                    prompt_config,
                    default_mode=PromptMode.STRICT,
                ),
            )
            self.assertTrue(prompt.set_enabled(True, True, temporary)["ok"])
            strict_gate = user_prompt_submit({"cwd": temporary, "prompt": "实现登录功能"})
            strict_context = strict_gate["hookSpecificOutput"]["additionalContext"]
            self.assertNotIn("decision", strict_gate)
            self.assertIn("STRICT PREFLIGHT GATE", strict_context)
            self.assertIn("4) cancel", strict_context)

            project_config = load_config(paths)
            save_config(
                paths,
                replace(
                    project_config,
                    provider=ProviderConfig(
                        mode=ProviderMode.BYOK,
                        name="placeholder",
                        api_key_env="PLACEHOLDER_API_KEY",
                    ),
                ),
            )
            unavailable = prompt.prepare_review(raw_prompt, "review", temporary)
            self.assertFalse(unavailable["ok"])
            self.assertEqual("provider_not_implemented", unavailable["error"]["code"])

            self.assertEqual(original_source, source.read_bytes())
            self.assertEqual(original_secret, secret.read_bytes())


if __name__ == "__main__":
    unittest.main()
