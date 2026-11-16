from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_secretary.config import ProjectConfig  # noqa: E402
from vibe_secretary.paths import ProjectPaths  # noqa: E402
from vibe_secretary.process_config import default_process_config  # noqa: E402
from vibe_secretary.process_repository import (  # noqa: E402
    parse_process_markdown,
    render_indexes,
    render_process_markdown,
    scan_process_documents,
)
from vibe_secretary.scope import ScopePolicy  # noqa: E402


class ProcessRepositoryTests(unittest.TestCase):
    def _context(self, root: Path) -> tuple[ProjectPaths, ScopePolicy]:
        (root / ".vibesecretaryignore").write_text("", encoding="utf-8")
        paths = ProjectPaths(root.resolve())
        policy = ScopePolicy(paths, ProjectConfig())
        return paths, policy

    def test_front_matter_round_trip_preserves_unicode_and_relations(self) -> None:
        metadata = {
            "id": "PLAN-0001",
            "type": "plan",
            "title": "配置模型",
            "status": "active",
            "created_at": "2026-08-18",
            "updated_at": "2026-08-18",
            "tags": ["配置"],
            "relates_to": ["ADR-0001"],
        }

        rendered = render_process_markdown(metadata, "# 正文\n")
        parsed, body = parse_process_markdown(rendered)

        self.assertEqual(metadata, parsed)
        self.assertEqual("# 正文\n", body)

    def test_scan_reports_unmanaged_duplicate_and_unknown_relation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths, policy = self._context(root)
            (root / "plans").mkdir()
            (root / "build_hist").mkdir()
            managed = {
                "id": "PLAN-0001",
                "type": "plan",
                "title": "One",
                "status": "active",
                "stage": "stage-1",
                "created_at": "2026-08-18",
                "updated_at": "2026-08-18",
                "relates_to": ["MISSING-0001"],
            }
            content = render_process_markdown(managed, "body")
            first = root / "plans" / "legacy-one.md"
            second = root / "plans" / "legacy-two.md"
            first.write_text(content, encoding="utf-8")
            second.write_text(content, encoding="utf-8")
            (root / "plans" / "notes.md").write_text("plain markdown", encoding="utf-8")

            scan = scan_process_documents(paths, default_process_config(), policy)
            codes = [issue.code for issue in scan.issues]

            self.assertEqual(3, len(scan.documents))
            self.assertIn("missing_front_matter", codes)
            self.assertIn("duplicate_document_id", codes)
            self.assertIn("unknown_relation_target", codes)
            self.assertIn("path_template_mismatch", codes)

    def test_indexes_include_forward_and_reverse_relations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths, policy = self._context(root)
            (root / "plans" / "stage").mkdir(parents=True)
            (root / "build_hist" / "stage" / "task").mkdir(parents=True)
            plan = {
                "id": "PLAN-0001",
                "type": "plan",
                "title": "Plan",
                "status": "active",
                "stage": "stage",
                "created_at": "2026-08-18",
                "updated_at": "2026-08-18",
            }
            build = {
                "id": "BUILD-0001",
                "type": "build_history",
                "title": "Build",
                "status": "completed",
                "stage": "stage",
                "task": "task",
                "created_at": "2026-08-18",
                "updated_at": "2026-08-18",
                "relates_to": ["PLAN-0001"],
            }
            (root / "plans" / "stage" / "PLAN-0001_plan.md").write_text(
                render_process_markdown(plan, ""), encoding="utf-8"
            )
            (root / "build_hist" / "stage" / "task" / "BUILD-0001_build.md").write_text(
                render_process_markdown(build, ""), encoding="utf-8"
            )

            scan = scan_process_documents(paths, default_process_config(), policy)
            json_index, markdown_index = render_indexes(paths, default_process_config(), scan)

            self.assertIn('"referenced_by": [\n        "BUILD-0001"', json_index)
            self.assertIn("relates to: PLAN-0001", markdown_index)
            self.assertIn("referenced by: BUILD-0001", markdown_index)

    def test_completed_plan_requires_a_related_build_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths, policy = self._context(root)
            plan_path = root / "plans" / "stage" / "PLAN-0001_completed-work.md"
            plan_path.parent.mkdir(parents=True)
            plan = {
                "id": "PLAN-0001",
                "type": "plan",
                "title": "Completed work",
                "status": "completed",
                "stage": "stage",
                "created_at": "2026-08-18",
                "updated_at": "2026-08-18",
            }
            plan_path.write_text(render_process_markdown(plan, "# Plan\n"), encoding="utf-8")

            first_scan = scan_process_documents(paths, default_process_config(), policy)
            self.assertIn(
                "completed_plan_without_build_history",
                {issue.code for issue in first_scan.issues},
            )

            build_path = root / "build_hist" / "stage" / "task" / "BUILD-0001_build.md"
            build_path.parent.mkdir(parents=True)
            build = {
                "id": "BUILD-0001",
                "type": "build_history",
                "title": "Completed work implementation",
                "status": "completed",
                "stage": "stage",
                "task": "task",
                "created_at": "2026-08-18",
                "updated_at": "2026-08-18",
                "relates_to": ["PLAN-0001"],
            }
            build_path.write_text(render_process_markdown(build, "# Build\n"), encoding="utf-8")

            second_scan = scan_process_documents(paths, default_process_config(), policy)
            self.assertNotIn(
                "completed_plan_without_build_history",
                {issue.code for issue in second_scan.issues},
            )


if __name__ == "__main__":
    unittest.main()
