"""Unit tests for IPC client and server."""

import time
import pytest
from iris.ipc.client import IPCClient
from iris.ipc.protocol import IPCMessage
from iris.ipc.server import IPCServer


def test_ipc_protocol_serialization():
    msg = IPCMessage(
        msg_type="request",
        command="get_status",
        payload={"query": "test"},
    )
    raw = msg.serialize()
    deserialized = IPCMessage.deserialize(raw)
    assert deserialized.command == "get_status"
    assert deserialized.payload == {"query": "test"}


def test_ipc_server_client_roundtrip():
    # Use high port to prevent conflict
    port = 20499
    server = IPCServer(port=port)
    server.register_command("ping", lambda payload: {"pong": True, "val": payload.get("val")})
    assert server.start()

    time.sleep(0.1)

    try:
        client = IPCClient(port=port)
        resp = client.send_command("ping", {"val": 42})
        assert resp.success
        assert resp.payload == {"pong": True, "val": 42}
    finally:
        server.stop()
