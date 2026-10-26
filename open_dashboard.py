"""
Project IRIS - Open Dashboard Utility
Brings the IRIS configuration dashboard to the foreground if already running,
or launches IRIS if it is not currently active.
"""

import json
import socket
import subprocess
import sys
from pathlib import Path

IPC_HOST = "127.0.0.1"
IPC_PORT = 19842


def open_dashboard() -> None:
    # 1. Try sending show_dashboard to already running instance
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        sock.connect((IPC_HOST, IPC_PORT))
        req = json.dumps({"msg_type": "request", "command": "show_dashboard", "payload": {}}) + "\n"
        sock.sendall(req.encode("utf-8"))
        resp = sock.recv(4096)
        sock.close()
        print("Project IRIS is active. Dashboard has been brought to the foreground.")
        return
    except Exception:
        pass

    # 2. Not running yet; launch IRIS
    print("Project IRIS is not currently running. Launching...")
    root_dir = Path(__file__).resolve().parent
    python_exe = root_dir / ".venv" / "Scripts" / "python.exe"
    run_script = root_dir / "run_iris.py"

    if not python_exe.exists():
        python_exe = Path(sys.executable)

    subprocess.Popen([str(python_exe), str(run_script)], cwd=str(root_dir))
    print("Project IRIS launched.")


if __name__ == "__main__":
    open_dashboard()
