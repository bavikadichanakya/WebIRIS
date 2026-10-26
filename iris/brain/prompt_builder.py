"""
Project IRIS - Prompt Builder
Formats structured system prompts for SmolLM3-3B with tool catalog and schema constraints.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from iris.tools.schemas import ToolDefinition


class PromptBuilder:
    """Constructs constrained prompts for SmolLM3-3B action planning."""

    SYSTEM_BASE = (
        "You are IRIS, a native Windows desktop voice assistant. "
        "Your mission is to understand user requests, choose the correct action, and respond concisely.\n"
        "RULES:\n"
        "1. You must respond ONLY with a single JSON object matching the required schema.\n"
        "2. Do NOT output markdown code fences (```json), commentary, or text before/after the JSON.\n"
        "3. Select intents strictly from the REGISTERED TOOLS list or BUILT-IN INTENTS below.\n"
        "4. Keep the 'response' field concise, natural, and suitable for Text-to-Speech (1 sentence).\n"
        "5. If a request is ambiguous or missing critical information, choose intent 'ask_clarification'.\n"
        "6. If the request is a general question or greeting, choose intent 'answer_question'.\n"
        "7. Never attempt to run shell scripts, commands, or unapproved programs.\n"
        "8. CRITICAL: Do NOT use <think> tags or internal thoughts. Output starts immediately with '{'.\n\n"
        "EXAMPLES:\n"
        'User: "open notepad"\n'
        '{"thought": "Open notepad", "intent": "open_application", "arguments": {"application": "notepad"}, "response": "Opening Notepad."}\n\n'
        'User: "type I am a good boy in notepad"\n'
        '{"thought": "Type text into notepad", "intent": "type_text", "arguments": {"text": "I am a good boy", "target_application": "notepad"}, "response": "Typing in Notepad."}\n\n'
        'User: "type hello world"\n'
        '{"thought": "Type text", "intent": "type_text", "arguments": {"text": "hello world"}, "response": "Typing."}\n\n'
        'User: "what is the capital of France?"\n'
        '{"thought": "Answer question", "intent": "answer_question", "arguments": {"answer": "The capital of France is Paris."}, "response": "The capital of France is Paris."}\n'
    )

    JSON_SCHEMA_EXAMPLE = (
        '{\n'
        '  "thought": "brief reasoning",\n'
        '  "intent": "open_application",\n'
        '  "arguments": {"application": "notepad"},\n'
        '  "response": "Opening Notepad."\n'
        '}'
    )

    def __init__(self, registered_tools: Optional[Dict[str, ToolDefinition]] = None) -> None:
        self.registered_tools = registered_tools or {}

    def set_registered_tools(self, tools: Dict[str, ToolDefinition]) -> None:
        self.registered_tools = tools

    def build_tool_catalog_text(self) -> str:
        """Format the registered tools for inclusion in prompt."""
        lines = ["REGISTERED TOOLS:"]
        for tool in self.registered_tools.values():
            param_desc = []
            for p in tool.parameters:
                req = "required" if p.required else "optional"
                param_desc.append(f"{p.name} ({p.type}, {req}): {p.description}")
            params_str = ", ".join(param_desc) if param_desc else "none"
            lines.append(f"- {tool.name}: {tool.description} | Arguments: [{params_str}]")

        lines.append("\nBUILT-IN INTENTS:")
        lines.append("- answer_question: Answer greetings, facts, or questions directly. Arguments: {'answer': 'string'}")
        lines.append("- ask_clarification: Ask the user to clarify an ambiguous command. Arguments: {'question': 'string'}")
        lines.append("- unknown: When the request cannot be handled safely. Arguments: {}")
        return "\n".join(lines)

    def build_prompt(
        self,
        user_input: str,
        active_window_title: Optional[str] = None,
        context_notes: Optional[str] = None,
    ) -> str:
        """Assemble complete system prompt and user turn for SmolLM3-3B."""
        catalog = self.build_tool_catalog_text()
        context_block = ""
        if active_window_title:
            context_block += f"\nCURRENT FOCUSED WINDOW: '{active_window_title}'\n"
        if context_notes:
            context_block += f"ADDITIONAL CONTEXT: {context_notes}\n"

        prompt = (
            f"<|im_start|>system\n"
            f"{self.SYSTEM_BASE}\n"
            f"{catalog}\n"
            f"{context_block}\n"
            f"REQUIRED OUTPUT SCHEMA:\n"
            f"{self.JSON_SCHEMA_EXAMPLE}\n"
            f"<|im_end|>\n"
            f"<|im_start|>user\n"
            f"{user_input}\n"
            f"<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        return prompt
