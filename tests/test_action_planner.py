"""Unit tests for ActionPlanner deterministic fast-path and planning."""

import pytest
from iris.brain.action_planner import ActionPlanner
from iris.brain.model_manager import ModelManager, ModelStatus
from iris.core.config import ModelConfig
from iris.tools.schemas import ToolDefinition, ToolParameter


class MockModelManager(ModelManager):
    def __init__(self, canned_response: str = ""):
        super().__init__(ModelConfig())
        self.canned_response = canned_response
        self._status = ModelStatus.READY

    def is_ready(self) -> bool:
        return True

    def generate(self, prompt: str, **kwargs) -> str:
        return self.canned_response


def test_deterministic_fast_path_open_app():
    mgr = MockModelManager()
    planner = ActionPlanner(mgr)

    plan = planner.check_deterministic_fast_path("open notepad")
    assert plan is not None
    assert plan.intent == "open_application"
    assert plan.arguments == {"application": "notepad"}

    plan2 = planner.check_deterministic_fast_path("launch calculator")
    assert plan2 is not None
    assert plan2.intent == "open_application"
    assert plan2.arguments == {"application": "calculator"}


def test_deterministic_fast_path_focus_window():
    mgr = MockModelManager()
    planner = ActionPlanner(mgr)

    plan = planner.check_deterministic_fast_path("switch to chrome")
    assert plan is not None
    assert plan.intent == "focus_window"
    assert plan.arguments == {"window_title": "chrome"}


def test_deterministic_fast_path_greetings():
    mgr = MockModelManager()
    planner = ActionPlanner(mgr)

    plan = planner.check_deterministic_fast_path("hello iris")
    assert plan is not None
    assert plan.intent == "answer_question"


def test_deterministic_fast_path_type_text():
    mgr = MockModelManager()
    planner = ActionPlanner(mgr)

    # 1. Direct typing
    plan1 = planner.check_deterministic_fast_path("type hello world")
    assert plan1 is not None
    assert plan1.intent == "type_text"
    assert plan1.arguments["text"] == "hello world"

    # 2. Type into notepad
    plan2 = planner.check_deterministic_fast_path("type I am a good boy in notepad")
    assert plan2 is not None
    assert plan2.intent == "type_text"
    assert plan2.arguments["text"] == "I am a good boy"
    assert plan2.arguments["target_application"] == "notepad"

    # 3. Whisper acoustic confusion "not bad" -> notepad
    plan3 = planner.check_deterministic_fast_path("type I am good boy in not bad.")
    assert plan3 is not None
    assert plan3.intent == "type_text"
    assert plan3.arguments["text"] == "I am good boy"
    assert plan3.arguments["target_application"] == "notepad"


def test_model_planning_invocation():
    canned = '{"thought": "Opening browser", "intent": "open_application", "arguments": {"application": "edge"}, "response": "Opening Edge."}'
    mgr = MockModelManager(canned_response=canned)
    tools = {
        "open_application": ToolDefinition(
            name="open_application",
            description="open app",
            parameters=[ToolParameter(name="application", type="string", description="app", required=True)],
            permission_key="open_application",
        )
    }
    planner = ActionPlanner(mgr, registered_tools=tools)
    plan = planner.plan_action("could you kindly bring up the internet browser for me")
    assert plan.intent == "open_application"
    assert plan.arguments == {"application": "edge"}


def test_deterministic_fast_path_bare_app_names():
    mgr = MockModelManager()
    planner = ActionPlanner(mgr)

    # 1. Direct bare app names
    for phrase in ["notepad", "Notepad", "Notepad.", "no bad", "No bad.", "not bad", "notbad"]:
        plan = planner.check_deterministic_fast_path(phrase)
        assert plan is not None, f"Failed for {phrase}"
        assert plan.intent == "open_application"
        assert plan.arguments == {"application": "notepad"}

    # 2. Other common apps
    for phrase, expected in [("calculator", "calculator"), ("calc", "calculator"), ("chrome", "chrome")]:
        plan = planner.check_deterministic_fast_path(phrase)
        assert plan is not None, f"Failed for {phrase}"
        assert plan.intent == "open_application"
        assert plan.arguments == {"application": expected}


def test_model_planning_strips_thinking_tags():
    canned = '<think>\nUser wants to open notepad\n</think>\n{"thought": "Opening notepad", "intent": "open_application", "arguments": {"application": "notepad"}, "response": "Opening Notepad."}'
    mgr = MockModelManager(canned_response=canned)
    tools = {
        "open_application": ToolDefinition(
            name="open_application",
            description="open app",
            parameters=[ToolParameter(name="application", type="string", description="app", required=True)],
            permission_key="open_application",
        )
    }
    planner = ActionPlanner(mgr, registered_tools=tools)
    plan = planner.plan_action("please run the text editor for me")
    assert plan.intent == "open_application"
    assert plan.arguments == {"application": "notepad"}


def test_think_tag_only_output_rejected():
    # If the model emits only </think>, it must NOT be spoken as an answer
    mgr = MockModelManager(canned_response="</think>")
    planner = ActionPlanner(mgr)
    plan = planner.plan_action("some random ambiguous query")
    assert plan.intent == "ask_clarification"
    assert "</think>" not in plan.response


def test_infina_hands_free_video_commands():
    mgr = MockModelManager()
    planner = ActionPlanner(mgr)

    # 1. "Open Claude"
    plan_claude = planner.check_deterministic_fast_path("Open Claude")
    assert plan_claude is not None
    assert plan_claude.intent == "open_application"
    assert plan_claude.arguments == {"application": "claude"}

    # 2. "New chat"
    plan_new_chat = planner.check_deterministic_fast_path("New chat")
    assert plan_new_chat is not None
    assert plan_new_chat.intent == "new_chat"

    # 3. "Type" (standalone dictation trigger)
    plan_dictate = planner.check_deterministic_fast_path("Type")
    assert plan_dictate is not None
    assert plan_dictate.intent == "start_dictation"

    # 4. "Type Tell me everything that we have done this week."
    plan_type = planner.check_deterministic_fast_path("Type Tell me everything that we have done this week.")
    assert plan_type is not None
    assert plan_type.intent == "type_text"
    assert "Tell me everything" in plan_type.arguments["text"]

    # 5. "Send it"
    plan_send = planner.check_deterministic_fast_path("Send it")
    assert plan_send is not None
    assert plan_send.intent == "submit_text"

    # 6. "Open Codex"
    plan_codex = planner.check_deterministic_fast_path("Open Codex")
    assert plan_codex is not None
    assert plan_codex.intent == "open_application"
    assert plan_codex.arguments == {"application": "codex"}

    # 7. "Open Slack"
    plan_slack = planner.check_deterministic_fast_path("Open Slack")
    assert plan_slack is not None
    assert plan_slack.intent == "open_application"
    assert plan_slack.arguments == {"application": "slack"}

    # 8. "Open YouTube" & bare "YouTube."
    for yt in ["Open YouTube", "Open YouTube.", "YouTube", "YouTube."]:
        plan_yt = planner.check_deterministic_fast_path(yt)
        assert plan_yt is not None
        assert plan_yt.intent == "open_application"
        assert plan_yt.arguments == {"application": "youtube"}

    # 9. "Open anti gravity"
    for ag in ["Open anti gravity", "Open anti gravity.", "anti gravity", "antigravity"]:
        plan_ag = planner.check_deterministic_fast_path(ag)
        assert plan_ag is not None
        assert plan_ag.intent == "open_application"
        assert plan_ag.arguments == {"application": "antigravity"}



