from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.errors import FoundationError  # noqa: E402
from vibe_secretary.prompt_analysis import (  # noqa: E402
    PromptDirective,
    analyze_gaps,
    analyze_intent,
    parse_prompt_directive,
)
from vibe_secretary.prompt_models import PromptMode  # noqa: E402


class PromptAnalysisTests(unittest.TestCase):
    def test_leading_control_directives_are_deterministic_and_prefix_only(self) -> None:
        cases = (
            ("@pc implement login", PromptDirective.FORCE, "implement login"),
            ("  @PC\n实施阶段1", PromptDirective.FORCE, "实施阶段1"),
            ("@npc implement login", PromptDirective.BYPASS, "implement login"),
            ("@NpC\n直接执行", PromptDirective.BYPASS, "直接执行"),
            ("mention @pc in docs", PromptDirective.AUTOMATIC, "mention @pc in docs"),
            ("someone@pc.com", PromptDirective.AUTOMATIC, "someone@pc.com"),
            ("@pcc implement login", PromptDirective.AUTOMATIC, "@pcc implement login"),
            ("@pc @npc implement login", PromptDirective.FORCE, "@npc implement login"),
        )

        for prompt, expected_directive, expected_task in cases:
            with self.subTest(prompt=prompt):
                directive, task = parse_prompt_directive(prompt)
                self.assertIs(expected_directive, directive)
                self.assertEqual(expected_task, task)

    def test_implementation_word_is_recognized_as_development_action(self) -> None:
        intent = analyze_intent("根据plan-001，实施阶段1的工作", 1000)

        self.assertEqual("implement", intent.action)
        self.assertTrue(intent.development_request)

    def test_intent_extracts_action_target_keywords_and_risks(self) -> None:
        intent = analyze_intent(
            "请重构 src/service.py 并删除旧接口，同时更新依赖和测试。",
            1000,
        )

        self.assertEqual("refactor", intent.action)
        self.assertIn("src/service.py", intent.targets)
        self.assertIn("destructive_change", intent.risk_flags)
        self.assertIn("dependency_change", intent.risk_flags)
        self.assertTrue(intent.development_request)

    def test_modes_change_question_blocking_not_detected_facts(self) -> None:
        intent = analyze_intent("实现登录功能", 1000)

        quick_gaps, quick_questions = analyze_gaps("实现登录功能", intent, PromptMode.QUICK)
        review_gaps, review_questions = analyze_gaps("实现登录功能", intent, PromptMode.REVIEW)
        strict_gaps, strict_questions = analyze_gaps("实现登录功能", intent, PromptMode.STRICT)

        self.assertEqual(
            [item.code for item in review_gaps],
            [item.code for item in strict_gaps],
        )
        self.assertEqual([item.code for item in quick_gaps], [item.code for item in review_gaps])
        self.assertEqual([], list(quick_questions))
        self.assertFalse(any(item.required for item in review_questions))
        self.assertTrue(any(item.required for item in strict_questions))

    def test_empty_and_oversized_prompts_are_rejected(self) -> None:
        with self.assertRaises(FoundationError) as empty:
            analyze_intent("  ", 100)
        with self.assertRaises(FoundationError) as large:
            analyze_intent("x" * 101, 100)

        self.assertEqual("prompt_empty", empty.exception.code)
        self.assertEqual("prompt_too_large", large.exception.code)


if __name__ == "__main__":
    unittest.main()
