"""
Project IRIS - IPC Protocol Definition
Provides JSON-RPC structured messaging across local Windows processes.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class IPCMessage(BaseModel):
    """Message packet exchanged between IRIS runtime daemon and UI client."""
    msg_type: str = Field(description="'request', 'response', or 'event'")
    command: Optional[str] = None
    topic: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None

    def serialize(self) -> bytes:
        return (json.dumps(self.model_dump()) + "\n").encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes | str) -> IPCMessage:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        parsed = json.loads(data.strip())
        return cls.model_validate(parsed)
