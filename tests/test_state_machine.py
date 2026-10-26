"""Unit tests for the IRIS state machine."""

import pytest
from iris.core.state_machine import RuntimeState, StateMachine


def test_initial_state():
    sm = StateMachine(RuntimeState.IDLE)
    assert sm.current_state == RuntimeState.IDLE


def test_valid_transitions_pipeline():
    sm = StateMachine(RuntimeState.IDLE)
    assert sm.transition_to(RuntimeState.LISTENING)
    assert sm.transition_to(RuntimeState.WAKE_DETECTED)
    assert sm.transition_to(RuntimeState.TRANSCRIBING)
    assert sm.transition_to(RuntimeState.THINKING)
    assert sm.transition_to(RuntimeState.EXECUTING)
    assert sm.transition_to(RuntimeState.SPEAKING)
    assert sm.transition_to(RuntimeState.LISTENING)
    assert sm.current_state == RuntimeState.LISTENING


def test_invalid_transition_rejected():
    sm = StateMachine(RuntimeState.IDLE)
    # Direct jump from IDLE to SPEAKING is invalid
    assert not sm.transition_to(RuntimeState.SPEAKING)
    assert sm.current_state == RuntimeState.IDLE


def test_state_listener():
    sm = StateMachine(RuntimeState.IDLE)
    transitions = []

    def on_change(old, new, reason):
        transitions.append((old, new, reason))

    sm.add_listener(on_change)
    sm.transition_to(RuntimeState.LISTENING, reason="User started")
    sm.transition_to(RuntimeState.WAKE_DETECTED)

    assert len(transitions) == 2
    assert transitions[0] == (RuntimeState.IDLE, RuntimeState.LISTENING, "User started")
    assert transitions[1] == (RuntimeState.LISTENING, RuntimeState.WAKE_DETECTED, None)
