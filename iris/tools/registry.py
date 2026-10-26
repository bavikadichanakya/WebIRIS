"""
Project IRIS - Tool Registry
Central catalogue, validation, and dispatcher for Windows desktop automation tools.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from iris.tools.app_launcher import AppLauncherTool
from iris.tools.schemas import ActionResult, ToolDefinition
from iris.tools.text_input import TextInputTool
from iris.tools.ui_automation import UIAutomationTool
from iris.tools.window_manager import WindowManagerTool

logger = logging.getLogger("iris.tools.registry")


class ToolRegistry:
    """Registers and executes all automation tools in a decoupled, testable structure."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._executors: Dict[str, Callable[[Dict[str, Any]], ActionResult]] = {}

    def register_tool(
        self,
        definition: ToolDefinition,
        executor: Callable[[Dict[str, Any]], ActionResult],
    ) -> None:
        """Register a tool definition and its handler function."""
        self._tools[definition.name] = definition
        self._executors[definition.name] = executor
        logger.debug(f"Registered tool: '{definition.name}'")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, ToolDefinition]:
        return dict(self._tools)

    def execute(self, intent: str, arguments: Dict[str, Any]) -> ActionResult:
        """Dispatch action execution to the registered tool executor."""
        intent = intent.strip().lower()
        if intent not in self._executors:
            return ActionResult(
                success=False,
                tool_name=intent,
                message=f"No executor registered for intent '{intent}'.",
                error="unknown_tool",
            )

        executor = self._executors[intent]
        try:
            return executor(arguments)
        except Exception as e:
            logger.error(f"Execution error in tool '{intent}': {e}", exc_info=True)
            return ActionResult(
                success=False,
                tool_name=intent,
                message=f"Error executing tool '{intent}': {str(e)}",
                error=str(e),
            )

    execute_action = execute


def create_default_registry(
    allowed_apps: Optional[Dict[str, str]] = None,
    typing_delay_ms: int = 15,
) -> ToolRegistry:
    """Instantiate and configure the standard Windows automation tool catalogue."""
    registry = ToolRegistry()

    # 1. App Launcher
    app_tool = AppLauncherTool(allowed_apps=allowed_apps)
    registry.register_tool(AppLauncherTool.DEFINITION, app_tool.execute)

    # 2. Window Manager
    win_tool = WindowManagerTool()
    registry.register_tool(
        WindowManagerTool.FOCUS_DEFINITION,
        lambda args: win_tool.focus_window(args.get("window_title", "")),
    )
    registry.register_tool(
        WindowManagerTool.SWITCH_DEFINITION,
        lambda args: win_tool.switch_window(),
    )

    # 3. Text Input & Submission
    input_tool = TextInputTool(typing_delay_ms=typing_delay_ms)
    registry.register_tool(
        TextInputTool.TYPE_DEFINITION,
        lambda args: input_tool.type_text(
            args.get("text", ""),
            target_application=args.get("target_application") or args.get("application"),
        ),
    )
    registry.register_tool(
        TextInputTool.SUBMIT_DEFINITION,
        lambda args: input_tool.submit_text(),
    )
    registry.register_tool(
        TextInputTool.NEW_CHAT_DEFINITION,
        lambda args: input_tool.new_chat(),
    )

    # 4. UI Automation Reader
    uia_tool = UIAutomationTool()
    registry.register_tool(
        UIAutomationTool.READ_DEFINITION,
        lambda args: uia_tool.read_focused_element(),
    )

    return registry
