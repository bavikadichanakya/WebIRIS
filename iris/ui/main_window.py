"""
Project IRIS - Desktop Main Window
Polished PySide6 user interface hosting navigation sidebar, settings pages, and system tray.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from iris.brain.model_manager import ModelManager
from iris.core.config import IrisConfig
from iris.core.event_bus import EventBus
from iris.core.state_machine import StateMachine
from iris.tools.registry import ToolRegistry
from iris.ui.settings_pages import (
    AutomationSettingsPage,
    BrainSettingsPage,
    DashboardPage,
    DiagnosticsPage,
    SetupModelsPage,
    VoiceSettingsPage,
)
from iris.ui.theme import IRIS_STYLE_SHEET
from iris.ui.tray import IrisSystemTray
from iris.voice.audio_capture import AudioCapture
from iris.voice.tts_adapter import TTSAdapter
from iris.voice.voice_pipeline import VoicePipeline

logger = logging.getLogger("iris.ui.main_window")


class IrisMainWindow(QMainWindow):
    """Main desktop configuration window for Project IRIS."""

    def __init__(
        self,
        config: IrisConfig,
        state_machine: StateMachine,
        model_manager: ModelManager,
        voice_pipeline: VoicePipeline,
        audio_capture: AudioCapture,
        tts: TTSAdapter,
        tool_registry: ToolRegistry,
        bus: EventBus,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.state_machine = state_machine
        self.model_manager = model_manager
        self.voice_pipeline = voice_pipeline
        self.audio_capture = audio_capture
        self.tts = tts
        self.tool_registry = tool_registry
        self.bus = bus

        self.setWindowTitle("Project IRIS — Desktop Voice Assistant")
        self.resize(self.config.ui.window_width, self.config.ui.window_height)
        self.setStyleSheet(IRIS_STYLE_SHEET)

        # System Tray
        self.tray = IrisSystemTray(self)
        self.tray.show_settings_requested.connect(self.show_and_activate)
        self.tray.toggle_listening_requested.connect(self._toggle_listening)
        self.tray.exit_requested.connect(self.exit_application)
        self.tray.show()

        # Connect state machine changes to tray icon
        self.state_machine.add_listener(self._on_state_changed)

        self._init_ui()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar Navigation
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("nav_sidebar")
        self.sidebar.setFixedWidth(210)

        nav_items = [
            ("Dashboard", "Overview & controls"),
            ("SmolLM3-3B Brain", "Model & inference"),
            ("Voice & Audio", "Mic, wake-word, TTS"),
            ("Automation Tools", "Permissions & tools"),
            ("Setup & Models", "Repair & downloads"),
            ("Diagnostics", "System logs"),
        ]

        for title, sub in nav_items:
            item = QListWidgetItem(title)
            self.sidebar.addItem(item)

        main_layout.addWidget(self.sidebar)

        # 2. Stacked Content Pages
        self.stack = QStackedWidget()

        self.page_dashboard = DashboardPage(
            config=self.config,
            state_machine=self.state_machine,
            audio_capture=self.audio_capture,
            bus=self.bus,
            action_planner=self.voice_pipeline.action_planner,
            tool_registry=self.tool_registry,
            tts=self.tts,
            voice_pipeline=self.voice_pipeline,
        )
        self.page_dashboard.pause_toggled.connect(self._on_dashboard_pause_toggled)

        self.page_brain = BrainSettingsPage(self.config, self.model_manager)
        self.page_voice = VoiceSettingsPage(self.config, self.tts)
        self.page_automation = AutomationSettingsPage(self.config, self.tool_registry)
        self.page_setup = SetupModelsPage(self.config)
        self.page_diagnostics = DiagnosticsPage()

        self.stack.addWidget(self.page_dashboard)
        self.stack.addWidget(self.page_brain)
        self.stack.addWidget(self.page_voice)
        self.stack.addWidget(self.page_automation)
        self.stack.addWidget(self.page_setup)
        self.stack.addWidget(self.page_diagnostics)

        main_layout.addWidget(self.stack)

        # Connect sidebar selection to stacked pages
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

    def _on_state_changed(self, old_state, new_state, reason) -> None:
        QTimer.singleShot(0, lambda: self.tray.update_state(new_state))

    def _on_dashboard_pause_toggled(self, should_pause: bool) -> None:
        if should_pause:
            self.voice_pipeline.pause_listening()
        else:
            self.voice_pipeline.resume_listening()

    def _toggle_listening(self) -> None:
        if self.voice_pipeline.is_paused:
            self.voice_pipeline.resume_listening()
        else:
            self.voice_pipeline.pause_listening()

    def show_and_activate(self) -> None:
        """Show, restore, and bring window to front."""
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.raise_()
        self.activateWindow()
        try:
            import win32gui
            import win32con
            hwnd = int(self.winId())
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Intercept close event. Unless configured otherwise, hide window to tray
        so the background voice runtime continues operating seamlessly.
        """
        if self.config.ui.close_to_tray:
            event.ignore()
            self.hide()
            self.tray.show_message(
                "IRIS is running in the background",
                "Listening for 'Hey Iris'. Click this icon to open settings or exit.",
            )
            logger.info("Configuration window hidden to tray; voice agent runtime active.")
        else:
            self.exit_application()

    def exit_application(self) -> None:
        """Cleanly shutdown runtime, stop voice pipeline, and exit."""
        logger.info("Exiting IRIS application...")
        # Save configuration on exit
        try:
            self.config.save()
        except Exception:
            pass

        self.voice_pipeline.stop()
        self.model_manager.shutdown()
        self.tray.hide()
        QApplication.instance().quit()
