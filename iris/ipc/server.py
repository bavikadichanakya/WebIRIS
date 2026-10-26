"""
Project IRIS - IPC Server
Runs a local socket server allowing external UI or CLI tools to query runtime state and execute commands.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Callable, Dict, Optional

from iris.ipc.protocol import IPCMessage

logger = logging.getLogger("iris.ipc.server")

DEFAULT_IPC_HOST = "127.0.0.1"
DEFAULT_IPC_PORT = 19842


class IPCServer:
    """Local socket server dispatching commands to the running IRIS engine."""

    def __init__(
        self,
        host: str = DEFAULT_IPC_HOST,
        port: int = DEFAULT_IPC_PORT,
    ) -> None:
        self.host = host
        self.port = port
        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._command_handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    def register_command(
        self, command: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    ) -> None:
        self._command_handlers[command] = handler

    def start(self) -> bool:
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(5)
            self._running = True

            self._thread = threading.Thread(
                target=self._accept_loop, name="iris_ipc_server", daemon=True
            )
            self._thread.start()
            logger.info(f"IPC Server listening on {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start IPC Server: {e}")
            return False

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        logger.info("IPC Server stopped.")

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client_sock, addr = self._server_sock.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock,),
                    daemon=True,
                ).start()
            except Exception:
                break

    def _handle_client(self, sock: socket.socket) -> None:
        with sock:
            file_obj = sock.makefile("r", encoding="utf-8")
            while self._running:
                line = file_obj.readline()
                if not line:
                    break
                try:
                    msg = IPCMessage.deserialize(line)
                    if msg.msg_type == "request" and msg.command in self._command_handlers:
                        res_data = self._command_handlers[msg.command](msg.payload)
                        reply = IPCMessage(
                            msg_type="response",
                            request_id=msg.request_id,
                            payload=res_data,
                            success=True,
                        )
                    else:
                        reply = IPCMessage(
                            msg_type="response",
                            request_id=msg.request_id,
                            success=False,
                            error=f"Unknown command: {msg.command}",
                        )
                    sock.sendall(reply.serialize())
                except Exception as e:
                    err_reply = IPCMessage(
                        msg_type="response",
                        success=False,
                        error=str(e),
                    )
                    sock.sendall(err_reply.serialize())
