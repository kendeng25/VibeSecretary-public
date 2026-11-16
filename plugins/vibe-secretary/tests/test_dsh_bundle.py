from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class DshBundleTests(unittest.TestCase):
    def test_bundle_manifest_and_patch_are_well_formed(self) -> None:
        package = json.loads((PLUGIN_ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual("module", package["type"])
        self.assertEqual("./dsh/index.js", package["exports"]["."])
        self.assertEqual("./dsh/cordis.patch.yml", package["dsh"]["bundle"]["patch"])

        patch = (PLUGIN_ROOT / "dsh" / "cordis.patch.yml").read_text(encoding="utf-8")
        self.assertIn("@deepseek-ai/dsh-mcp-client", patch)
        self.assertIn("serverName: vibesecretary", patch)
        self.assertIn("transport: stdio", patch)
        self.assertIn("command: vibe-secretary-mcp", patch)
        self.assertIn("@kendeng/vibe-secretary-dsh", patch)

        # The patch must not hardcode any machine-specific absolute path or venv.
        self.assertNotIn("D:\\", patch)
        self.assertNotIn(".venv", patch)

    def test_bundle_assets_are_packaged(self) -> None:
        for relative in (
            "dsh/index.js",
            "dsh/cordis.patch.yml",
            "locale/en.json",
            "locale/zh.json",
            "icon.svg",
        ):
            self.assertTrue((PLUGIN_ROOT / relative).is_file(), relative)
        for skill in (
            "vibe-secretary-foundation",
            "vibe-secretary-process-hub",
            "vibe-secretary-implementation-lens",
            "vibe-secretary-prompt-copilot",
        ):
            self.assertTrue((PLUGIN_ROOT / "skills" / skill / "SKILL.md").is_file(), skill)

    def test_bundle_index_has_valid_js_syntax(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not on PATH")
        result = subprocess.run(
            ["node", "--check", str(PLUGIN_ROOT / "dsh" / "index.js")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
