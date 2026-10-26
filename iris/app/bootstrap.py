"""
Project IRIS - Application Bootstrapper
Initializes core components, dependency injection, and returns the runtime container.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from iris.brain.action_planner import ActionPlanner
from iris.brain.model_manager import ModelManager
from iris.core.config import IrisConfig, get_default_base_dir
from iris.core.event_bus import EventBus
from iris.core.logging_setup import setup_logging
from iris.core.state_machine import RuntimeState, StateMachine
from iris.security.confirmations import ConfirmationManager
from iris.security.permissions import PermissionManager
from iris.tools.registry import create_default_registry
from iris.voice.audio_capture import AudioCapture
from iris.voice.stt_adapter import FasterWhisperSTT, MockSTT
from iris.voice.tts_adapter import MockTTS, WindowsSAPI5TTS
from iris.voice.wake_word_adapter import OpenWakeWordAdapter, MockWakeWordAdapter
from iris.voice.voice_pipeline import VoicePipeline

from iris.ipc.server import IPCServer

logger = logging.getLogger("iris.app.bootstrap")


class IrisRuntimeContainer:
    """Dependency container holding all active IRIS system components."""

    def __init__(
        self,
        config: IrisConfig,
        state_machine: StateMachine,
        event_bus: EventBus,
        model_manager: ModelManager,
        action_planner: ActionPlanner,
        tool_registry: Any,
        permission_mgr: PermissionManager,
        confirmation_mgr: ConfirmationManager,
        audio_capture: AudioCapture,
        wake_word: Any,
        stt: Any,
        tts: Any,
        voice_pipeline: VoicePipeline,
        ipc_server: Optional[IPCServer] = None,
    ) -> None:
        self.config = config
        self.state_machine = state_machine
        self.event_bus = event_bus
        self.model_manager = model_manager
        self.action_planner = action_planner
        self.tool_registry = tool_registry
        self.permission_mgr = permission_mgr
        self.confirmation_mgr = confirmation_mgr
        self.audio_capture = audio_capture
        self.wake_word = wake_word
        self.stt = stt
        self.tts = tts
        self.voice_pipeline = voice_pipeline
        self.ipc_server = ipc_server


def bootstrap_iris(
    config_path: Optional[str] = None,
    mock_audio: bool = False,
    mock_models: bool = False,
) -> IrisRuntimeContainer:
    """Initialize and wire all IRIS subsystems."""
    # 1. Setup logging
    setup_logging()
    logger.info("Initializing Project IRIS Runtime...")

    # 2. Configuration
    config = IrisConfig.load(config_path)

    # 3. Core infrastructure
    bus = EventBus()
    state_machine = StateMachine(RuntimeState.IDLE)

    # 4. Tool Registry and Safety
    tool_registry = create_default_registry(
        allowed_apps=config.automation.allowed_applications,
        typing_delay_ms=config.automation.typing_delay_ms,
    )
    permission_mgr = PermissionManager(config.security)
    confirmation_mgr = ConfirmationManager()

    # 5. Local Brain (SmolLM3-3B)
    model_manager = ModelManager(config.model, bus=bus)
    action_planner = ActionPlanner(
        model_manager=model_manager,
        registered_tools=tool_registry.list_tools(),
    )

    # 6. Audio Subsystem
    audio_capture = AudioCapture(
        sample_rate=config.wake_word.sample_rate,
        chunk_size=config.wake_word.chunk_size,
    )

    # 7. Wake-Word Model
    if mock_audio or mock_models:
        wake_word = MockWakeWordAdapter()
    else:
        wake_word = OpenWakeWordAdapter(
            model_path=config.wake_word.model_path,
            melspec_path=config.wake_word.melspec_path,
            embedding_path=config.wake_word.embedding_path,
            threshold=config.wake_word.threshold,
            cooldown_seconds=config.wake_word.cooldown_seconds,
        )

    # 8. STT & TTS
    if mock_audio or mock_models:
        stt = MockSTT()
        tts = MockTTS()
    else:
        stt = FasterWhisperSTT(
            model_size=config.stt.model_size,
            device=config.stt.device,
            compute_type=config.stt.compute_type,
            language=config.stt.language,
        )
        tts = WindowsSAPI5TTS(
            voice_id=config.tts.voice_id,
            rate=config.tts.rate,
            volume=config.tts.volume,
        )

    # 9. Voice Pipeline Orchestrator
    voice_pipeline = VoicePipeline(
        config=config,
        state_machine=state_machine,
        audio_capture=audio_capture,
        wake_word=wake_word,
        stt=stt,
        tts=tts,
        action_planner=action_planner,
        tool_registry=tool_registry,
        permission_mgr=permission_mgr,
        confirmation_mgr=confirmation_mgr,
        bus=bus,
    )

    # 10. IPC Server
    ipc_server = IPCServer()

    def handle_ping(payload: dict) -> dict:
        return {"status": "ok", "message": "pong"}

    def handle_get_state(payload: dict) -> dict:
        return {
            "state": state_machine.current_state.value,
            "model_status": model_manager.status.value,
            "mic_running": audio_capture.is_running,
            "mic_muted": audio_capture.is_muted,
            "voice_paused": voice_pipeline.is_paused,
        }

    def handle_pause(payload: dict) -> dict:
        voice_pipeline.pause_listening()
        return {"status": "paused"}

    def handle_resume(payload: dict) -> dict:
        voice_pipeline.resume_listening()
        return {"status": "resumed"}

    def handle_execute(payload: dict) -> dict:
        command_text = payload.get("text", "")
        if not command_text:
            return {"status": "error", "message": "No text provided"}
        plan = action_planner.plan(command_text)
        results = []
        if plan.intent not in ("answer_question", "ask_clarification"):
            res = tool_registry.execute_action(plan.intent, plan.arguments)
            results.append({"tool": plan.intent, "success": res.success, "result": res.message, "error": res.error})
        return {"status": "ok", "spoken_response": plan.spoken_response, "intent": plan.intent, "arguments": plan.arguments, "actions": results}

    ipc_server.register_command("ping", handle_ping)
    ipc_server.register_command("get_state", handle_get_state)
    ipc_server.register_command("pause_listening", handle_pause)
    ipc_server.register_command("resume_listening", handle_resume)
    ipc_server.register_command("execute_command", handle_execute)

    container = IrisRuntimeContainer(
        config=config,
        state_machine=state_machine,
        event_bus=bus,
        model_manager=model_manager,
        action_planner=action_planner,
        tool_registry=tool_registry,
        permission_mgr=permission_mgr,
        confirmation_mgr=confirmation_mgr,
        audio_capture=audio_capture,
        wake_word=wake_word,
        stt=stt,
        tts=tts,
        voice_pipeline=voice_pipeline,
        ipc_server=ipc_server,
    )

    logger.info("Project IRIS bootstrapped successfully.")
    return container
