"""
Project IRIS - Main Application Entrypoint
Launches the native PySide6 desktop assistant and background voice runtime.
"""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from iris.app.bootstrap import bootstrap_iris
from iris.ui.main_window import IrisMainWindow
from iris.ui.setup_wizard import SetupWizardDialog

logger = logging.getLogger("iris.app.main")


def main() -> int:
    """Main execution function for Project IRIS."""
    # 0. Single instance check: if IRIS is already running, tell it to show the dashboard
    try:
        import socket
        import json
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(("127.0.0.1", 19842))
        req = json.dumps({"msg_type": "request", "command": "show_dashboard", "payload": {}}) + "\n"
        sock.sendall(req.encode("utf-8"))
        sock.close()
        print("Project IRIS is already running. Brought existing dashboard to front.")
        return 0
    except Exception:
        pass  # Proceed with starting the application

    # Enable high-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Project IRIS")
    app.setOrganizationName("IRIS")
    app.setQuitOnLastWindowClosed(False)  # Keep running in system tray!

    try:
        # Bootstrap runtime container
        container = bootstrap_iris()

        # Connect GUI confirmation callback
        def show_gui_confirmation(title: str, text: str) -> bool:
            resp = QMessageBox.question(
                None,
                title,
                text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return resp == QMessageBox.Yes

        container.confirmation_mgr.set_gui_confirmation_callback(show_gui_confirmation)

        # First-run check: verify if SmolLM3-3B model exists
        model_exists = os.path.exists(container.config.model.model_path)
        ww_exists = os.path.exists(container.config.wake_word.model_path)

        if not model_exists or not ww_exists:
            logger.info("First run detected: Some assets missing. Launching Setup Wizard...")
            wizard = SetupWizardDialog(container.config)
            # If user closes wizard without finishing, still allow opening settings
            wizard.exec()

        # Create and display Main Window
        window = IrisMainWindow(
            config=container.config,
            state_machine=container.state_machine,
            model_manager=container.model_manager,
            voice_pipeline=container.voice_pipeline,
            audio_capture=container.audio_capture,
            tts=container.tts,
            tool_registry=container.tool_registry,
            bus=container.event_bus,
        )

        # Load wake word and STT
        container.wake_word.load()
        container.stt.load()

        # Load SmolLM3-3B in background if file exists
        if os.path.exists(container.config.model.model_path):
            container.model_manager.load_model_async()

        # Start Voice Pipeline in background
        container.voice_pipeline.start()

        # Start IPC Server
        if container.ipc_server:
            def _handle_show_dashboard(payload: dict) -> dict:
                QTimer.singleShot(0, window.show_and_activate)
                return {"status": "ok", "message": "Dashboard brought to front"}

            container.ipc_server.register_command("show_dashboard", _handle_show_dashboard)
            container.ipc_server.start()

        # Clean shutdown handler
        def _on_about_to_quit() -> None:
            logger.info("Project IRIS application shutting down...")
            if container.ipc_server:
                container.ipc_server.stop()
            container.voice_pipeline.stop()

        app.aboutToQuit.connect(_on_about_to_quit)

        # Show window unless configured to start minimized
        if not container.config.ui.start_minimized:
            window.show()
        else:
            window.hide()

        logger.info("Project IRIS is active and listening in background.")
        return app.exec()

    except Exception as e:
        logger.critical(f"Unhandled exception in IRIS application main: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
