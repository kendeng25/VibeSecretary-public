from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "src"))


class PackagingTests(unittest.TestCase):
    def test_manifest_identity_and_mcp_declaration_match(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        marketplace = json.loads(
            (REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))

        self.assertEqual("vibe-secretary", manifest["name"])
        self.assertEqual("./.mcp.json", manifest["mcpServers"])
        self.assertEqual("vibe-secretary", marketplace["plugins"][0]["name"])
        self.assertEqual("./plugins/vibe-secretary", marketplace["plugins"][0]["source"]["path"])
        foundation = mcp_config["mcpServers"]["foundation"]
        mcp_entrypoint = Path(foundation["command"])
        self.assertTrue(mcp_entrypoint.is_absolute())
        self.assertEqual(REPOSITORY_ROOT / ".venv", mcp_entrypoint.parents[1])
        self.assertEqual("vibe-secretary-mcp.exe", mcp_entrypoint.name)
        self.assertEqual([], foundation["args"])
        self.assertNotIn("PLUGIN_ROOT", json.dumps(mcp_config))

        runtime = json.loads(
            (PLUGIN_ROOT / "runtime" / "runtime.json").read_text(encoding="utf-8")
        )
        runtime_python = Path(runtime["python_executable"])
        self.assertEqual(1, runtime["schema_version"])
        self.assertTrue(runtime_python.is_absolute())
        self.assertEqual(REPOSITORY_ROOT / ".venv", runtime_python.parents[1])

    def test_runtime_imports_do_not_reference_refs_project(self) -> None:
        source_files = list((PLUGIN_ROOT / "src").rglob("*.py"))
        source_files += list((PLUGIN_ROOT / "hooks").rglob("*.py"))
        source_files += list((PLUGIN_ROOT / "scripts").rglob("*.py"))

        for source_file in source_files:
            tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
            imported_modules: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_modules.append(node.module)
            for module in imported_modules:
                self.assertFalse(module == "refs" or module.startswith("refs."), source_file)



    def test_prompt_copilot_plugin_metadata_and_hook_are_packaged(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        prompt_hooks = hooks["hooks"]["UserPromptSubmit"]

        self.assertIn("Prompt optimization", manifest["interface"]["capabilities"])
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 3)
        self.assertTrue(
            (PLUGIN_ROOT / "skills" / "vibe-secretary-prompt-copilot" / "SKILL.md").is_file()
        )
        self.assertEqual(1, len(prompt_hooks))
        self.assertNotIn("matcher", prompt_hooks[0])
        handler = prompt_hooks[0]["hooks"][0]
        self.assertEqual(10, handler["timeout"])
        self.assertEqual(900, handler["additionalContextLimit"])
        self.assertIn("%PLUGIN_ROOT%\\scripts\\run_hook.cmd", handler["commandWindows"])
        self.assertIn("user-prompt-submit", handler["commandWindows"])

        for event_groups in hooks["hooks"].values():
            for group in event_groups:
                for command_handler in group["hooks"]:
                    command_windows = command_handler.get("commandWindows", "")
                    self.assertNotIn(str(REPOSITORY_ROOT), command_windows)
                    self.assertNotIn(".venv", command_windows)

    def test_implementation_lens_assets_and_metadata_are_packaged(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        skill = PLUGIN_ROOT / "skills" / "vibe-secretary-implementation-lens"
        self.assertIn("Implementation stories", manifest["interface"]["capabilities"])
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertTrue((skill / "agents" / "openai.yaml").is_file())
        self.assertIn(
            "allow_implicit_invocation: false",
            (skill / "agents" / "openai.yaml").read_text(encoding="utf-8"),
        )
        expected_feature_docs = {
            "process-hub.md",
            "process-hub_zh.md",
            "prompt-copilot.md",
            "prompt-copilot_zh.md",
            "implementation-lens.md",
            "implementation-lens_zh.md",
        }
        packaged_feature_docs = {
            path.name for path in (PLUGIN_ROOT / "docs").glob("*.md")
        }
        self.assertEqual(expected_feature_docs, packaged_feature_docs)

    def test_implementation_runtime_does_not_execute_projects_or_use_network_clients(self) -> None:
        implementation_files = list(
            (PLUGIN_ROOT / "src" / "vibe_secretary").glob("implementation_*.py")
        )
        forbidden = {
            "subprocess",
            "runpy",
            "importlib",
            "requests",
            "httpx",
            "urllib",
            "socket",
            "openai",
        }
        for source_file in implementation_files:
            tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertTrue(forbidden.isdisjoint(imported), source_file)

    def test_host_only_prompt_runtime_has_no_network_client_imports(self) -> None:
        prompt_files = list((PLUGIN_ROOT / "src" / "vibe_secretary").glob("prompt_*.py"))
        forbidden = {"requests", "httpx", "urllib", "socket", "openai"}

        for source_file in prompt_files:
            tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertTrue(forbidden.isdisjoint(imported), source_file)
if __name__ == "__main__":
    unittest.main()
