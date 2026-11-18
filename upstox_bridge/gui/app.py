"""Native CustomTkinter Desktop Application for Upstox Trading Bridge."""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from tkinter import filedialog, messagebox
    import customtkinter as ctk
    from PIL import Image, ImageTk
    _TK_AVAILABLE = True
except Exception:
    _TK_AVAILABLE = False
    ctk = None

from upstox_bridge.core.config import get_asset_path, settings
from upstox_bridge.core.logger import get_gui_logs, setup_production_logging
from upstox_bridge.gui.icons import IconManager
from upstox_bridge.gui.settings_dialog import SettingsDialog
from upstox_bridge.gui.tray import SystemTrayController
from upstox_bridge.runner import BridgeRunner

# Ensure Windows assigns a distinct Application User Model ID for the taskbar icon
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bhavinamesara.bsatradingbridge.desktop.2_0")
    except Exception:
        pass

# Monkey-patch CustomTkinter's default Windows icon setter so it never replaces custom icon
if _TK_AVAILABLE and ctk:
    def _patched_windows_set_titlebar_icon(self):
        try:
            ico_path = get_asset_path("app_icon.ico")
            if sys.platform == "win32" and ico_path.exists():
                self.iconbitmap(default=str(ico_path))
        except Exception:
            pass

    try:
        ctk.CTk._windows_set_titlebar_icon = _patched_windows_set_titlebar_icon
        ctk.CTkToplevel._windows_set_titlebar_icon = _patched_windows_set_titlebar_icon
    except Exception:
        pass

logger = logging.getLogger("DesktopApp")

# Color Tokens — Pure Dark Black (OLED Pitch Black)
COLOR_BG_CANVAS = "#000000"
COLOR_BG_SUBTLE = "#08080A"
COLOR_CARD_SURFACE = "#101114"
COLOR_CARD_HOVER = "#16171B"
COLOR_CARD_BORDER = "#1E2026"
COLOR_CARD_BORDER_ACTIVE = "#2E323D"
COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#A1A1AA"
COLOR_BRAND_CYAN = "#08B6DE"
COLOR_BRAND_AMBER = "#F5A623"
COLOR_STATUS_BULL = "#00E676"
COLOR_STATUS_BEAR = "#FF334B"
COLOR_FLASH_BULL = "#052414"
COLOR_FLASH_BEAR = "#2E0A0E"


def get_market_sessions() -> Tuple[str, str, str, str, str]:
    """Calculate live Indian market session status and clock in IST."""
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist_tz)
    weekday = now.weekday()  # 0 = Monday, 6 = Sunday
    ist_time_str = now.strftime("%H:%M:%S IST")

    if weekday >= 5:
        return "CLOSED (WEEKEND)", ist_time_str, "#A1A1AA", "#141416", "#27272A"

    now_minutes = now.hour * 60 + now.minute
    if 555 <= now_minutes <= 930:  # 09:15 to 15:30
        return "NSE & MCX LIVE", ist_time_str, "#00E676", "#042314", "#0d5e35"
    elif 540 <= now_minutes < 555:  # 09:00 to 09:15
        return "NSE PRE-OPEN", ist_time_str, "#F5A623", "#261a06", "#66440c"
    elif 930 < now_minutes <= 1410:  # 15:30 to 23:30 (MCX Commodity evening session)
        return "MCX COMMODITY LIVE", ist_time_str, "#08B6DE", "#051b24", "#0d4e68"
    else:
        return "MARKET CLOSED", ist_time_str, "#A1A1AA", "#141416", "#27272A"


