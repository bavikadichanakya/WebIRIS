"""
Project IRIS - Desktop UI Theme & Styling
Modern dark aesthetic with vibrant accents, clean typography, and elevated cards.
"""

from __future__ import annotations

# Complete Qt stylesheet for Project IRIS
IRIS_STYLE_SHEET = """
/* Base Window and Dialogs */
QWidget {
    background-color: #0f1115;
    color: #e4e7eb;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}

/* Sidebar Navigation */
QListWidget#nav_sidebar {
    background-color: #14171d;
    border: none;
    border-right: 1px solid #232730;
    padding-top: 12px;
}

QListWidget#nav_sidebar::item {
    height: 42px;
    padding-left: 16px;
    border-radius: 8px;
    margin: 3px 8px;
    color: #9ba3af;
    font-weight: 500;
}

QListWidget#nav_sidebar::item:hover {
    background-color: #1c2028;
    color: #ffffff;
}

QListWidget#nav_sidebar::item:selected {
    background-color: #0078d4;
    color: #ffffff;
    font-weight: 600;
}

/* ScrollBars */
QScrollBar:vertical {
    background: #14171d;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #2b313d;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #0078d4;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Cards & Groupboxes */
QGroupBox {
    background-color: #161920;
    border: 1px solid #232834;
    border-radius: 10px;
    margin-top: 24px;
    padding: 16px;
    font-weight: 600;
    font-size: 13px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 6px;
    color: #00d2ff;
    padding: 0 6px;
    background-color: #0f1115;
    border-radius: 4px;
}

/* Buttons */
QPushButton {
    background-color: #212631;
    color: #ffffff;
    border: 1px solid #313847;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #2b3240;
    border-color: #0078d4;
}

QPushButton:pressed {
    background-color: #181d26;
}

QPushButton:disabled {
    background-color: #16181f;
    color: #555b66;
    border-color: #20232b;
}

QPushButton#btn_primary {
    background-color: #0078d4;
    border: 1px solid #0086ed;
    font-weight: 600;
}

QPushButton#btn_primary:hover {
    background-color: #1084df;
}

QPushButton#btn_success {
    background-color: #107c41;
    border: 1px solid #138d4b;
}

QPushButton#btn_danger {
    background-color: #a80000;
    border: 1px solid #c20000;
}

/* Input Fields */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #111318;
    color: #ffffff;
    border: 1px solid #282e3c;
    border-radius: 6px;
    padding: 6px 10px;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #00d2ff;
}

/* ComboBox */
QComboBox {
    background-color: #161920;
    color: #ffffff;
    border: 1px solid #282e3c;
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 120px;
}

QComboBox:hover {
    border-color: #0078d4;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #161920;
    border: 1px solid #282e3c;
    selection-background-color: #0078d4;
    color: #ffffff;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background: #232834;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #0078d4;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #0078d4;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: #00d2ff;
}

/* Progress Bar */
QProgressBar {
    background-color: #161920;
    border: 1px solid #282e3c;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    height: 18px;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078d4, stop:1 #00d2ff);
    border-radius: 5px;
}

/* Tables */
QTableWidget {
    background-color: #111318;
    border: 1px solid #232834;
    border-radius: 6px;
    gridline-color: #1c212a;
    color: #e4e7eb;
}

QHeaderView::section {
    background-color: #161920;
    color: #9ba3af;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #232834;
    font-weight: 600;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #1f2735;
    color: #00d2ff;
}

/* Badges and Status Pills */
QLabel#pill_listening {
    background-color: #092e1b;
    color: #00ff88;
    border: 1px solid #0e5e34;
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: 600;
}

QLabel#pill_thinking {
    background-color: #2b1d07;
    color: #ffb800;
    border: 1px solid #573a0e;
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: 600;
}

QLabel#pill_idle {
    background-color: #1c212a;
    color: #8b949e;
    border: 1px solid #2d3542;
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: 600;
}

QLabel#pill_error {
    background-color: #380d12;
    color: #ff4466;
    border: 1px solid #6b1420;
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: 600;
}
"""
