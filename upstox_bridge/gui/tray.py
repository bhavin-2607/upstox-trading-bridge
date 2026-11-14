"""System Tray Controller for background bridge execution."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw

try:
    import pystray
    _PYSTRAY_AVAILABLE = True
except Exception:
    pystray = None
    _PYSTRAY_AVAILABLE = False

logger = logging.getLogger("SystemTray")


def create_tray_icon_image(color: str = "#16a34a", text: str = "U") -> Image.Image:
    """Generate a sharp circular tray icon with status color."""
    size = (64, 64)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Outer circle
    draw.ellipse([4, 4, 60, 60], fill=color)

    # Inner letter 'U'
    draw.text((24, 18), text, fill="white")
    return image


class SystemTrayController:
    """Manages the OS system tray icon and background menu options."""

    def __init__(
        self,
        on_show: Optional[Callable[[], None]] = None,
        on_start_live: Optional[Callable[[], None]] = None,
        on_start_sim: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ):
        self.on_show = on_show
        self.on_start_live = on_start_live
        self.on_start_sim = on_start_sim
        self.on_stop = on_stop
        self.on_exit = on_exit

        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start system tray in a background thread (Windows only)."""
        if sys.platform != "win32" or not _PYSTRAY_AVAILABLE:
            logger.info("System tray is disabled on macOS/Linux (AppKit requires main-thread run loop; uses standard macOS Dock).")
            return

        image = create_tray_icon_image(color="#64748b", text="U")

        menu = pystray.Menu(
            pystray.MenuItem("Show Dashboard", self._handle_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Live Feed", self._handle_start_live),
            pystray.MenuItem("Run Simulation", self._handle_start_sim),
            pystray.MenuItem("Stop Feed", self._handle_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Application", self._handle_exit),
        )

        self._icon = pystray.Icon(
            name="UpstoxBridge",
            icon=image,
            title="Upstox Trading Bridge",
            menu=menu,
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="TrayThread")
        self._thread.start()
        logger.info("System tray controller initialized.")

    def set_status(self, mode: str) -> None:
        """Update tray icon color according to running state."""
        if not self._icon:
            return

        mode_lower = mode.lower()
        if "live" in mode_lower or "running" in mode_lower:
            color = "#16a34a"  # Green
            tooltip = "Upstox Bridge: Live Streaming"
        elif "sim" in mode_lower:
            color = "#f59e0b"  # Amber
            tooltip = "Upstox Bridge: Simulating Ticks"
        else:
            color = "#64748b"  # Slate / Grey
            tooltip = "Upstox Bridge: Stopped"

        self._icon.icon = create_tray_icon_image(color=color, text="U")
        self._icon.title = tooltip

    def _handle_show(self, icon=None, item=None):
        if self.on_show:
            self.on_show()

    def _handle_start_live(self, icon=None, item=None):
        if self.on_start_live:
            self.on_start_live()

    def _handle_start_sim(self, icon=None, item=None):
        if self.on_start_sim:
            self.on_start_sim()

    def _handle_stop(self, icon=None, item=None):
        if self.on_stop:
            self.on_stop()

    def _handle_exit(self, icon=None, item=None):
        if self.on_exit:
            self.on_exit()
        if self._icon:
            self._icon.stop()

    def stop(self) -> None:
        """Stop tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
