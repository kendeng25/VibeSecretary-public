from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from vibe_secretary.local_runtime import (
    LocalRuntimeConfigurationError,
    configure_local_runtime,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class LocalRuntimeConfigurationTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        repository_root = root / "Repository With Spaces"
        plugin_root = repository_root / "plugins" / "vibe-secretary"
        (plugin_root / "hooks").mkdir(parents=True)
        (plugin_root / "scripts").mkdir()
        if os.name == "nt":
            environment_bin = repository_root / ".venv" / "Scripts"
            python_executable = environment_bin / "python.exe"
            mcp_entrypoint = environment_bin / "vibe-secretary-mcp.exe"
        else:
            environment_bin = repository_root / ".venv" / "bin"
            python_executable = environment_bin / "python"
            mcp_entrypoint = environment_bin / "vibe-secretary-mcp"
        environment_bin.mkdir(parents=True)
        python_executable.write_bytes(b"")
        mcp_entrypoint.write_bytes(b"")
        (plugin_root / "scripts" / "run_hook.cmd").write_text(
            "@echo off\n",
            encoding="ascii",
        )
        (plugin_root / "scripts" / "run_hook.ps1").write_text(
            "param([string]$Hook)\n",
            encoding="utf-8",
        )
        (plugin_root / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "foundation": {
                            "command": "vibe-secretary-mcp",
                            "args": [],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        hook_groups = {}
        for event, script_name in {
            "SessionStart": "session_start.py",
            "PreToolUse": "pre_tool_use.py",
            "UserPromptSubmit": "user_prompt_submit.py",
        }.items():
            hook_groups[event] = [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python "${{PLUGIN_ROOT}}/hooks/{script_name}"',
                            "commandWindows": f'python "${{PLUGIN_ROOT}}\\hooks\\{script_name}"',
                        }
                    ]
                }
            ]
        (plugin_root / "hooks" / "hooks.json").write_text(
            json.dumps({"description": "fixture", "hooks": hook_groups}),
            encoding="utf-8",
        )
        return repository_root, plugin_root, python_executable, mcp_entrypoint

    def test_centralizes_runtime_and_uses_relative_windows_hook_launchers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_root, plugin_root, python_executable, mcp_entrypoint = self._fixture(
                Path(temporary_directory)
            )
            result = configure_local_runtime(repository_root, python_executable)

            runtime = json.loads(
                (plugin_root / "runtime" / "runtime.json").read_text(encoding="utf-8")
            )
            self.assertEqual(1, runtime["schema_version"])
            self.assertEqual(str(python_executable), runtime["python_executable"])

            mcp = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
            foundation = mcp["mcpServers"]["foundation"]
            self.assertEqual(str(mcp_entrypoint), foundation["command"])
            self.assertEqual([], foundation["args"])

            hook_path = plugin_root / "hooks" / "hooks.json"
            hooks = json.loads(hook_path.read_text(encoding="utf-8"))["hooks"]
            expected_launch_names = {
                "SessionStart": "session-start",
                "PreToolUse": "pre-tool-use",
                "UserPromptSubmit": "user-prompt-submit",
            }
            for event, launch_name in expected_launch_names.items():
                command = hooks[event][0]["hooks"][0]["commandWindows"]
                self.assertEqual(
                    'cmd.exe /d /c call "%PLUGIN_ROOT%\\scripts\\run_hook.cmd" '
                    + launch_name,
                    command,
                )
                self.assertNotIn(str(repository_root), command)
                self.assertNotIn(".venv", command)
            self.assertEqual(str(python_executable), result["python_executable"])
            self.assertEqual(str(mcp_entrypoint), result["mcp_entrypoint"])

    def test_repeated_configuration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_root, plugin_root, python_executable, _ = self._fixture(
                Path(temporary_directory)
            )
            configure_local_runtime(repository_root, python_executable)
            paths = (
                plugin_root / ".mcp.json",
                plugin_root / "hooks" / "hooks.json",
                plugin_root / "runtime" / "runtime.json",
            )
            first_rendering = [path.read_text(encoding="utf-8") for path in paths]

            configure_local_runtime(repository_root, python_executable)

            self.assertEqual(
                first_rendering,
                [path.read_text(encoding="utf-8") for path in paths],
            )

    def test_rejects_python_outside_repository_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository_root, _, _, _ = self._fixture(root)
            outside_python = root / "other-python.exe"
            outside_python.write_bytes(b"")

            with self.assertRaisesRegex(
                LocalRuntimeConfigurationError,
                "must be inside",
            ):
                configure_local_runtime(repository_root, outside_python)

    def test_rejects_missing_expected_hook(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_root, plugin_root, python_executable, _ = self._fixture(
                Path(temporary_directory)
            )
            hook_path = plugin_root / "hooks" / "hooks.json"
            hooks = json.loads(hook_path.read_text(encoding="utf-8"))
            del hooks["hooks"]["PreToolUse"]
            hook_path.write_text(json.dumps(hooks), encoding="utf-8")

            with self.assertRaisesRegex(
                LocalRuntimeConfigurationError,
                "missing PreToolUse",
            ):
                configure_local_runtime(repository_root, python_executable)

    def test_rejects_missing_mcp_console_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_root, _, python_executable, mcp_entrypoint = self._fixture(
                Path(temporary_directory)
            )
            mcp_entrypoint.unlink()

            with self.assertRaisesRegex(
                LocalRuntimeConfigurationError,
                "MCP console entrypoint does not exist",
            ):
                configure_local_runtime(repository_root, python_executable)

    @unittest.skipUnless(os.name == "nt", "Windows Hook launcher test")
    def test_packaged_windows_launcher_executes_all_hooks(self) -> None:
        hooks = json.loads(
            (PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )["hooks"]
        environment = os.environ.copy()
        environment["PLUGIN_ROOT"] = str(PLUGIN_ROOT)
        with tempfile.TemporaryDirectory() as consumer_project:
            for event in ("SessionStart", "PreToolUse", "UserPromptSubmit"):
                command = hooks[event][0]["hooks"][0]["commandWindows"]
                with self.subTest(event=event):
                    hook_input = ""
                    if event == "UserPromptSubmit":
                        hook_input = json.dumps(
                            {
                                "hook_event_name": "UserPromptSubmit",
                                "cwd": consumer_project,
                                "prompt": "@lens explain login",
                                "turn_id": "test-turn",
                            }
                        )
                    result = subprocess.run(
                        command,
                        cwd=consumer_project,
                        env=environment,
                        input=hook_input,
                        text=True,
                        capture_output=True,
                        shell=True,
                        timeout=15,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    if event == "UserPromptSubmit":
                        self.assertTrue(
                            result.stdout.startswith("VibeSecretary Implementation Lens"),
                            result.stdout,
                        )
                        self.assertFalse(result.stdout.lstrip().startswith("{"))


if __name__ == "__main__":
    unittest.main()