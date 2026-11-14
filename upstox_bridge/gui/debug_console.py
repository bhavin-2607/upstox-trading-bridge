"""Windows debug console controller to show/hide terminal on demand."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("DebugConsole")
_CONSOLE_ALLOCATED = False


def is_debug_console_active() -> bool:
    """Check if debug console is currently allocated and visible on Windows."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not hwnd:
            return False
        return bool(ctypes.windll.user32.IsWindowVisible(hwnd))
    except Exception:
        return False


def set_debug_console(show: bool) -> None:
    """Show or hide the native Windows debug command prompt window."""
    global _CONSOLE_ALLOCATED
    if sys.platform != "win32":
        return

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        hwnd = kernel32.GetConsoleWindow()

        if show:
            if not hwnd:
                # Allocate new console window on demand for windowed GUI executable
                if kernel32.AllocConsole():
                    _CONSOLE_ALLOCATED = True
                    kernel32.SetConsoleTitleW("Upstox Trading Bridge - Live Debug Console")
                    try:
                        # Redirect stdout and stderr to the newly created console
                        sys.stdout = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
                        sys.stderr = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
                    except Exception as e:
                        logger.warning(f"Failed to redirect streams to debug console: {e}")

                    print("=" * 65)
                    print("       UPSTOX TRADING BRIDGE - LIVE DEBUG CONSOLE")
                    print("=" * 65)
                    print("Live logs and diagnostic output will stream here.")
                    print("You can hide this terminal at any time from GUI -> Settings.")
                    print("=" * 65)
            else:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
                user32.SetForegroundWindow(hwnd)
        else:
            if hwnd:
                user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception as e:
        logger.warning(f"Error toggling debug console: {e}")
