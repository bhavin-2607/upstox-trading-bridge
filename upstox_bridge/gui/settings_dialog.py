"""Settings and Credential Management Dialog for Upstox Bridge Desktop App."""

from __future__ import annotations

import os
import sys
from pathlib import Path
try:
    from tkinter import filedialog, messagebox
    import customtkinter as ctk
    _TK_AVAILABLE = True
except Exception:
    _TK_AVAILABLE = False
    ctk = None

from upstox_bridge.core.config import get_asset_path, settings, update_env_variable
from upstox_bridge.destinations.gsheet_webhook import GoogleSheetWebhookSyncer
from upstox_bridge.gui.debug_console import is_debug_console_active, set_debug_console
from upstox_bridge.gui.icons import IconManager


class SettingsDialog(ctk.CTkToplevel if ctk else object):
    """Modern modal dialog for configuring credentials and workbook paths."""

    def __init__(self, parent, on_save_callback=None):
        if not _TK_AVAILABLE:
            raise RuntimeError("Tkinter/CustomTkinter is not available in this environment.")
        super().__init__(parent)
        self.parent = parent
        self.on_save_callback = on_save_callback

        self.title("BSA Trading Bridge — Settings & Credentials")
        self.geometry("660x720")
        self.minsize(580, 520)
        self.resizable(True, True)

        # Apply Pure Dark Black OLED canvas styling
        self.configure(fg_color="#000000")

        # Set dialog icon using resolved asset path
        icon_ico = get_asset_path("app_icon.ico")
        icon_png = get_asset_path("app_icon.png")
        if sys.platform == "win32" and icon_ico.exists():
            try:
                self.iconbitmap(default=str(icon_ico))
            except Exception:
                pass
        elif icon_png.exists():
            try:
                from PIL import ImageTk
                self._icon_photo = ImageTk.PhotoImage(file=str(icon_png))
                self.wm_iconphoto(True, self._icon_photo)
            except Exception:
                pass

        # Center on parent
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _windows_set_titlebar_icon(self):
        """Override CustomTkinter's default so it never sets CustomTkinter_icon_Windows.ico."""
        pass

    def _build_ui(self):
        pad_x = 20

        # 1. FIXED BOTTOM ACTION BAR (Packed first with side="bottom" so it is ALWAYS 100% visible)
        footer_frame = ctk.CTkFrame(self, fg_color="#0A0B0E", border_color="#1E2026", border_width=1, corner_radius=0, height=64)
        footer_frame.pack(side="bottom", fill="x")
        footer_frame.pack_propagate(False)

        btn_row = ctk.CTkFrame(footer_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=pad_x, pady=14)

        cancel_btn = ctk.CTkButton(
            btn_row,
            text=" Cancel",
            image=IconManager.get_icon("clear", size=(13, 13)),
            compound="left",
            width=100,
            height=36,
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color="#A1A1AA",
            command=self.destroy,
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_row,
            text=" Save Changes",
            image=IconManager.get_icon("play", size=(13, 13)),
            compound="left",
            width=140,
            height=36,
            fg_color="#08B6DE",
            hover_color="#0693b3",
            text_color="#FFFFFF",
            command=self._save_settings,
        )
        save_btn.pack(side="right")

        # 2. SCROLLABLE FORM CONTAINER (fills everything above the fixed bottom bar)
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=pad_x, pady=(12, 0))

        # Title
        title_label = ctk.CTkLabel(
            scroll,
            text="Settings & API Credentials",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#FFFFFF",
        )
        title_label.pack(padx=0, pady=(4, 6), anchor="w")

        # Official Brand Endorsement Card
        endorse_frame = ctk.CTkFrame(scroll, fg_color="#0B1933", border_color="#1687E8", border_width=1, corner_radius=10)
        endorse_frame.pack(fill="x", padx=0, pady=(0, 10))

        endorse_inner = ctk.CTkFrame(endorse_frame, fg_color="transparent")
        endorse_inner.pack(fill="x", padx=12, pady=8)

        ba_logo = IconManager.get_icon("ba_monogram", size=(28, 28))
        if ba_logo:
            ba_lbl = ctk.CTkLabel(endorse_inner, text="", image=ba_logo)
            ba_lbl.pack(side="left", padx=(0, 10))

        txt_col = ctk.CTkFrame(endorse_inner, fg_color="transparent")
        txt_col.pack(side="left")

        ctk.CTkLabel(
            txt_col,
            text="AN INDEPENDENT PRODUCT BY BHAVIN AMESARA",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F7FAFC",
        ).pack(anchor="w")

        ctk.CTkLabel(
            txt_col,
            text="BSA Trading Bridge  •  Engine Build 2.0.0",
            font=ctk.CTkFont(size=10),
            text_color="#A9B8CC",
        ).pack(anchor="w")

        # 1. Upstox Access Token
        token_frame = ctk.CTkFrame(scroll, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=10)
        token_frame.pack(fill="x", padx=0, pady=8)

        token_lbl = ctk.CTkLabel(
            token_frame,
            text="Upstox Access Token (JWT):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        )
        token_lbl.pack(anchor="w", padx=12, pady=(8, 2))

        self.token_entry = ctk.CTkEntry(
            token_frame,
            placeholder_text="Paste your UPSTOX_ACCESS_TOKEN here...",
            show="*",
            height=34,
            fg_color="#08080A",
            border_color="#27272A",
            text_color="#FFFFFF",
        )
        self.token_entry.pack(fill="x", padx=12, pady=(0, 6))
        current_token = settings.upstox_access_token
        if current_token:
            self.token_entry.insert(0, current_token)

        # Paste & Show button row
        token_btn_row = ctk.CTkFrame(token_frame, fg_color="transparent")
        token_btn_row.pack(fill="x", padx=12, pady=(0, 8))

        self.show_token_btn = ctk.CTkButton(
            token_btn_row,
            text="Show Token",
            width=90,
            height=26,
            command=self._toggle_show_token,
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color="#A1A1AA",
        )
        self.show_token_btn.pack(side="left", padx=(0, 8))

        paste_btn = ctk.CTkButton(
            token_btn_row,
            text=" Paste Token",
            image=IconManager.get_icon("token", size=(13, 13)),
            compound="left",
            width=140,
            height=26,
            command=self._paste_token,
            fg_color="#08B6DE",
            hover_color="#0693b3",
            text_color="#FFFFFF",
        )
        paste_btn.pack(side="left")

        # 2. Excel Workbook File Path
        excel_frame = ctk.CTkFrame(scroll, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=10)
        excel_frame.pack(fill="x", padx=0, pady=8)

        excel_lbl = ctk.CTkLabel(
            excel_frame,
            text="Target Excel Workbook & Sheet:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        )
        excel_lbl.pack(anchor="w", padx=12, pady=(8, 4))

        excel_row = ctk.CTkFrame(excel_frame, fg_color="transparent")
        excel_row.pack(fill="x", padx=12, pady=(0, 4))

        self.excel_path_entry = ctk.CTkEntry(
            excel_row, height=32, fg_color="#08080A", border_color="#27272A", text_color="#FFFFFF"
        )
        self.excel_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.excel_path_entry.insert(0, str(settings.excel_file_path))

        browse_btn = ctk.CTkButton(
            excel_row,
            text=" Browse...",
            image=IconManager.get_icon("excel", size=(13, 13)),
            compound="left",
            width=95,
            height=32,
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color="#A1A1AA",
            command=self._browse_excel,
        )
        browse_btn.pack(side="right")

        sheet_row = ctk.CTkFrame(excel_frame, fg_color="transparent")
        sheet_row.pack(fill="x", padx=12, pady=(0, 8))

        sheet_lbl = ctk.CTkLabel(sheet_row, text="Target Sheet Name:", text_color="#A1A1AA")
        sheet_lbl.pack(side="left", padx=(0, 8))

        self.sheet_entry = ctk.CTkEntry(
            sheet_row, width=120, height=28, fg_color="#08080A", border_color="#27272A", text_color="#FFFFFF"
        )
        self.sheet_entry.pack(side="left")
        self.sheet_entry.insert(0, settings.excel_sheet_name)

        # 3. Google Sheets Webhook URL
        gsheet_frame = ctk.CTkFrame(scroll, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=10)
        gsheet_frame.pack(fill="x", padx=0, pady=8)

        gsheet_lbl = ctk.CTkLabel(
            gsheet_frame,
            text="Google Sheets Webhook URL (Optional):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        )
        gsheet_lbl.pack(anchor="w", padx=12, pady=(8, 4))

        gsheet_row = ctk.CTkFrame(gsheet_frame, fg_color="transparent")
        gsheet_row.pack(fill="x", padx=12, pady=(0, 8))

        self.gsheet_entry = ctk.CTkEntry(
            gsheet_row,
            placeholder_text="https://script.google.com/macros/s/.../exec",
            height=32,
            fg_color="#08080A",
            border_color="#27272A",
            text_color="#FFFFFF",
        )
        self.gsheet_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        current_gsheet = settings.gsheet_webhook_url
        if current_gsheet:
            self.gsheet_entry.insert(0, current_gsheet)

        test_btn = ctk.CTkButton(
            gsheet_row,
            text=" Test Hook",
            image=IconManager.get_icon("feed", size=(13, 13)),
            compound="left",
            width=100,
            height=32,
            command=self._test_gsheet,
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color="#A1A1AA",
        )
        test_btn.pack(side="right")

        restore_row = ctk.CTkFrame(gsheet_frame, fg_color="transparent")
        restore_row.pack(fill="x", padx=12, pady=(0, 6))

        restore_btn = ctk.CTkButton(
            restore_row,
            text=" Restore BST Template to Google Sheet",
            image=IconManager.get_icon("save", size=(13, 13)),
            compound="left",
            height=30,
            command=self._restore_gsheet_bst,
            fg_color="#18181B",
            hover_color="#27272A",
            border_color="#3F3F46",
            border_width=1,
            text_color="#F4F4F5",
        )
        restore_btn.pack(fill="x")

        mode_row = ctk.CTkFrame(gsheet_frame, fg_color="transparent")
        mode_row.pack(fill="x", padx=12, pady=(0, 10))

        self.formula_mask_var = ctk.BooleanVar(value=(settings.gsheet_publish_mode == "values"))
        self.formula_mask_checkbox = ctk.CTkCheckBox(
            mode_row,
            text="Mask Formulas (Values-Only / Safe for Public View-Only Sharing)",
            variable=self.formula_mask_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#F4F4F5",
            fg_color="#3B82F6",
            hover_color="#2563EB",
        )
        self.formula_mask_checkbox.pack(anchor="w")

        mask_desc = ctk.CTkLabel(
            mode_row,
            text="Checked: Hides proprietary trading formulas. Excel computes signals locally and publishes evaluated values to Google Sheets.\nUnchecked: Publishes live raw prices (LTP, Open, High, Low, Vol) directly into the sheet with live sheet formulas.",
            font=ctk.CTkFont(size=11),
            text_color="#94A3B8",
            wraplength=480,
            justify="left",
        )
        mask_desc.pack(anchor="w", padx=(28, 0), pady=(2, 0))

        # 4. Audio Alerts & Bell Chimes
        sound_frame = ctk.CTkFrame(scroll, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=10)
        sound_frame.pack(fill="x", padx=0, pady=8)

        sound_row = ctk.CTkFrame(sound_frame, fg_color="transparent")
        sound_row.pack(fill="x", padx=12, pady=10)

        sound_info_col = ctk.CTkFrame(sound_row, fg_color="transparent")
        sound_info_col.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            sound_info_col,
            text="Audio Bell & Chime Alerts:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w")

        ctk.CTkLabel(
            sound_info_col,
            text="Play audio bells on target hit, approaching warnings, and connection status",
            font=ctk.CTkFont(size=11),
            text_color="#94A3B8",
        ).pack(anchor="w")

        self.sound_switch_var = ctk.BooleanVar(value=settings.sound_enabled)
        self.sound_switch = ctk.CTkSwitch(
            sound_row,
            text="Enabled" if settings.sound_enabled else "Muted",
            variable=self.sound_switch_var,
            command=self._on_sound_switch_toggled,
            font=ctk.CTkFont(size=12, weight="bold"),
            progress_color="#08B6DE",
        )
        self.sound_switch.pack(side="right")

        # Sound Theme Selector Row
        sound_theme_row = ctk.CTkFrame(sound_frame, fg_color="transparent")
        sound_theme_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(
            sound_theme_row,
            text="Bell Sound Style:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94A3B8",
        ).pack(side="left", padx=(0, 8))

        theme_labels = ["Exchange Bell (BSE/NYSE)", "TradingView Chime", "Cash Register"]
        self.settings_theme_combo = ctk.CTkComboBox(
            sound_theme_row,
            values=theme_labels,
            height=28,
            width=230,
            fg_color="#08080A",
            border_color="#27272A",
            text_color="#FFFFFF",
        )
        cur_theme = settings.sound_theme
        def_label = "Exchange Bell (BSE/NYSE)"
        if "tradingview" in cur_theme:
            def_label = "TradingView Chime"
        elif "cash" in cur_theme:
            def_label = "Cash Register"
        self.settings_theme_combo.set(def_label)
        self.settings_theme_combo.pack(side="left")

        # 5. Debug Console Option (Windows)
        debug_frame = ctk.CTkFrame(scroll, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=10)
        debug_frame.pack(fill="x", padx=0, pady=8)

        debug_row = ctk.CTkFrame(debug_frame, fg_color="transparent")
        debug_row.pack(fill="x", padx=12, pady=10)

        debug_info_col = ctk.CTkFrame(debug_row, fg_color="transparent")
        debug_info_col.pack(side="left", fill="x", expand=True)

        debug_lbl = ctk.CTkLabel(
            debug_info_col,
            text="Debug Terminal Window:",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        debug_lbl.pack(anchor="w")

        debug_sub = ctk.CTkLabel(
            debug_info_col,
            text="Show live background command prompt window (Windows only)",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
        )
        debug_sub.pack(anchor="w")

        self.debug_switch = ctk.CTkSwitch(
            debug_row,
            text="Enabled" if is_debug_console_active() else "Hidden",
            command=self._on_debug_switch_toggled,
        )
        self.debug_switch.pack(side="right")
        if is_debug_console_active():
            self.debug_switch.select()
        else:
            self.debug_switch.deselect()

    def _toggle_show_token(self):
        if self.token_entry.cget("show") == "*":
            self.token_entry.configure(show="")
            self.show_token_btn.configure(text="Hide Token")
        else:
            self.token_entry.configure(show="*")
            self.show_token_btn.configure(text="Show Token")

    def _paste_token(self):
        try:
            clipboard = self.clipboard_get().strip()
            if clipboard:
                self.token_entry.delete(0, "end")
                self.token_entry.insert(0, clipboard)
        except Exception:
            pass

    def _browse_excel(self):
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Select Excel Trading Workbook",
            filetypes=[("Excel Files", "*.xlsx;*.xls"), ("All Files", "*.*")],
        )
        if chosen:
            self.excel_path_entry.delete(0, "end")
            self.excel_path_entry.insert(0, chosen)

    def _test_gsheet(self):
        url = self.gsheet_entry.get().strip()
        if not url:
            messagebox.showwarning("Empty URL", "Please enter a Google Apps Script Webhook URL to test.", parent=self)
            return

        syncer = GoogleSheetWebhookSyncer(
            market_store=None,
            webhook_url=url,
            sheet_name=self.sheet_entry.get().strip() or "BST",
        )
        res = syncer.test_connection()
        if res.get("success"):
            messagebox.showinfo("Success", res.get("message", "Google Sheet connection successful!"), parent=self)
        else:
            messagebox.showerror("Connection Failed", res.get("error", "Failed to connect to Google Sheet."), parent=self)

    def _restore_gsheet_bst(self):
        url = self.gsheet_entry.get().strip()
        if not url:
            messagebox.showwarning("Empty URL", "Please enter a Google Apps Script Webhook URL first.", parent=self)
            return

        excel_path = self.excel_path_entry.get().strip()
        sheet_name = self.sheet_entry.get().strip() or "BST"
        is_masked = self.formula_mask_var.get()
        mode_str = "values" if is_masked else "formulas"
        mode_label = "Values-Only (Formulas Hidden for Viewers)" if is_masked else "Live Formulas (Logic Exposed)"

        confirm = messagebox.askyesno(
            "Restore Google Sheet BST",
            f"This will restore the '{sheet_name}' sheet in your Google Sheet with all 230+ scripts and headers directly from:\n{excel_path}\n\nMode: {mode_label}\n\nAny corrupted or missing cells will be cleanly restored.\n\nDo you want to proceed?",
            parent=self,
        )
        if not confirm:
            return

        syncer = GoogleSheetWebhookSyncer(
            market_store=None,
            webhook_url=url,
            sheet_name=sheet_name,
            publish_mode=mode_str,
        )
        res = syncer.restore_bst_template(excel_path=excel_path)
        if res.get("success"):
            messagebox.showinfo(
                "Restoration Complete",
                res.get("message", f"BST sheet '{sheet_name}' successfully restored in Google Sheets!"),
                parent=self,
            )
        else:
            messagebox.showerror(
                "Restoration Failed",
                res.get("error", "Failed to restore BST template to Google Sheet."),
                parent=self,
            )

    def _on_sound_switch_toggled(self):
        is_on = bool(self.sound_switch_var.get())
        self.sound_switch.configure(text="Enabled" if is_on else "Muted")

    def _on_debug_switch_toggled(self):
        is_on = bool(self.debug_switch.get())
        self.debug_switch.configure(text="Enabled" if is_on else "Hidden")
        set_debug_console(is_on)

    def _save_settings(self):
        token_val = self.token_entry.get().strip()
        gsheet_val = self.gsheet_entry.get().strip()
        excel_path_val = self.excel_path_entry.get().strip()
        sheet_val = self.sheet_entry.get().strip()
        publish_mode = "values" if self.formula_mask_var.get() else "formulas"
        sound_val = "1" if self.sound_switch_var.get() else "0"

        chosen_theme_label = self.settings_theme_combo.get().lower()
        if "tradingview" in chosen_theme_label:
            theme_val = "tradingview"
        elif "cash" in chosen_theme_label or "register" in chosen_theme_label:
            theme_val = "cash_register"
        else:
            theme_val = "exchange_bell"

        env_path = settings.root_dir / ".env"

        # Update environment variables
        update_env_variable("UPSTOX_ACCESS_TOKEN", token_val, env_path)
        update_env_variable("GOOGLE_SHEET_WEBHOOK_URL", gsheet_val, env_path)
        update_env_variable("GSHEET_PUBLISH_MODE", publish_mode, env_path)
        update_env_variable("SOUND_ENABLED", sound_val, env_path)
        update_env_variable("SOUND_THEME", theme_val, env_path)

        os.environ["UPSTOX_ACCESS_TOKEN"] = token_val
        os.environ["GOOGLE_SHEET_WEBHOOK_URL"] = gsheet_val
        os.environ["GSHEET_PUBLISH_MODE"] = publish_mode
        os.environ["SOUND_ENABLED"] = sound_val
        os.environ["SOUND_THEME"] = theme_val

        # Update runtime settings
        settings.config.setdefault("excel", {})["file_path"] = excel_path_val
        settings.config.setdefault("excel", {})["sheet_name"] = sheet_val
        settings.config.setdefault("sound", {})["enabled"] = (sound_val == "1")
        settings.config.setdefault("sound", {})["theme"] = theme_val

        if self.on_save_callback:
            self.on_save_callback()

        messagebox.showinfo("Saved", "Settings successfully saved to .env and applied!", parent=self)
        self.destroy()
