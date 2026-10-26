"""
Project IRIS - Configuration Management System
Provides type-safe, validated configuration using Pydantic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


def get_default_base_dir() -> Path:
    """Return the root directory of the IRIS project."""
    return Path(__file__).resolve().parent.parent.parent


class ModelConfig(BaseModel):
    """Configuration for SmolLM3-3B and inference runtime."""
    model_path: str = Field(
        default="models/smollm3/smol-Q4_K_M.gguf",
        description="Path to local SmolLM3-3B model file or directory"
    )
    backend: str = Field(
        default="auto",
        description="Inference backend: 'auto', 'llama_cpp', or 'transformers'"
    )
    context_length: int = Field(default=2048, ge=256, le=8192)
    max_output_tokens: int = Field(default=96, ge=16, le=2048)
    temperature: float = Field(default=0.1, ge=0.0, le=1.5)
    n_threads: int = Field(default=4, ge=1, le=32)
    n_gpu_layers: int = Field(default=0, ge=0, le=128)
    system_prompt: str = Field(
        default=(
            "You are IRIS, an intelligent, concise, and helpful Windows desktop voice assistant. "
            "You control the user's computer via permitted actions. Always output valid JSON."
        )
    )


class WakeWordConfig(BaseModel):
    """Configuration for the local wake-word detector."""
    model_path: str = Field(
        default="models/wakeword/hey_iris.onnx",
        description="Path to hey_iris.onnx model"
    )
    melspec_path: str = Field(
        default="models/wakeword/melspectrogram.onnx",
        description="Path to openWakeWord melspectrogram preprocessor"
    )
    embedding_path: str = Field(
        default="models/wakeword/embedding_model.onnx",
        description="Path to openWakeWord embedding model"
    )
    threshold: float = Field(default=0.5, ge=0.01, le=0.99)
    sample_rate: int = Field(default=16000)
    chunk_size: int = Field(default=1280)  # 80ms at 16kHz
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    cooldown_seconds: float = Field(default=1.5, ge=0.5, le=5.0)
    enabled: bool = Field(default=True)


class STTConfig(BaseModel):
    """Configuration for Speech-to-Text engine."""
    backend: str = Field(default="faster_whisper")  # 'faster_whisper' or 'mock'
    model_size: str = Field(default="tiny.en")       # 'tiny.en', 'base.en', etc.
    language: str = Field(default="en")
    device: str = Field(default="cpu")
    compute_type: str = Field(default="int8")
    silence_threshold_seconds: float = Field(default=0.5, ge=0.2, le=3.0)
    max_record_seconds: float = Field(default=10.0, ge=2.0, le=30.0)


class TTSConfig(BaseModel):
    """Configuration for Text-to-Speech output."""
    backend: str = Field(default="sapi5")  # 'sapi5', 'piper', or 'mock'
    voice_id: str = Field(default="")
    rate: int = Field(default=180, ge=100, le=300)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    piper_model_path: str = Field(default="")
    piper_config_path: str = Field(default="")
    silent_action_mode: bool = Field(
        default=True,
        description="When True, desktop actions execute silently without blocking TTS for fluid hands-free control."
    )


class AutomationConfig(BaseModel):
    """Configuration for Windows automation and safety boundaries."""
    allowed_applications: Dict[str, str] = Field(
        default_factory=lambda: {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "file explorer": "explorer.exe",
            "browser": "msedge.exe",
            "edge": "msedge.exe",
            "chrome": "chrome.exe",
            "code": "code.exe",
            "terminal": "wt.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "task manager": "taskmgr.exe"
        }
    )
    typing_delay_ms: int = Field(default=15, ge=0, le=200)
    allow_submit_on_request: bool = Field(default=True)
    block_password_fields: bool = Field(default=True)


class SecurityConfig(BaseModel):
    """Security and tool execution policies."""
    require_confirmation_for_destructive: bool = Field(default=True)
    require_confirmation_for_submission: bool = Field(default=False)
    tool_permissions: Dict[str, str] = Field(
        default_factory=lambda: {
            "open_application": "allow",
            "focus_window": "allow",
            "switch_window": "allow",
            "type_text": "allow",
            "submit_text": "allow",
            "new_chat": "allow",
            "read_ui_element": "allow",
            "ask_clarification": "allow",
            "answer_question": "allow"
        }
    )
    log_audio: bool = Field(default=False)
    log_transcripts: bool = Field(default=False)


class UIConfig(BaseModel):
    """Configuration for PySide6 desktop interface."""
    start_minimized: bool = Field(default=False)
    close_to_tray: bool = Field(default=True)
    dark_mode: bool = Field(default=True)
    window_width: int = Field(default=960)
    window_height: int = Field(default=680)


class IrisConfig(BaseModel):
    """Root configuration model for Project IRIS."""
    version: str = "1.0.0"
    model: ModelConfig = Field(default_factory=ModelConfig)
    wake_word: WakeWordConfig = Field(default_factory=WakeWordConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    automation: AutomationConfig = Field(default_factory=AutomationConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    def save(self, filepath: Optional[Path | str] = None) -> None:
        """Save configuration to JSON file."""
        if filepath is None:
            filepath = get_default_base_dir() / "config" / "iris_config.json"
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, filepath: Optional[Path | str] = None) -> IrisConfig:
        """Load configuration from JSON file or return default."""
        if filepath is None:
            filepath = get_default_base_dir() / "config" / "iris_config.json"
        filepath = Path(filepath)
        if not filepath.exists():
            config = cls()
            config.save(filepath)
            return config
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.model_validate(data)
        except Exception:
            return cls()
