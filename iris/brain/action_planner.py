"""
Project IRIS - Action Planner
Coordinates prompt generation, deterministic fast-path routing, model inference,
and structured validation for intent execution.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

from iris.brain.model_manager import ModelManager
from iris.brain.output_validator import OutputValidator, ValidationResult
from iris.brain.prompt_builder import PromptBuilder
from iris.tools.schemas import PlanOutput, ToolDefinition

logger = logging.getLogger("iris.brain.action_planner")


class ActionPlanner:
    """Plans desktop actions by combining deterministic routing and SmolLM3-3B reasoning."""

    # Deterministic pattern regexes for zero-latency execution
    OPEN_APP_PATTERN = re.compile(
        r"^(?:open|launch|start|run)\s+([a-zA-Z0-9_\s]+)[\.\s!?,]*$", re.IGNORECASE
    )
    FOCUS_WINDOW_PATTERN = re.compile(
        r"^(?:switch\s+to|focus|bring\s+up|go\s+to)\s+([a-zA-Z0-9_\s]+)[\.\s!?,]*$", re.IGNORECASE
    )
    SWITCH_WINDOW_PATTERN = re.compile(
        r"^(?:switch\s+window|next\s+window|alt\s+tab)[\.\s!?,]*$", re.IGNORECASE
    )
    SUBMIT_PATTERN = re.compile(
        r"^(?:send\s+it|send|submit|press\s+enter|hit\s+enter|send\s+message)[\.\s!?,]*$", re.IGNORECASE
    )
    NEW_CHAT_PATTERN = re.compile(
        r"^(?:new\s+chat|new\s+tab|new\s+conversation|new\s+doc|new\s+document|new\s+file|new\s+session)[\.\s!?,]*$", re.IGNORECASE
    )
    DICTATE_START_PATTERN = re.compile(
        r"^(?:type|dictate|start\s+typing)[\.\s!?,]*$", re.IGNORECASE
    )
    GREETING_PATTERN = re.compile(
        r"^(?:hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening)\b", re.IGNORECASE
    )

    TYPE_PATTERN = re.compile(
        r"^(?:type|write|enter|input)\s+(?:text\s+)?(.+)$", re.IGNORECASE
    )

    APP_ALIASES: Dict[str, str] = {
        "notepad": "notepad",
        "not bad": "notepad",
        "notbad": "notepad",
        "no bad": "notepad",
        "nobad": "notepad",
        "note pad": "notepad",
        "calculator": "calculator",
        "calc": "calculator",
        "calculate": "calculator",
        "browser": "browser",
        "edge": "edge",
        "msedge": "edge",
        "chrome": "chrome",
        "google chrome": "chrome",
        "explorer": "file explorer",
        "file explorer": "file explorer",
        "files": "file explorer",
        "my computer": "file explorer",
        "paint": "paint",
        "mspaint": "paint",
        "draw": "paint",
        "terminal": "terminal",
        "wt": "terminal",
        "cmd": "cmd",
        "command prompt": "cmd",
        "powershell": "powershell",
        "task manager": "task manager",
        "taskmgr": "task manager",
        "word": "word",
        "excel": "excel",
        "claude": "claude",
        "codex": "codex",
        "slack": "slack",
        "cursor": "cursor",
        "spotify": "spotify",
        "discord": "discord",
        "youtube": "youtube",
        "you tube": "youtube",
        "google": "google",
        "github": "github",
        "chatgpt": "chatgpt",
        "antigravity": "antigravity",
        "anti gravity": "antigravity",
        "netflix": "netflix",
    }

    CLOSE_APP_PATTERN = re.compile(
        r"^(?:close|quit|exit|kill)\s+([a-zA-Z0-9_\s]+)[\.\s!?,]*$", re.IGNORECASE
    )

    def __init__(
        self,
        model_manager: ModelManager,
        registered_tools: Optional[Dict[str, ToolDefinition]] = None,
    ) -> None:
        self.model_manager = model_manager
        self.registered_tools = registered_tools or {}
        self.prompt_builder = PromptBuilder(self.registered_tools)
        self.validator = OutputValidator(self.registered_tools)

    def update_tools(self, tools: Dict[str, ToolDefinition]) -> None:
        """Update registered tools across subcomponents."""
        self.registered_tools = tools
        self.prompt_builder.set_registered_tools(tools)
        self.validator.set_registered_tools(tools)

    def check_deterministic_fast_path(self, user_text: str) -> Optional[PlanOutput]:
        """
        Check if user input can be resolved with deterministic rules
        to eliminate latency for routine commands without invoking the LLM.
        """
        text = user_text.strip().rstrip(".!?,")
        clean_text = text.lower().rstrip(".!?,")

        # 0. Bare Application Name (e.g. "notepad", "no bad", "calculator")
        if clean_text in self.APP_ALIASES:
            app_name = self.APP_ALIASES[clean_text]
            return PlanOutput(
                thought=f"Deterministic fast-path: recognized application name '{clean_text}' -> '{app_name}'.",
                intent="open_application",
                arguments={"application": app_name},
                response=f"Opening {app_name.capitalize()}.",
            )

        # 1. Open Application (e.g. "open notepad", "launch calculator")
        m = self.OPEN_APP_PATTERN.match(text)
        if m:
            raw_app = m.group(1).strip().lower().rstrip(".!?,")
            app_name = self.APP_ALIASES.get(raw_app, raw_app)
            return PlanOutput(
                thought=f"Deterministic fast-path: recognized application launch command '{raw_app}'.",
                intent="open_application",
                arguments={"application": app_name},
                response=f"Opening {app_name.capitalize()}.",
            )

        # 1b. Close Application (e.g. "close notepad", "quit calculator")
        m = self.CLOSE_APP_PATTERN.match(text)
        if m:
            raw_app = m.group(1).strip().lower().rstrip(".!?,")
            app_name = self.APP_ALIASES.get(raw_app, raw_app)
            return PlanOutput(
                thought=f"Deterministic fast-path: recognized application close command '{raw_app}'.",
                intent="close_application",
                arguments={"application": app_name},
                response=f"Closing {app_name.capitalize()}.",
            )

        # 2. Type Text Command
        m = self.TYPE_PATTERN.match(text)
        if m:
            content = m.group(1).strip().rstrip(".!?,")
            while content.lower().startswith("type "):
                content = content[5:].strip()

            target_app = None
            target_match = re.search(
                r"\s+(?:in|into|on)\s+(notepad|not\s*bad|editor|word|calc|calculator|browser)[\.\s]*$",
                content,
                re.IGNORECASE,
            )
            if target_match:
                raw_app = target_match.group(1).lower().replace(" ", "")
                target_app = "notepad" if "notbad" in raw_app else raw_app
                content = content[:target_match.start()].strip()

            args = {"text": content}
            if target_app:
                args["target_application"] = target_app
                resp_text = f"Typing into {target_app.capitalize()}."
            else:
                resp_text = "Typing."

            return PlanOutput(
                thought=f"Deterministic fast-path: recognized type text command: '{content}'",
                intent="type_text",
                arguments=args,
                response=resp_text,
            )

        # 2. Focus Window
        m = self.FOCUS_WINDOW_PATTERN.match(text)
        if m:
            win_title = m.group(1).strip()
            return PlanOutput(
                thought="Deterministic fast-path: recognized window focus command.",
                intent="focus_window",
                arguments={"window_title": win_title},
                response=f"Switching to {win_title}.",
            )

        # 3. Switch Window
        if self.SWITCH_WINDOW_PATTERN.match(text):
            return PlanOutput(
                thought="Deterministic fast-path: recognized window switch command.",
                intent="switch_window",
                arguments={},
                response="Switching window.",
            )

        # 3b. New Chat / New Tab
        if self.NEW_CHAT_PATTERN.match(text):
            return PlanOutput(
                thought="Deterministic fast-path: recognized new chat/document command.",
                intent="new_chat",
                arguments={},
                response="New chat.",
            )

        # 3c. Standalone Dictation Command ("type", "dictate")
        if self.DICTATE_START_PATTERN.match(text):
            return PlanOutput(
                thought="Deterministic fast-path: entering dictation mode.",
                intent="start_dictation",
                arguments={},
                response="Listening.",
            )

        # 4. Submit text / enter
        if self.SUBMIT_PATTERN.match(text):
            return PlanOutput(
                thought="Deterministic fast-path: recognized submission command.",
                intent="submit_text",
                arguments={},
                response="Submitting.",
            )

        # 5. Simple Greetings
        if self.GREETING_PATTERN.match(text) and len(text.split()) <= 4:
            return PlanOutput(
                thought="Deterministic fast-path: recognized greeting.",
                intent="answer_question",
                arguments={"answer": "Hello! I am IRIS, your desktop voice assistant. How can I help you?"},
                response="Hello! How can I help you?",
            )

        return None

    def plan(
        self,
        user_input: str,
        active_window_title: Optional[str] = None,
        context_notes: Optional[str] = None,
        max_retries: int = 2,
    ) -> PlanOutput:
        """Alias for plan_action."""
        return self.plan_action(user_input, active_window_title, context_notes, max_retries)

    def plan_action(
        self,
        user_input: str,
        active_window_title: Optional[str] = None,
        context_notes: Optional[str] = None,
        max_retries: int = 2,
    ) -> PlanOutput:
        """
        Plan an action for user speech input.
        Checks deterministic path first; if none matches, invokes SmolLM3-3B with validation.
        """
        # 1. Deterministic Fast-Path
        fast_plan = self.check_deterministic_fast_path(user_input)
        if fast_plan:
            logger.info(f"Fast-path matched for '{user_input}': {fast_plan.intent}")
            return fast_plan

        # 2. SmolLM3-3B Local Reasoning
        if not self.model_manager.is_ready():
            logger.warning("SmolLM3-3B is not ready; falling back to clarification.")
            return PlanOutput(
                thought="Model is not loaded or ready.",
                intent="ask_clarification",
                arguments={"question": "The local brain is still initializing. Please try again shortly."},
                response="The local brain is still initializing. Please try again in a moment.",
            )

        prompt = self.prompt_builder.build_prompt(
            user_input=user_input,
            active_window_title=active_window_title,
            context_notes=context_notes,
        )

        attempts = 0
        last_error = ""

        while attempts <= max_retries:
            attempts += 1
            try:
                # Add error feedback on retries if previous attempt failed
                curr_prompt = prompt
                if attempts > 1 and last_error:
                    curr_prompt += f"\nPrevious attempt was invalid: {last_error}. Output ONLY valid JSON matching the schema."

                logger.info(f"Invoking SmolLM3-3B (attempt {attempts})...")
                raw_output = self.model_manager.generate(
                    curr_prompt,
                    max_tokens=self.model_manager.config.max_output_tokens,
                    temperature=self.model_manager.config.temperature,
                    stop=["<|im_end|>", "<|im_start|>"],
                )

                # Strip any thinking tags or internal thoughts
                cleaned_output = re.sub(r"<think>[\s\S]*?</think>", "", raw_output, flags=re.IGNORECASE)
                cleaned_output = re.sub(r"</?think>", "", cleaned_output, flags=re.IGNORECASE).strip()

                validation: ValidationResult = self.validator.validate(cleaned_output)
                if validation.is_valid and validation.plan:
                    logger.info(f"Model plan accepted: intent='{validation.plan.intent}'")
                    return validation.plan
                else:
                    last_error = validation.error_message or "Unknown validation error"
                    logger.warning(f"Model output validation failed on attempt {attempts}: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.error(f"Inference error during planning attempt {attempts}: {e}")

        # Safe Fallback if all attempts failed
        logger.error(f"Action planning failed after {attempts} attempts. Last error: {last_error}")
        return PlanOutput(
            thought=f"Planning failed after validation errors: {last_error}",
            intent="ask_clarification",
            arguments={"question": "I had trouble understanding that command. Could you please rephrase?"},
            response="I didn't quite catch that. Could you please rephrase?",
        )
