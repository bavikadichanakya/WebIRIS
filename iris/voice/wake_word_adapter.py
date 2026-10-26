"""
Project IRIS - Wake-Word Detection Adapter
Dedicated adapter for the user's trained 'Hey Iris' openWakeWord ONNX model.
"""

from __future__ import annotations

import abc
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger("iris.voice.wake_word_adapter")


class WakeWordAdapter(abc.ABC):
    """Abstract interface for wake-word detection backends."""

    @abc.abstractmethod
    def load(self) -> bool:
        """Load and initialize wake-word model assets."""
        pass

    @abc.abstractmethod
    def process_audio(self, audio_chunk: np.ndarray) -> Tuple[bool, float]:
        """
        Process an 80ms (1280-sample) 16kHz audio chunk.
        Returns (is_detected, confidence_score_0_to_1).
        """
        pass

    @abc.abstractmethod
    def set_threshold(self, threshold: float) -> None:
        """Set detection threshold (0.01 - 0.99)."""
        pass

    @abc.abstractmethod
    def get_diagnostics(self) -> Dict[str, Any]:
        """Return diagnostic metrics for UI."""
        pass


class OpenWakeWordAdapter(WakeWordAdapter):
    """Production adapter for the user's trained 'hey_iris.onnx' model using openWakeWord."""

    def __init__(
        self,
        model_path: str = "models/wakeword/hey_iris.onnx",
        melspec_path: str = "models/wakeword/melspectrogram.onnx",
        embedding_path: str = "models/wakeword/embedding_model.onnx",
        threshold: float = 0.5,
        cooldown_seconds: float = 1.5,
    ) -> None:
        self.model_path = model_path
        self.melspec_path = melspec_path
        self.embedding_path = embedding_path
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds

        self._model: Any = None
        self._is_loaded = False
        self._last_confidence: float = 0.0
        self._last_trigger_time: float = 0.0
        self._total_triggers: int = 0
        self._model_key: str = "hey_iris"

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load(self) -> bool:
        """Load openWakeWord model and feature extractors."""
        # Check required files
        for p, label in [
            (self.model_path, "Wake word model (hey_iris.onnx)"),
            (self.melspec_path, "Melspectrogram preprocessor"),
            (self.embedding_path, "Speech embedding model"),
        ]:
            if not os.path.exists(p):
                logger.error(f"OpenWakeWordAdapter: {label} not found at: {p}")
                self._is_loaded = False
                return False

        try:
            import openwakeword
            from openwakeword.model import Model

            logger.info(f"Loading wake-word model: {self.model_path}")
            self._model = Model(
                wakeword_models=[self.model_path],
                melspec_model_path=self.melspec_path,
                embedding_model_path=self.embedding_path,
                inference_framework="onnx",
            )
            # Retrieve model key (e.g. 'hey_iris')
            keys = list(self._model.models.keys())
            if keys:
                self._model_key = keys[0]
            self._is_loaded = True
            logger.info(f"Wake-word model loaded successfully. Target key: '{self._model_key}'")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize openWakeWord: {e}", exc_info=True)
            self._is_loaded = False
            return False

    def process_audio(self, audio_chunk: np.ndarray) -> Tuple[bool, float]:
        if not self._is_loaded or self._model is None:
            return False, 0.0

        try:
            # openWakeWord expects 16-bit PCM numpy array of shape (N,)
            if audio_chunk.dtype != np.int16:
                audio_chunk = audio_chunk.astype(np.int16)

            prediction = self._model.predict(audio_chunk)
            score = float(prediction.get(self._model_key, 0.0))
            self._last_confidence = score

            now = time.time()
            if score >= self.threshold:
                if (now - self._last_trigger_time) >= self.cooldown_seconds:
                    self._last_trigger_time = now
                    self._total_triggers += 1
                    logger.info(f"WAKE WORD DETECTED! ('{self._model_key}', confidence={score:.3f})")
                    return True, score
                else:
                    logger.debug(f"Wake word detected but suppressed by cooldown: {score:.3f}")

            return False, score
        except Exception as e:
            logger.error(f"Error in wake-word processing: {e}")
            return False, 0.0

    def set_threshold(self, threshold: float) -> None:
        self.threshold = max(0.01, min(0.99, threshold))
        logger.info(f"Wake-word sensitivity threshold updated to: {self.threshold:.2f}")

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "is_loaded": self._is_loaded,
            "model_path": self.model_path,
            "threshold": self.threshold,
            "last_confidence": round(self._last_confidence, 4),
            "total_triggers": self._total_triggers,
            "cooldown_seconds": self.cooldown_seconds,
        }


class MockWakeWordAdapter(WakeWordAdapter):
    """Mock adapter for testing without audio hardware or ONNX models."""

    def __init__(self, should_trigger: bool = False) -> None:
        self.should_trigger = should_trigger
        self.threshold = 0.5
        self._last_confidence = 0.0
        self._total_triggers = 0

    def load(self) -> bool:
        return True

    def process_audio(self, audio_chunk: np.ndarray) -> Tuple[bool, float]:
        if self.should_trigger:
            self._last_confidence = 0.95
            self._total_triggers += 1
            return True, 0.95
        return False, 0.0

    def set_threshold(self, threshold: float) -> None:
        self.threshold = threshold

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "is_loaded": True,
            "model_path": "mock",
            "threshold": self.threshold,
            "last_confidence": self._last_confidence,
            "total_triggers": self._total_triggers,
        }
