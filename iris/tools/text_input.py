"""
Project IRIS - Text Input & Automation Tool
Safely types text into focused controls with password field detection and safety controls.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from iris.tools.schemas import ActionResult, ToolDefinition, ToolParameter

logger = logging.getLogger("iris.tools.text_input")

try:
    import win32api
    import win32clipboard
    import win32con
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    import uiautomation as auto
    UIA_AVAILABLE = True
except ImportError:
    UIA_AVAILABLE = False


class TextInputTool:
    """Safely enters text into active Windows controls with security verification."""

    TYPE_DEFINITION = ToolDefinition(
        name="type_text",
        description="Types text into the currently focused input field or target application.",
        parameters=[
            ToolParameter(
                name="text",
                type="string",
                description="The exact text string to type into the active application.",
                required=True,
            ),
            ToolParameter(
                name="target_application",
                type="string",
                description="Optional application to focus before typing (e.g. 'notepad').",
                required=False,
                default="",
            ),
        ],
        requires_confirmation=False,
        permission_key="type_text",
    )

    SUBMIT_DEFINITION = ToolDefinition(
        name="submit_text",
        description="Presses the Enter key to submit text in the active input field.",
        parameters=[],
        requires_confirmation=False,
        permission_key="submit_text",
    )

    NEW_CHAT_DEFINITION = ToolDefinition(
        name="new_chat",
        description="Starts a new chat, new tab, or new document in the active application.",
        parameters=[],
        requires_confirmation=False,
        permission_key="new_chat",
    )

    def __init__(self, typing_delay_ms: int = 15, block_password_fields: bool = True) -> None:
        self.typing_delay_ms = typing_delay_ms
        self.block_password_fields = block_password_fields

    def _ensure_target_focused(self, app_name: str) -> None:
        """Find and bring target application to front, or launch it if not open."""
        if not WIN32_AVAILABLE or not app_name:
            return

        query = app_name.strip().lower()
        matched_hwnd = None

        def enum_cb(hwnd, extra):
            nonlocal matched_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title and query in title.lower():
                    matched_hwnd = hwnd

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass

        if matched_hwnd:
            try:
                win32gui.ShowWindow(matched_hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(matched_hwnd)
                time.sleep(0.2)
                return
            except Exception:
                pass

        # If not open and it's notepad, launch it automatically
        if query == "notepad":
            try:
                os.startfile("notepad.exe")
                time.sleep(0.6)
            except Exception as e:
                logger.error(f"Failed to launch {query}: {e}")

    def is_focused_element_password(self) -> bool:
        """Check via UI Automation if the currently focused control is a password field."""
        if not UIA_AVAILABLE:
            return False

        try:
            focused = auto.GetFocusedControl()
            if focused:
                # Check IsPassword attribute
                is_password = getattr(focused, "IsPassword", False)
                if is_password:
                    return True
                # Check control type and edit pattern
                type_name = getattr(focused, "ControlTypeName", "")
                name = getattr(focused, "Name", "").lower()
                if "password" in name or "passcode" in name or "pin" in name:
                    return True
        except Exception as e:
            logger.debug(f"UIA password check exception: {e}")

        return False

    def type_text(self, text: str, target_application: Optional[str] = None) -> ActionResult:
        """Type text character-by-character into the active window or target application."""
        if not WIN32_AVAILABLE:
            return ActionResult(
                success=False,
                tool_name="type_text",
                message="Windows API (pywin32) is not available.",
                error="missing_dependency",
            )

        if not text:
            return ActionResult(
                success=False,
                tool_name="type_text",
                message="No text provided to type.",
                error="empty_text",
            )

        # Focus target application if specified (e.g. 'notepad')
        if target_application:
            self._ensure_target_focused(target_application)

        # Check for password field safety boundary
        if self.block_password_fields and self.is_focused_element_password():
            logger.warning("BLOCKED: Attempted to type into a detected password/sensitive field.")
            return ActionResult(
                success=False,
                tool_name="type_text",
                message="Action blocked for security: The active control is a password field.",
                error="password_field_blocked",
            )

        hwnd = win32gui.GetForegroundWindow()
        win_title = win32gui.GetWindowText(hwnd) if hwnd else "Unknown"

        logger.info(f"Injecting {len(text)} characters into '{win_title}'...")

        try:
            # 1. Fast clipboard paste for instant text entry
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()

                # Send Ctrl+V
                time.sleep(0.01)
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord('V'), 0, 0, 0)
                time.sleep(0.01)
                win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.01)

                return ActionResult(
                    success=True,
                    tool_name="type_text",
                    message=f"Typed text into '{win_title}'.",
                    data={"characters_typed": len(text), "target_window": win_title},
                )
            except Exception as clip_err:
                logger.debug(f"Clipboard paste fallback: {clip_err}")

            # 2. Fallback to keybd_event simulation
            delay_sec = max(0.001, self.typing_delay_ms / 1000.0)
            for char in text:
                if char == "\n":
                    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
                    time.sleep(0.005)
                    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
                else:
                    vk = 0
                    scan = ord(char)
                    flags = win32con.KEYEVENTF_UNICODE
                    win32api.keybd_event(vk, scan, flags, 0)
                    time.sleep(0.002)
                    win32api.keybd_event(vk, scan, flags | win32con.KEYEVENTF_KEYUP, 0)

                if delay_sec > 0:
                    time.sleep(delay_sec)

            return ActionResult(
                success=True,
                tool_name="type_text",
                message=f"Typed text into '{win_title}'.",
                data={"characters_typed": len(text), "target_window": win_title},
            )
        except Exception as e:
            logger.error(f"Failed to type text: {e}", exc_info=True)
            return ActionResult(
                success=False,
                tool_name="type_text",
                message=f"Error while typing text: {e}",
                error=str(e),
            )

    def submit_text(self) -> ActionResult:
        """Send the Enter key to submit text."""
        if not WIN32_AVAILABLE:
            return ActionResult(
                success=False,
                tool_name="submit_text",
                message="Windows API (pywin32) is not available.",
                error="missing_dependency",
            )

        hwnd = win32gui.GetForegroundWindow()
        win_title = win32gui.GetWindowText(hwnd) if hwnd else "Unknown"

        try:
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            return ActionResult(
                success=True,
                tool_name="submit_text",
                message=f"Submitted text in '{win_title}'.",
                data={"target_window": win_title},
            )
        except Exception as e:
            return ActionResult(
                success=False,
                tool_name="submit_text",
                message=f"Failed to submit: {e}",
                error=str(e),
            )

    def new_chat(self) -> ActionResult:
        """Send shortcut (Ctrl+N) to trigger a new chat / conversation / document."""
        if not WIN32_AVAILABLE:
            return ActionResult(
                success=False,
                tool_name="new_chat",
                message="Windows API (pywin32) is not available.",
                error="missing_dependency",
            )

        hwnd = win32gui.GetForegroundWindow()
        win_title = win32gui.GetWindowText(hwnd) if hwnd else "Unknown"

        try:
            # Press Ctrl+N
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('N'), 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(ord('N'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

            return ActionResult(
                success=True,
                tool_name="new_chat",
                message=f"Started new chat in '{win_title}'.",
                data={"target_window": win_title},
            )
        except Exception as e:
            return ActionResult(
                success=False,
                tool_name="new_chat",
                message=f"Failed to start new chat: {e}",
                error=str(e),
            )
