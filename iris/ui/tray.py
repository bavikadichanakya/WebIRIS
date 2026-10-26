"""
Project IRIS - Windows System Tray Integration
Manages background notification icon, status tooltips, and background controls.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from iris.core.state_machine import RuntimeState

logger = logging.getLogger("iris.ui.tray")


def create_tray_icon_pixmap(color_hex: str = "#00d2ff") -> QIcon:
    """Dynamically draw a crisp 32x32 tray icon with the IRIS iris/ring glyph."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))  # Transparent

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Outer circle
    color = QColor(color_hex)
    painter.setPen(color)
    painter.setBrush(QColor(0, 0, 0, 0))
    painter.drawEllipse(3, 3, 26, 26)

    # Inner core
    painter.setBrush(color)
    painter.drawEllipse(11, 11, 10, 10)

    painter.end()
    return QIcon(pixmap)


class IrisSystemTray(QObject):
    """Windows system tray icon with dynamic menus and lifecycle actions."""

    show_settings_requested = Signal()
    toggle_listening_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._current_state = RuntimeState.IDLE
        self._tray_icon = QSystemTrayIcon(parent)
        self._tray_icon.setIcon(create_tray_icon_pixmap("#00d2ff"))
        self._tray_icon.setToolTip("IRIS Desktop Voice Assistant")

        self._menu = QMenu()
        self._init_menu()
        self._tray_icon.setContextMenu(self._menu)
        self._tray_icon.activated.connect(self._on_tray_activated)

    def _init_menu(self) -> None:
        # Title header
        title_action = QAction("IRIS Voice Assistant", self._menu)
        title_font = QFont()
        title_font.setBold(True)
        title_action.setFont(title_font)
        title_action.setEnabled(False)
        self._menu.addAction(title_action)

        # Status item
        self._status_action = QAction("Status: Initializing", self._menu)
        self._status_action.setEnabled(False)
        self._menu.addAction(self._status_action)

        self._menu.addSeparator()

        # Open Settings
        self._open_action = QAction("Open Settings", self._menu)
        self._open_action.triggered.connect(self.show_settings_requested.emit)
        self._menu.addAction(self._open_action)

        # Pause / Resume Listening
        self._pause_resume_action = QAction("Pause Listening", self._menu)
        self._pause_resume_action.triggered.connect(self.toggle_listening_requested.emit)
        self._menu.addAction(self._pause_resume_action)

        self._menu.addSeparator()

        # Exit IRIS
        self._exit_action = QAction("Exit IRIS Completely", self._menu)
        self._exit_action.triggered.connect(self.exit_requested.emit)
        self._menu.addAction(self._exit_action)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:  # Single click
            self.show_settings_requested.emit()

    def show(self) -> None:
        self._tray_icon.show()

    def hide(self) -> None:
        self._tray_icon.hide()

    def update_state(self, state: RuntimeState) -> None:
        self._current_state = state
        self._status_action.setText(f"Status: {state.value}")

        if state == RuntimeState.LISTENING:
            self._tray_icon.setIcon(create_tray_icon_pixmap("#00ff88"))
            self._tray_icon.setToolTip("IRIS - Listening for 'Hey Iris'")
            self._pause_resume_action.setText("Pause Listening")
        elif state == RuntimeState.THINKING:
            self._tray_icon.setIcon(create_tray_icon_pixmap("#ffb800"))
            self._tray_icon.setToolTip("IRIS - Processing Command...")
        elif state == RuntimeState.SPEAKING:
            self._tray_icon.setIcon(create_tray_icon_pixmap("#00d2ff"))
            self._tray_icon.setToolTip("IRIS - Speaking...")
        elif state == RuntimeState.ERROR:
            self._tray_icon.setIcon(create_tray_icon_pixmap("#ff4466"))
            self._tray_icon.setToolTip("IRIS - Diagnostic Error")
        else:
            self._tray_icon.setIcon(create_tray_icon_pixmap("#8b949e"))
            self._tray_icon.setToolTip("IRIS - Paused")
            self._pause_resume_action.setText("Resume Listening")

    def show_message(self, title: str, message: str, msec: int = 3000) -> None:
        """Display Windows native balloon notification."""
        self._tray_icon.showMessage(title, message, QSystemTrayIcon.Information, msec)
