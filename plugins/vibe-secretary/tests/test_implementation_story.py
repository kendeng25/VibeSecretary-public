from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vibe_secretary.implementation_service import ImplementationLensService
from vibe_secretary.service import FoundationService


class ImplementationStoryTests(unittest.TestCase):
    def _react_project(self, temporary: str) -> tuple[Path, ImplementationLensService, dict]:
        root = Path(temporary)
        (root / "src").mkdir()
        (root / "src/agent.py").write_text(
            "def think(value):\n    return value\n\n"
            "def act(plan):\n    return plan\n\n"
            "def observe(result):\n    return result\n\n"
            "def finish(state):\n    return state\n\n"
            "def run_agent(task):\n"
            "    state = think(task)\n"
            "    while state:\n"
            "        action = act(state)\n"
            "        observation = observe(action)\n"
            "        state = think(observation)\n"
            "        if state == 'done':\n"
            "            return finish(state)\n"
            "    return finish(state)\n\n"
            "def unrelated_helper():\n    return 'not part of the loop'\n",
            encoding="utf-8",
        )
        foundation = FoundationService()
        self.assertTrue(foundation.initialize_project(temporary)["ok"])
        self.assertTrue(foundation.set_project_enabled(True, True, temporary)["ok"])
        service = ImplementationLensService()
        self.assertTrue(service.initialize(temporary)["ok"])
        self.assertTrue(service.set_enabled(True, True, temporary)["ok"])
        inspected = service.inspect_model(temporary)
        self.assertTrue(inspected["ok"], inspected)
        return root, service, inspected

    @staticmethod
    def _ids(inspected: dict) -> dict[str, str]:
        return {
            item["qualified_name"]: item["id"]
            for item in inspected["data"]["evidence_package"]["nodes"]
        }

    def test_react_module_story_is_semantic_minimum_sufficient_and_evidence_linked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service, inspected = self._react_project(temporary)
            ids = self._ids(inspected)
            records = [
                {
                    "id": "overview",
                    "kind": "overview",
                    "title": "ReAct agent overview",
                    "summary": "The agent iterates through thought, action, and observation before completion.",
                    "details": ["The loop returns only through finish."],
                    "evidence": [
                        {"kind": "node", "ref_id": ids["agent.run_agent"], "claim": "Loop coordinator."}
                    ],
                    "related_records": ["react-loop"],
                },
                {
                    "id": "react-loop",
                    "kind": "flow",
                    "title": "ReAct loop",
                    "summary": "run_agent repeatedly plans, acts, and observes.",
                    "evidence": [
                        {"kind": "node", "ref_id": ids["agent.think"], "claim": "Thought step."},
                        {"kind": "node", "ref_id": ids["agent.act"], "claim": "Action step."},
                        {"kind": "node", "ref_id": ids["agent.observe"], "claim": "Observation step."},
                    ],
                    "related_records": ["overview"],
                },
            ]
            modeled = service.update_model(records, "complete", project_root=temporary)
            self.assertTrue(modeled["ok"], modeled)
            story = {
                "stages": [
                    {
                        "id": "receive-goal",
                        "title": "接收目标",
                        "summary": "The coordinator accepts the task and initializes loop state.",
                        "role": "input",
                        "basis": "interpretation",
                        "evidence": [{"kind": "node", "ref_id": ids["agent.run_agent"], "claim": "Task enters here."}],
                    },
                    {
                        "id": "think",
                        "title": "Think / 规划",
                        "summary": "The implementation derives or revises the next plan.",
                        "role": "reasoning",
                        "basis": "interpretation",
                        "evidence": [{"kind": "node", "ref_id": ids["agent.think"], "claim": "Planning function."}],
                    },
                    {
                        "id": "act",
                        "title": "Act / 执行动作",
                        "summary": "The selected plan is executed as an action.",
                        "role": "action",
                        "basis": "interpretation",
                        "evidence": [{"kind": "node", "ref_id": ids["agent.act"], "claim": "Action function."}],
                    },
                    {
                        "id": "observe",
                        "title": "Observe / 处理结果",
                        "summary": "The action result becomes the next observation.",
                        "role": "observation",
                        "basis": "interpretation",
                        "evidence": [{"kind": "node", "ref_id": ids["agent.observe"], "claim": "Observation function."}],
                    },
                    {
                        "id": "finish",
                        "title": "完成或继续",
                        "summary": "The loop either returns a finished state or feeds the observation back into thought.",
                        "role": "decision",
                        "basis": "interpretation",
                        "evidence": [{"kind": "node", "ref_id": ids["agent.finish"], "claim": "Completion boundary."}],
                    },
                ],
                "transitions": [
                    {"source": "receive-goal", "target": "think", "kind": "next", "label": "initialize", "basis": "interpretation", "evidence": [{"kind": "node", "ref_id": ids["agent.run_agent"]}]},
                    {"source": "think", "target": "act", "kind": "next", "label": "select action", "basis": "interpretation", "evidence": [{"kind": "node", "ref_id": ids["agent.run_agent"]}]},
                    {"source": "act", "target": "observe", "kind": "next", "label": "produce result", "basis": "interpretation", "evidence": [{"kind": "node", "ref_id": ids["agent.run_agent"]}]},
                    {"source": "observe", "target": "think", "kind": "loop", "label": "continue iteration", "basis": "interpretation", "evidence": [{"kind": "node", "ref_id": ids["agent.run_agent"]}]},
                    {"source": "observe", "target": "finish", "kind": "complete", "label": "completion condition", "basis": "interpretation", "evidence": [{"kind": "node", "ref_id": ids["agent.finish"]}]},
                ],
                "omitted_summary": "Unrelated helpers and low-level syntax are omitted because they do not change the ReAct loop explanation.",
                "limitations": ["Static analysis does not prove the runtime value of the completion condition."],
            }

            rendered = service.render(
                "explain the agent architecture",
                "module",
                "ReAct implementation",
                temporary,
                story=story,
            )

            self.assertTrue(rendered["ok"], rendered)
            data = rendered["data"]
            self.assertFalse(data["storyboard"]["fallback"])
            self.assertEqual(5, data["storyboard"]["stages"])
            self.assertEqual("fresh", data["project_model"]["status"])
            html = (root / data["html"]).read_text(encoding="utf-8")
            markdown = (root / data["markdown"]).read_text(encoding="utf-8")
            for label in ("Think / 规划", "Act / 执行动作", "Observe / 处理结果"):
                self.assertIn(label, html)
                self.assertIn(label, markdown)
            self.assertIn('class="transition loop"', html)
            self.assertIn('<details class="stage"', html)
            self.assertNotIn("unrelated_helper", html)
            self.assertNotIn("<svg", html)
            self.assertIn("Unrelated helpers", html)

    def test_story_rejects_unknown_evidence_and_does_not_invent_a_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, service, inspected = self._react_project(temporary)
            ids = self._ids(inspected)
            story = {
                "stages": [
                    {
                        "id": "request",
                        "title": "Validate request",
                        "summary": "A non-ReAct request stage.",
                        "role": "validation",
                        "basis": "interpretation",
                        "evidence": [{"kind": "node", "ref_id": ids["agent.run_agent"]}],
                    }
                ],
                "transitions": [],
                "omitted_summary": "Only the requested validation concern is shown.",
            }
            rendered = service.render(
                "validate request",
                "module",
                "Validation flow",
                temporary,
                story=story,
            )
            self.assertTrue(rendered["ok"], rendered)
            html = (root / rendered["data"]["html"]).read_text(encoding="utf-8")
            self.assertIn("Validate request", html)
            self.assertNotIn("Think / 规划", html)

            story["stages"][0]["evidence"][0]["ref_id"] = "node:missing"
            rejected = service.render(
                "another validation request",
                "module",
                "Invalid evidence",
                temporary,
                story=story,
            )
            self.assertFalse(rejected["ok"])
            self.assertEqual("invalid_implementation_evidence", rejected["error"]["code"])


if __name__ == "__main__":
    unittest.main()
