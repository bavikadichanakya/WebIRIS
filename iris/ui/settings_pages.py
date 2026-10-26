"""
Project IRIS - Settings and Diagnostics Pages
Contains modular PySide6 widget pages for Dashboard, Brain, Voice, Automation, Setup, and Logs.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iris.brain.model_manager import ModelManager, ModelStatus
from iris.core.config import IrisConfig
from iris.core.event_bus import EventBus, EventTopic
from iris.core.logging_setup import get_recent_logs
from iris.core.state_machine import RuntimeState, StateMachine
from iris.setup.downloader import Downloader, DownloadProgress
from iris.setup.manifest import COMPONENTS_MANIFEST
from iris.setup.verifier import Verifier
from iris.tools.registry import ToolRegistry
from iris.voice.audio_capture import AudioCapture
from iris.voice.tts_adapter import TTSAdapter

logger = logging.getLogger("iris.ui.settings_pages")


# ============================================================================
# 1. Dashboard Page
# ============================================================================
class DashboardPage(QWidget):
    """Runtime status overview, live audio metering, quick controls, and direct SmolLM3-3B command input."""

    pause_toggled = Signal(bool)

    def __init__(
        self,
        config: IrisConfig,
        state_machine: StateMachine,
        audio_capture: AudioCapture,
        bus: EventBus,
        action_planner: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        tts: Optional[Any] = None,
        voice_pipeline: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.state_machine = state_machine
        self.audio_capture = audio_capture
        self.bus = bus
        self.action_planner = action_planner
        self.tool_registry = tool_registry
        self.tts = tts
        self.voice_pipeline = voice_pipeline
        self._init_ui()

        # Connect audio level meter
        self.audio_capture.add_level_callback(self._on_audio_level)
        self.bus.subscribe(EventTopic.STATE_CHANGED, self._on_state_changed)
        self.bus.subscribe(EventTopic.TRANSCRIPTION_COMPLETED, self._on_transcription)
        self.bus.subscribe(EventTopic.TTS_START, self._on_tts_start)

        # Periodic check for mic status
        self._mic_check_timer = QTimer(self)
        self._mic_check_timer.setInterval(2000)
        self._mic_check_timer.timeout.connect(self._check_mic_status)
        self._mic_check_timer.start()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header Title
        title = QLabel("System Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # 1. Runtime State Card
        state_card = QGroupBox("Runtime Status")
        sc_layout = QHBoxLayout(state_card)

        self.lbl_state_pill = QLabel("IDLE")
        self.lbl_state_pill.setObjectName("pill_idle")
        self.lbl_state_pill.setAlignment(Qt.AlignCenter)
        self.lbl_state_pill.setFixedWidth(160)

        self.btn_toggle_pause = QPushButton("Pause Listening")
        self.btn_toggle_pause.setObjectName("btn_primary")
        self.btn_toggle_pause.clicked.connect(self._toggle_pause)

        sc_layout.addWidget(QLabel("Current Engine State:"))
        sc_layout.addWidget(self.lbl_state_pill)
        sc_layout.addStretch()
        sc_layout.addWidget(self.btn_toggle_pause)
        layout.addWidget(state_card)

        # 2. Microphone & Audio Meter Card
        mic_card = QGroupBox("Microphone & Audio Activity")
        mc_layout = QVBoxLayout(mic_card)

        # Mic warning banner (shown when mic capture is blocked or offline)
        self.mic_warning_frame = QFrame()
        self.mic_warning_frame.setStyleSheet(
            "background-color: #2b1f14; border: 1px solid #f59e0b; border-radius: 6px; padding: 6px;"
        )
        mw_layout = QHBoxLayout(self.mic_warning_frame)
        self.lbl_mic_status = QLabel("⚠️ Microphone unavailable. Enable 'Microphone access' in Windows Settings.")
        self.lbl_mic_status.setStyleSheet("color: #fbbf24; font-size: 12px; font-weight: 500; border: none;")
        self.btn_open_win_mic = QPushButton("Open Windows Mic Settings")
        self.btn_open_win_mic.setStyleSheet(
            "background-color: #f59e0b; color: #000000; font-weight: bold; padding: 4px 10px; border-radius: 4px;"
        )
        self.btn_open_win_mic.clicked.connect(self._open_windows_mic_settings)
        self.btn_retry_mic = QPushButton("Retry Mic")
        self.btn_retry_mic.setStyleSheet(
            "background-color: #334155; color: #ffffff; padding: 4px 10px; border-radius: 4px;"
        )
        self.btn_retry_mic.clicked.connect(self._retry_microphone)
        mw_layout.addWidget(self.lbl_mic_status)
        mw_layout.addStretch()
        mw_layout.addWidget(self.btn_open_win_mic)
        mw_layout.addWidget(self.btn_retry_mic)
        mc_layout.addWidget(self.mic_warning_frame)

        if self.audio_capture.is_running:
            self.mic_warning_frame.hide()

        meter_layout = QHBoxLayout()
        meter_layout.addWidget(QLabel("Input Level:"))
        self.progress_audio = QProgressBar()
        self.progress_audio.setRange(0, 100)
        self.progress_audio.setValue(0)
        meter_layout.addWidget(self.progress_audio)
        mc_layout.addLayout(meter_layout)

        sens_layout = QHBoxLayout()
        sens_layout.addWidget(QLabel("Wake-Word Sensitivity:"))
        self.slider_sens = QSlider(Qt.Horizontal)
        self.slider_sens.setRange(10, 95)
        self.slider_sens.setValue(int(self.config.wake_word.threshold * 100))
        self.slider_sens.valueChanged.connect(self._on_sens_changed)
        self.lbl_sens_val = QLabel(f"{self.config.wake_word.threshold:.2f}")
        sens_layout.addWidget(self.slider_sens)
        sens_layout.addWidget(self.lbl_sens_val)
        mc_layout.addLayout(sens_layout)

        layout.addWidget(mic_card)

        # 3. Direct Natural Language Command Box (SmolLM3-3B Brain)
        cmd_card = QGroupBox("Direct Command Execution (Local SmolLM3-3B Brain)")
        cc_layout = QVBoxLayout(cmd_card)

        row_input = QHBoxLayout()
        self.txt_command_input = QLineEdit()
        self.txt_command_input.setPlaceholderText("e.g. 'open notepad', 'minimize active window', 'type hello world'...")
        self.txt_command_input.returnPressed.connect(self._execute_direct_command)
        self.btn_run_cmd = QPushButton("Execute with SmolLM3-3B")
        self.btn_run_cmd.setObjectName("btn_primary")
        self.btn_run_cmd.clicked.connect(self._execute_direct_command)
        row_input.addWidget(self.txt_command_input)
        row_input.addWidget(self.btn_run_cmd)
        cc_layout.addLayout(row_input)

        self.lbl_cmd_feedback = QLabel("")
        self.lbl_cmd_feedback.setStyleSheet("color: #38bdf8; font-size: 12px; padding: 2px;")
        cc_layout.addWidget(self.lbl_cmd_feedback)
        layout.addWidget(cmd_card)

        # 4. Recent Speech Interaction Cards
        inter_card = QGroupBox("Recent Voice & Natural Language Interaction")
        ic_layout = QVBoxLayout(inter_card)

        ic_layout.addWidget(QLabel("Last Recognized Command:"))
        self.lbl_last_cmd = QLabel("<i>(Waiting for command...)</i>")
        self.lbl_last_cmd.setStyleSheet("color: #00d2ff; font-size: 14px; padding: 4px;")
        ic_layout.addWidget(self.lbl_last_cmd)

        ic_layout.addWidget(QLabel("Last Spoken Response:"))
        self.lbl_last_resp = QLabel("<i>(None)</i>")
        self.lbl_last_resp.setStyleSheet("color: #00ff88; font-size: 14px; padding: 4px;")
        ic_layout.addWidget(self.lbl_last_resp)

        layout.addWidget(inter_card)
        layout.addStretch()

    def _open_windows_mic_settings(self) -> None:
        import subprocess
        try:
            subprocess.Popen(["cmd", "/c", "start", "ms-settings:privacy-microphone"], shell=True)
        except Exception as e:
            logger.error(f"Failed to open Windows mic settings: {e}")

    def _retry_microphone(self) -> None:
        if self.voice_pipeline:
            self.voice_pipeline.audio_capture.stop()
            started = self.voice_pipeline.audio_capture.start()
            if started:
                self.mic_warning_frame.hide()
                if not self.voice_pipeline.is_running:
                    self.voice_pipeline.start()
            else:
                self.mic_warning_frame.show()
        else:
            self.audio_capture.stop()
            if self.audio_capture.start():
                self.mic_warning_frame.hide()
            else:
                self.mic_warning_frame.show()

    def _check_mic_status(self) -> None:
        if self.audio_capture.is_running:
            if not self.mic_warning_frame.isHidden():
                self.mic_warning_frame.hide()
        else:
            if self.mic_warning_frame.isHidden():
                self.mic_warning_frame.show()

    def _execute_direct_command(self) -> None:
        text = self.txt_command_input.text().strip()
        if not text:
            return
        self.txt_command_input.clear()
        self.lbl_last_cmd.setText(f'<b>"{text}"</b>')
        self.lbl_cmd_feedback.setText("SmolLM3-3B thinking...")
        self.state_machine.transition_to(RuntimeState.THINKING, reason="Executing direct UI command")

        def _bg_task() -> None:
            try:
                plan = self.action_planner.plan(text) if self.action_planner else None
                actions_summary = []
                if plan and plan.intent not in ("answer_question", "ask_clarification") and self.tool_registry:
                    self.state_machine.transition_to(RuntimeState.EXECUTING, reason="Executing action plan")
                    res = self.tool_registry.execute(plan.intent, plan.arguments)
                    status_str = "OK" if res.success else f"Failed: {res.error}"
                    actions_summary.append(f"{plan.intent} -> {status_str}")

                resp = plan.spoken_response if plan else f"Processed: {text}"
                feedback = f"Plan: {resp}"
                if actions_summary:
                    feedback += " | " + ", ".join(actions_summary)

                QTimer.singleShot(0, lambda: self.lbl_last_resp.setText(f'<b>"{resp}"</b>'))
                QTimer.singleShot(0, lambda: self.lbl_cmd_feedback.setText(feedback))

                if self.tts and resp:
                    self.state_machine.transition_to(RuntimeState.SPEAKING, reason="Speaking response")
                    self.tts.speak(resp)
            except Exception as e:
                logger.error(f"Direct command error: {e}", exc_info=True)
                err_msg = str(e)
                QTimer.singleShot(0, lambda: self.lbl_cmd_feedback.setText(f"Error: {err_msg}"))
            finally:
                QTimer.singleShot(0, lambda: self.state_machine.transition_to(RuntimeState.IDLE, reason="Direct command completed"))

        threading.Thread(target=_bg_task, daemon=True).start()

    def _on_audio_level(self, level_0_to_1: float) -> None:
        # Triggered from audio thread; schedule update on Qt GUI thread
        val = int(level_0_to_1 * 100)
        QTimer.singleShot(0, lambda: self.progress_audio.setValue(val))

    def _on_state_changed(self, data: Any) -> None:
        state = self.state_machine.current_state
        QTimer.singleShot(0, lambda: self.update_state_display(state))

    def update_state_display(self, state: RuntimeState) -> None:
        self.lbl_state_pill.setText(state.value)
        if state == RuntimeState.LISTENING:
            self.lbl_state_pill.setObjectName("pill_listening")
            self.btn_toggle_pause.setText("Pause Listening")
        elif state == RuntimeState.THINKING:
            self.lbl_state_pill.setObjectName("pill_thinking")
        elif state == RuntimeState.ERROR:
            self.lbl_state_pill.setObjectName("pill_error")
        else:
            self.lbl_state_pill.setObjectName("pill_idle")
            self.btn_toggle_pause.setText("Resume Listening")
        # Force stylesheet refresh
        self.lbl_state_pill.style().unpolish(self.lbl_state_pill)
        self.lbl_state_pill.style().polish(self.lbl_state_pill)

    def _toggle_pause(self) -> None:
        is_paused = self.btn_toggle_pause.text().startswith("Resume")
        self.pause_toggled.emit(not is_paused)

    def _on_sens_changed(self, value: int) -> None:
        thresh = value / 100.0
        self.lbl_sens_val.setText(f"{thresh:.2f}")
        self.config.wake_word.threshold = thresh

    def _on_transcription(self, data: Any) -> None:
        text = data.get("text", "")
        QTimer.singleShot(0, lambda: self.lbl_last_cmd.setText(f"<b>\"{text}\"</b>"))

    def _on_tts_start(self, data: Any) -> None:
        text = data.get("text", "")
        QTimer.singleShot(0, lambda: self.lbl_last_resp.setText(f"<b>\"{text}\"</b>"))


# ============================================================================
# 2. SmolLM3-3B Brain Settings Page
# ============================================================================
class BrainSettingsPage(QWidget):
    """Configuration, inference testing, and metrics for the local SmolLM3-3B model."""

    def __init__(
        self,
        config: IrisConfig,
        model_manager: ModelManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.model_manager = model_manager
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("SmolLM3-3B Local Brain")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # 1. Model Configuration Card
        cfg_card = QGroupBox("Model File & Runtime Backend")
        form = QFormLayout(cfg_card)

        # Path selector
        path_layout = QHBoxLayout()
        self.edit_model_path = QLineEdit(self.config.model.model_path)
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_model)
        path_layout.addWidget(self.edit_model_path)
        path_layout.addWidget(self.btn_browse)
        form.addRow("Model Path:", path_layout)

        # Backend Selector
        self.combo_backend = QComboBox()
        self.combo_backend.addItems(["auto", "llama_cpp", "transformers"])
        self.combo_backend.setCurrentText(self.config.model.backend)
        form.addRow("Backend:", self.combo_backend)

        # Parameters
        self.spin_ctx = QSpinBox()
        self.spin_ctx.setRange(256, 8192)
        self.spin_ctx.setValue(self.config.model.context_length)
        form.addRow("Context Length:", self.spin_ctx)

        self.spin_tokens = QSpinBox()
        self.spin_tokens.setRange(32, 2048)
        self.spin_tokens.setValue(self.config.model.max_output_tokens)
        form.addRow("Max Tokens:", self.spin_tokens)

        # Status & Load Button
        status_layout = QHBoxLayout()
        self.lbl_status = QLabel(f"Status: {self.model_manager.status.value}")
        self.lbl_status.setStyleSheet("font-weight: 600; color: #00d2ff;")
        self.btn_load_model = QPushButton("Load / Reload Model")
        self.btn_load_model.setObjectName("btn_primary")
        self.btn_load_model.clicked.connect(self._load_model)
        status_layout.addWidget(self.lbl_status)
        status_layout.addStretch()
        status_layout.addWidget(self.btn_load_model)
        form.addRow(status_layout)

        layout.addWidget(cfg_card)

        # 2. Interactive Inference Sandbox
        test_card = QGroupBox("Interactive Inference Sandbox")
        tc_layout = QVBoxLayout(test_card)

        tc_layout.addWidget(QLabel("Test Prompt:"))
        self.edit_prompt = QLineEdit("Say 'Hello from SmolLM3-3B' in JSON format.")
        tc_layout.addWidget(self.edit_prompt)

        btn_row = QHBoxLayout()
        self.btn_run_test = QPushButton("Generate Response")
        self.btn_run_test.clicked.connect(self._run_test_inference)
        self.lbl_test_metrics = QLabel("Latency: - | Speed: -")
        self.lbl_test_metrics.setStyleSheet("color: #9ba3af;")
        btn_row.addWidget(self.btn_run_test)
        btn_row.addWidget(self.lbl_test_metrics)
        btn_row.addStretch()
        tc_layout.addLayout(btn_row)

        tc_layout.addWidget(QLabel("Model Output:"))
        self.txt_output = QPlainTextEdit()
        self.txt_output.setReadOnly(True)
        self.txt_output.setFixedHeight(120)
        tc_layout.addWidget(self.txt_output)

        layout.addWidget(test_card)
        layout.addStretch()

    def _browse_model(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Model File", os.getcwd(), "Model Files (*.gguf *.bin *.safetensors)"
        )
        if filepath:
            self.edit_model_path.setText(filepath)
            self.config.model.model_path = filepath

    def _load_model(self) -> None:
        self.config.model.model_path = self.edit_model_path.text().strip()
        self.config.model.backend = self.combo_backend.currentText()
        self.config.model.context_length = self.spin_ctx.value()
        self.config.model.max_output_tokens = self.spin_tokens.value()

        self.btn_load_model.setEnabled(False)
        self.lbl_status.setText("Status: LOADING...")

        def on_done(success: bool, msg: str):
            def gui_update():
                self.btn_load_model.setEnabled(True)
                self.lbl_status.setText(f"Status: {self.model_manager.status.value}")
                if not success:
                    self.lbl_status.setText(f"Status: ERROR - {msg[:40]}")
            QTimer.singleShot(0, gui_update)

        self.model_manager.load_model_async(on_done)

    def _run_test_inference(self) -> None:
        prompt = self.edit_prompt.text().strip()
        if not prompt:
            return

        self.btn_run_test.setEnabled(False)
        self.txt_output.setPlainText("Generating...")

        def on_result(text: Optional[str], exc: Optional[Exception]):
            def gui_update():
                self.btn_run_test.setEnabled(True)
                if exc:
                    self.txt_output.setPlainText(f"Error: {exc}")
                elif text:
                    self.txt_output.setPlainText(text)
                    if self.model_manager.backend:
                        m = self.model_manager.backend.metrics
                        self.lbl_test_metrics.setText(
                            f"Latency: {m.last_latency_ms:.1f}ms | Speed: {m.last_tokens_per_sec:.1f} tok/s"
                        )
            QTimer.singleShot(0, gui_update)

        self.model_manager.generate_async(prompt, on_result)


# ============================================================================
# 3. Voice & Audio Settings Page
# ============================================================================
class VoiceSettingsPage(QWidget):
    """Configuration for microphone, wake-word, STT, and TTS engines."""

    def __init__(
        self,
        config: IrisConfig,
        tts: TTSAdapter,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.tts = tts
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Voice & Audio Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # 1. Microphone Input Device
        mic_card = QGroupBox("Microphone Input")
        form_mic = QFormLayout(mic_card)
        self.combo_mic = QComboBox()
        self._refresh_mic_devices()
        form_mic.addRow("Input Device:", self.combo_mic)
        layout.addWidget(mic_card)

        # 2. Wake-Word Model Card
        ww_card = QGroupBox("Wake-Word Detection ('Hey Iris')")
        form_ww = QFormLayout(ww_card)
        self.edit_ww_path = QLineEdit(self.config.wake_word.model_path)
        form_ww.addRow("Model Path:", self.edit_ww_path)
        layout.addWidget(ww_card)

        # 3. Speech-to-Text (STT) Card
        stt_card = QGroupBox("Speech-to-Text (STT)")
        form_stt = QFormLayout(stt_card)
        self.combo_stt_backend = QComboBox()
        self.combo_stt_backend.addItems(["faster_whisper", "mock"])
        self.combo_stt_backend.setCurrentText(self.config.stt.backend)
        form_stt.addRow("Engine:", self.combo_stt_backend)

        self.combo_stt_size = QComboBox()
        self.combo_stt_size.addItems(["tiny.en", "base.en", "small.en"])
        self.combo_stt_size.setCurrentText(self.config.stt.model_size)
        form_stt.addRow("Model Size:", self.combo_stt_size)
        layout.addWidget(stt_card)

        # 4. Text-to-Speech (TTS) Card
        tts_card = QGroupBox("Text-to-Speech (TTS)")
        form_tts = QFormLayout(tts_card)

        self.combo_tts_backend = QComboBox()
        self.combo_tts_backend.addItems(["sapi5", "piper", "mock"])
        self.combo_tts_backend.setCurrentText(self.config.tts.backend)
        form_tts.addRow("TTS Backend:", self.combo_tts_backend)

        self.combo_voice = QComboBox()
        self._refresh_voices()
        form_tts.addRow("Voice:", self.combo_voice)

        self.slider_rate = QSlider(Qt.Horizontal)
        self.slider_rate.setRange(120, 250)
        self.slider_rate.setValue(self.config.tts.rate)
        form_tts.addRow("Speech Rate:", self.slider_rate)

        test_tts_btn = QPushButton("Test Voice Output")
        test_tts_btn.clicked.connect(self._test_tts)
        form_tts.addRow("", test_tts_btn)
        layout.addWidget(tts_card)

        layout.addStretch()

    def _refresh_mic_devices(self) -> None:
        self.combo_mic.clear()
        devs = AudioCapture.list_input_devices()
        if not devs:
            self.combo_mic.addItem("Default Microphone", None)
        for d in devs:
            self.combo_mic.addItem(d["name"], d["index"])

    def _refresh_voices(self) -> None:
        self.combo_voice.clear()
        voices = self.tts.get_voices()
        for v in voices:
            self.combo_voice.addItem(v["name"], v["id"])

    def _test_tts(self) -> None:
        threading.Thread(
            target=lambda: self.tts.speak("This is a test of the IRIS voice synthesis system."),
            daemon=True,
        ).start()


# ============================================================================
# 4. Windows Automation & Tools Settings Page
# ============================================================================
class AutomationSettingsPage(QWidget):
    """Permissions, safety boundaries, and approved application catalogue."""

    def __init__(
        self,
        config: IrisConfig,
        tool_registry: ToolRegistry,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.tool_registry = tool_registry
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Windows Automation & Tool Security")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # 1. Tool Permissions Table
        perm_card = QGroupBox("Tool Permissions")
        pc_layout = QVBoxLayout(perm_card)

        self.table_tools = QTableWidget()
        self.table_tools.setColumnCount(3)
        self.table_tools.setHorizontalHeaderLabels(["Tool Intent", "Description", "Permission Policy"])
        self.table_tools.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_tools.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_tools.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_tools.setFixedHeight(220)
        self._populate_tools_table()
        pc_layout.addWidget(self.table_tools)
        layout.addWidget(perm_card)

        # 2. Approved Applications
        apps_card = QGroupBox("Approved Applications Allowlist")
        ac_layout = QVBoxLayout(apps_card)

        self.table_apps = QTableWidget()
        self.table_apps.setColumnCount(2)
        self.table_apps.setHorizontalHeaderLabels(["Application Name", "Executable Path"])
        self.table_apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_apps.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_apps.setFixedHeight(180)
        self._populate_apps_table()
        ac_layout.addWidget(self.table_apps)

        btn_row = QHBoxLayout()
        self.btn_add_app = QPushButton("Add Application...")
        self.btn_add_app.clicked.connect(self._add_app)
        self.btn_remove_app = QPushButton("Remove Selected")
        self.btn_remove_app.clicked.connect(self._remove_app)
        btn_row.addWidget(self.btn_add_app)
        btn_row.addWidget(self.btn_remove_app)
        btn_row.addStretch()
        ac_layout.addLayout(btn_row)

        layout.addWidget(apps_card)
        layout.addStretch()

    def _populate_tools_table(self) -> None:
        tools = self.tool_registry.list_tools()
        self.table_tools.setRowCount(len(tools))
        for row, (name, tool) in enumerate(tools.items()):
            self.table_tools.setItem(row, 0, QTableWidgetItem(name))
            self.table_tools.setItem(row, 1, QTableWidgetItem(tool.description))

            combo = QComboBox()
            combo.addItems(["allow", "confirm", "deny"])
            curr_policy = self.config.security.tool_permissions.get(name, "allow")
            combo.setCurrentText(curr_policy)
            combo.currentTextChanged.connect(
                lambda val, n=name: self._on_perm_changed(n, val)
            )
            self.table_tools.setCellWidget(row, 2, combo)

    def _on_perm_changed(self, tool_name: str, policy: str) -> None:
        self.config.security.tool_permissions[tool_name] = policy
        logger.info(f"Updated permission for '{tool_name}' to '{policy}'")

    def _populate_apps_table(self) -> None:
        apps = self.config.automation.allowed_applications
        self.table_apps.setRowCount(len(apps))
        for row, (name, exe) in enumerate(apps.items()):
            self.table_apps.setItem(row, 0, QTableWidgetItem(name))
            self.table_apps.setItem(row, 1, QTableWidgetItem(exe))

    def _add_app(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Application Executable", os.environ.get("ProgramFiles", r"C:\Program Files"), "Executables (*.exe *.cmd *.bat)"
        )
        if filepath:
            name = os.path.splitext(os.path.basename(filepath))[0].lower()
            self.config.automation.allowed_applications[name] = filepath
            self._populate_apps_table()

    def _remove_app(self) -> None:
        curr_row = self.table_apps.currentRow()
        if curr_row >= 0:
            name_item = self.table_apps.item(curr_row, 0)
            if name_item and name_item.text() in self.config.automation.allowed_applications:
                del self.config.automation.allowed_applications[name_item.text()]
                self._populate_apps_table()


# ============================================================================
# 5. Setup & Models Dashboard Page
# ============================================================================
class SetupModelsPage(QWidget):
    """Component inspection, automatic downloading, and offline readiness checks."""

    def __init__(
        self,
        config: IrisConfig,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._downloader = Downloader()
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Setup & Model Management")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # 1. Component Health Table
        comp_card = QGroupBox("Installed Components Status")
        cc_layout = QVBoxLayout(comp_card)

        self.table_comps = QTableWidget()
        self.table_comps.setColumnCount(4)
        self.table_comps.setHorizontalHeaderLabels(["Component", "Category", "Status", "Path / Details"])
        self.table_comps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_comps.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_comps.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_comps.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_comps.setFixedHeight(220)
        cc_layout.addWidget(self.table_comps)

        btn_row = QHBoxLayout()
        self.btn_check_all = QPushButton("Verify All Components")
        self.btn_check_all.clicked.connect(self._check_all_components)
        self.btn_download_brain = QPushButton("Download SmolLM3-3B (1.78 GB)")
        self.btn_download_brain.setObjectName("btn_primary")
        self.btn_download_brain.clicked.connect(self._start_smollm_download)

        btn_row.addWidget(self.btn_check_all)
        btn_row.addWidget(self.btn_download_brain)
        btn_row.addStretch()
        cc_layout.addLayout(btn_row)
        layout.addWidget(comp_card)

        # 2. Live Download Progress Card
        dl_card = QGroupBox("Download Operations")
        dl_layout = QVBoxLayout(dl_card)

        self.lbl_dl_status = QLabel("Ready.")
        self.lbl_dl_status.setStyleSheet("color: #9ba3af;")
        dl_layout.addWidget(self.lbl_dl_status)

        self.progress_dl = QProgressBar()
        self.progress_dl.setRange(0, 100)
        self.progress_dl.setValue(0)
        dl_layout.addWidget(self.progress_dl)

        dl_ctrl_row = QHBoxLayout()
        self.lbl_dl_details = QLabel("0 MB / 0 MB (0 MB/s) | ETA: -")
        self.lbl_dl_details.setStyleSheet("color: #00d2ff;")
        self.btn_cancel_dl = QPushButton("Cancel Download")
        self.btn_cancel_dl.setObjectName("btn_danger")
        self.btn_cancel_dl.setEnabled(False)
        self.btn_cancel_dl.clicked.connect(self._cancel_download)

        dl_ctrl_row.addWidget(self.lbl_dl_details)
        dl_ctrl_row.addStretch()
        dl_ctrl_row.addWidget(self.btn_cancel_dl)
        dl_layout.addLayout(dl_ctrl_row)

        layout.addWidget(dl_card)
        layout.addStretch()

        # Run initial check
        QTimer.singleShot(100, self._check_all_components)

    def _check_all_components(self) -> None:
        self.table_comps.setRowCount(len(COMPONENTS_MANIFEST))
        for row, (cid, comp) in enumerate(COMPONENTS_MANIFEST.items()):
            self.table_comps.setItem(row, 0, QTableWidgetItem(comp.name))
            self.table_comps.setItem(row, 1, QTableWidgetItem(comp.category.upper()))

            status = "Ready"
            details = comp.installed_path or "System Built-in"

            if comp.installed_path:
                if os.path.exists(comp.installed_path):
                    size_mb = os.path.getsize(comp.installed_path) / (1024 * 1024)
                    details = f"{comp.installed_path} ({size_mb:.1f} MB)"
                    status = "Ready"
                else:
                    status = "Missing"
                    details = f"Not found at: {comp.installed_path}"

            item_status = QTableWidgetItem(status)
            item_status.setForeground(Qt.green if status == "Ready" else Qt.red)
            self.table_comps.setItem(row, 2, item_status)
            self.table_comps.setItem(row, 3, QTableWidgetItem(details))

    def _start_smollm_download(self) -> None:
        comp = COMPONENTS_MANIFEST["smollm3_3b_model"]
        url = comp.download_url
        dest = comp.installed_path

        self.btn_download_brain.setEnabled(False)
        self.btn_cancel_dl.setEnabled(True)
        self.lbl_dl_status.setText("Downloading SmolLM3-3B (smol-Q4_K_M.gguf)...")

        def progress_cb(p: DownloadProgress):
            def update_gui():
                self.progress_dl.setValue(int(p.percent))
                eta_str = f"{int(p.eta_seconds)}s" if p.eta_seconds > 0 else "-"
                self.lbl_dl_details.setText(
                    f"{p.downloaded_mb:.1f} MB / {p.total_mb:.1f} MB ({p.speed_mbps:.2f} MB/s) | ETA: {eta_str}"
                )
            QTimer.singleShot(0, update_gui)

        def worker():
            try:
                success = self._downloader.download_file(
                    url=url,
                    dest_path=dest,
                    expected_size=comp.approx_size_bytes,
                    progress_callback=progress_cb,
                )
                def done_gui():
                    self.btn_download_brain.setEnabled(True)
                    self.btn_cancel_dl.setEnabled(False)
                    if success:
                        self.lbl_dl_status.setText("SmolLM3-3B download and verification complete!")
                        self._check_all_components()
                    else:
                        self.lbl_dl_status.setText("Download cancelled.")
                QTimer.singleShot(0, done_gui)
            except Exception as e:
                def err_gui():
                    self.btn_download_brain.setEnabled(True)
                    self.btn_cancel_dl.setEnabled(False)
                    self.lbl_dl_status.setText(f"Download failed: {e}")
                QTimer.singleShot(0, err_gui)

        threading.Thread(target=worker, daemon=True).start()

    def _cancel_download(self) -> None:
        self._downloader.cancel()
        self.btn_cancel_dl.setEnabled(False)


# ============================================================================
# 6. Logs & Diagnostics Page
# ============================================================================
class DiagnosticsPage(QWidget):
    """Real-time operational log viewer with filtering and export."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_logs)
        self._timer.start(1000)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("System Logs & Operational Diagnostics")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("Filter Level:"))
        self.combo_level = QComboBox()
        self.combo_level.addItems(["ALL", "INFO", "WARNING", "ERROR"])
        self.combo_level.currentTextChanged.connect(self._refresh_logs)
        ctrl_row.addWidget(self.combo_level)

        self.btn_clear = QPushButton("Clear View")
        self.btn_clear.clicked.connect(self._clear_logs)
        ctrl_row.addWidget(self.btn_clear)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        self.txt_logs = QPlainTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; background: #0c0d10;")
        layout.addWidget(self.txt_logs)

    def _refresh_logs(self) -> None:
        filter_lvl = self.combo_level.currentText()
        logs = get_recent_logs(200)
        lines = []
        for entry in logs:
            if filter_lvl != "ALL" and entry["level"] != filter_lvl:
                continue
            lines.append(f"[{entry['time_str']}] [{entry['level']}] [{entry['name']}]: {entry['message']}")

        # Keep scroll position if not at bottom
        self.txt_logs.setPlainText("\n".join(lines))
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )

    def _clear_logs(self) -> None:
        self.txt_logs.clear()
