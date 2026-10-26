"""
Project IRIS - Voice Pipeline Orchestrator
Executes the complete system-wide voice loop:
Microphone -> Wake Word ('Hey Iris') -> Command Recording -> STT -> Brain (SmolLM3-3B)
-> Permission -> Automation Execution -> TTS Response -> Loopback-safe Reset.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import numpy as np

from iris.brain.action_planner import ActionPlanner
from iris.core.config import IrisConfig
from iris.core.event_bus import EventBus, EventTopic
from iris.core.state_machine import RuntimeState, StateMachine
from iris.security.confirmations import ConfirmationManager
from iris.security.permissions import PermissionManager
from iris.tools.registry import ToolRegistry
from iris.voice.audio_capture import AudioCapture
from iris.voice.stt_adapter import STTAdapter
from iris.voice.tts_adapter import TTSAdapter
from iris.voice.wake_word_adapter import WakeWordAdapter

logger = logging.getLogger("iris.voice.voice_pipeline")


class VoicePipeline:
    """Manages the background voice listening, processing, and execution thread."""

    def __init__(
        self,
        config: IrisConfig,
        state_machine: StateMachine,
        audio_capture: AudioCapture,
        wake_word: WakeWordAdapter,
        stt: STTAdapter,
        tts: TTSAdapter,
        action_planner: ActionPlanner,
        tool_registry: ToolRegistry,
        permission_mgr: PermissionManager,
        confirmation_mgr: ConfirmationManager,
        bus: Optional[EventBus] = None,
    ) -> None:
        self.config = config
        self.state_machine = state_machine
        self.audio_capture = audio_capture
        self.wake_word = wake_word
        self.stt = stt
        self.tts = tts
        self.action_planner = action_planner
        self.tool_registry = tool_registry
        self.permission_mgr = permission_mgr
        self.confirmation_mgr = confirmation_mgr
        self.bus = bus or EventBus()

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.RLock()
        self._is_paused = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    def pause_listening(self) -> None:
        """Pause wake-word detection."""
        with self._lock:
            self._is_paused = True
        self.state_machine.transition_to(RuntimeState.IDLE, reason="Listening paused by user.")
        self.bus.publish(EventTopic.RUNTIME_PAUSED)
        logger.info("Voice pipeline listening paused.")

    def resume_listening(self) -> None:
        """Resume wake-word detection."""
        with self._lock:
            self._is_paused = False
        self.state_machine.transition_to(RuntimeState.LISTENING, reason="Listening resumed by user.")
        self.bus.publish(EventTopic.RUNTIME_RESUMED)
        logger.info("Voice pipeline listening resumed.")

    def start(self) -> bool:
        """Start the background voice pipeline thread."""
        with self._lock:
            if self._running:
                return True

            # Start audio capture
            if not self.audio_capture.start():
                logger.error("Failed to start audio capture.")
                return False

            self._running = True
            self.state_machine.transition_to(RuntimeState.LISTENING, reason="Voice pipeline started.")
            self._thread = threading.Thread(
                target=self._pipeline_loop,
                name="iris_voice_pipeline_thread",
                daemon=True,
            )
            self._thread.start()
            logger.info("Voice pipeline background loop started.")
            return True

    def stop(self) -> None:
        """Stop background voice thread and release microphone."""
        with self._lock:
            self._running = False
        self.audio_capture.stop()
        self.state_machine.transition_to(RuntimeState.IDLE, reason="Voice pipeline stopped.")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Voice pipeline stopped.")

    def _pipeline_loop(self) -> None:
        """Core loop processing microphone chunks and handling state machine transitions."""
        logger.info("Entering voice pipeline processing loop.")
        while self.is_running:
            try:
                # If paused or not in LISTENING state, sleep briefly
                if self.is_paused or self.state_machine.current_state != RuntimeState.LISTENING:
                    time.sleep(0.05)
                    continue

                chunk = self.audio_capture.read_chunk(timeout=0.2)
                if chunk is None or len(chunk) == 0:
                    continue

                # 1. Evaluate Wake Word
                detected, score = self.wake_word.process_audio(chunk)
                if detected:
                    self._handle_wake_detection(score)

            except Exception as e:
                logger.error(f"Error in voice pipeline loop: {e}", exc_info=True)
                time.sleep(0.5)

    def _handle_wake_detection(self, confidence: float) -> None:
        """Triggered when 'Hey Iris' is recognized. Runs a continuous hands-free interaction session."""
        logger.info(f"Triggering hands-free session (confidence={confidence:.3f}).")
        self.state_machine.transition_to(RuntimeState.WAKE_DETECTED, reason="Wake word triggered.")
        self.bus.publish(EventTopic.WAKE_WORD_TRIGGERED, {"confidence": confidence})

        in_dictation_mode = False
        turns = 0

        # Continuous Hands-Free Session Loop
        while self.is_running:
            turns += 1
            # Initial command has 3.5s timeout; subsequent follow-ups give 10.0s to speak
            turn_timeout = 3.5 if turns == 1 else (8.0 if in_dictation_mode else 10.0)

            # 1. Record User Speech Command
            command_audio = self._record_command_audio(timeout_if_no_speech=turn_timeout)
            if command_audio is None or len(command_audio) == 0:
                if turns == 1:
                    logger.info("No speech captured after wake word; returning to passive LISTENING.")
                else:
                    logger.info("Hands-free session ended due to silence; returning to passive LISTENING.")
                break

            # 2. Transcribe via STT
            self.state_machine.transition_to(RuntimeState.TRANSCRIBING, reason="Transcribing speech.")
            user_text = self.stt.transcribe(command_audio, sample_rate=self.audio_capture.sample_rate)
            if not user_text or not user_text.strip():
                if turns == 1:
                    logger.info("Transcription was empty; returning to LISTENING.")
                    break
                continue

            clean_text = user_text.strip()
            logger.info(f"User spoken command: '{clean_text}'")
            self.bus.publish(EventTopic.TRANSCRIPTION_COMPLETED, {"text": clean_text})

            # Check for dismiss/sleep command
            dismiss_match = re.match(
                r"^(?:stop\s+listening|go\s+to\s+sleep|sleep|never\s+mind|thank\s+you|bye|goodbye|cancel)[\.\s!?,]*$",
                clean_text,
                re.IGNORECASE,
            )
            if dismiss_match:
                logger.info("User requested to stop listening / go to sleep.")
                self._speak_with_loopback_protection("Going to sleep.")
                break

            # 3. Direct Dictation Handling
            if in_dictation_mode:
                in_dictation_mode = False
                self.state_machine.transition_to(RuntimeState.EXECUTING, reason="Typing dictated text.")
                res = self.tool_registry.execute("type_text", {"text": clean_text})
                logger.info(f"Dictation completed: '{clean_text}' (success={res.success})")
                continue

            # 4. Reason and Plan Action via SmolLM3-3B / Fast-Path
            self.state_machine.transition_to(RuntimeState.THINKING, reason="Planning action.")
            plan = self.action_planner.plan_action(clean_text)
            self.bus.publish(EventTopic.BRAIN_PLAN_READY, plan.model_dump())

            # Handle start_dictation mode
            if plan.intent == "start_dictation":
                in_dictation_mode = True
                logger.info("Entered dictation mode. Awaiting text to type...")
                continue

            # 5. Permission Verification & Execution
            intent = plan.intent
            decision = self.permission_mgr.check_permission(intent, plan.arguments)
            spoken_response = plan.response

            if not decision.allowed:
                spoken_response = decision.reason or f"Action {intent} is not permitted."
                logger.warning(f"Blocked action: {intent} ({decision.reason})")
                self._speak_with_loopback_protection(spoken_response)
            elif decision.requires_confirmation:
                confirmed = self.confirmation_mgr.request_confirmation(
                    intent=intent,
                    arguments=plan.arguments,
                    prompt_message=f"Execute action '{intent}' with arguments {plan.arguments}?",
                )
                if not confirmed:
                    spoken_response = f"Action {intent} was cancelled."
                    logger.info(f"User cancelled action {intent}.")
                    self._speak_with_loopback_protection(spoken_response)
                else:
                    success, exec_msg = self._execute_and_format_response(intent, plan.arguments, plan.response)
                    if not success or not self.config.tts.silent_action_mode:
                        self._speak_with_loopback_protection(exec_msg or spoken_response)
            else:
                # Fully permitted execution
                success, exec_msg = self._execute_and_format_response(intent, plan.arguments, plan.response)
                if not success:
                    self._speak_with_loopback_protection(exec_msg)
                elif intent in ("answer_question", "ask_clarification") or not self.config.tts.silent_action_mode:
                    self._speak_with_loopback_protection(exec_msg or spoken_response)
                else:
                    logger.info(f"Action '{intent}' executed silently for fluid hands-free workflow.")

        # Safe return to passive LISTENING
        self.state_machine.reset_to_listening(reason="Voice session completed.")

    def _execute_and_format_response(
        self, intent: str, arguments: Dict[str, Any], default_response: str
    ) -> tuple[bool, str]:
        """Execute tool and return (success, confirmation message)."""
        if intent in ("ask_clarification", "answer_question", "unknown"):
            return True, default_response

        self.state_machine.transition_to(RuntimeState.EXECUTING, reason=f"Executing {intent}.")
        self.bus.publish(EventTopic.TOOL_EXECUTION_START, {"intent": intent, "arguments": arguments})

        result = self.tool_registry.execute(intent, arguments)

        if result.success:
            self.bus.publish(EventTopic.TOOL_EXECUTION_SUCCESS, result.model_dump())
            return True, default_response or result.message
        else:
            self.bus.publish(EventTopic.TOOL_EXECUTION_FAILURE, result.model_dump())
            return False, f"I couldn't complete that: {result.message}"

    def _record_command_audio(self, timeout_if_no_speech: float = 3.0) -> Optional[np.ndarray]:
        """Record audio chunks until silence or max duration is reached."""
        chunks: List[np.ndarray] = []
        silence_limit_sec = self.config.stt.silence_threshold_seconds
        max_duration_sec = self.config.stt.max_record_seconds
        silence_threshold_rms = 0.014
        ambient_samples: List[float] = []

        start_time = time.time()
        last_speech_time = start_time
        has_spoken = False

        while self.is_running:
            chunk = self.audio_capture.read_chunk(timeout=0.1)
            now = time.time()
            if chunk is None:
                if has_spoken and (now - last_speech_time) >= silence_limit_sec:
                    break
                if (now - start_time) >= max_duration_sec:
                    break
                continue

            chunks.append(chunk)
            rms = float(np.sqrt(np.mean((chunk.astype(np.float32) / 32768.0) ** 2)))

            # Adapt threshold to ambient room noise over first 3 chunks
            if len(ambient_samples) < 3:
                ambient_samples.append(rms)
                if len(ambient_samples) == 3:
                    ambient_baseline = float(np.mean(ambient_samples))
                    silence_threshold_rms = max(0.014, ambient_baseline * 1.6)

            if rms > silence_threshold_rms:
                has_spoken = True
                last_speech_time = now

            # Check max duration
            if (now - start_time) >= max_duration_sec:
                break

            # Check trailing silence after speech has occurred
            if has_spoken and (now - last_speech_time) >= silence_limit_sec:
                break

            # If no speech at all within timeout, exit early
            if not has_spoken and (now - start_time) >= timeout_if_no_speech:
                break

        if chunks:
            return np.concatenate(chunks)
        return None

    def _speak_with_loopback_protection(self, text: str) -> None:
        """Speak response while completely muting audio input to prevent feedback loop."""
        if not text or not text.strip():
            return

        self.state_machine.transition_to(RuntimeState.SPEAKING, reason="Speaking response.")
        self.bus.publish(EventTopic.TTS_START, {"text": text})

        # MUTE audio capture so IRIS cannot hear itself
        self.audio_capture.set_muted(True)

        try:
            self.tts.speak(text)
        finally:
            # Sleep tiny margin to let room reverberation settle
            time.sleep(0.15)
            # UNMUTE audio capture
            self.audio_capture.set_muted(False)
            self.bus.publish(EventTopic.TTS_FINISH)
