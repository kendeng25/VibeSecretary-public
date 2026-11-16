from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import ProjectConfig  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.scope import ScopePolicy  # noqa: E402


class ScopePolicyTests(unittest.TestCase):
    def _policy(self, root: Path, patterns: str) -> ScopePolicy:
        (root / ".vibesecretaryignore").write_text(patterns, encoding="utf-8")
        return ScopePolicy(ProjectPaths(root.resolve()), ProjectConfig())

    def test_gitignore_patterns_exclude_and_reinclude_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy = self._policy(root, "private/\n!private/public.txt\n")

            self.assertFalse(policy.decide("private/secret.txt").allowed)
            self.assertTrue(policy.decide("private/public.txt").allowed)
            self.assertTrue(policy.decide("src/app.py").allowed)

    def test_outside_project_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy = self._policy(root, "")

            decision = policy.decide(root.parent / "outside.txt")

            self.assertFalse(decision.allowed)
            self.assertEqual("outside_project", decision.reason)

    def test_scope_digest_detects_changes_after_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initial = self._policy(root, ".env\n")
            confirmed = ProjectConfig(enabled=True, scope_digest=initial.digest)
            policy = ScopePolicy(ProjectPaths(root.resolve()), confirmed)
            self.assertTrue(policy.effective_enabled)

            (root / ".vibesecretaryignore").write_text(".env\nsecrets/\n", encoding="utf-8")
            changed = ScopePolicy(ProjectPaths(root.resolve()), confirmed)

            self.assertFalse(changed.confirmed)
            self.assertFalse(changed.effective_enabled)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_symlink_escape_is_denied_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as outside:
            root = Path(project)
            link = root / "escape"
            try:
                link.symlink_to(Path(outside), target_is_directory=True)
            except OSError:
                self.skipTest("creating a symlink is not permitted")
            policy = self._policy(root, "")

            self.assertFalse(policy.decide(link / "secret.txt").allowed)


if __name__ == "__main__":
    unittest.main()
