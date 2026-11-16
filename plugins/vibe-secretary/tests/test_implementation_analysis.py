from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vibe_secretary.config import load_config
from vibe_secretary.implementation_config import (
    default_implementation_config,
    implementation_config_digest,
    save_implementation_config,
)
from vibe_secretary.implementation_models import Granularity
from vibe_secretary.implementation_repository import (
    build_implementation_index,
    select_implementation_view,
)
from vibe_secretary.paths import ProjectPaths
from vibe_secretary.scope import ScopePolicy
from vibe_secretary.service import FoundationService


class ImplementationAnalysisTests(unittest.TestCase):
    def _project(self, temporary: str):
        root = Path(temporary)
        (root / "src").mkdir()
        (root / "src" / "service.py").write_text(
            "class Store:\n"
            "    def save(self, value):\n"
            "        return value\n\n"
            "def build_widget(value):\n"
            "    return Store().save(value)\n",
            encoding="utf-8",
        )
        (root / "src" / "app.py").write_text(
            "from service import build_widget\n\n"
            "class Server:\n"
            "    def tool(self, function):\n"
            "        return function\n\n"
            "server = Server()\n\n"
            "@server.tool\n"
            "def create_widget(value):\n"
            "    return build_widget(value)\n\n"
            "def main():\n"
            "    return create_widget('demo')\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n",
            encoding="utf-8",
        )
        (root / "pyproject.toml").write_text(
            "[project]\nname='fixture'\nversion='0.0.1'\n"
            "[project.scripts]\nfixture='app:main'\n",
            encoding="utf-8",
        )
        foundation = FoundationService()
        foundation.initialize_project(temporary)
        foundation.set_project_enabled(True, True, temporary)
        paths = ProjectPaths(root.resolve())
        project_config = load_config(paths)
        save_implementation_config(paths, project_config, default_implementation_config())
        policy = ScopePolicy(paths, project_config)
        digest = implementation_config_digest(paths, project_config)
        return root, paths, policy, digest

    def test_python_analysis_finds_symbols_entrypoints_imports_calls_and_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, paths, policy, digest = self._project(temporary)
            config = default_implementation_config()

            index = build_implementation_index(paths, policy, config, digest, persist=False)

            names = {node.qualified_name: node for node in index.nodes}
            self.assertIn("app.create_widget", names)
            self.assertIn("service.Store.save", names)
            self.assertTrue(names["app.create_widget"].entrypoint)
            self.assertTrue(names["app.main"].entrypoint)
            edge_pairs = {
                (
                    edge.kind,
                    next(node.qualified_name for node in index.nodes if node.node_id == edge.source_id),
                    next(node.qualified_name for node in index.nodes if node.node_id == edge.target_id),
                )
                for edge in index.edges
            }
            self.assertIn(("calls", "app.create_widget", "service.build_widget"), edge_pairs)
            self.assertIn(("calls", "app.main", "app.create_widget"), edge_pairs)
            self.assertTrue(any(edge.kind == "registers" for edge in index.edges))
            self.assertTrue(
                any(
                    edge.kind == "writes"
                    and next(node.qualified_name for node in index.nodes if node.node_id == edge.target_id)
                    == "service.Store.save"
                    for edge in index.edges
                )
            )
            self.assertFalse(index.truncated)

    def test_incremental_index_reuses_changes_and_removes_deleted_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, policy, digest = self._project(temporary)
            config = default_implementation_config()
            first = build_implementation_index(paths, policy, config, digest, persist=True)
            second = build_implementation_index(paths, policy, config, digest, persist=True)
            self.assertEqual(first.scanned_files, second.reused_files)
            self.assertEqual(0, second.changed_files)

            service_file = root / "src" / "service.py"
            service_file.write_text("def replacement():\n    return 1\n", encoding="utf-8")
            third = build_implementation_index(paths, policy, config, digest, persist=True)
            self.assertEqual(1, third.changed_files)
            service_file.unlink()
            fourth = build_implementation_index(paths, policy, config, digest, persist=False)
            self.assertEqual(1, fourth.deleted_files)
            self.assertFalse(any(node.path == "src/service.py" for node in fourth.nodes))

    def test_query_supports_module_symbol_and_detail_views(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, paths, policy, digest = self._project(temporary)
            config = default_implementation_config()
            index = build_implementation_index(paths, policy, config, digest, persist=False)

            symbol = select_implementation_view(index, "create_widget implementation", Granularity.SYMBOL, config)
            detail = select_implementation_view(index, "create_widget impact", Granularity.DETAIL, config)
            module = select_implementation_view(index, "app entry", Granularity.MODULE, config)

            self.assertTrue(any(node.label == "create_widget" for node in symbol.nodes))
            self.assertGreaterEqual(len(detail.nodes), len(symbol.seed_ids))
            self.assertTrue(all(node.kind in {"module", "external"} for node in module.nodes))

    def test_python_encoding_cookie_is_respected_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, policy, digest = self._project(temporary)
            (root / "src" / "latin.py").write_bytes(
                b"# -*- coding: latin-1 -*-\ndef caf\xe9():\n    return 'ok'\n"
            )

            index = build_implementation_index(
                paths, policy, default_implementation_config(), digest, persist=False
            )

            self.assertTrue(any(node.label == "caf\u00e9" for node in index.nodes))

    def test_syntax_error_is_a_diagnostic_not_a_global_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, policy, digest = self._project(temporary)
            (root / "src" / "broken.py").write_text("def broken(:\n", encoding="utf-8")

            index = build_implementation_index(
                paths, policy, default_implementation_config(), digest, persist=False
            )

            self.assertTrue(any(item.code == "python_syntax_error" for item in index.diagnostics))
            self.assertTrue(any(node.qualified_name == "app.main" for node in index.nodes))


if __name__ == "__main__":
    unittest.main()