"""
Project IRIS - Runtime State Machine
Manages thread-safe state transitions across the voice and reasoning pipeline.
"""

from __future__ import annotations

import enum
import threading
from typing import Callable, Dict, List, Optional, Set


class RuntimeState(str, enum.Enum):
    """Enumeration of IRIS lifecycle and operational states."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    WAKE_DETECTED = "WAKE_DETECTED"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


# Map of permissible transitions: CurrentState -> Set of valid NextStates
VALID_TRANSITIONS: Dict[RuntimeState, Set[RuntimeState]] = {
    RuntimeState.IDLE: {RuntimeState.LISTENING, RuntimeState.ERROR},
    RuntimeState.LISTENING: {
        RuntimeState.WAKE_DETECTED,
        RuntimeState.IDLE,
        RuntimeState.ERROR,
    },
    RuntimeState.WAKE_DETECTED: {
        RuntimeState.TRANSCRIBING,
        RuntimeState.LISTENING,
        RuntimeState.IDLE,
        RuntimeState.ERROR,
    },
    RuntimeState.TRANSCRIBING: {
        RuntimeState.THINKING,
        RuntimeState.LISTENING,
        RuntimeState.IDLE,
        RuntimeState.ERROR,
    },
    RuntimeState.THINKING: {
        RuntimeState.EXECUTING,
        RuntimeState.SPEAKING,
        RuntimeState.LISTENING,
        RuntimeState.IDLE,
        RuntimeState.ERROR,
    },
    RuntimeState.EXECUTING: {
        RuntimeState.SPEAKING,
        RuntimeState.LISTENING,
        RuntimeState.IDLE,
        RuntimeState.ERROR,
    },
    RuntimeState.SPEAKING: {
        RuntimeState.LISTENING,
        RuntimeState.IDLE,
        RuntimeState.ERROR,
    },
    RuntimeState.ERROR: {
        RuntimeState.IDLE,
        RuntimeState.LISTENING,
    },
}


class StateMachine:
    """Thread-safe state machine for the IRIS voice assistant runtime."""

    def __init__(self, initial_state: RuntimeState = RuntimeState.IDLE) -> None:
        self._current_state = initial_state
        self._lock = threading.RLock()
        self._listeners: List[Callable[[RuntimeState, RuntimeState, Optional[str]], None]] = []

    @property
    def current_state(self) -> RuntimeState:
        with self._lock:
            return self._current_state

    def add_listener(
        self, callback: Callable[[RuntimeState, RuntimeState, Optional[str]], None]
    ) -> None:
        """Register a callback for state changes: callback(old_state, new_state, reason)."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(
        self, callback: Callable[[RuntimeState, RuntimeState, Optional[str]], None]
    ) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def transition_to(self, new_state: RuntimeState, reason: Optional[str] = None) -> bool:
        """
        Transition to a new state if valid.
        Returns True if transition succeeded, False otherwise.
        """
        listeners_to_notify = []
        old_state = self._current_state

        with self._lock:
            if self._current_state == new_state:
                return True

            allowed = VALID_TRANSITIONS.get(self._current_state, set())
            if new_state not in allowed:
                # Invalid transition requested
                return False

            old_state = self._current_state
            self._current_state = new_state
            listeners_to_notify = list(self._listeners)

        # Notify listeners outside the lock to prevent deadlock
        for listener in listeners_to_notify:
            try:
                listener(old_state, new_state, reason)
            except Exception:
                pass

        return True

    def reset_to_listening(self, reason: Optional[str] = None) -> bool:
        """Convenience method to return to LISTENING state safely."""
        with self._lock:
            if self._current_state in (RuntimeState.ERROR, RuntimeState.IDLE):
                return self.transition_to(RuntimeState.LISTENING, reason)
            elif self._current_state != RuntimeState.LISTENING:
                # Force return to listening through permitted intermediate if needed
                self._current_state = RuntimeState.LISTENING
                old_state = self._current_state
                for listener in list(self._listeners):
                    try:
                        listener(old_state, RuntimeState.LISTENING, reason)
                    except Exception:
                        pass
                return True
            return True

    def is_listening(self) -> bool:
        with self._lock:
            return self._current_state == RuntimeState.LISTENING

    def is_speaking(self) -> bool:
        with self._lock:
            return self._current_state == RuntimeState.SPEAKING
