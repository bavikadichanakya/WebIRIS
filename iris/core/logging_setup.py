"""
Project IRIS - Logging Infrastructure
Provides rotating file logs, in-memory buffer for UI diagnostics, and data sanitization.
"""

from __future__ import annotations

import collections
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Deque, List, Optional

from iris.core.config import get_default_base_dir
from iris.core.event_bus import EventBus, EventTopic

# Memory buffer of the most recent log records
MAX_LOG_BUFFER_SIZE = 1000
log_buffer: Deque[dict] = collections.deque(maxlen=MAX_LOG_BUFFER_SIZE)

# Patterns for sensitive data redaction
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]?([^'\"\s]+)"),
]


def sanitize_message(msg: str) -> str:
    """Redact sensitive patterns from log messages."""
    sanitized = str(msg)
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(r"\1: [REDACTED]", sanitized)
    return sanitized


class MemoryLogHandler(logging.Handler):
    """Custom logging handler that buffers records and forwards to EventBus."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        super().__init__()
        self.bus = bus or EventBus()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            sanitized = sanitize_message(msg)
            entry = {
                "timestamp": record.created,
                "level": record.levelname,
                "name": record.name,
                "message": sanitized,
                "time_str": self.formatter.formatTime(record, "%H:%M:%S") if self.formatter else "",
            }
            log_buffer.append(entry)
            self.bus.publish(EventTopic.LOG_MESSAGE, entry)
        except Exception:
            self.handleError(record)


def setup_logging(
    log_dir: Optional[Path | str] = None,
    level: int = logging.INFO,
    console_output: bool = True,
) -> logging.Logger:
    """Configure IRIS system-wide logging."""
    if log_dir is None:
        log_dir = get_default_base_dir() / "logs"
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("iris")
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if root_logger.handlers:
        return root_logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Rotating File Handler (5 MB max per file, 3 backups)
    file_handler = RotatingFileHandler(
        log_dir / "iris.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    # 2. In-Memory Handler for UI Viewer
    mem_handler = MemoryLogHandler()
    mem_handler.setFormatter(formatter)
    mem_handler.setLevel(level)
    root_logger.addHandler(mem_handler)

    # 3. Console Handler
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)

    return root_logger


def get_recent_logs(limit: int = 100) -> List[dict]:
    """Retrieve the most recent log entries from memory buffer."""
    return list(log_buffer)[-limit:]
