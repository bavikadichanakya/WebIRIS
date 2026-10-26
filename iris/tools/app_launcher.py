"""
Project IRIS - Application Launcher Tool
Safely launches approved Windows applications using allowlist validation.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional

from iris.tools.schemas import ActionResult, ToolDefinition, ToolParameter

logger = logging.getLogger("iris.tools.app_launcher")


class AppLauncherTool:
    """Tool for launching approved Windows desktop applications."""

    DEFINITION = ToolDefinition(
        name="open_application",
        description="Opens an approved Windows application on the desktop.",
        parameters=[
            ToolParameter(
                name="application",
                type="string",
                description="The name or alias of the application to open (e.g. 'notepad', 'calculator', 'chrome')",
                required=True,
            )
        ],
        requires_confirmation=False,
        permission_key="open_application",
    )

    def __init__(self, allowed_apps: Optional[Dict[str, str]] = None) -> None:
        self.allowed_apps: Dict[str, str] = allowed_apps or {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "file explorer": "explorer.exe",
            "explorer": "explorer.exe",
            "browser": "msedge.exe",
            "edge": "msedge.exe",
            "chrome": "chrome.exe",
            "code": "code.cmd",
            "codex": "code.cmd",
            "claude": "claude.exe",
            "slack": "slack.exe",
            "cursor": "cursor.exe",
            "spotify": "spotify.exe",
            "discord": "discord.exe",
            "terminal": "wt.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "task manager": "taskmgr.exe",
            "paint": "mspaint.exe",
            "word": "winword.exe",
            "excel": "excel.exe",
        }

    def execute(self, arguments: Dict[str, Any]) -> ActionResult:
        app_query = arguments.get("application", "").strip().lower()
        if not app_query:
            return ActionResult(
                success=False,
                tool_name="open_application",
                message="No application name specified.",
                error="missing_argument",
            )

        # 1. First check if a window matching the application is already open
        try:
            from iris.tools.window_manager import WindowManagerTool
            win_tool = WindowManagerTool()
            for win in win_tool.get_visible_windows():
                title = win["title"].lower()
                if app_query in title or (app_query == "anti gravity" and "antigravity" in title):
                    focus_res = win_tool.focus_window(win["title"])
                    if focus_res.success:
                        return ActionResult(
                            success=True,
                            tool_name="open_application",
                            message=f"Switched to '{win['title']}'.",
                            data={"target_window": win["title"], "hwnd": win["hwnd"]},
                        )
        except Exception as e:
            logger.debug(f"Window focus attempt before launch: {e}")

        # 2. Check if query is a web service / URL
        WEB_SERVICES = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://www.github.com",
            "chatgpt": "https://chatgpt.com",
            "reddit": "https://www.reddit.com",
            "twitter": "https://x.com",
            "x": "https://x.com",
            "netflix": "https://www.netflix.com",
        }
        if app_query in WEB_SERVICES:
            url = WEB_SERVICES[app_query]
            try:
                import webbrowser
                webbrowser.open(url)
                return ActionResult(
                    success=True,
                    tool_name="open_application",
                    message=f"Opened {app_query.capitalize()} in browser.",
                    data={"url": url},
                )
            except Exception as e:
                logger.error(f"Failed to open web service {app_query}: {e}")

        # Resolve application in allowlist
        target_executable = self.allowed_apps.get(app_query)
        if not target_executable:
            # Fuzzy check if partial match exists in allowed_apps
            for name, exe in self.allowed_apps.items():
                if app_query in name or name in app_query:
                    target_executable = exe
                    break

        if not target_executable:
            allowed_names = list(self.allowed_apps.keys())
            return ActionResult(
                success=False,
                tool_name="open_application",
                message=f"Application '{app_query}' is not in the approved applications allowlist.",
                error="not_allowed",
                data={"allowed_applications": allowed_names},
            )

        # Verify executable existence via PATH or absolute path
        resolved_path = shutil.which(target_executable) or target_executable
        if not os.path.isabs(resolved_path) and not shutil.which(target_executable):
            # Check System32 as default for standard Windows apps
            sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", target_executable)
            if os.path.exists(sys32):
                resolved_path = sys32

        logger.info(f"Launching approved application '{app_query}' -> '{resolved_path}'")
        try:
            # Launch detached from IRIS process so it remains open independently
            creation_flags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            ) if os.name == "nt" else 0

            proc = subprocess.Popen(
                [resolved_path],
                shell=False,
                creationflags=creation_flags,
                close_fds=True,
            )
            return ActionResult(
                success=True,
                tool_name="open_application",
                message=f"Successfully launched {app_query}.",
                data={"pid": proc.pid, "executable": resolved_path},
            )
        except Exception as e:
            logger.error(f"Failed to launch application '{target_executable}': {e}", exc_info=True)
            return ActionResult(
                success=False,
                tool_name="open_application",
                message=f"Failed to launch {app_query}: {str(e)}",
                error=str(e),
            )
