"""Production-grade logging subsystem with rotating file handler and GUI ring buffer."""

from __future__ import annotations

import collections
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List

from upstox_bridge.core.config import settings

# In-memory buffer for GUI log viewer (stores last 300 log lines)
LOG_BUFFER_MAX = 300
_log_buffer: collections.deque[str] = collections.deque(maxlen=LOG_BUFFER_MAX)


class GuiLogBufferHandler(logging.Handler):
    """Custom logging handler that retains the latest N formatted log entries in memory."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _log_buffer.append(msg)
        except Exception:
            self.handleError(record)


def get_gui_logs() -> List[str]:
    """Retrieve in-memory logs for UI log drawer display."""
    return list(_log_buffer)


def setup_production_logging(log_level: int = logging.INFO) -> None:
    """Configure console, rotating file, and GUI memory buffer logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers on re-init
    if any(isinstance(h, GuiLogBufferHandler) for h in root_logger.handlers):
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # 1. Console Handler (stdout)
    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root_logger.handlers)
    if not has_stream:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)

    # 2. Rotating File Handler (logs/bridge.log, 5MB max, 3 backups)
    try:
        log_dir = settings.root_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "bridge.log"

        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    except Exception:
        # Gracefully fall back if filesystem permissions restrict creating logs/ folder
        pass

    # 3. GUI In-Memory Buffer Handler
    gui_handler = GuiLogBufferHandler()
    gui_handler.setFormatter(formatter)
    gui_handler.setLevel(log_level)
    root_logger.addHandler(gui_handler)
