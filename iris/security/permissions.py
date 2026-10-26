"""
Project IRIS - Security & Permissions System
Enforces deterministic access control policies and permission boundaries.
The local model is treated as an untrusted planner; permissions are strictly evaluated here.
"""

from __future__ import annotations

import enum
import logging
from typing import Any, Dict, Optional

from iris.core.config import SecurityConfig

logger = logging.getLogger("iris.security.permissions")


class PermissionPolicy(str, enum.Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class PermissionDecision:
    """Outcome of checking tool permissions."""

    def __init__(
        self,
        allowed: bool,
        requires_confirmation: bool = False,
        reason: str = "",
    ) -> None:
        self.allowed = allowed
        self.requires_confirmation = requires_confirmation
        self.reason = reason

    def __repr__(self) -> str:
        return f"<PermissionDecision allowed={self.allowed} confirm={self.requires_confirmation} reason='{self.reason}'>"


class PermissionManager:
    """Evaluates and enforces permission rules for requested tools and actions."""

    def __init__(self, config: SecurityConfig) -> None:
        self.config = config

    def check_permission(self, intent: str, arguments: Optional[Dict[str, Any]] = None) -> PermissionDecision:
        """Check whether an action is allowed, requires user confirmation, or is denied."""
        intent = intent.strip().lower()

        # Built-in safe conversational intents always allowed
        if intent in ("ask_clarification", "answer_question", "unknown"):
            return PermissionDecision(allowed=True, requires_confirmation=False, reason="Built-in safe intent.")

        policy_str = self.config.tool_permissions.get(intent, "confirm").lower()

        if policy_str == PermissionPolicy.DENY.value:
            logger.warning(f"Security: Execution of tool '{intent}' is DENIED by configuration.")
            return PermissionDecision(
                allowed=False,
                requires_confirmation=False,
                reason=f"Tool '{intent}' is disabled by your security settings.",
            )

        if policy_str == PermissionPolicy.CONFIRM.value:
            return PermissionDecision(
                allowed=True,
                requires_confirmation=True,
                reason=f"Tool '{intent}' requires explicit confirmation.",
            )

        # ALLOW policy
        return PermissionDecision(allowed=True, requires_confirmation=False, reason="Allowed by policy.")
