"""
Project IRIS - First-Run Setup Wizard
Automated dependency detection, verification, and guided component installer.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iris.core.config import IrisConfig
from iris.setup.downloader import Downloader, DownloadProgress
from iris.setup.environment import EnvironmentInspector
from iris.setup.manifest import COMPONENTS_MANIFEST, ComponentInfo
from iris.setup.verifier import Verifier

logger = logging.getLogger("iris.ui.setup_wizard")


class SetupWizardDialog(QDialog):
    """First-run setup wizard verifying and installing dependencies."""

    setup_completed = Signal()

    def __init__(self, config: IrisConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("IRIS Setup Wizard — Environment & Models")
        self.setMinimumSize(820, 560)
        self._downloader = Downloader()
        self._statuses: Dict[str, str] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel("Welcome to Project IRIS")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #00d2ff;")
        layout.addWidget(header)

        subtitle = QLabel(
            "Verifying local AI brain, wake-word model, and Windows speech/automation dependencies."
        )
        subtitle.setStyleSheet("color: #9ba3af; font-size: 13px;")
        layout.addWidget(subtitle)

        # Dependency Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Component", "Type", "Status", "Details"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.lbl_progress_text = QLabel("Click 'Verify Installation' to begin.")
        self.lbl_progress_text.setStyleSheet("color: #00ff88;")
        layout.addWidget(self.lbl_progress_text)

        # Action Buttons
        btn_box = QHBoxLayout()
        self.btn_verify = QPushButton("Verify Installation")
        self.btn_verify.clicked.connect(self._run_verification)

        self.btn_install_all = QPushButton("Install Missing Components")
        self.btn_install_all.setObjectName("btn_primary")
        self.btn_install_all.clicked.connect(self._install_missing)

        self.btn_finish = QPushButton("Launch IRIS")
        self.btn_finish.setObjectName("btn_success")
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self.accept)

        btn_box.addWidget(self.btn_verify)
        btn_box.addWidget(self.btn_install_all)
        btn_box.addStretch()
        btn_box.addWidget(self.btn_finish)
        layout.addLayout(btn_box)

        # Initial check
        QTimer.singleShot(100, self._run_verification)

    def _run_verification(self) -> None:
        self.table.setRowCount(len(COMPONENTS_MANIFEST))
        all_ready = True

        for row, (cid, comp) in enumerate(COMPONENTS_MANIFEST.items()):
            self.table.setItem(row, 0, QTableWidgetItem(comp.name))
            self.table.setItem(row, 1, QTableWidgetItem(comp.category.upper()))

            status = "Checking"
            details = ""

            if cid == "python_runtime":
                status = "Ready"
                details = f"Python {sys.version.split()[0]} ({sys.executable})"
            elif cid == "wake_word_model":
                if os.path.exists(comp.installed_path):
                    status = "Ready"
                    details = f"Verified: {comp.installed_path}"
                else:
                    status = "Not Installed"
                    details = "Model file hey_iris.onnx missing"
                    all_ready = False
            elif cid == "wake_word_preprocessors":
                melspec = "models/wakeword/melspectrogram.onnx"
                embed = "models/wakeword/embedding_model.onnx"
                if os.path.exists(melspec) and os.path.exists(embed):
                    status = "Ready"
                    details = "Melspectrogram and Embedding ONNX models verified."
                else:
                    status = "Not Installed"
                    details = "Download required (~2.4 MB)"
                    all_ready = False
            elif cid == "smollm3_3b_model":
                if os.path.exists(comp.installed_path):
                    size_mb = os.path.getsize(comp.installed_path) / (1024 * 1024)
                    status = "Ready"
                    details = f"smol-Q4_K_M.gguf ({size_mb:.1f} MB)"
                else:
                    status = "Not Installed"
                    details = "SmolLM3-3B GGUF required (~1.78 GB)"
                    all_ready = False
            elif cid == "stt_engine":
                try:
                    import faster_whisper
                    status = "Ready"
                    details = f"faster_whisper {faster_whisper.__version__}"
                except ImportError:
                    status = "Not Installed"
                    all_ready = False
            elif cid == "tts_engine":
                try:
                    import pyttsx3
                    status = "Ready"
                    details = "Windows SAPI5 voice engine ready."
                except ImportError:
                    status = "Not Installed"
                    all_ready = False
            elif cid == "windows_automation":
                try:
                    import win32gui
                    status = "Ready"
                    details = "pywin32 and UI automation verified."
                except ImportError:
                    status = "Not Installed"
                    all_ready = False
            else:
                status = "Ready"
                details = "OK"

            self._statuses[cid] = status
            item_status = QTableWidgetItem(status)
            item_status.setForeground(Qt.green if status == "Ready" else Qt.yellow)
            self.table.setItem(row, 2, item_status)
            self.table.setItem(row, 3, QTableWidgetItem(details))

        self.btn_finish.setEnabled(all_ready)
        if all_ready:
            self.lbl_progress_text.setText("All components verified! IRIS is ready to launch.")
        else:
            self.lbl_progress_text.setText("Some components need installation. Click 'Install Missing Components'.")

    def _install_missing(self) -> None:
        self.btn_install_all.setEnabled(False)
        self.btn_verify.setEnabled(False)

        def worker():
            # 1. Download wake word preprocessors if needed
            melspec = "models/wakeword/melspectrogram.onnx"
            embed = "models/wakeword/embedding_model.onnx"
            if not os.path.exists(melspec) or not os.path.exists(embed):
                self._downloader.download_file(
                    "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx",
                    melspec,
                )
                self._downloader.download_file(
                    "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx",
                    embed,
                )

            # 2. Download SmolLM3-3B if missing
            smol_path = COMPONENTS_MANIFEST["smollm3_3b_model"].installed_path
            if not os.path.exists(smol_path):
                def progress_cb(p: DownloadProgress):
                    def update_ui():
                        self.progress_bar.setValue(int(p.percent))
                        self.lbl_progress_text.setText(
                            f"Downloading SmolLM3-3B: {p.downloaded_mb:.1f} MB / {p.total_mb:.1f} MB ({p.speed_mbps:.2f} MB/s)"
                        )
                    QTimer.singleShot(0, update_ui)

                self._downloader.download_file(
                    url=COMPONENTS_MANIFEST["smollm3_3b_model"].download_url,
                    dest_path=smol_path,
                    expected_size=COMPONENTS_MANIFEST["smollm3_3b_model"].approx_size_bytes,
                    progress_callback=progress_cb,
                )

            def done():
                self.btn_install_all.setEnabled(True)
                self.btn_verify.setEnabled(True)
                self._run_verification()
            QTimer.singleShot(0, done)

        threading.Thread(target=worker, daemon=True).start()
