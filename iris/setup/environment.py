"""
Project IRIS - Environment & System Inspector
Inspects host hardware, Python runtime, memory, and devices.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
from typing import Any, Dict, List

logger = logging.getLogger("iris.setup.environment")


class EnvironmentInspector:
    """Inspects the Windows host environment and audio/compute capabilities."""

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Collect host operating system and hardware diagnostics."""
        info: Dict[str, Any] = {
            "os_name": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "python_version": sys.version.split()[0],
            "python_executable": sys.executable,
            "architecture": platform.machine(),
            "cpu_count": os.cpu_count() or 4,
            "disk_free_gb": round(shutil.disk_usage(os.getcwd()).free / (1024**3), 2),
            "disk_total_gb": round(shutil.disk_usage(os.getcwd()).total / (1024**3), 2),
        }

        # RAM info using psutil or ctypes
        try:
            import psutil
            mem = psutil.virtual_memory()
            info["ram_total_gb"] = round(mem.total / (1024**3), 2)
            info["ram_available_gb"] = round(mem.available / (1024**3), 2)
        except ImportError:
            info["ram_total_gb"] = "Unknown"
            info["ram_available_gb"] = "Unknown"

        # Check GPU / PyTorch CUDA
        try:
            import torch
            info["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                info["gpu_name"] = torch.cuda.get_device_name(0)
            else:
                info["gpu_name"] = "CPU / Integrated Graphics"
        except ImportError:
            info["cuda_available"] = False
            info["gpu_name"] = "CPU"

        return info

    @staticmethod
    def get_package_statuses() -> Dict[str, bool]:
        """Check availability of critical Python libraries."""
        packages = {
            "pyside6": "PySide6",
            "sounddevice": "sounddevice",
            "openwakeword": "openwakeword",
            "onnxruntime": "onnxruntime",
            "pyttsx3": "pyttsx3",
            "faster_whisper": "faster_whisper",
            "llama_cpp": "llama_cpp",
            "pywin32": "win32gui",
            "uiautomation": "uiautomation",
            "pydantic": "pydantic",
        }
        status = {}
        for pkg_name, import_mod in packages.items():
            try:
                __import__(import_mod)
                status[pkg_name] = True
            except ImportError:
                status[pkg_name] = False
        return status
