"""Unit tests for OutputValidator."""

import pytest
from iris.brain.output_validator import OutputValidator
from iris.tools.schemas import ToolDefinition, ToolParameter


@pytest.fixture
def test_tools():
    return {
        "open_application": ToolDefinition(
            name="open_application",
            description="Open app",
            parameters=[ToolParameter(name="application", type="string", description="app name", required=True)],
            permission_key="open_application",
        ),
        "type_text": ToolDefinition(
            name="type_text",
            description="Type text",
            parameters=[ToolParameter(name="text", type="string", description="text to type", required=True)],
            permission_key="type_text",
        ),
    }


def test_valid_json_plain(test_tools):
    validator = OutputValidator(test_tools)
    raw = '{"thought": "Opening notepad", "intent": "open_application", "arguments": {"application": "notepad"}, "response": "Opening Notepad."}'
    res = validator.validate(raw)
    assert res.is_valid
    assert res.plan.intent == "open_application"
    assert res.plan.arguments == {"application": "notepad"}


def test_valid_json_markdown_block(test_tools):
    validator = OutputValidator(test_tools)
    raw = """
    Here is the plan:
    ```json
    {
        "thought": "Typing message",
        "intent": "type_text",
        "arguments": {"text": "hello world"},
        "response": "Typing hello world."
    }
    ```
    """
    res = validator.validate(raw)
    assert res.is_valid
    assert res.plan.intent == "type_text"
    assert res.plan.arguments == {"text": "hello world"}


def test_json_repair_trailing_commas(test_tools):
    validator = OutputValidator(test_tools)
    raw = '{"thought": "test", "intent": "open_application", "arguments": {"application": "calc",}, "response": "Opening.",}'
    res = validator.validate(raw)
    assert res.is_valid
    assert res.plan.intent == "open_application"


def test_missing_required_argument(test_tools):
    validator = OutputValidator(test_tools)
    raw = '{"thought": "Missing app", "intent": "open_application", "arguments": {}, "response": "Opening."}'
    res = validator.validate(raw)
    assert not res.is_valid
    assert "Missing required argument 'application'" in res.error_message


def test_unknown_tool_rejected(test_tools):
    validator = OutputValidator(test_tools)
    raw = '{"thought": "Format C", "intent": "delete_hard_drive", "arguments": {}, "response": "Deleting."}'
    res = validator.validate(raw)
    assert not res.is_valid
    assert "is not a registered tool" in res.error_message


def test_builtin_conversational_intents_allowed(test_tools):
    validator = OutputValidator(test_tools)
    raw = '{"thought": "Greeting", "intent": "answer_question", "arguments": {"answer": "Hello!"}, "response": "Hello!"}'
    res = validator.validate(raw)
    assert res.is_valid
    assert res.plan.intent == "answer_question"


def test_conversational_plaintext_fallback(test_tools):
    validator = OutputValidator(test_tools)
    raw = "The capital of France is Paris."
    res = validator.validate(raw)
    assert res.is_valid
    assert res.plan.intent == "answer_question"
    assert res.plan.response == "The capital of France is Paris."
