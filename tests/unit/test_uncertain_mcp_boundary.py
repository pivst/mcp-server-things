"""Exercise every registered mutation through FastMCP, real services and executor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP

from things_mcp.config import ThingsMCPConfig
from things_mcp.context_manager import ContextAwareResponseManager
from things_mcp.server import ThingsMCPServer
from things_mcp.services.applescript.executor import AppleScriptExecutor
from things_mcp.services.applescript.formatters import AppleScriptFormatters
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools

CASES = [
    ("create_tag", {"tag_name": "mock-tag"}),
    ("add_todo", {"title": "mock todo"}),
    ("add_project", {"title": "mock project"}),
    ("add_area", {"title": "mock area"}),
    ("update_todo", {"id": "todo1", "title": "changed"}),
    ("update_project", {"id": "project1", "title": "changed"}),
    ("update_area", {"id": "area1", "title": "changed"}),
    ("delete_todo", {"todo_id": "todo1"}),
    ("move_record", {"todo_id": "todo1", "destination_list": "today"}),
    ("bulk_move_records", {"todo_ids": "todo1", "destination": "today"}),
    ("add_tags", {"todo_id": "todo1", "tags": "new"}),
    ("remove_tags", {"todo_id": "todo1", "tags": "new"}),
    ("add_checklist_items", {"todo_id": "todo1", "items": ["one"]}),
    ("prepend_checklist_items", {"todo_id": "todo1", "items": ["one"]}),
    ("replace_checklist_items", {"todo_id": "todo1", "items": ["one"]}),
    ("bulk_update_todos", {"todo_ids": "todo1,todo2", "title": "changed"}),
]


def make_server():
    # Bypass environment/credential discovery, shutdown hooks and logging setup;
    # use real tool registration, config, services, manager and executor.
    app = AppleScriptManager.__new__(AppleScriptManager)
    app.executor = AppleScriptExecutor(timeout=1, retry_count=3)
    app.formatters = AppleScriptFormatters()
    app.auth_token = "mock-test-token"
    server = ThingsMCPServer.__new__(ThingsMCPServer)
    server.mcp = FastMCP("mock-boundary")
    server.config = ThingsMCPConfig(ai_can_create_tags=True, _env_file=None)
    server.applescript_manager = app
    server.tools = ThingsTools(app, server.config)
    server.context_manager = ContextAwareResponseManager()
    server._register_tools()
    return server


@pytest.mark.parametrize("name,arguments", CASES)
async def test_registered_mutation_timeout_preserves_uncertainty(name, arguments):
    server = make_server()
    writes = []

    async def spawn(*command, **_kwargs):
        script = command[-1]
        process = MagicMock(returncode=0)
        process.wait = AsyncMock()
        if "return tag names" in script or "return tagString" in script:
            process.communicate = AsyncMock(return_value=(b"new", b""))
        else:
            writes.append(script)
            process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        return process

    with patch("asyncio.create_subprocess_exec", side_effect=spawn), patch(
        "things.get"
    ) as get:
        get.side_effect = RuntimeError("mock unavailable database")
        async with Client(server.mcp) as client:
            response = await client.call_tool(name, arguments)
    result = response.structured_content
    assert result["success"] is False, result
    assert result["error"] == "OUTCOME_UNCERTAIN", result
    assert result["outcome_uncertain"] is True, result
    assert result["retry_safe"] is False, result
    assert len(writes) == 1


def test_covers_all_registered_mutation_names():
    from test_write_tool_error_contract import MUTATING_TOOLS

    assert {name for name, _ in CASES} == MUTATING_TOOLS
