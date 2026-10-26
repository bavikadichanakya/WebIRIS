"""
Project IRIS - Setup Manifest & Component Metadata
Defines required dependencies, models, and download sources for IRIS.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ComponentInfo(BaseModel):
    """Metadata specification for a required or optional IRIS component."""
    id: str
    name: str
    category: str  # 'runtime', 'model', 'speech', 'automation'
    description: str
    is_required: bool = True
    installed_path: Optional[str] = None
    download_url: Optional[str] = None
    approx_size_bytes: Optional[int] = None
    expected_sha256: Optional[str] = None
    verification_func: Optional[str] = None


# Official component manifest for Project IRIS
COMPONENTS_MANIFEST: Dict[str, ComponentInfo] = {
    "python_runtime": ComponentInfo(
        id="python_runtime",
        name="Python Runtime",
        category="runtime",
        description="Python 3.10+ runtime environment for IRIS.",
        is_required=True,
    ),
    "virtual_environment": ComponentInfo(
        id="virtual_environment",
        name="IRIS Virtual Environment",
        category="runtime",
        description="Isolated virtual environment with pinned packages.",
        is_required=True,
        installed_path=".venv",
    ),
    "wake_word_model": ComponentInfo(
        id="wake_word_model",
        name="Hey Iris Wake-Word Model",
        category="model",
        description="Trained openWakeWord classifier for 'Hey Iris'.",
        is_required=True,
        installed_path="models/wakeword/hey_iris.onnx",
        approx_size_bytes=203304,
    ),
    "wake_word_preprocessors": ComponentInfo(
        id="wake_word_preprocessors",
        name="Wake-Word Feature Models",
        category="model",
        description="openWakeWord melspectrogram and embedding models.",
        is_required=True,
        installed_path="models/wakeword/embedding_model.onnx",
        download_url="https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx",
        approx_size_bytes=2414536,
    ),
    "smollm3_3b_model": ComponentInfo(
        id="smollm3_3b_model",
        name="SmolLM3-3B Local Brain",
        category="model",
        description="Local SmolLM3-3B language & reasoning model (Q4_K_M GGUF format).",
        is_required=True,
        installed_path="models/smollm3/smol-Q4_K_M.gguf",
        download_url="https://huggingface.co/ShayonSarker/SmolLM3-3B-Q4_K_M-GGUF/resolve/main/smol-Q4_K_M.gguf",
        approx_size_bytes=1915300064,
    ),
    "stt_engine": ComponentInfo(
        id="stt_engine",
        name="Faster-Whisper STT",
        category="speech",
        description="Local offline speech-to-text engine (CTranslate2).",
        is_required=True,
    ),
    "tts_engine": ComponentInfo(
        id="tts_engine",
        name="Windows SAPI5 TTS",
        category="speech",
        description="Native Windows speech synthesis (zero download, offline).",
        is_required=True,
    ),
    "windows_automation": ComponentInfo(
        id="windows_automation",
        name="Windows UI Automation",
        category="automation",
        description="Windows pywin32 and UIAutomationCore control libraries.",
        is_required=True,
    ),
}
