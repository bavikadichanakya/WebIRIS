"""
Project IRIS - In-Process Event Bus
Provides thread-safe publish/subscribe messaging for all subsystems.
"""

from __future__ import annotations

import collections
import logging
import threading
from typing import Any, Callable, DefaultDict, Dict, List

logger = logging.getLogger("iris.event_bus")


class EventTopic:
    """Predefined event topics for IRIS."""
    STATE_CHANGED = "state.changed"
    WAKE_WORD_TRIGGERED = "voice.wake_word_triggered"
    SPEECH_START = "voice.speech_start"
    TRANSCRIPTION_COMPLETED = "voice.transcription_completed"
    BRAIN_GENERATION_START = "brain.generation_start"
    BRAIN_GENERATION_CHUNK = "brain.generation_chunk"
    BRAIN_PLAN_READY = "brain.plan_ready"
    TOOL_EXECUTION_START = "tool.execution_start"
    TOOL_EXECUTION_SUCCESS = "tool.execution_success"
    TOOL_EXECUTION_FAILURE = "tool.execution_failure"
    TTS_START = "tts.start"
    TTS_FINISH = "tts.finish"
    AUDIO_LEVEL_UPDATE = "voice.audio_level"
    LOG_MESSAGE = "system.log_message"
    ERROR_OCCURRED = "system.error"
    RUNTIME_PAUSED = "runtime.paused"
    RUNTIME_RESUMED = "runtime.resumed"


class EventBus:
    """Thread-safe event bus supporting topic-based subscriptions."""

    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls) -> EventBus:
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._subscribers = collections.defaultdict(list)
                cls._instance._lock = threading.RLock()
            return cls._instance

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        """Subscribe a handler to a specific topic."""
        with self._lock:
            if handler not in self._subscribers[topic]:
                self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        """Unsubscribe a handler from a topic."""
        with self._lock:
            if handler in self._subscribers[topic]:
                self._subscribers[topic].remove(handler)

    def publish(self, topic: str, data: Any = None) -> None:
        """Publish an event to all subscribers of a topic."""
        with self._lock:
            handlers = list(self._subscribers.get(topic, []))

        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Error executing event handler for topic '{topic}': {e}", exc_info=True)

    def clear(self) -> None:
        """Clear all subscriptions."""
        with self._lock:
            self._subscribers.clear()


# Global default instance
event_bus = EventBus()
