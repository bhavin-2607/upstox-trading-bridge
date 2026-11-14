"""Production-grade logging subsystem with rotating file handler and GUI ring buffer."""

from __future__ import annotations

import collections
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List

from upstox_bridge.core.config import settings

# In-memory buffer for GUI log viewer (stores last 300 log lines)
LOG_BUFFER_MAX = 300
_log_buffer: collections.deque[str] = collections.deque(maxlen=LOG_BUFFER_MAX)


class _NullWriter:
    """Safe fallback writer when running headless/windowed without stdout/stderr."""

    def write(self, s: str) -> int:
        return len(s) if s else 0

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


# Ensure standard streams are never None anywhere in the process runtime
if sys.stdout is None:
    sys.stdout = _NullWriter()
if sys.stderr is None:
    sys.stderr = _NullWriter()


class SafeStreamHandler(logging.Handler):
    """Console stream handler that safely writes to stdout/stderr/CONOUT$ without crashing if stream is None."""

    def __init__(self, stream=None):
        super().__init__()
        self._custom_stream = stream

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stream = self._custom_stream
            if stream is None or not hasattr(stream, "write") or isinstance(stream, _NullWriter):
                if sys.stderr is not None and hasattr(sys.stderr, "write") and not isinstance(sys.stderr, _NullWriter):
                    stream = sys.stderr
                elif sys.stdout is not None and hasattr(sys.stdout, "write") and not isinstance(sys.stdout, _NullWriter):
                    stream = sys.stdout
                else:
                    return

            msg = self.format(record)
            stream.write(msg + "\n")
            if hasattr(stream, "flush"):
                stream.flush()
        except Exception:
            pass

    def flush(self) -> None:
        try:
            stream = self._custom_stream or sys.stderr or sys.stdout
            if stream and hasattr(stream, "flush") and not isinstance(stream, _NullWriter):
                stream.flush()
        except Exception:
            pass


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
    # Ensure sys.stdout and sys.stderr are never None
    if sys.stdout is None:
        sys.stdout = _NullWriter()
    if sys.stderr is None:
        sys.stderr = _NullWriter()

    # Disable Python's fallback lastResort handler from crashing on headless Windows
    logging.lastResort = None

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 1. Purge any unsafe standard StreamHandlers (e.g. from basicConfig or 3rd-party libs)
    for h in list(root_logger.handlers):
        if type(h) is logging.StreamHandler:  # exactly standard StreamHandler, not SafeStreamHandler
            root_logger.removeHandler(h)

    for lg in list(logging.root.manager.loggerDict.values()):
        if isinstance(lg, logging.Logger):
            for h in list(lg.handlers):
                if type(h) is logging.StreamHandler:
                    lg.removeHandler(h)

    # Avoid duplicate handlers on re-init
    if any(isinstance(h, GuiLogBufferHandler) for h in root_logger.handlers):
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # 2. Safe Console Handler (stdout/stderr)
    has_stream = any(isinstance(h, SafeStreamHandler) for h in root_logger.handlers)
    if not has_stream:
        console_handler = SafeStreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)

    # 3. Rotating File Handler (logs/bridge.log, 5MB max, 3 backups)
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
