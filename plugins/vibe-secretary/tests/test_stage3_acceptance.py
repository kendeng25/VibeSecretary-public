from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vibe_secretary.hooks import user_prompt_submit
from vibe_secretary.implementation_service import ImplementationLensService
from vibe_secretary.service import FoundationService


class Stage3AcceptanceTests(unittest.TestCase):
    def test_explicit_lens_consumer_workflow_builds_model_and_semantic_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "repository.py").write_text(
                "class UserRepository:\n"
                "    def load(self, user_id):\n"
                "        return {'id': user_id}\n",
                encoding="utf-8",
            )
            (root / "src" / "service.py").write_text(
                "from repository import UserRepository\n\n"
                "def authenticate(user_id):\n"
                "    return UserRepository().load(user_id)\n",
                encoding="utf-8",
            )
            (root / "src" / "app.py").write_text(
                "from service import authenticate\n\n"
                "def login_route(user_id):\n"
                "    return authenticate(user_id)\n\n"
                "def main():\n"
                "    return login_route('demo')\n",
                encoding="utf-8",
            )
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            foundation = FoundationService()
            foundation.initialize_project(temporary)
            foundation.set_project_enabled(True, True, temporary)
            lens = ImplementationLensService()
            lens.initialize(temporary)
            lens.set_enabled(True, True, temporary)

            route = user_prompt_submit(
                {
                    "cwd": temporary,
                    "prompt": "@lens 登录请求如何进入服务并访问仓库，symbol 颗粒度",
                }
            )
            context = route["hookSpecificOutput"]["additionalContext"]
            self.assertIn("explicit @lens route", context)
            self.assertIn("Do not send this message through Prompt Copilot", context)
            self.assertIn("reusable project model", context)

            inspected = lens.inspect_model(temporary)
            self.assertTrue(inspected["ok"], inspected)
            self.assertEqual("missing", inspected["data"]["project_model"]["status"])
            ids = {
                node["qualified_name"]: node["id"]
                for node in inspected["data"]["evidence_package"]["nodes"]
            }
            modeled = lens.update_model(
                [
                    {
                        "id": "overview",
                        "kind": "overview",
                        "title": "Login request architecture",
                        "summary": "The route delegates authentication to a service backed by a repository.",
                        "evidence": [
                            {
                                "kind": "node",
                                "ref_id": ids["app.login_route"],
                                "claim": "HTTP-facing login entry.",
                            },
                            {
                                "kind": "node",
                                "ref_id": ids["repository.UserRepository.load"],
                                "claim": "Storage boundary.",
                            },
                        ],
                    }
                ],
                "complete",
                project_root=temporary,
            )
            self.assertTrue(modeled["ok"], modeled)

            story = {
                "stages": [
                    {
                        "id": "receive-login",
                        "title": "Receive login request",
                        "summary": "The route accepts the user identifier.",
                        "role": "entry",
                        "basis": "fact",
                        "evidence": [
                            {"kind": "node", "ref_id": ids["app.login_route"]}
                        ],
                    },
                    {
                        "id": "authenticate",
                        "title": "Authenticate user",
                        "summary": "The service coordinates credential lookup.",
                        "role": "service",
                        "basis": "interpretation",
                        "evidence": [
                            {"kind": "node", "ref_id": ids["service.authenticate"]}
                        ],
                    },
                    {
                        "id": "load-user",
                        "title": "Load repository record",
                        "summary": "The repository returns the matching user record.",
                        "role": "storage",
                        "basis": "fact",
                        "evidence": [
                            {
                                "kind": "node",
                                "ref_id": ids["repository.UserRepository.load"],
                            }
                        ],
                    },
                ],
                "transitions": [
                    {
                        "source": "receive-login",
                        "target": "authenticate",
                        "kind": "next",
                        "label": "delegate",
                        "basis": "interpretation",
                        "evidence": [
                            {"kind": "node", "ref_id": ids["app.login_route"]}
                        ],
                    },
                    {
                        "source": "authenticate",
                        "target": "load-user",
                        "kind": "next",
                        "label": "lookup",
                        "basis": "interpretation",
                        "evidence": [
                            {"kind": "node", "ref_id": ids["service.authenticate"]}
                        ],
                    },
                ],
                "omitted_summary": "The process entrypoint is omitted because it does not change the login path.",
                "limitations": ["Static analysis does not prove runtime dependency dispatch."],
            }
            rendered = lens.render(
                "login_route authenticate UserRepository load",
                "symbol",
                "Login implementation flow",
                temporary,
                story=story,
            )
            self.assertTrue(rendered["ok"], rendered)
            data = rendered["data"]
            self.assertEqual("passed", data["read_only_check"]["status"])
            self.assertEqual("fresh", data["project_model"]["status"])
            self.assertEqual(3, data["storyboard"]["stages"])
            self.assertEqual(2, data["storyboard"]["transitions"])
            self.assertFalse(data["storyboard"]["fallback"])
            self.assertTrue((root / data["markdown"]).is_file())
            self.assertTrue((root / data["html"]).is_file())
            self.assertTrue(data["markdown"].startswith("ImplementationLens/reports/symbol/"))
            self.assertTrue(data["html"].startswith("ImplementationLens/reports/symbol/"))
            self.assertTrue(
                (root / "ImplementationLens/_project_model/manifest.json").is_file()
            )

            for relative, content in before.items():
                self.assertEqual(content, (root / relative).read_bytes(), relative)
            self.assertEqual(
                {},
                user_prompt_submit({"cwd": temporary, "prompt": "解释登录实现"}),
                "ordinary prompts must not trigger Lens when Prompt Copilot is inactive",
            )


if __name__ == "__main__":
    unittest.main()
