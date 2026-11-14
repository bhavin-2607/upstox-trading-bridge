"""Modern Desktop Dashboard for Upstox Live Market Data Bridge."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

try:
    from tkinter import messagebox
    import customtkinter as ctk
    _TK_AVAILABLE = True
except Exception:
    _TK_AVAILABLE = False
    ctk = None

from upstox_bridge.core.config import settings
from upstox_bridge.core.logger import get_gui_logs, setup_production_logging
from upstox_bridge.gui.settings_dialog import SettingsDialog
from upstox_bridge.gui.tray import SystemTrayController
from upstox_bridge.runner import BridgeRunner

logger = logging.getLogger("DesktopApp")


def is_indian_market_open() -> bool:
    """Check if Indian stock exchanges (NSE/BSE) are currently open (Mon-Fri 09:15-15:30 IST)."""
    now = datetime.now()
    # 0 = Monday, 6 = Sunday
    if now.weekday() >= 5:
        return False
    # Check IST time range 09:15 to 15:30
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


class UpstoxBridgeApp(ctk.CTk if ctk else object):
    """Main Production Desktop Application Window."""

    def __init__(self):
        if not _TK_AVAILABLE:
            raise RuntimeError("Tkinter/CustomTkinter is not supported on this headless Python build.")
        super().__init__()

        # Setup logging
        setup_production_logging()

        # Window Configuration
        self.title("Upstox Trading Bridge - Desktop Edition")
        self.geometry("880x640")
        self.minsize(800, 560)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Engine runner reference
        self.runner: Optional[BridgeRunner] = None
        self._runner_thread: Optional[threading.Thread] = None
        self._is_closing = False

        # Build UI components
        self._build_header()
        self._build_status_cards()
        self._build_control_panel()
        self._build_log_drawer()

        # Initialize System Tray
        self.tray = SystemTrayController(
            on_show=self._restore_from_tray,
            on_start_live=self._start_live_bridge,
            on_start_sim=self._start_simulation,
            on_stop=self._stop_bridge,
            on_exit=self._quit_application,
        )
        self.tray.start()

        # Window close handler (minimize to tray if running)
        self.protocol("WM_DELETE_WINDOW", self._on_close_clicked)

        # Start periodic GUI telemetry loop
        self._telemetry_loop()

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=24, pady=(16, 8))

        # Title and Subtitle
        title_col = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_col.pack(side="left")

        app_title = ctk.CTkLabel(
            title_col,
            text="UPSTOX TRADING BRIDGE",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        app_title.pack(anchor="w")

        app_sub = ctk.CTkLabel(
            title_col,
            text="Institutional Real-Time Feed Engine for Excel & Google Sheets",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
        )
        app_sub.pack(anchor="w")

        # Badges Column
        badges_col = ctk.CTkFrame(header_frame, fg_color="transparent")
        badges_col.pack(side="right", anchor="e")

        # Market Badge
        is_open = is_indian_market_open()
        market_txt = "● Market Open" if is_open else "○ Market Closed (Weekend/After-Hours)"
        market_color = "#16a34a" if is_open else "#f59e0b"

        self.market_badge = ctk.CTkLabel(
            badges_col,
            text=market_txt,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=market_color,
        )
        self.market_badge.pack(anchor="e")

        # Token Badge
        has_token = bool(settings.upstox_access_token)
        token_txt = "✓ Upstox Token Active" if has_token else "⚠ No Token Configured"
        token_color = "#38bdf8" if has_token else "#ef4444"

        self.token_badge = ctk.CTkLabel(
            badges_col,
            text=token_txt,
            font=ctk.CTkFont(size=11),
            text_color=token_color,
        )
        self.token_badge.pack(anchor="e")

    def _build_status_cards(self):
        cards_grid = ctk.CTkFrame(self, fg_color="transparent")
        cards_grid.pack(fill="x", padx=24, pady=8)
        cards_grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="card")

        # Card 1: Feed Status
        self.card_feed = self._create_card(
            cards_grid,
            col=0,
            title="UPSTOX FEED",
            status_text="STOPPED",
            detail_1="0 ticks processed",
            detail_2="232 instruments",
            status_color="#64748b",
        )

        # Card 2: Excel Sync
        excel_name = settings.excel_file_path.name
        sheet_name = settings.excel_sheet_name
        self.card_excel = self._create_card(
            cards_grid,
            col=1,
            title="EXCEL SYNC",
            status_text="READY",
            detail_1=f"File: {excel_name}",
            detail_2=f"Sheet: {sheet_name}",
            status_color="#0284c7",
        )

        # Card 3: Google Sheets
        gsheet_active = bool(settings.gsheet_webhook_url)
        self.card_gsheet = self._create_card(
            cards_grid,
            col=2,
            title="GOOGLE SHEETS",
            status_text="CONFIGURED" if gsheet_active else "DISABLED",
            detail_1="Interval: 3.0s",
            detail_2="BST In-Place Mode",
            status_color="#10b981" if gsheet_active else "#64748b",
        )

        # Card 4: Local HTTP Server
        self.card_server = self._create_card(
            cards_grid,
            col=3,
            title="LOCAL FEED",
            status_text="STANDBY",
            detail_1=f"Port: {settings.local_server_port}",
            detail_2="http://127.0.0.1:8080",
            status_color="#8b5cf6",
        )

    def _create_card(self, parent, col, title, status_text, detail_1, detail_2, status_color):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=0, column=col, padx=6, pady=4, sticky="nsew")

        lbl_title = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
        )
        lbl_title.pack(padx=12, pady=(10, 2), anchor="w")

        lbl_status = ctk.CTkLabel(
            card,
            text=status_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=status_color,
        )
        lbl_status.pack(padx=12, pady=(0, 4), anchor="w")

        lbl_d1 = ctk.CTkLabel(
            card,
            text=detail_1,
            font=ctk.CTkFont(size=11),
            text_color="#cbd5e1",
        )
        lbl_d1.pack(padx=12, pady=0, anchor="w")

        lbl_d2 = ctk.CTkLabel(
            card,
            text=detail_2,
            font=ctk.CTkFont(size=11),
            text_color="#64748b",
        )
        lbl_d2.pack(padx=12, pady=(0, 10), anchor="w")

        return {
            "card": card,
            "status": lbl_status,
            "detail_1": lbl_d1,
            "detail_2": lbl_d2,
        }

    def _build_control_panel(self):
        control_frame = ctk.CTkFrame(self, corner_radius=10)
        control_frame.pack(fill="x", padx=24, pady=10)

        # Left action buttons
        self.btn_live = ctk.CTkButton(
            control_frame,
            text="▶ Start Live Feed",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            height=38,
            width=150,
            command=self._start_live_bridge,
        )
        self.btn_live.pack(side="left", padx=12, pady=12)

        self.btn_sim = ctk.CTkButton(
            control_frame,
            text="⚡ Run Simulation",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            height=38,
            width=150,
            command=self._start_simulation,
        )
        self.btn_sim.pack(side="left", padx=(0, 12), pady=12)

        self.btn_stop = ctk.CTkButton(
            control_frame,
            text="■ Stop",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            height=38,
            width=100,
            state="disabled",
            command=self._stop_bridge,
        )
        self.btn_stop.pack(side="left", padx=(0, 12), pady=12)

        # Right utility buttons
        self.btn_settings = ctk.CTkButton(
            control_frame,
            text="⚙ Settings & Token",
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            height=38,
            width=140,
            command=self._open_settings,
        )
        self.btn_settings.pack(side="right", padx=12, pady=12)

        self.btn_open_excel = ctk.CTkButton(
            control_frame,
            text="📂 Open in Excel",
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            height=38,
            width=120,
            command=self._open_excel_file,
        )
        self.btn_open_excel.pack(side="right", padx=(0, 8), pady=12)

    def _build_log_drawer(self):
        log_frame = ctk.CTkFrame(self, corner_radius=10)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        # Log Header
        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=12, pady=(8, 4))

        log_lbl = ctk.CTkLabel(
            log_header,
            text="LIVE ACTIVITY & TELEMETRY LOGS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
        )
        log_lbl.pack(side="left")

        clear_btn = ctk.CTkButton(
            log_header,
            text="Clear",
            width=60,
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color="#334155",
            hover_color="#475569",
            command=self._clear_logs,
        )
        clear_btn.pack(side="right")

        # Log Text Box
        self.log_textbox = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas" if sys.platform == "win32" else "Menlo", size=11),
            text_color="#e2e8f0",
            wrap="none",
        )
        self.log_textbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # =========================================================================
    # BRIDGE CONTROL ACTIONS
    # =========================================================================

    def _start_live_bridge(self):
        """Start the live market data bridge asynchronously."""
        if self.runner and self.runner.is_running:
            return

        if not settings.upstox_access_token:
            messagebox.showwarning(
                "Access Token Required",
                "No UPSTOX_ACCESS_TOKEN found!\n\nPlease click 'Settings & Token' to paste your access token.",
                parent=self,
            )
            self._open_settings()
            return

        self.btn_live.configure(state="disabled")
        self.btn_sim.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.card_feed["status"].configure(text="CONNECTING...", text_color="#f59e0b")

        def _worker():
            try:
                self.runner = BridgeRunner(
                    custom_file=settings.excel_file_path,
                    custom_sheet=settings.excel_sheet_name,
                )
                self.runner.start_services(interactive_login_if_needed=False)
                self.tray.set_status("live")
            except Exception as e:
                logger.error(f"Failed to start live bridge: {e}")
                self.after(0, lambda: self._on_start_error(str(e)))

        self._runner_thread = threading.Thread(target=_worker, daemon=True, name="BridgeWorker")
        self._runner_thread.start()

    def _start_simulation(self):
        """Start simulated market tick generator."""
        if self.runner and self.runner.is_running:
            return

        self.btn_live.configure(state="disabled")
        self.btn_sim.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.card_feed["status"].configure(text="STARTING SIM...", text_color="#f59e0b")

        def _worker():
            try:
                self.runner = BridgeRunner(
                    custom_file=settings.excel_file_path,
                    custom_sheet=settings.excel_sheet_name,
                )
                self.runner.start_simulation_services()
                self.tray.set_status("sim")
            except Exception as e:
                logger.error(f"Failed to start simulation: {e}")
                self.after(0, lambda: self._on_start_error(str(e)))

        self._runner_thread = threading.Thread(target=_worker, daemon=True, name="SimWorker")
        self._runner_thread.start()

    def _on_start_error(self, err_msg: str):
        self.btn_live.configure(state="normal")
        self.btn_sim.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.card_feed["status"].configure(text="ERROR", text_color="#ef4444")
        messagebox.showerror("Startup Error", f"Could not start bridge:\n\n{err_msg}", parent=self)

    def _stop_bridge(self):
        """Stop all live feeds and syncers."""
        if not self.runner:
            return

        self.btn_stop.configure(state="disabled")
        self.card_feed["status"].configure(text="STOPPING...", text_color="#f59e0b")

        def _worker():
            try:
                if self.runner:
                    self.runner.stop()
                    self.runner = None
            except Exception as e:
                logger.debug(f"Stop error: {e}")
            finally:
                self.after(0, self._on_stopped)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stopped(self):
        self.btn_live.configure(state="normal")
        self.btn_sim.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.card_feed["status"].configure(text="STOPPED", text_color="#64748b")
        self.card_excel["status"].configure(text="READY", text_color="#0284c7")
        self.tray.set_status("stopped")

    def _open_settings(self):
        SettingsDialog(self, on_save_callback=self._on_settings_saved)

    def _on_settings_saved(self):
        has_token = bool(settings.upstox_access_token)
        self.token_badge.configure(
            text="✓ Upstox Token Active" if has_token else "⚠ No Token Configured",
            text_color="#38bdf8" if has_token else "#ef4444",
        )
        self.card_excel["detail_1"].configure(text=f"File: {settings.excel_file_path.name}")
        self.card_excel["detail_2"].configure(text=f"Sheet: {settings.excel_sheet_name}")

        gsheet_active = bool(settings.gsheet_webhook_url)
        self.card_gsheet["status"].configure(
            text="CONFIGURED" if gsheet_active else "DISABLED",
            text_color="#10b981" if gsheet_active else "#64748b",
        )

    def _open_excel_file(self):
        """Launch or bring Excel workbook to the front."""
        path = settings.excel_file_path
        if not path.exists():
            messagebox.showwarning("File Missing", f"Target workbook does not exist:\n{path}", parent=self)
            return

        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            logger.warning(f"Could not open Excel file: {e}")

    def _clear_logs(self):
        self.log_textbox.delete("1.0", "end")

    # =========================================================================
    # TELEMETRY & TRAY MINIMIZATION
    # =========================================================================

    def _telemetry_loop(self):
        """Periodic 500ms loop updating dashboard metrics and activity log."""
        if self._is_closing:
            return

        # 1. Update Feed Status Card
        if self.runner and self.runner.is_running:
            if self.runner.is_simulation:
                self.card_feed["status"].configure(text="● SIMULATION", text_color="#f59e0b")
            else:
                self.card_feed["status"].configure(text="● LIVE FEED", text_color="#16a34a")

            ticks = self.runner.ticks_received
            self.card_feed["detail_1"].configure(text=f"{ticks:,} ticks processed")

            # Excel Card status
            excel_st = self.runner.excel_status
            excel_color = "#16a34a" if excel_st == "Connected" else ("#f59e0b" if "Edit" in excel_st else "#64748b")
            self.card_excel["status"].configure(text=excel_st.upper(), text_color=excel_color)

            # Google Sheets Card status
            gs_st = self.runner.gsheet_status
            self.card_gsheet["status"].configure(text=gs_st.upper(), text_color="#10b981" if "Active" in gs_st else "#64748b")

            self.card_server["status"].configure(text="STREAMING", text_color="#16a34a")
        else:
            if not self.btn_live.cget("state") == "disabled":
                self.card_feed["status"].configure(text="STOPPED", text_color="#64748b")
                self.card_server["status"].configure(text="STANDBY", text_color="#8b5cf6")

        # 2. Update Live Logs in textbox
        recent_logs = get_gui_logs()
        if recent_logs:
            current_text = self.log_textbox.get("1.0", "end-1c")
            current_count = len(current_text.splitlines()) if current_text else 0
            if len(recent_logs) > current_count:
                new_lines = recent_logs[current_count:]
                self.log_textbox.insert("end", "\n".join(new_lines) + "\n")
                self.log_textbox.see("end")

        self.after(500, self._telemetry_loop)

    def _on_close_clicked(self):
        """Minimize to tray if running, or prompt to quit."""
        if self.runner and self.runner.is_running:
            self.withdraw()  # Hide window to system tray
        else:
            self._quit_application()

    def _restore_from_tray(self):
        """Restore window from System Tray."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_application(self):
        """Completely exit the desktop application."""
        self._is_closing = True
        if self.runner:
            try:
                self.runner.stop()
            except Exception:
                pass
        if self.tray:
            self.tray.stop()
        self.destroy()
        sys.exit(0)


def launch_gui(prefer_web: bool = False):
    """Entry point to launch the UI: uses CustomTkinter if available, else Web Dashboard."""
    if not prefer_web and _TK_AVAILABLE:
        try:
            app = UpstoxBridgeApp()
            app.mainloop()
            return
        except Exception as e:
            logger.warning(f"Native Desktop GUI failed to initialize ({e}). Launching Web Dashboard...")

    # Fallback to Web Dashboard (works on all platforms without Tkinter)
    from upstox_bridge.gui.web_dashboard import launch_web_dashboard
    launch_web_dashboard()