def get_token_health(token: str) -> Tuple[str, str, str, str]:
    """Decode JWT expiration from token and return health pill status."""
    if not token or "." not in token:
        return "No Token Configured", "#EF4444", "#290a0d", "#63161e"
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return "Invalid Token Format", "#EF4444", "#290a0d", "#63161e"
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
        data = json.loads(payload_json)
        exp = data.get("exp")
        if not exp:
            return "Token Active", "#08B6DE", "#051b24", "#0d4e68"

        remaining_sec = exp - time.time()
        if remaining_sec <= 0:
            return "Token Expired", "#FF334B", "#290a0d", "#63161e"
        elif remaining_sec < 2 * 3600:
            h = int(remaining_sec // 3600)
            m = int((remaining_sec % 3600) // 60)
            return f"Token: {h}h {m}m (Expiring)", "#F5A623", "#261a06", "#66440c"
        else:
            h = int(remaining_sec // 3600)
            m = int((remaining_sec % 3600) // 60)
            return f"Token: {h}h {m}m Active", "#00E676", "#042314", "#0d5e35"
    except Exception:
        return "Token Active", "#08B6DE", "#051b24", "#0d4e68"


class UpstoxBridgeApp(ctk.CTk if ctk else object):
    """Institutional High-Performance Desktop Cockpit for Upstox Bridge."""

    def __init__(self):
        if not _TK_AVAILABLE:
            raise RuntimeError("Tkinter/CustomTkinter is not supported on this headless Python build.")
        super().__init__()

        # Setup production logging
        setup_production_logging()

        # Window Configuration & Dimensions
        self.title("BSA Trading Bridge — Market Data Engine")
        self.geometry("960x780")
        self.minsize(900, 680)

        # Apply Pure Dark Black OLED styling
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=COLOR_BG_CANVAS)

        # Set taskbar and window application icons
        self._apply_application_icons()

        # Engine runner reference
        self.runner: Optional[BridgeRunner] = None
        self._runner_thread: Optional[threading.Thread] = None
        self._is_closing = False
        self._log_filter = "ALL"
        self._prev_watchlist_ltp: Dict[str, float] = {}

        # Build UI components
        self._build_header_cockpit()
        self._build_quick_add_omnibar()
        self._build_mini_watchlist_strip()
        self._build_status_cards()
        self._build_control_panel()
        self._build_activity_console()

        # Initialize System Tray
        self.tray = SystemTrayController(
            on_show=self._restore_from_tray,
            on_alerts=self._open_alerts_from_tray,
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

    def _windows_set_titlebar_icon(self):
        """Override CustomTkinter's default so it never overwrites with CustomTkinter_icon_Windows.ico."""
        self._apply_application_icons()

    def _apply_application_icons(self):
        """Configure native OS taskbar, Alt-Tab, and window title bar icons."""
        icon_ico = get_asset_path("app_icon.ico")
        icon_png = get_asset_path("app_icon.png")

        if sys.platform == "win32" and icon_ico.exists():
            try:
                self.iconbitmap(default=str(icon_ico))
            except Exception:
                try:
                    self.wm_iconbitmap(str(icon_ico))
                except Exception:
                    pass
            try:
                if icon_png.exists():
                    self._app_icon_photo = ImageTk.PhotoImage(file=str(icon_png))
                    self.wm_iconphoto(True, self._app_icon_photo)
            except Exception:
                pass
            # Explicit Win32 WM_SETICON message to guarantee taskbar binding
            try:
                import ctypes
                hwnd = self.winfo_id()
                h_icon = ctypes.windll.user32.LoadImageW(
                    None, str(icon_ico), 1, 0, 0, 0x00000010 | 0x00008000
                )
                if h_icon and hwnd:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x80, 0, h_icon)  # ICON_SMALL
                    ctypes.windll.user32.SendMessageW(hwnd, 0x80, 1, h_icon)  # ICON_BIG
            except Exception:
                pass
        elif icon_png.exists():
            try:
                self._app_icon_photo = ImageTk.PhotoImage(file=str(icon_png))
                self.wm_iconphoto(True, self._app_icon_photo)
            except Exception:
                pass

    # =========================================================================
    # UI CONSTRUCTION — HEADER COCKPIT
    # =========================================================================

    def _build_header_cockpit(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(14, 6))

        # Title & Institutional Wordmark with brand icon
        title_col = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_col.pack(side="left")

        self._header_logo = IconManager.get_icon("bridge_logo", size=(26, 26))
        if self._header_logo:
            app_title = ctk.CTkLabel(
                title_col,
                text="  BSA TRADING BRIDGE",
                image=self._header_logo,
                compound="left",
                font=ctk.CTkFont(size=20, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            )
        else:
            app_title = ctk.CTkLabel(
                title_col,
                text="BSA TRADING BRIDGE",
                font=ctk.CTkFont(size=20, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            )
        app_title.pack(anchor="w")

        app_sub = ctk.CTkLabel(
            title_col,
            text="An independent product by Bhavin Amesara  •  Real-Time Market Data Engine",
            font=ctk.CTkFont(size=11),
            text_color="#A9B8CC",
        )
        app_sub.pack(anchor="w")

        # Telemetry Cockpit Badges (Right side)
        cockpit_pills = ctk.CTkFrame(header_frame, fg_color="transparent")
        cockpit_pills.pack(side="right", anchor="e")

        session_txt, clock_txt, ses_col, ses_bg, ses_border = get_market_sessions()

        # 1. Market Session Pill
        self.pill_session = ctk.CTkFrame(
            cockpit_pills, fg_color=ses_bg, border_color=ses_border, border_width=1, corner_radius=14
        )
        self.pill_session.pack(side="left", padx=4)
        self.lbl_session = ctk.CTkLabel(
            self.pill_session, text=session_txt, font=ctk.CTkFont(size=11, weight="bold"), text_color=ses_col
        )
        self.lbl_session.pack(padx=10, pady=3)

        # 2. Live IST Clock Pill
        self.pill_clock = ctk.CTkFrame(
            cockpit_pills, fg_color="#101114", border_color=COLOR_CARD_BORDER, border_width=1, corner_radius=14
        )
        self.pill_clock.pack(side="left", padx=4)
        self._clock_icon = IconManager.get_icon("clock", size=(13, 13))
        self.lbl_clock = ctk.CTkLabel(
            self.pill_clock,
            text=f" {clock_txt}",
            image=self._clock_icon,
            compound="left",
            font=ctk.CTkFont(family="Consolas" if sys.platform == "win32" else "Menlo", size=11, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.lbl_clock.pack(padx=10, pady=3)

        # 3. Token Health Pill
        tok_txt, tok_col, tok_bg, tok_border = get_token_health(settings.upstox_access_token)
        self.pill_token = ctk.CTkFrame(
            cockpit_pills, fg_color=tok_bg, border_color=tok_border, border_width=1, corner_radius=14
        )
        self.pill_token.pack(side="left", padx=4)
        self._token_icon = IconManager.get_icon("token", size=(13, 13))
        self.lbl_token = ctk.CTkLabel(
            self.pill_token,
            text=f" {tok_txt}",
            image=self._token_icon,
            compound="left",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=tok_col,
        )
        self.lbl_token.pack(padx=10, pady=3)

    # =========================================================================
    # UI CONSTRUCTION — QUICK-ADD OMNIBAR
    # =========================================================================

    def _build_quick_add_omnibar(self):
        omni_box = ctk.CTkFrame(
            self,
            fg_color=COLOR_CARD_SURFACE,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        omni_box.pack(fill="x", padx=20, pady=(4, 6))

        bar_inner = ctk.CTkFrame(omni_box, fg_color="transparent")
        bar_inner.pack(fill="x", padx=12, pady=8)

        self.omni_entry = ctk.CTkEntry(
            bar_inner,
            placeholder_text="Quick Add Script (e.g. NIFTY 26000 CE, BANKNIFTY 54000 PE, CRUDEOIL DEC FUT)...",
            font=ctk.CTkFont(size=12),
            fg_color=COLOR_BG_SUBTLE,
            border_color="#27272A",
            text_color=COLOR_TEXT_PRIMARY,
            height=34,
        )
        self.omni_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.omni_entry.bind("<Return>", lambda _: self._on_quick_add_script())

        self.btn_add_script = ctk.CTkButton(
            bar_inner,
            text=" Add to Sheet",
            image=IconManager.get_icon("add", size=(14, 14)),
            compound="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_BRAND_CYAN,
            hover_color="#0693b3",
            text_color="#FFFFFF",
            height=34,
            width=135,
            command=self._on_quick_add_script,
        )
        self.btn_add_script.pack(side="right")

        # Feedback Toast Label
        self.lbl_omni_feedback = ctk.CTkLabel(
            omni_box,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_STATUS_BULL,
        )

    def _on_quick_add_script(self):
        """Resolve and inject user script into BST Excel and live stream."""
        raw_val = self.omni_entry.get().strip()
        if not raw_val:
            return

        self.btn_add_script.configure(state="disabled")

        def _task():
            success = False
            msg = ""
            target_row = 0

            # 1. If runner is actively running with BSTSyncer
            if self.runner and self.runner.is_running and self.runner.bst_syncer:
                success, msg, target_row = self.runner.quick_add_script(raw_val)
            else:
                # 2. Append offline to workbook directly
                try:
                    import sys
                    if sys.platform == "win32":
                        try:
                            import pythoncom
                            pythoncom.CoInitialize()
                        except Exception:
                            pass

                    import openpyxl
                    from upstox_bridge.instruments.master import InstrumentMaster
                    im = InstrumentMaster()
                    im.load()
                    clean_sym = im.clean_script_symbol(raw_val)
                    key = im.resolve_symbol(raw_val)

                    wb_path = settings.excel_file_path
                    if not wb_path.exists():
                        success = False
                        msg = f"Workbook not found: {wb_path}"
                    else:
                        written = False
                        # Try xlwings first if Excel is currently running
                        try:
                            import xlwings as xw
                            target_book = None
                            try:
                                target_book = xw.Book(wb_path.name)
                            except Exception:
                                try:
                                    target_book = xw.Book(str(wb_path))
                                except Exception:
                                    pass

                            if target_book:
                                ws = target_book.sheets[settings.excel_sheet_name] if settings.excel_sheet_name in [s.name for s in target_book.sheets] else target_book.sheets.active
                                vals = ws.range("A10:A1000").value or []
                                last_r = 9
                                for idx, v in enumerate(vals, start=10):
                                    if v is not None and str(v).strip():
                                        last_r = idx
                                target_row = last_r + 1
                                ws.range(f"A{target_row}").value = clean_sym
                                written = True
                                success = True
                                msg = f"Added {clean_sym} to row {target_row} in active Excel"
                        except Exception:
                            pass

                        # If Excel was not running, fall back to openpyxl
                        if not written:
                            try:
                                wb = openpyxl.load_workbook(wb_path, data_only=False)
                                ws = wb[settings.excel_sheet_name] if settings.excel_sheet_name in wb.sheetnames else wb.active
                                last_r = 9
                                for r in range(10, 1000):
                                    v = ws.cell(r, 1).value
                                    if v is not None and str(v).strip():
                                        last_r = r
                                target_row = last_r + 1
                                ws.cell(target_row, 1, clean_sym)
                                wb.save(wb_path)
                                wb.close()
                                success = True
                                msg = f"Added {clean_sym} to row {target_row} in {wb_path.name}"
                            except PermissionError:
                                success = False
                                msg = f"File locked: '{wb_path.name}' is open in Excel. Start Live Feed or close the file."
                            except Exception as e:
                                success = False
                                msg = f"Failed to save workbook: {e}"
                except Exception as e:
                    success = False
                    msg = f"Failed to add script: {e}"

            def _update_ui():
                self.btn_add_script.configure(state="normal")
                if success:
                    self.omni_entry.delete(0, "end")
                    self.lbl_omni_feedback.configure(text=f"SUCCESS: {msg}", text_color=COLOR_STATUS_BULL)
                    self.lbl_omni_feedback.pack(padx=14, pady=(0, 6), anchor="w")
                    self.after(5000, lambda: self.lbl_omni_feedback.pack_forget())
                else:
                    self.lbl_omni_feedback.configure(text=f"ERROR: {msg}", text_color=COLOR_STATUS_BEAR)
                    self.lbl_omni_feedback.pack(padx=14, pady=(0, 6), anchor="w")
                    self.after(5000, lambda: self.lbl_omni_feedback.pack_forget())

            self.after(0, _update_ui)

        threading.Thread(target=_task, daemon=True).start()

    # =========================================================================
    # UI CONSTRUCTION — PINNED MINI-WATCHLIST STRIP
    # =========================================================================

    def _build_mini_watchlist_strip(self):
        strip_frame = ctk.CTkFrame(self, fg_color="transparent")
        strip_frame.pack(fill="x", padx=20, pady=(2, 6))
        strip_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="watchlist")

        self.watchlist_cards = {}
        symbols_config = [
            ("NIFTY 50", "NSE_INDEX|Nifty 50", "BENCHMARK"),
            ("BANKNIFTY", "NSE_INDEX|Nifty Bank", "BANKING"),
            ("NIFTY 26000 CE", "NSE_FO|45436", "OPT CURRENT WK"),
            ("FINNIFTY", "NSE_INDEX|Nifty Fin Service", "FINANCIALS"),
        ]

        mono_font = "Consolas" if sys.platform == "win32" else "Menlo"

        for idx, (sym_name, key, tag) in enumerate(symbols_config):
            card = ctk.CTkFrame(
                strip_frame,
                fg_color=COLOR_CARD_SURFACE,
                border_color=COLOR_CARD_BORDER,
                border_width=1,
                corner_radius=8,
            )
            card.grid(row=0, column=idx, padx=4, pady=2, sticky="nsew")

            header_row = ctk.CTkFrame(card, fg_color="transparent")
            header_row.pack(fill="x", padx=10, pady=(8, 2))

            lbl_name = ctk.CTkLabel(
                header_row,
                text=sym_name,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            )
            lbl_name.pack(side="left")

            lbl_tag = ctk.CTkLabel(
                header_row,
                text=tag,
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=COLOR_BRAND_CYAN,
            )
            lbl_tag.pack(side="right")

            lbl_ltp = ctk.CTkLabel(
                card,
                text="₹0.00",
                font=ctk.CTkFont(family=mono_font, size=16, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            )
            lbl_ltp.pack(anchor="w", padx=10, pady=(0, 1))

            delta_row = ctk.CTkFrame(card, fg_color="transparent")
            delta_row.pack(fill="x", padx=10, pady=(0, 6))

            lbl_delta = ctk.CTkLabel(
                delta_row,
                text="0.00 (0.00%)",
                font=ctk.CTkFont(family=mono_font, size=10, weight="bold"),
                text_color=COLOR_TEXT_SECONDARY,
            )
            lbl_delta.pack(side="left")

            lbl_range = ctk.CTkLabel(
                delta_row,
                text="H: -  L: -",
                font=ctk.CTkFont(size=10),
                text_color=COLOR_TEXT_SECONDARY,
            )
            lbl_range.pack(side="right")

            self.watchlist_cards[key] = {
                "card": card,
                "name": sym_name,
                "ltp": lbl_ltp,
                "delta": lbl_delta,
                "range": lbl_range,
                "last_ltp": 0.0,
            }

    # =========================================================================
    # UI CONSTRUCTION — TELEMETRY STATUS CARDS
    # =========================================================================

    def _build_status_cards(self):
        cards_grid = ctk.CTkFrame(self, fg_color="transparent")
        cards_grid.pack(fill="x", padx=20, pady=(2, 6))
        cards_grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="card")

        mono_font = "Consolas" if sys.platform == "win32" else "Menlo"

        # Card 1: Feed Status
        self.card_feed = self._create_card(
            cards_grid,
            col=0,
            title="UPSTOX FEED",
            status_text="STOPPED",
            detail_1="0 ticks processed",
            detail_2="242 instruments tracked",
            status_color=COLOR_TEXT_SECONDARY,
            mono_font=mono_font,
        )

        # Card 2: Excel Sync
        excel_name = settings.excel_file_path.name
        sheet_name = settings.excel_sheet_name
        self.card_excel = self._create_card(
            cards_grid,
            col=1,
            title="EXCEL (BST)",
            status_text="READY",
            detail_1=f"File: {excel_name}",
            detail_2=f"Sheet: {sheet_name}",
            status_color=COLOR_BRAND_CYAN,
            mono_font=mono_font,
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
            status_color=COLOR_STATUS_BULL if gsheet_active else COLOR_TEXT_SECONDARY,
            mono_font=mono_font,
        )

        # Card 4: System Throughput / Local Server
        self.card_server = self._create_card(
            cards_grid,
            col=3,
            title="THROUGHPUT",
            status_text="STANDBY",
            detail_1="Rate: 0 ticks/sec",
            detail_2=f"Local Port: {settings.local_server_port}",
            status_color=COLOR_BRAND_AMBER,
            mono_font=mono_font,
        )

    def _create_card(self, parent, col, title, status_text, detail_1, detail_2, status_color, mono_font):
        card = ctk.CTkFrame(
            parent,
            fg_color=COLOR_CARD_SURFACE,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        card.grid(row=0, column=col, padx=4, pady=2, sticky="nsew")

        lbl_title = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        lbl_title.pack(padx=12, pady=(8, 1), anchor="w")

        lbl_status = ctk.CTkLabel(
            card,
            text=status_text,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=status_color,
        )
        lbl_status.pack(padx=12, pady=(0, 2), anchor="w")

        lbl_d1 = ctk.CTkLabel(
            card,
            text=detail_1,
            font=ctk.CTkFont(family=mono_font, size=11),
            text_color=COLOR_TEXT_PRIMARY,
        )
        lbl_d1.pack(padx=12, pady=0, anchor="w")

        lbl_d2 = ctk.CTkLabel(
            card,
            text=detail_2,
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_SECONDARY,
        )
        lbl_d2.pack(padx=12, pady=(0, 8), anchor="w")

        return {
            "card": card,
            "status": lbl_status,
            "detail_1": lbl_d1,
            "detail_2": lbl_d2,
        }

    # =========================================================================
    # UI CONSTRUCTION — PRIMARY CONTROLS
    # =========================================================================

    def _build_control_panel(self):
        control_frame = ctk.CTkFrame(
            self,
            fg_color=COLOR_CARD_SURFACE,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        control_frame.pack(fill="x", padx=20, pady=(2, 6))

        # Left action buttons
        self.btn_live = ctk.CTkButton(
            control_frame,
            text=" Start Live Feed",
            image=IconManager.get_icon("play", size=(16, 16)),
            compound="left",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#10b981",
            text_color="#FFFFFF",
            height=36,
            width=150,
            command=self._start_live_bridge,
        )
        self.btn_live.pack(side="left", padx=10, pady=8)

        self.btn_sim = ctk.CTkButton(
            control_frame,
            text=" Run Simulation",
            image=IconManager.get_icon("simulate", size=(16, 16)),
            compound="left",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_BRAND_CYAN,
            hover_color="#0693b3",
            text_color="#FFFFFF",
            height=36,
            width=150,
            command=self._start_simulation,
        )
        self.btn_sim.pack(side="left", padx=(0, 10), pady=8)

        self.btn_stop = ctk.CTkButton(
            control_frame,
            text=" Stop Bridge",
            image=IconManager.get_icon("stop", size=(16, 16)),
            compound="left",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#e11d48",
            hover_color="#f43f5e",
            text_color="#FFFFFF",
            height=36,
            width=120,
            state="disabled",
            command=self._stop_bridge,
        )
        self.btn_stop.pack(side="left", padx=(0, 10), pady=8)

        # Right utility buttons
        self.btn_settings = ctk.CTkButton(
            control_frame,
            text=" Settings & Token",
            image=IconManager.get_icon("settings", size=(16, 16)),
            compound="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color=COLOR_TEXT_PRIMARY,
            height=36,
            width=145,
            command=self._open_settings,
        )
        self.btn_settings.pack(side="right", padx=(6, 10), pady=8)

        self.btn_alerts = ctk.CTkButton(
            control_frame,
            text=" 🔔 Alerts",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color=COLOR_BRAND_CYAN,
            height=36,
            width=110,
            command=self._open_alerts_dialog,
        )
        self.btn_alerts.pack(side="right", padx=(0, 6), pady=8)

        self.btn_open_excel = ctk.CTkButton(
            control_frame,
            text=" Open in Excel",
            image=IconManager.get_icon("excel", size=(16, 16)),
            compound="left",
            font=ctk.CTkFont(size=12),
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color=COLOR_TEXT_PRIMARY,
            height=36,
            width=130,
            command=self._open_excel_file,
        )
        self.btn_open_excel.pack(side="right", padx=(0, 6), pady=8)

    # =========================================================================
    # UI CONSTRUCTION — ACTIVITY CONSOLE WITH LOG FILTER TABS
    # =========================================================================

    def _build_activity_console(self):
        log_frame = ctk.CTkFrame(
            self,
            fg_color=COLOR_CARD_SURFACE,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        log_frame.pack(fill="both", expand=True, padx=20, pady=(2, 14))

        # Log Header with Filter Tabs
        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=12, pady=(6, 4))

        log_lbl = ctk.CTkLabel(
            log_header,
            text="ACTIVITY & DIAGNOSTIC CONSOLE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        log_lbl.pack(side="left", padx=(0, 16))

        # Filter Tabs
        tabs_container = ctk.CTkFrame(log_header, fg_color="transparent")
        tabs_container.pack(side="left")

        self.filter_buttons = {}
        filters = [("All Logs", "ALL"), ("Market Ticks", "TICKS"), ("Excel Sync", "SYNC"), ("Alerts Only", "ALERTS")]

        for label, f_key in filters:
            btn = ctk.CTkButton(
                tabs_container,
                text=label,
                font=ctk.CTkFont(size=10, weight="bold" if f_key == "ALL" else "normal"),
                fg_color=COLOR_BRAND_CYAN if f_key == "ALL" else "#16171B",
                hover_color="#0693b3" if f_key == "ALL" else "#23252E",
                border_color="#27272A",
                border_width=1,
                text_color="#FFFFFF" if f_key == "ALL" else COLOR_TEXT_SECONDARY,
                height=24,
                width=80,
                command=lambda k=f_key: self._set_log_filter(k),
            )
            btn.pack(side="left", padx=2)
            self.filter_buttons[f_key] = btn

        # Utility Buttons
        clear_btn = ctk.CTkButton(
            log_header,
            text=" Clear",
            image=IconManager.get_icon("clear", size=(12, 12)),
            compound="left",
            width=68,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color=COLOR_TEXT_SECONDARY,
            command=self._clear_logs,
        )
        clear_btn.pack(side="right", padx=(4, 0))

        # Log Text Box with Tabular Monospaced Digits
        mono_font = "Consolas" if sys.platform == "win32" else "Menlo"
        self.log_textbox = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family=mono_font, size=11),
            fg_color=COLOR_BG_SUBTLE,
            text_color=COLOR_TEXT_PRIMARY,
            wrap="none",
        )
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=(2, 10))

    def _set_log_filter(self, filter_key: str):
        """Switch active activity console log category."""
        self._log_filter = filter_key
        for k, btn in self.filter_buttons.items():
            if k == filter_key:
                btn.configure(fg_color=COLOR_BRAND_CYAN, text_color="#FFFFFF")
            else:
                btn.configure(fg_color="#16171B", text_color=COLOR_TEXT_SECONDARY)
        # Re-render logs immediately
        self._refresh_logs_display()

    def _refresh_logs_display(self):
        """Render in-memory logs according to current filter."""
        all_logs = get_gui_logs()
        filtered = []
        for line in all_logs:
            if self._log_filter == "ALL":
                filtered.append(line)
            elif self._log_filter == "TICKS" and any(k in line for k in ("FeedStreamer", "tick", "Subscribed", "LTP", "Quote")):
                filtered.append(line)
            elif self._log_filter == "SYNC" and any(k in line for k in ("BSTSyncer", "Excel", "GoogleSheet", "sync", "Row")):
                filtered.append(line)
            elif self._log_filter == "ALERTS" and any(k in line for k in ("WARNING", "ERROR", "failed", "Exception", "alert")):
                filtered.append(line)

        self.log_textbox.delete("1.0", "end")
        if filtered:
            self.log_textbox.insert("end", "\n".join(filtered) + "\n")
            self.log_textbox.see("end")

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
        self.card_feed["status"].configure(text="CONNECTING...", text_color=COLOR_BRAND_AMBER)

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
        self.card_feed["status"].configure(text="STARTING SIM...", text_color=COLOR_BRAND_AMBER)

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
        self.card_feed["status"].configure(text="ERROR", text_color=COLOR_STATUS_BEAR)
        messagebox.showerror("Startup Error", f"Could not start bridge:\n\n{err_msg}", parent=self)

    def _stop_bridge(self):
        """Stop all live feeds and syncers."""
        if not self.runner:
            return

        self.btn_stop.configure(state="disabled")
        self.card_feed["status"].configure(text="STOPPING...", text_color=COLOR_BRAND_AMBER)

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
        self.card_feed["status"].configure(text="STOPPED", text_color=COLOR_TEXT_SECONDARY)
        self.card_excel["status"].configure(text="READY", text_color=COLOR_BRAND_CYAN)
        self.card_server["status"].configure(text="STANDBY", text_color=COLOR_BRAND_AMBER)
        self.tray.set_status("stopped")

    def _open_settings(self):
        SettingsDialog(self, on_save_callback=self._on_settings_saved)

    def _open_alerts_from_tray(self):
        self._restore_from_tray()
        self.after(200, self._open_alerts_dialog)

    def _open_alerts_dialog(self):
        from upstox_bridge.gui.alerts_dialog import AlertsDialog
        store = self.runner.market_store if hasattr(self, "runner") and self.runner else None
        AlertsDialog(self, market_store=store)

    def _on_settings_saved(self):
        tok_txt, tok_col, tok_bg, tok_border = get_token_health(settings.upstox_access_token)
        self.pill_token.configure(fg_color=tok_bg, border_color=tok_border)
        self.lbl_token.configure(text=tok_txt, text_color=tok_col)

        self.card_excel["detail_1"].configure(text=f"File: {settings.excel_file_path.name}")
        self.card_excel["detail_2"].configure(text=f"Sheet: {settings.excel_sheet_name}")

        gsheet_active = bool(settings.gsheet_webhook_url)
        self.card_gsheet["status"].configure(
            text="CONFIGURED" if gsheet_active else "DISABLED",
            text_color=COLOR_STATUS_BULL if gsheet_active else COLOR_TEXT_SECONDARY,
        )

        # Dynamically apply changes to running syncer if active
        if hasattr(self, "runner") and self.runner and self.runner.gsheet_syncer:
            self.runner.gsheet_syncer.publish_mode = settings.gsheet_publish_mode
            self.runner.gsheet_syncer.webhook_url = settings.gsheet_webhook_url
            self.runner.gsheet_syncer.sheet_name = settings.excel_sheet_name

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
        """Periodic 500ms loop updating dashboard metrics, clock, watchlist cards, and activity log."""
        if self._is_closing:
            return

        try:
            # 1. Update Market Session & Clock
            ses_txt, clock_txt, ses_col, ses_bg, ses_border = get_market_sessions()
            self.pill_session.configure(fg_color=ses_bg, border_color=ses_border)
            self.lbl_session.configure(text=session_txt if 'session_txt' in locals() else ses_txt, text_color=ses_col)
            self.lbl_clock.configure(text=f" {clock_txt}")

            # 2. Update Feed & Telemetry Cards
            if self.runner and self.runner.is_running:
                if self.runner.is_simulation:
                    self.card_feed["status"].configure(text="SIMULATING", text_color=COLOR_BRAND_AMBER)
                else:
                    self.card_feed["status"].configure(text="LIVE STREAMING", text_color=COLOR_STATUS_BULL)

                ticks = self.runner.ticks_received
                tracked_count = self.runner.market_store.count()
                self.card_feed["detail_1"].configure(text=f"{ticks:,} ticks processed")
                self.card_feed["detail_2"].configure(text=f"{tracked_count} instruments streaming")

                # Excel Card status
                excel_st = self.runner.excel_status
                excel_color = COLOR_STATUS_BULL if excel_st == "Connected" else (COLOR_BRAND_AMBER if "Edit" in excel_st else COLOR_TEXT_SECONDARY)
                self.card_excel["status"].configure(text=excel_st.upper(), text_color=excel_color)

                # Google Sheets Card status
                gs_st = self.runner.gsheet_status
                self.card_gsheet["status"].configure(
                    text=gs_st.upper(),
                    text_color=COLOR_STATUS_BULL if "Active" in gs_st else COLOR_TEXT_SECONDARY,
                )

                self.card_server["status"].configure(text="STREAMING", text_color=COLOR_STATUS_BULL)

                # 3. Update Pinned Mini-Watchlist Cards with Live Ticks
                store = self.runner.market_store
                for key, ui_card in self.watchlist_cards.items():
                    item = store.get_quote_item(key)
                    if item:
                        ltp = item.ltp if (item.ltp and item.ltp > 0) else (item.close or item.prev_close or 0.0)
                        prev_c = item.prev_close or item.close or ltp or 0.0
                        delta = ltp - prev_c if prev_c else 0.0
                        pct = (delta / prev_c * 100) if prev_c else 0.0

                        # Format LTP with tabular precision
                        ui_card["ltp"].configure(text=f"₹{ltp:,.2f}")

                        if delta >= 0:
                            ui_card["delta"].configure(text=f"+{delta:.2f} (+{pct:.2f}%)", text_color=COLOR_STATUS_BULL)
                        else:
                            ui_card["delta"].configure(text=f"{delta:.2f} ({pct:.2f}%)", text_color=COLOR_STATUS_BEAR)

                        h_val = f"{item.high:,.2f}" if item.high else (f"{item.prev_high:,.2f}" if item.prev_high else "-")
                        l_val = f"{item.low:,.2f}" if item.low else (f"{item.prev_low:,.2f}" if item.prev_low else "-")
                        ui_card["range"].configure(text=f"H: {h_val}  L: {l_val}")

                        # Tick Flash Interaction
                        old_ltp = ui_card["last_ltp"]
                        if old_ltp > 0 and ltp != old_ltp:
                            flash_color = COLOR_FLASH_BULL if ltp > old_ltp else COLOR_FLASH_BEAR
                            ui_card["card"].configure(fg_color=flash_color)
                            self.after(300, lambda c=ui_card["card"]: c.configure(fg_color=COLOR_CARD_SURFACE))
                        ui_card["last_ltp"] = ltp
            else:
                if not self.btn_live.cget("state") == "disabled":
                    self.card_feed["status"].configure(text="STOPPED", text_color=COLOR_TEXT_SECONDARY)
                    self.card_server["status"].configure(text="STANDBY", text_color=COLOR_BRAND_AMBER)

            # 4. Update Active Alerts Badge
            try:
                from upstox_bridge.core.alert_engine import alert_engine
                act_count = alert_engine.get_active_count()
                if hasattr(self, "btn_alerts"):
                    if act_count > 0:
                        self.btn_alerts.configure(text=f" 🔔 Alerts ({act_count})", text_color=COLOR_STATUS_BULL)
                    else:
                        self.btn_alerts.configure(text=" 🔔 Alerts", text_color=COLOR_BRAND_CYAN)
            except Exception:
                pass

            # 5. Update Activity Console Logs
            recent_logs = get_gui_logs()
            if recent_logs:
                current_text = self.log_textbox.get("1.0", "end-1c")
                current_count = len(current_text.splitlines()) if current_text else 0
                if len(recent_logs) > current_count:
                    new_lines = recent_logs[current_count:]
                    # Filter new lines
                    to_append = []
                    for line in new_lines:
                        if self._log_filter == "ALL":
                            to_append.append(line)
                        elif self._log_filter == "TICKS" and any(k in line for k in ("FeedStreamer", "tick", "Subscribed", "LTP", "Quote")):
                            to_append.append(line)
                        elif self._log_filter == "SYNC" and any(k in line for k in ("BSTSyncer", "Excel", "GoogleSheet", "sync", "Row")):
                            to_append.append(line)
                        elif self._log_filter == "ALERTS" and any(k in line for k in ("WARNING", "ERROR", "failed", "Exception", "alert")):
                            to_append.append(line)

                    if to_append:
                        self.log_textbox.insert("end", "\n".join(to_append) + "\n")
                        self.log_textbox.see("end")
        except Exception as e:
            logger.debug(f"Telemetry loop error: {e}")
        finally:
            if not self._is_closing:
                self.after(500, self._telemetry_loop)

    def _on_close_clicked(self):
        """Minimize to tray if running on Windows with active tray, or quit."""
        if sys.platform == "win32" and self.runner and self.runner.is_running and self.tray and self.tray._icon:
            self.withdraw()  # Hide window to system tray on Windows
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


def launch_gui():
    """Entry point to launch the native CustomTkinter Desktop application."""
    if not _TK_AVAILABLE:
        print("[ERROR] Tkinter is not installed on this Python build.")
        print("On macOS with Homebrew, please run: brew install python-tk@3.15")
        sys.exit(1)

    app = UpstoxBridgeApp()
    app.mainloop()
