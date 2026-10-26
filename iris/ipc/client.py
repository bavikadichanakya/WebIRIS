"""
Project IRIS - IPC Client
Allows separate UI or CLI processes to interact with the background IRIS engine.
"""

from __future__ import annotations

import logging
import socket
import uuid
from typing import Any, Dict, Optional

from iris.ipc.protocol import IPCMessage

logger = logging.getLogger("iris.ipc.client")

DEFAULT_IPC_HOST = "127.0.0.1"
DEFAULT_IPC_PORT = 19842


class IPCClient:
    """Client for communicating with the IRIS IPC daemon."""

    def __init__(
        self, host: str = DEFAULT_IPC_HOST, port: int = DEFAULT_IPC_PORT
    ) -> None:
        self.host = host
        self.port = port

    def send_command(
        self, command: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 5.0
    ) -> IPCMessage:
        """Send command to IRIS server and receive structured response."""
        req_id = str(uuid.uuid4())
        msg = IPCMessage(
            msg_type="request",
            command=command,
            payload=payload or {},
            request_id=req_id,
        )

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))
            sock.sendall(msg.serialize())

            file_obj = sock.makefile("r", encoding="utf-8")
            response_line = file_obj.readline()
            return IPCMessage.deserialize(response_line)
