"""Unit tests for Windows automation tools and registry."""

import pytest
from iris.tools.app_launcher import AppLauncherTool
from iris.tools.registry import create_default_registry


def test_app_launcher_unapproved_rejection():
    tool = AppLauncherTool(allowed_apps={"notepad": "notepad.exe"})
    res = tool.execute({"application": "malicious_script.bat"})
    assert not res.success
    assert res.error == "not_allowed"


def test_app_launcher_missing_arg():
    tool = AppLauncherTool()
    res = tool.execute({})
    assert not res.success
    assert res.error == "missing_argument"


def test_default_registry_initialization():
    registry = create_default_registry()
    tools = registry.list_tools()

    assert "open_application" in tools
    assert "focus_window" in tools
    assert "switch_window" in tools
    assert "type_text" in tools
    assert "submit_text" in tools
    assert "read_ui_element" in tools


def test_registry_unknown_tool_execution():
    registry = create_default_registry()
    res = registry.execute("non_existent_tool", {})
    assert not res.success
    assert res.error == "unknown_tool"
