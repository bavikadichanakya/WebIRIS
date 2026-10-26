"""
Project IRIS - Speech-to-Text (STT) Adapter
Provides local speech recognition using Faster-Whisper or pluggable alternatives.
"""

from __future__ import annotations

import abc
import logging
import os
from typing import Any, Dict, Optional
import numpy as np

logger = logging.getLogger("iris.voice.stt_adapter")


class STTAdapter(abc.ABC):
    """Abstract interface for local speech-to-text recognition engines."""

    @abc.abstractmethod
    def load(self) -> bool:
        """Load STT model into memory."""
        pass

    @abc.abstractmethod
    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe 16-bit PCM or float32 audio data into text."""
        pass

    @abc.abstractmethod
    def is_loaded(self) -> bool:
        pass


class FasterWhisperSTT(STTAdapter):
    """Local offline STT powered by Faster-Whisper (CTranslate2)."""

    def __init__(
        self,
        model_size: str = "tiny.en",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model: Any = None
        self._is_loaded = False

    def is_loaded(self) -> bool:
        return self._is_loaded

    def load(self) -> bool:
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Faster-Whisper model '{self.model_size}' on {self.device} ({self.compute_type})...")
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._is_loaded = True
            logger.info("Faster-Whisper model loaded successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to load Faster-Whisper model: {e}", exc_info=True)
            self._is_loaded = False
            return False

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> str:
        if not self._is_loaded or self._model is None:
            logger.warning("STT transcription requested but model is not loaded.")
            return ""

        if len(audio_data) < sample_rate * 0.3:  # Less than 300ms is too short
            return ""

        try:
            # Faster-Whisper expects float32 in range [-1.0, 1.0]
            if audio_data.dtype == np.int16:
                float_audio = audio_data.astype(np.float32) / 32768.0
            else:
                float_audio = audio_data.astype(np.float32)

            segments, info = self._model.transcribe(
                float_audio,
                beam_size=1,
                language=self.language,
                initial_prompt="IRIS, YouTube, Google, Notepad, Calculator, Claude, Codex, Slack, Antigravity, Type, Send it, New chat, Browser, Chrome, Edge, Window, Close.",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            transcription = " ".join([seg.text.strip() for seg in segments]).strip()
            logger.info(f"Transcription: '{transcription}'")
            return transcription
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            return ""


class MockSTT(STTAdapter):
    """Mock STT adapter for testing and deterministic unit test verification."""

    def __init__(self, canned_text: str = "open notepad") -> None:
        self.canned_text = canned_text
        self._is_loaded = True

    def is_loaded(self) -> bool:
        return self._is_loaded

    def load(self) -> bool:
        return True

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> str:
        return self.canned_text
