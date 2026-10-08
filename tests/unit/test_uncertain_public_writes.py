"""Public facade -> real executor -> mocked subprocess: uncertainty is terminal."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from things_mcp.services.applescript.executor import AppleScriptExecutor
from things_mcp.services.applescript.formatters import AppleScriptFormatters
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools

CASES = [
    ("add_todo", ("mock todo",), {}),
    ("add_todo", ("mock todo",), {"checklist_items": ["one"]}),
    ("add_project", ("mock project",), {}),
    ("add_project", ("mock project",), {"todos": ["## heading", "one"]}),
    ("add_area", ("mock area",), {}),
    ("update_todo", ("todo1",), {"title": "changed"}),
    ("update_project", ("project1",), {"title": "changed"}),
    ("update_area", ("area1",), {"title": "changed"}),
    ("delete_todo", ("todo1",), {}),
    ("move_record", ("todo1", "today"), {}),
    ("add_tags", ("todo1", ["new"]), {}),
    ("remove_tags", ("todo1", ["new"]), {}),
    ("add_checklist_items", ("todo1", ["one"]), {}),
    ("prepend_checklist_items", ("todo1", ["one"]), {}),
    ("replace_checklist_items", ("todo1", ["one"]), {}),
    ("bulk_update_todos", (["todo1", "todo2"],), {"title": "changed"}),
    ("update_todo", ("todo1",), {"when": "tomorrow"}),
    ("update_todo", ("todo1",), {"when": "evening"}),
]


def manager():
    value = AppleScriptManager.__new__(AppleScriptManager)
    value.executor = AppleScriptExecutor(timeout=1, retry_count=3)
    value.formatters = AppleScriptFormatters()
    value.auth_token = "mock-test-token"
    return value


def assert_uncertain(result):
    assert result["success"] is False, result
    assert result["error"] == "OUTCOME_UNCERTAIN", result
    assert result["outcome_uncertain"] is True, result
    assert result["retry_safe"] is False, result


@pytest.mark.parametrize("method,args,kwargs", CASES)
async def test_public_write_timeout_is_terminal(method, args, kwargs):
    app = manager()
    tools = ThingsTools(app)
    writes = []

    async def spawn(*command, **_kwargs):
        script = command[-1]
        process = MagicMock()
        process.wait = AsyncMock()
        process.returncode = 0
        # Read-only preflight for tag merges and URL creation snapshots.
        if (
            "return tag names" in script
            or "set foundTodos to" in script
            or "set foundProjects to" in script
        ):
            process.communicate = AsyncMock(return_value=(b"", b""))
        else:
            writes.append(script)
            process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        return process

    with patch("asyncio.create_subprocess_exec", side_effect=spawn), patch(
        "things.get"
    ) as get:
        # Unavailable DB must not trigger delete/project/trash fallback after timeout.
        get.side_effect = RuntimeError("mock unavailable DB")
        result = await getattr(tools, method)(*args, **kwargs)
    assert_uncertain(result)
    assert len(writes) == 1, writes


@pytest.mark.parametrize("when", ["today", "2030-11-12", "unparseable date"])
async def test_scheduling_never_advances_to_another_strategy_after_timeout(when):
    app = manager()
    tools = ThingsTools(app)
    process = MagicMock()
    process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    process.wait = AsyncMock()
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    ) as spawn:
        result = await tools.reliable_scheduler.schedule_todo_reliable("todo1", when)
    assert_uncertain(result)
    assert spawn.await_count == 1


async def test_public_create_then_schedule_timeout_preserves_uncertainty():
    app = manager()
    tools = ThingsTools(app)
    created = MagicMock(returncode=0)
    created.communicate = AsyncMock(return_value=(b"created-id", b""))
    timed_out = MagicMock()
    timed_out.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    timed_out.wait = AsyncMock()
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(side_effect=[created, timed_out])
    ) as spawn:
        result = await tools.add_todo("mock todo", when="tomorrow")
    assert_uncertain(result)
    assert spawn.await_count == 2  # one create, one schedule; no fallback/replay


@pytest.mark.parametrize(
    "method,args,kwargs,output",
    [
        ("add_project", ("mock project",), {"when": "2030-11-12@12:00"}, b"created-id"),
        ("update_project", ("project1",), {"when": "2030-11-12@12:00"}, b"updated"),
        (
            "update_todo",
            ("todo1",),
            {"title": "changed", "when": "evening"},
            b"updated",
        ),
        (
            "bulk_update_todos",
            (["todo1", "todo2"],),
            {"when": "evening"},
            b"successCount: 2",
        ),
        (
            "bulk_update_todos",
            (["todo1", "todo2"],),
            {"when": "tomorrow"},
            b"successCount: 2",
        ),
    ],
)
async def test_followup_write_timeout_stops_public_operation(
    method, args, kwargs, output
):
    app = manager()
    tools = ThingsTools(app)
    first = MagicMock(returncode=0)
    first.communicate = AsyncMock(return_value=(output, b""))
    second = MagicMock()
    second.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    second.wait = AsyncMock()
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(side_effect=[first, second])
    ) as spawn, patch("things.get") as get:
        get.side_effect = RuntimeError("mock unavailable DB")
        result = await getattr(tools, method)(*args, **kwargs)
    assert_uncertain(result)
    assert spawn.await_count == 2


async def test_bulk_move_preserves_uncertainty_at_top_level():
    tools = ThingsTools(manager())
    process = MagicMock()
    process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    process.wait = AsyncMock()
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    ) as spawn, patch("things.get") as get:
        get.side_effect = RuntimeError("mock unavailable DB")
        result = await tools.move_operations.bulk_move(["todo1"], "today")
    assert_uncertain(result)
    assert result["failed_moves"][0]["outcome_uncertain"] is True
    assert spawn.await_count == 1


async def test_legacy_scheduler_also_stops_on_uncertainty():
    from things_mcp.reliable_scheduling import ReliableThingsScheduler

    app = manager()
    scheduler = ReliableThingsScheduler(app)
    process = MagicMock()
    process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    process.wait = AsyncMock()
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    ) as spawn:
        result = await scheduler.schedule_todo_reliable("todo1", "2030-11-12")
    assert_uncertain(result)
    assert spawn.await_count == 1
