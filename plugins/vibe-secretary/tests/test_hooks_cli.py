from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _run_hook(event: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "vibe_secretary.hooks_cli", event],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(cwd),
        timeout=30,
        check=False,
    )


class HookCliTests(unittest.TestCase):
    def test_unknown_event_returns_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "vibe_secretary.hooks_cli", "bogus"],
            input="{}",
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(2, result.returncode)

    def test_session_start_and_pre_tool_use_succeed_on_uninitialized_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            for event in ("session-start", "pre-tool-use"):
                with self.subTest(event=event):
                    result = _run_hook(event, {"cwd": str(cwd)}, cwd)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn(result.stdout.strip(), ("", "{}"))

    def test_user_prompt_submit_routes_lens_directive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            result = _run_hook(
                "user-prompt-submit",
                {"cwd": str(cwd), "prompt": "@lens explain login"},
                cwd,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(
                result.stdout.startswith("VibeSecretary Implementation Lens"),
                result.stdout,
            )
            self.assertFalse(result.stdout.lstrip().startswith("{"))


if __name__ == "__main__":
    unittest.main()
