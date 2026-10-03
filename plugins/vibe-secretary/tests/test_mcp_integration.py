from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class MCPIntegrationTests(unittest.TestCase):
    def test_stdio_server_lists_and_calls_foundation_tools(self) -> None:
        anyio.run(self._exercise_server)

    async def _exercise_server(self) -> None:
        mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        foundation = mcp_config["mcpServers"]["foundation"]
        self.assertTrue(Path(foundation["command"]).is_absolute())
        with tempfile.TemporaryDirectory() as consumer_project:
            parameters = StdioServerParameters(
                command=foundation["command"],
                args=foundation["args"],
                cwd=consumer_project,
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    listing = await session.list_tools()
                    tools = {tool.name: tool for tool in listing.tools}
                    names = set(tools)

                    self.assertEqual("vibe-secretary-foundation", initialized.server_info.name)
                    self.assertEqual(
                        {
                        "foundation_health",
                        "project_status",
                        "initialize_project",
                        "set_project_enabled",
                        "scope_decision",
                        "process_hub_status",
                        "initialize_process_hub",
                        "set_process_hub_enabled",
                        "validate_process_hub",
                        "scan_process_documents",
                        "query_process_documents",
                        "get_process_document",
                        "preview_process_document",
                        "create_process_document",
                        "transition_process_document",
                        "organize_process_documents",
                        "rebuild_process_index",
                        "implementation_lens_status",
                        "initialize_implementation_lens",
                        "set_implementation_lens_enabled",
                        "refresh_implementation_index",
                        "inspect_implementation_model",
                        "update_implementation_model",
                        "query_implementation",
                        "render_implementation_map",
                        "prompt_copilot_status",
                        "initialize_prompt_copilot",
                        "set_prompt_copilot_enabled",
                        "prepare_prompt_review",
                        "validate_prompt_package",
                        },
                        names,
                    )

                    create_schema = tools["create_process_document"].input_schema
                    self.assertEqual("boolean", create_schema["properties"]["apply"]["type"])
                    self.assertEqual("object", create_schema["properties"]["metadata"]["anyOf"][0]["type"])

                    lens_schema = tools["render_implementation_map"].input_schema
                    self.assertIn("query", lens_schema["required"])
                    self.assertEqual(
                        "string", lens_schema["properties"]["granularity"]["type"]
                    )
                    self.assertEqual(
                        {"object", "null"},
                        {
                            option["type"]
                            for option in lens_schema["properties"]["story"]["anyOf"]
                        },
                    )
                    model_schema = tools["update_implementation_model"].input_schema
                    self.assertIn("records", model_schema["required"])
                    self.assertIn("coverage", model_schema["required"])

                    result = await session.call_tool("foundation_health", {})
                    self.assertFalse(result.is_error)
                    self.assertIsNotNone(result.structured_content)
                    self.assertTrue(result.structured_content["ok"])

                    lens_status = await session.call_tool(
                        "implementation_lens_status", {"project_root": consumer_project}
                    )
                    self.assertFalse(lens_status.is_error)
                    self.assertEqual(
                        str(Path(consumer_project).resolve()),
                        lens_status.structured_content["data"]["project_root"],
                    )

                    status = await session.call_tool(
                        "process_hub_status", {"project_root": consumer_project}
                    )
                    self.assertFalse(status.is_error)
                    self.assertEqual(
                        str(Path(consumer_project).resolve()),
                        status.structured_content["data"]["project_root"],
                    )


if __name__ == "__main__":
    unittest.main()
