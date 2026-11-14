"""Settings and Credential Management Dialog for Upstox Bridge Desktop App."""

from __future__ import annotations

import os
from pathlib import Path
try:
    from tkinter import filedialog, messagebox
    import customtkinter as ctk
    _TK_AVAILABLE = True
except Exception:
    _TK_AVAILABLE = False
    ctk = None

from upstox_bridge.core.config import settings, update_env_variable
from upstox_bridge.destinations.gsheet_webhook import GoogleSheetWebhookSyncer


class SettingsDialog(ctk.CTkToplevel if ctk else object):
    """Modern modal dialog for configuring credentials and workbook paths."""

    def __init__(self, parent, on_save_callback=None):
        if not _TK_AVAILABLE:
            raise RuntimeError("Tkinter/CustomTkinter is not available in this environment.")
        super().__init__(parent)
        self.parent = parent
        self.on_save_callback = on_save_callback

        self.title("Configuration & Credentials")
        self.geometry("640x540")
        self.resizable(False, False)

        # Center on parent
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        pad_x = 20

        # Title
        title_label = ctk.CTkLabel(
            self,
            text="Settings & API Credentials",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.pack(padx=pad_x, pady=(20, 10), anchor="w")

        # 1. Upstox Access Token
        token_frame = ctk.CTkFrame(self)
        token_frame.pack(fill="x", padx=pad_x, pady=8)

        token_lbl = ctk.CTkLabel(
            token_frame,
            text="Upstox Access Token (JWT):",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        token_lbl.pack(anchor="w", padx=12, pady=(8, 2))

        self.token_entry = ctk.CTkEntry(
            token_frame,
            placeholder_text="Paste your UPSTOX_ACCESS_TOKEN here...",
            show="*",
            height=34,
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
            fg_color="#334155",
            hover_color="#475569",
        )
        self.show_token_btn.pack(side="left", padx=(0, 8))

        paste_btn = ctk.CTkButton(
            token_btn_row,
            text="Paste from Clipboard",
            width=140,
            height=26,
            command=self._paste_token,
            fg_color="#0284c7",
            hover_color="#0369a1",
        )
        paste_btn.pack(side="left")

        # 2. Excel Workbook File Path
        excel_frame = ctk.CTkFrame(self)
        excel_frame.pack(fill="x", padx=pad_x, pady=8)

        excel_lbl = ctk.CTkLabel(
            excel_frame,
            text="Target Excel Workbook & Sheet:",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        excel_lbl.pack(anchor="w", padx=12, pady=(8, 4))

        excel_row = ctk.CTkFrame(excel_frame, fg_color="transparent")
        excel_row.pack(fill="x", padx=12, pady=(0, 4))

        self.excel_path_entry = ctk.CTkEntry(excel_row, height=32)
        self.excel_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.excel_path_entry.insert(0, str(settings.excel_file_path))

        browse_btn = ctk.CTkButton(
            excel_row,
            text="Browse...",
            width=80,
            height=32,
            command=self._browse_excel,
        )
        browse_btn.pack(side="right")

        sheet_row = ctk.CTkFrame(excel_frame, fg_color="transparent")
        sheet_row.pack(fill="x", padx=12, pady=(0, 8))

        sheet_lbl = ctk.CTkLabel(sheet_row, text="Target Sheet Name:")
        sheet_lbl.pack(side="left", padx=(0, 8))

        self.sheet_entry = ctk.CTkEntry(sheet_row, width=120, height=28)
        self.sheet_entry.pack(side="left")
        self.sheet_entry.insert(0, settings.excel_sheet_name)

        # 3. Google Sheets Webhook URL
        gsheet_frame = ctk.CTkFrame(self)
        gsheet_frame.pack(fill="x", padx=pad_x, pady=8)

        gsheet_lbl = ctk.CTkLabel(
            gsheet_frame,
            text="Google Sheets Webhook URL (Optional):",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        gsheet_lbl.pack(anchor="w", padx=12, pady=(8, 4))

        gsheet_row = ctk.CTkFrame(gsheet_frame, fg_color="transparent")
        gsheet_row.pack(fill="x", padx=12, pady=(0, 8))

        self.gsheet_entry = ctk.CTkEntry(
            gsheet_row,
            placeholder_text="https://script.google.com/macros/s/.../exec",
            height=32,
        )
        self.gsheet_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        current_gsheet = settings.gsheet_webhook_url
        if current_gsheet:
            self.gsheet_entry.insert(0, current_gsheet)

        test_btn = ctk.CTkButton(
            gsheet_row,
            text="Test Hook",
            width=90,
            height=32,
            command=self._test_gsheet,
            fg_color="#475569",
            hover_color="#64748b",
        )
        test_btn.pack(side="right")

        # Bottom Action Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=pad_x, pady=(16, 16), side="bottom")

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancel",
            width=100,
            height=36,
            fg_color="#334155",
            hover_color="#475569",
            command=self.destroy,
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_row,
            text="Save Changes",
            width=140,
            height=36,
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self._save_settings,
        )
        save_btn.pack(side="right")

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

    def _save_settings(self):
        token_val = self.token_entry.get().strip()
        gsheet_val = self.gsheet_entry.get().strip()
        excel_path_val = self.excel_path_entry.get().strip()
        sheet_val = self.sheet_entry.get().strip()

        env_path = settings.root_dir / ".env"

        # Update environment variables
        update_env_variable("UPSTOX_ACCESS_TOKEN", token_val, env_path)
        update_env_variable("GOOGLE_SHEET_WEBHOOK_URL", gsheet_val, env_path)

        os.environ["UPSTOX_ACCESS_TOKEN"] = token_val
        os.environ["GOOGLE_SHEET_WEBHOOK_URL"] = gsheet_val

        # Update runtime settings
        settings.config.setdefault("excel", {})["file_path"] = excel_path_val
        settings.config.setdefault("excel", {})["sheet_name"] = sheet_val

        if self.on_save_callback:
            self.on_save_callback()

        messagebox.showinfo("Saved", "Settings successfully saved to .env and applied!", parent=self)
        self.destroy()
