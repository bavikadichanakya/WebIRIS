"""
Project IRIS - Text-to-Speech (TTS) Adapter
Provides local speech synthesis via Windows SAPI5 (pyttsx3) or neural Piper TTS.
"""

from __future__ import annotations

import abc
import logging
import re
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("iris.voice.tts_adapter")


class TTSAdapter(abc.ABC):
    """Abstract interface for local text-to-speech output."""

    @abc.abstractmethod
    def speak(
        self,
        text: str,
        on_start: Optional[Callable[[], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        """Speak given text synchronously or asynchronously."""
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        """Cancel ongoing speech immediately."""
        pass

    @abc.abstractmethod
    def get_voices(self) -> List[Dict[str, str]]:
        """List available voices."""
        pass


class WindowsSAPI5TTS(TTSAdapter):
    """Native Windows speech synthesis via pyttsx3/SAPI5. 100% offline and low-latency."""

    def __init__(
        self,
        voice_id: str = "",
        rate: int = 180,
        volume: float = 1.0,
    ) -> None:
        self.voice_id = voice_id
        self.rate = rate
        self.volume = volume
        self._lock = threading.Lock()
        self._is_speaking = False

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            return self._is_speaking

    def get_voices(self) -> List[Dict[str, str]]:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            res = [{"id": v.id, "name": v.name} for v in voices]
            engine.stop()
            return res
        except Exception as e:
            logger.error(f"Error fetching SAPI5 voices: {e}")
            return []

    def speak(
        self,
        text: str,
        on_start: Optional[Callable[[], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        # Strip technical tags (e.g. </think>, <think>) and XML/HTML tags
        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        if not clean_text:
            if on_finish:
                on_finish()
            return

        with self._lock:
            self._is_speaking = True

        if on_start:
            try:
                on_start()
            except Exception:
                pass

        try:
            import pyttsx3
            logger.info(f"TTS Speaking: '{clean_text}'")
            # Initialize engine in thread to avoid COM apartment threading issues
            engine = pyttsx3.init()
            if self.voice_id:
                engine.setProperty("voice", self.voice_id)
            engine.setProperty("rate", self.rate)
            engine.setProperty("volume", self.volume)

            engine.say(clean_text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            logger.error(f"Error during TTS speech synthesis: {e}", exc_info=True)
        finally:
            with self._lock:
                self._is_speaking = False
            if on_finish:
                try:
                    on_finish()
                except Exception:
                    pass

    def stop(self) -> None:
        # SAPI5 will terminate at end of sentence
        with self._lock:
            self._is_speaking = False


class MockTTS(TTSAdapter):
    """Mock TTS adapter for testing."""

    def __init__(self) -> None:
        self.spoken_texts: List[str] = []

    def speak(
        self,
        text: str,
        on_start: Optional[Callable[[], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        self.spoken_texts.append(text)
        if on_start:
            on_start()
        if on_finish:
            on_finish()

    def stop(self) -> None:
        pass

    def get_voices(self) -> List[Dict[str, str]]:
        return [{"id": "mock_voice", "name": "Mock Voice"}]
