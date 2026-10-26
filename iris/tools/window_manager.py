"""
Project IRIS - Window Manager Tool
Provides window discovery, focus management, and window switching using native Windows APIs.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from iris.tools.schemas import ActionResult, ToolDefinition, ToolParameter

logger = logging.getLogger("iris.tools.window_manager")

try:
    import win32con
    import win32gui
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class WindowManagerTool:
    """Tool for window enumeration, focusing, and switching on Windows."""

    FOCUS_DEFINITION = ToolDefinition(
        name="focus_window",
        description="Brings a specific application window to the foreground by matching its title.",
        parameters=[
            ToolParameter(
                name="window_title",
                type="string",
                description="Partial or full title of the window to bring to the foreground (e.g. 'Notepad', 'Chrome')",
                required=True,
            )
        ],
        requires_confirmation=False,
        permission_key="focus_window",
    )

    SWITCH_DEFINITION = ToolDefinition(
        name="switch_window",
        description="Switches focus to the next visible top-level application window.",
        parameters=[],
        requires_confirmation=False,
        permission_key="switch_window",
    )

    def __init__(self) -> None:
        pass

    def get_visible_windows(self) -> List[Dict[str, Any]]:
        """List all non-empty, visible desktop windows."""
        if not WIN32_AVAILABLE:
            return []

        windows: List[Dict[str, Any]] = []

        def enum_callback(hwnd: int, extra: Any) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True

            # Filter out common hidden tool windows
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width <= 10 or height <= 10:
                return True

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            windows.append({
                "hwnd": hwnd,
                "title": title,
                "pid": pid,
                "rect": rect,
            })
            return True

        try:
            win32gui.EnumWindows(enum_callback, None)
        except Exception as e:
            logger.error(f"Error enumerating windows: {e}")

        return windows

    def get_active_window_info(self) -> Dict[str, Any]:
        """Return information about the currently active foreground window."""
        if not WIN32_AVAILABLE:
            return {"title": "Unknown", "hwnd": 0}

        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                return {"title": title, "hwnd": hwnd, "pid": pid}
        except Exception as e:
            logger.error(f"Error getting foreground window: {e}")

        return {"title": "", "hwnd": 0}

    def focus_window(self, window_title_query: str) -> ActionResult:
        """Find and focus the best matching window."""
        if not WIN32_AVAILABLE:
            return ActionResult(
                success=False,
                tool_name="focus_window",
                message="Windows API (pywin32) is not available.",
                error="missing_dependency",
            )

        query = window_title_query.strip().lower()
        if not query:
            return ActionResult(
                success=False,
                tool_name="focus_window",
                message="No window title provided to search for.",
                error="missing_argument",
            )

        windows = self.get_visible_windows()
        matched_hwnd = None
        matched_title = ""

        # Priority 1: Exact match
        for w in windows:
            if w["title"].lower() == query:
                matched_hwnd = w["hwnd"]
                matched_title = w["title"]
                break

        # Priority 2: Substring match
        if not matched_hwnd:
            for w in windows:
                if query in w["title"].lower():
                    matched_hwnd = w["hwnd"]
                    matched_title = w["title"]
                    break

        if not matched_hwnd:
            available = [w["title"] for w in windows[:10]]
            return ActionResult(
                success=False,
                tool_name="focus_window",
                message=f"No open window matching '{window_title_query}' was found.",
                data={"available_windows": available},
                error="window_not_found",
            )

        try:
            # Restore window if minimized
            if win32gui.IsIconic(matched_hwnd):
                win32gui.ShowWindow(matched_hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(matched_hwnd, win32con.SW_SHOW)

            # Bring to foreground
            win32gui.SetForegroundWindow(matched_hwnd)
            return ActionResult(
                success=True,
                tool_name="focus_window",
                message=f"Focused window: '{matched_title}'.",
                data={"hwnd": matched_hwnd, "title": matched_title},
            )
        except Exception as e:
            logger.error(f"Failed to focus window {matched_hwnd}: {e}")
            return ActionResult(
                success=False,
                tool_name="focus_window",
                message=f"Failed to bring '{matched_title}' to foreground: {e}",
                error=str(e),
            )

    def switch_window(self) -> ActionResult:
        """Cycle to the next visible application window."""
        if not WIN32_AVAILABLE:
            return ActionResult(
                success=False,
                tool_name="switch_window",
                message="Windows API (pywin32) is not available.",
                error="missing_dependency",
            )

        windows = self.get_visible_windows()
        if len(windows) < 2:
            return ActionResult(
                success=False,
                tool_name="switch_window",
                message="Not enough visible windows to switch.",
                error="insufficient_windows",
            )

        # Active window is typically first or second
        current_hwnd = win32gui.GetForegroundWindow()
        target_window = None

        for idx, w in enumerate(windows):
            if w["hwnd"] == current_hwnd:
                next_idx = (idx + 1) % len(windows)
                target_window = windows[next_idx]
                break

        if not target_window and windows:
            target_window = windows[0]

        if not target_window:
            return ActionResult(
                success=False,
                tool_name="switch_window",
                message="Unable to locate next window.",
                error="no_target",
            )

        target_hwnd = target_window["hwnd"]
        try:
            if win32gui.IsIconic(target_hwnd):
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(target_hwnd)
            return ActionResult(
                success=True,
                tool_name="switch_window",
                message=f"Switched to '{target_window['title']}'.",
                data={"hwnd": target_hwnd, "title": target_window["title"]},
            )
        except Exception as e:
            return ActionResult(
                success=False,
                tool_name="switch_window",
                message=f"Failed to switch window: {e}",
                error=str(e),
            )
