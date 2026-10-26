"""
Project IRIS - Output Validator
Safely parses, repairs, and strictly validates structured JSON from SmolLM3-3B.
Enforces that model outputs cannot execute unsupported or malformed operations.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import ValidationError

from iris.tools.schemas import PlanOutput, ToolDefinition

logger = logging.getLogger("iris.brain.output_validator")


class ValidationResult:
    """Outcome of validating model-generated plan output."""

    def __init__(
        self,
        is_valid: bool,
        plan: Optional[PlanOutput] = None,
        error_message: Optional[str] = None,
        raw_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.is_valid = is_valid
        self.plan = plan
        self.error_message = error_message
        self.raw_json = raw_json

    def __repr__(self) -> str:
        return f"<ValidationResult valid={self.is_valid} plan={self.plan} error={self.error_message}>"


class OutputValidator:
    """Extracts, repairs, and strictly validates JSON output from the local model."""

    # Pre-compiled regex for JSON block extraction
    MARKDOWN_JSON_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    BRACE_JSON_PATTERN = re.compile(r"(\{[\s\S]*\})")

    def __init__(self, registered_tools: Optional[Dict[str, ToolDefinition]] = None) -> None:
        self.registered_tools = registered_tools or {}

    def set_registered_tools(self, tools: Dict[str, ToolDefinition]) -> None:
        self.registered_tools = tools

    def extract_json_string(self, text: str) -> Optional[str]:
        """Extract JSON substring from markdown codeblocks or raw braces."""
        if not text or not text.strip():
            return None

        clean_text = text.strip()

        # 1. Try markdown code block
        match = self.MARKDOWN_JSON_PATTERN.search(clean_text)
        if match:
            return match.group(1).strip()

        # 2. Try raw outer curly braces
        match = self.BRACE_JSON_PATTERN.search(clean_text)
        if match:
            return match.group(1).strip()

        return None

    def repair_json_string(self, json_str: str) -> str:
        """Fix common LLM slips such as trailing commas and unescaped quotes."""
        # Remove trailing commas before } or ]
        repaired = re.sub(r",\s*([\]}])", r"\1", json_str)
        # Ensure single quotes around keys are converted to double quotes
        repaired = re.sub(r"(?<=\{|\,)\s*'([a-zA-Z0-9_]+)'\s*:", r'"\1":', repaired)
        return repaired

    def validate(self, raw_model_text: str) -> ValidationResult:
        """
        Validate model output text against the action plan schema and tool catalog.
        Returns ValidationResult with is_valid=True or False with detailed error.
        """
        # Strip any thinking tags or thinking content before processing
        cleaned_input = re.sub(r"<think>[\s\S]*?</think>", "", raw_model_text, flags=re.IGNORECASE)
        cleaned_input = re.sub(r"</?think>", "", cleaned_input, flags=re.IGNORECASE).strip()

        json_candidate = self.extract_json_string(cleaned_input)
        if not json_candidate:
            cleaned_text = cleaned_input.replace("<|im_end|>", "").strip()
            # If the model produced a direct conversational text response without JSON wrapper
            # Reject technical tags, XML/HTML tags, or fragments
            is_tag = bool(re.match(r"^</?[a-zA-Z0-9_\-]+>$", cleaned_text))
            if cleaned_text and not cleaned_text.startswith("{") and len(cleaned_text) >= 3 and not is_tag:
                return ValidationResult(
                    is_valid=True,
                    plan=PlanOutput(
                        thought="Direct conversational response from model.",
                        intent="answer_question",
                        arguments={"answer": cleaned_text},
                        response=cleaned_text,
                    ),
                )
            return ValidationResult(
                is_valid=False,
                error_message="No JSON object found in model output.",
            )

        # Parse JSON
        parsed_dict = None
        try:
            parsed_dict = json.loads(json_candidate)
        except json.JSONDecodeError:
            # Try repairing
            repaired = self.repair_json_string(json_candidate)
            try:
                parsed_dict = json.loads(repaired)
            except json.JSONDecodeError as e:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Malformed JSON syntax: {e}",
                )

        if not isinstance(parsed_dict, dict):
            return ValidationResult(
                is_valid=False,
                error_message="Root JSON value is not an object/dictionary.",
            )

        # Validate with Pydantic
        try:
            plan = PlanOutput.model_validate(parsed_dict)
        except ValidationError as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"JSON does not conform to required schema: {e}",
                raw_json=parsed_dict,
            )

        # Validate Intent against Registered Tools or Built-in conversational intents
        intent = plan.intent.strip().lower()
        plan.intent = intent

        allowed_builtin_intents = {"ask_clarification", "answer_question", "unknown"}
        if intent not in self.registered_tools and intent not in allowed_builtin_intents:
            valid_list = list(self.registered_tools.keys()) + list(allowed_builtin_intents)
            return ValidationResult(
                is_valid=False,
                plan=plan,
                error_message=f"Intent '{intent}' is not a registered tool. Allowed: {valid_list}",
                raw_json=parsed_dict,
            )

        # Validate Tool Arguments
        if intent in self.registered_tools:
            tool_def = self.registered_tools[intent]
            arg_errors = self._validate_tool_arguments(tool_def, plan.arguments)
            if arg_errors:
                return ValidationResult(
                    is_valid=False,
                    plan=plan,
                    error_message="; ".join(arg_errors),
                    raw_json=parsed_dict,
                )

        return ValidationResult(
            is_valid=True,
            plan=plan,
            raw_json=parsed_dict,
        )

    def _validate_tool_arguments(
        self, tool: ToolDefinition, args: Dict[str, Any]
    ) -> List[str]:
        """Verify required parameters and parameter types."""
        errors: List[str] = []
        expected_params = {p.name: p for p in tool.parameters}

        # Check for missing required parameters
        for param in tool.parameters:
            if param.required and param.name not in args:
                errors.append(f"Missing required argument '{param.name}' for tool '{tool.name}'")

        # Check types for provided parameters
        for arg_name, arg_val in args.items():
            if arg_name not in expected_params:
                # Log warning or reject unknown argument
                continue
            param_spec = expected_params[arg_name]
            if param_spec.type == "string" and not isinstance(arg_val, str):
                errors.append(f"Argument '{arg_name}' must be a string, got {type(arg_val).__name__}")
            elif param_spec.type == "boolean" and not isinstance(arg_val, bool):
                errors.append(f"Argument '{arg_name}' must be a boolean, got {type(arg_val).__name__}")
            elif param_spec.type in ("integer", "int") and not isinstance(arg_val, int):
                errors.append(f"Argument '{arg_name}' must be an integer, got {type(arg_val).__name__}")

        return errors
