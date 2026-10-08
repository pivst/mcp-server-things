"""Credential discovery can be disabled before touching any source."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from things_mcp.config import ThingsMCPConfig
from things_mcp.services.applescript_manager import AppleScriptManager


def test_discovery_default_remains_compatible(monkeypatch):
    monkeypatch.delenv("THINGS_MCP_AUTH_TOKEN_AUTO_DISCOVERY", raising=False)
    assert ThingsMCPConfig().auth_token_auto_discovery is True


@pytest.mark.parametrize("value", ["false", "0", "true", "1"])
def test_discovery_environment_setting(monkeypatch, value):
    monkeypatch.setenv("THINGS_MCP_AUTH_TOKEN_AUTO_DISCOVERY", value)
    assert ThingsMCPConfig().auth_token_auto_discovery is (value in ("true", "1"))


def test_disabled_discovery_and_reload_touch_no_sources():
    config = ThingsMCPConfig(auth_token_auto_discovery=False)
    with (
        patch.object(Path, "home", side_effect=AssertionError("home lookup")),
        patch.object(Path, "exists", side_effect=AssertionError("file lookup")),
        patch.object(Path, "read_text", side_effect=AssertionError("file read")),
        patch("os.getenv", side_effect=AssertionError("environment lookup")),
    ):
        manager = AppleScriptManager(config=config)
        assert manager.auth_token is None
        assert manager.reload_auth_token_if_missing() is None
        assert manager._auth_token_trace == [
            {"source": "auto_discovery", "status": "disabled"}
        ]


@pytest.mark.asyncio
async def test_disabled_discovery_keeps_authenticated_writes_blocked():
    manager = AppleScriptManager(
        config=ThingsMCPConfig(auth_token_auto_discovery=False)
    )
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as dispatch:
        result = await manager.execute_url_scheme("update", {"id": "fake-id"})
    assert result["success"] is False
    assert result["error"] == "AUTH_TOKEN_NOT_CONFIGURED"
    assert result["checked_paths"] == [
        {"source": "auto_discovery", "status": "disabled"}
    ]
    dispatch.assert_not_called()


def test_server_passes_resolved_config_to_manager():
    from things_mcp.server import ThingsMCPServer

    config = ThingsMCPConfig(auth_token_auto_discovery=False)
    with (
        patch("things_mcp.server.load_config_from_env", return_value=config),
        patch("things_mcp.server.AppleScriptManager") as manager,
        patch("things_mcp.server.ThingsTools"),
        patch.object(ThingsMCPServer, "_configure_logging"),
        patch.object(ThingsMCPServer, "_register_tools"),
        patch.object(ThingsMCPServer, "_register_shutdown_handlers"),
    ):
        ThingsMCPServer()
    manager.assert_called_once_with(config=config)
