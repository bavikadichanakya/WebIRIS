"""Unit tests for VoicePipeline integration and state flow."""

import time
import numpy as np
from iris.brain.action_planner import ActionPlanner
from iris.brain.model_manager import ModelManager
from iris.core.config import IrisConfig, ModelConfig
from iris.core.event_bus import EventBus
from iris.core.state_machine import RuntimeState, StateMachine
from iris.security.confirmations import ConfirmationManager
from iris.security.permissions import PermissionManager
from iris.tools.registry import create_default_registry
from iris.voice.audio_capture import AudioCapture
from iris.voice.stt_adapter import MockSTT
from iris.voice.tts_adapter import MockTTS
from iris.voice.wake_word_adapter import MockWakeWordAdapter
from iris.voice.voice_pipeline import VoicePipeline


def test_voice_pipeline_pause_resume():
    config = IrisConfig()
    sm = StateMachine(RuntimeState.IDLE)
    bus = EventBus()
    ac = AudioCapture()
    ww = MockWakeWordAdapter()
    stt = MockSTT()
    tts = MockTTS()
    registry = create_default_registry()
    mgr = ModelManager(ModelConfig())
    planner = ActionPlanner(mgr, registry.list_tools())
    perm = PermissionManager(config.security)
    conf = ConfirmationManager()

    pipeline = VoicePipeline(
        config=config,
        state_machine=sm,
        audio_capture=ac,
        wake_word=ww,
        stt=stt,
        tts=tts,
        action_planner=planner,
        tool_registry=registry,
        permission_mgr=perm,
        confirmation_mgr=conf,
        bus=bus,
    )

    assert not pipeline.is_paused
    pipeline.pause_listening()
    assert pipeline.is_paused
    assert sm.current_state == RuntimeState.IDLE

    pipeline.resume_listening()
    assert not pipeline.is_paused
    assert sm.current_state == RuntimeState.LISTENING


def test_voice_pipeline_cycle_execution():
    config = IrisConfig()
    config.stt.silence_threshold_seconds = 0.2
    config.tts.silent_action_mode = False
    sm = StateMachine(RuntimeState.LISTENING)
    bus = EventBus()
    ac = AudioCapture()
    ww = MockWakeWordAdapter()
    stt = MockSTT(canned_text="open notepad")
    tts = MockTTS()
    registry = create_default_registry()
    mgr = ModelManager(ModelConfig())
    planner = ActionPlanner(mgr, registry.list_tools())
    perm = PermissionManager(config.security)
    conf = ConfirmationManager()

    pipeline = VoicePipeline(
        config=config,
        state_machine=sm,
        audio_capture=ac,
        wake_word=ww,
        stt=stt,
        tts=tts,
        action_planner=planner,
        tool_registry=registry,
        permission_mgr=perm,
        confirmation_mgr=conf,
        bus=bus,
    )

    # Simulate running pipeline with audio chunk in queue
    pipeline._running = True
    # Enqueue speech chunk with sufficient energy
    speech_chunk = (np.ones(1280, dtype=np.int16) * 5000)
    ac._audio_queue.put_nowait(speech_chunk)

    # Simulate wake detection directly
    pipeline._handle_wake_detection(0.95)

    # Verify TTS was triggered with response
    assert len(tts.spoken_texts) > 0
    assert "notepad" in tts.spoken_texts[0].lower() or "opening" in tts.spoken_texts[0].lower()

    # Verify pipeline returned safely to LISTENING
    assert sm.current_state == RuntimeState.LISTENING
