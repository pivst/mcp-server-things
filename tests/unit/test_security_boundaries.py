"""Security regressions: generated code and mocked dispatch only; never Things."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from things_mcp.move_operations import MoveOperationsTools
from things_mcp.scheduling.strategies import SchedulingStrategies
from things_mcp.scheduling.todo_operations import TodoOperations
from things_mcp.services.applescript.executor import AppleScriptExecutor
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools_helpers.bulk_operations import BulkOperations
from things_mcp.tools_helpers.write_operations import WriteOperations
from things_mcp.utils.applescript_utils import AppleScriptTemplates as AS

PAYLOADS = [
    'x" & do shell script "false" & "',
    'x\\"',
    "x\nend tell\n",
    "x\r\t",
    "中文😀",
    "",
]


def literal_contents(script):
    """Independent small lexer: literals may contain escapes, never raw line breaks."""
    values = []
    i = 0
    while i < len(script):
        if script[i] != '"':
            i += 1
            continue
        i += 1
        value = ""
        while i < len(script) and script[i] != '"':
            c = script[i]
            assert c not in "\n\r"
            if c == "\\":
                i += 1
                c = {"n": "\n", "r": "\r", "t": "\t"}.get(script[i], script[i])
            value += c
            i += 1
        assert i < len(script), "unterminated literal"
        values.append(value)
        i += 1
    return values


@pytest.mark.parametrize("value", PAYLOADS)
def test_literal_roundtrip(value):
    assert literal_contents(AS.escape_string(value)) == [value]


@pytest.mark.parametrize("code", [*range(32), *range(127, 160), 0x2028, 0x2029])
def test_controls_rejected_or_escaped(code):
    value = "prefix" + chr(code) + "suffix"
    if chr(code) in "\n\r\t":
        assert literal_contents(AS.escape_string(value)) == [value]
    else:
        with pytest.raises(ValueError):
            AS.escape_string(value)


@pytest.mark.parametrize("value", PAYLOADS[:-1])
@pytest.mark.parametrize("kind", ["project", "area"])
async def test_valid_source_malicious_destination(value, kind):
    manager = MagicMock()
    manager.execute_applescript = AsyncMock(
        return_value={"success": True, "output": "MOVED"}
    )
    moves = MoveOperationsTools(manager, MagicMock())
    # Exercise real lookup and its unavailable-DB fallback, not only builders.
    with patch("things_mcp.move_operations.things") as db:
        db.get.side_effect = RuntimeError("database unavailable")
        await moves.move_record("valid-source", kind + ":" + value)
    assert manager.execute_applescript.await_count == 1
    script = manager.execute_applescript.call_args.args[0]
    strings = literal_contents(script)
    assert "valid-source" in strings
    assert value in strings
    assert "MOVED to " + kind + " " + value in strings


@pytest.mark.parametrize("value", PAYLOADS[:-1])
async def test_update_project_and_scheduling_ids(value):
    manager = MagicMock()
    manager.execute_applescript = AsyncMock(
        return_value={"success": True, "output": "updated"}
    )
    ops = TodoOperations(manager, MagicMock())
    await ops.update_project(value, title="safe")
    assert value in literal_contents(manager.execute_applescript.call_args.args[0])
    manager.execute_applescript.reset_mock()
    await SchedulingStrategies(manager)._schedule_relative_date(value, "today")
    assert value in literal_contents(manager.execute_applescript.call_args.args[0])
    script = BulkOperations(manager, MagicMock())._build_bulk_update_script(
        [value], {"title": "safe"}
    )
    assert value in literal_contents(script)
    assert "ID " + value + ": " in literal_contents(script)


@pytest.mark.parametrize("method", ["add_tags", "remove_tags"])
@pytest.mark.parametrize(
    "read_result",
    [
        {"success": False, "error": "unavailable"},
        {"success": True},
        {"success": True, "output": "ERROR: failed"},
    ],
)
async def test_tag_read_failure_never_replaces_tags(method, read_result):
    manager = MagicMock()
    manager.execute_applescript = AsyncMock(return_value=read_result)
    ops = WriteOperations(manager, MagicMock(), MagicMock(), MagicMock())
    result = await getattr(ops, method)(PAYLOADS[0], ["new"])
    assert not result["success"]
    assert result["error"] == "TAG_READ_FAILED"
    assert manager.execute_applescript.await_count == 1
    assert PAYLOADS[0] in literal_contents(
        manager.execute_applescript.call_args.args[0]
    )


@pytest.mark.parametrize("method", ["add_tags", "remove_tags"])
async def test_tag_success_preserves_other_tags_and_escapes_id(method):
    manager = MagicMock()
    manager.execute_applescript = AsyncMock(
        side_effect=[
            {"success": True, "output": "keep, remove"},
            {"success": True, "output": "ok"},
        ]
    )
    ops = WriteOperations(manager, MagicMock(), MagicMock(), MagicMock())
    result = await getattr(ops, method)(PAYLOADS[0], ["remove"])
    assert result["success"]
    strings = literal_contents(manager.execute_applescript.call_args.args[0])
    assert PAYLOADS[0] in strings
    assert ("keep, remove" if method == "add_tags" else "keep") in strings


async def test_create_timeout_dispatches_once_and_publicly_reports_uncertainty():
    manager = AppleScriptManager.__new__(AppleScriptManager)
    manager.executor = AppleScriptExecutor(timeout=1, retry_count=3)
    ops = TodoOperations(manager, MagicMock())
    process = MagicMock()
    process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    process.wait = AsyncMock()
    with patch(
        "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    ) as spawn:
        result = await ops.add_project("mock-only project")
    assert spawn.await_count == 1
    assert result["error"] == "OUTCOME_UNCERTAIN"
    assert result["outcome_uncertain"] is True
    process.kill.assert_called_once()


@pytest.mark.parametrize(
    "failure",
    [
        {"success": False, "error": "failed after mutation"},
        {"success": True, "output": "ERROR: partial"},
        {"success": True, "output": "error: partial"},
    ],
)
async def test_writes_never_retry_any_ambiguous_failure(failure):
    executor = AppleScriptExecutor()
    executor._execute_script = AsyncMock(return_value=failure)
    result = await executor.execute_script("mock write")
    assert result["outcome_uncertain"]
    assert executor._execute_script.await_count == 1


async def test_explicit_readonly_can_retry():
    executor = AppleScriptExecutor()
    executor._execute_script = AsyncMock(
        side_effect=[
            {"success": False, "error": "temporary"},
            {"success": True, "output": "ok"},
        ]
    )
    with patch("asyncio.sleep", AsyncMock()):
        result = await executor.execute_script("return version", retry_safe=True)
    assert result["success"]
    assert executor._execute_script.await_count == 2


async def test_url_shell_and_applescript_boundaries():
    import shlex

    manager = AppleScriptManager.__new__(AppleScriptManager)
    manager.executor = MagicMock()
    manager.executor.execute_script = AsyncMock(return_value={"success": True})
    url = "things:///show?id='\"; echo unexpected; #\\\n"
    result = await manager.execute_url_scheme("show", {"url_override": url})
    assert result["success"]
    (command,) = literal_contents(manager.executor.execute_script.call_args.args[0])
    assert shlex.split(command) == ["open", "-g", "--", url]


@pytest.mark.parametrize("value", PAYLOADS[:-1])
async def test_update_todo_db_failure_fallback_escapes_source(value):
    manager = MagicMock()
    manager.execute_applescript = AsyncMock(
        return_value={"success": True, "output": "updated"}
    )
    ops = TodoOperations(manager, MagicMock())
    with patch("things_mcp.scheduling.todo_operations.things") as db:
        db.get.side_effect = RuntimeError("database unavailable")
        await ops.update_todo(value, title="safe")
    assert manager.execute_applescript.await_count == 1
    assert value in literal_contents(manager.execute_applescript.call_args.args[0])
