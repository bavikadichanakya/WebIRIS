"""
Project IRIS - Confirmation Handler
Coordinates voice and GUI confirmations for potentially impactful desktop actions.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("iris.security.confirmations")


class ConfirmationManager:
    """Handles confirmation requests either via UI signals or conversational prompts."""

    def __init__(self) -> None:
        self._gui_confirmation_callback: Optional[Callable[[str, str], bool]] = None
        self._pending_confirmation: Optional[Dict[str, Any]] = None

    def set_gui_confirmation_callback(self, callback: Callable[[str, str], bool]) -> None:
        """Register GUI dialog callback: callback(title, message) -> bool."""
        self._gui_confirmation_callback = callback

    def request_confirmation(
        self, intent: str, arguments: Dict[str, Any], prompt_message: str
    ) -> bool:
        """
        Request user confirmation. If GUI callback is registered, prompts user via dialog;
        otherwise defaults to safe refusal unless explicitly confirmed.
        """
        logger.info(f"Confirmation requested for '{intent}': {prompt_message}")
        if self._gui_confirmation_callback is not None:
            try:
                confirmed = self._gui_confirmation_callback(
                    "IRIS Security Confirmation",
                    f"IRIS wants to execute: {intent}\n\nDetails: {prompt_message}\n\nDo you want to proceed?",
                )
                logger.info(f"User confirmation result: {confirmed}")
                return confirmed
            except Exception as e:
                logger.error(f"Error during GUI confirmation prompt: {e}")
                return False

        # If running headlessly/without GUI callback, safe default is False
        return False
