"""Unit tests for PermissionManager and ConfirmationManager."""

import pytest
from iris.core.config import SecurityConfig
from iris.security.confirmations import ConfirmationManager
from iris.security.permissions import PermissionManager


def test_permission_allow():
    cfg = SecurityConfig(tool_permissions={"open_application": "allow"})
    mgr = PermissionManager(cfg)
    decision = mgr.check_permission("open_application")
    assert decision.allowed
    assert not decision.requires_confirmation


def test_permission_confirm():
    cfg = SecurityConfig(tool_permissions={"submit_text": "confirm"})
    mgr = PermissionManager(cfg)
    decision = mgr.check_permission("submit_text")
    assert decision.allowed
    assert decision.requires_confirmation


def test_permission_deny():
    cfg = SecurityConfig(tool_permissions={"format_drive": "deny"})
    mgr = PermissionManager(cfg)
    decision = mgr.check_permission("format_drive")
    assert not decision.allowed


def test_confirmation_callback():
    cm = ConfirmationManager()
    cm.set_gui_confirmation_callback(lambda title, msg: True)
    assert cm.request_confirmation("submit_text", {}, "test message")

    cm.set_gui_confirmation_callback(lambda title, msg: False)
    assert not cm.request_confirmation("submit_text", {}, "test message")
