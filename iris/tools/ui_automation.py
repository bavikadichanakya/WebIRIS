"""
Project IRIS - UI Automation Inspection Tool
Reads accessible UI elements and context from focused Windows applications.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from iris.tools.schemas import ActionResult, ToolDefinition, ToolParameter

logger = logging.getLogger("iris.tools.ui_automation")

try:
    import uiautomation as auto
    UIA_AVAILABLE = True
except ImportError:
    UIA_AVAILABLE = False


class UIAutomationTool:
    """Tool to read accessible text and element structure from the focused window."""

    READ_DEFINITION = ToolDefinition(
        name="read_ui_element",
        description="Reads accessible text or focused content from the active application window.",
        parameters=[],
        requires_confirmation=False,
        permission_key="read_ui_element",
    )

    def __init__(self) -> None:
        pass

    def read_focused_element(self) -> ActionResult:
        """Inspect the currently focused control and extract accessible text."""
        if not UIA_AVAILABLE:
            return ActionResult(
                success=False,
                tool_name="read_ui_element",
                message="UI Automation library is not installed.",
                error="missing_dependency",
            )

        try:
            control = auto.GetFocusedControl()
            if not control:
                return ActionResult(
                    success=False,
                    tool_name="read_ui_element",
                    message="No active control has focus.",
                    error="no_focused_element",
                )

            name = getattr(control, "Name", "")
            control_type = getattr(control, "ControlTypeName", "Unknown")
            is_password = getattr(control, "IsPassword", False)

            if is_password:
                return ActionResult(
                    success=True,
                    tool_name="read_ui_element",
                    message="Focused element is a password field (contents hidden).",
                    data={"type": control_type, "is_password": True},
                )

            # Extract value via ValuePattern if available
            value = ""
            try:
                val_pattern = control.GetValuePattern()
                if val_pattern:
                    value = val_pattern.Value
            except Exception:
                pass

            content = value or name or "(empty)"
            return ActionResult(
                success=True,
                tool_name="read_ui_element",
                message=f"Read from {control_type}: '{content[:80]}'",
                data={
                    "control_type": control_type,
                    "name": name,
                    "value": value,
                },
            )
        except Exception as e:
            logger.error(f"Error inspecting focused UI element: {e}")
            return ActionResult(
                success=False,
                tool_name="read_ui_element",
                message=f"Failed to read UI element: {e}",
                error=str(e),
            )
