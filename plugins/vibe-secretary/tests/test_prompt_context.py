from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import load_config  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.prompt_analysis import analyze_intent  # noqa: E402
from vibe_secretary.prompt_config import PromptCopilotConfig  # noqa: E402
from vibe_secretary.prompt_context import collect_context  # noqa: E402
from vibe_secretary.scope import ScopePolicy  # noqa: E402
from vibe_secretary.service import FoundationService  # noqa: E402


class PromptContextTests(unittest.TestCase):
    def _context(self, temporary: str):
        foundation = FoundationService()
        foundation.initialize_project(temporary)
        foundation.set_project_enabled(True, True, temporary)
        paths = ProjectPaths(Path(temporary).resolve())
        project_config = load_config(paths)
        return paths, project_config, ScopePolicy(paths, project_config)

    def test_repository_context_is_sourced_budgeted_and_sensitive_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "auth.py").write_text(
                "API_TOKEN = 'must-not-leak'\n"
                "AUTHORIZATION = 'Bearer abcdefghijklmnopqrstuvwxyz'\n"
                "def authenticate_user():\n    return 'session'\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("TOKEN=never-return-this", encoding="utf-8")
            (root / ".ssh").mkdir()
            (root / ".ssh" / "config").write_text("Host private-host", encoding="utf-8")
            paths, project_config, policy = self._context(temporary)
            config = PromptCopilotConfig(
                context_char_budget=300,
                hook_context_char_budget=200,
                per_source_char_budget=200,
                max_sources=3,
            )
            intent = analyze_intent("修复 src/auth.py 的 authenticate_user 登录逻辑并运行测试", 1000)

            results, evidence, budget = collect_context(
                paths=paths,
                project_config=project_config,
                policy=policy,
                config=config,
                intent=intent,
                hook=False,
            )

            self.assertEqual("repository", results[0].source)
            self.assertTrue(any(item.path == "src/auth.py" for item in evidence))
            serialized = str([item.to_dict() for item in evidence])
            self.assertNotIn("never-return-this", serialized)
            self.assertNotIn("must-not-leak", serialized)
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz", serialized)
            self.assertIn("[REDACTED]", serialized)
            self.assertIn("authenticate_user", serialized)
            self.assertNotIn("private-host", serialized)
            self.assertLessEqual(budget["characters_used"], 300)
            self.assertTrue(budget["token_estimate_is_approximate"])
            self.assertIn(
                "implementation_lens_unavailable",
                [item.degradation for item in results],
            )

    def test_scope_excluded_file_is_never_returned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "private").mkdir()
            (root / "private" / "auth.py").write_text("authenticate secret", encoding="utf-8")
            foundation = FoundationService()
            foundation.initialize_project(temporary)
            scope = root / ".vibesecretaryignore"
            scope.write_text(scope.read_text(encoding="utf-8") + "private/\n", encoding="utf-8")
            foundation.set_project_enabled(True, True, temporary)
            paths = ProjectPaths(root.resolve())
            project_config = load_config(paths)
            policy = ScopePolicy(paths, project_config)

            _, evidence, _ = collect_context(
                paths=paths,
                project_config=project_config,
                policy=policy,
                config=PromptCopilotConfig(),
                intent=analyze_intent("修复 private/auth.py", 1000),
                hook=False,
            )

            self.assertFalse(any(item.path.startswith("private/") for item in evidence))


if __name__ == "__main__":
    unittest.main()
