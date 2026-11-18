"""Custom Price Alerts and Audio Alert Manager Dialog."""

from __future__ import annotations

import os
import sys
from typing import Any, List, Optional
try:
    from tkinter import messagebox
    import customtkinter as ctk
    _TK_AVAILABLE = True
except Exception:
    _TK_AVAILABLE = False
    ctk = None

from upstox_bridge.core.alert_engine import AlertCondition, AlertStatus, PriceAlert, alert_engine
from upstox_bridge.core.config import get_asset_path, settings, update_env_variable
from upstox_bridge.core.market_store import MarketStore
from upstox_bridge.core.sound_engine import SoundEvent, SoundTheme, sound_engine
from upstox_bridge.gui.icons import IconManager


class AlertsDialog(ctk.CTkToplevel if ctk else object):
    """Modern modal dialog for creating and monitoring custom target price alerts."""

    def __init__(self, parent, market_store: Optional[MarketStore] = None):
        if not _TK_AVAILABLE:
            raise RuntimeError("Tkinter/CustomTkinter is not available in this environment.")
        super().__init__(parent)
        self.parent = parent
        self.market_store = market_store

        self.title("Price Alerts & Bell Sound Manager")
        self.geometry("700x700")
        self.minsize(620, 520)
        self.resizable(True, True)

        self.configure(fg_color="#000000")

        # Set dialog icon
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

        self.transient(parent)
        self.grab_set()

        self._refresh_timer_id: Optional[str] = None
        self._build_ui()
        self._start_live_refresh()

    def _windows_set_titlebar_icon(self):
        """Override CustomTkinter default icon behavior on Windows."""
        pass

    def _build_ui(self):
        pad_x = 20

        # 1. FIXED BOTTOM ACTION BAR
        footer = ctk.CTkFrame(self, fg_color="#0A0B0E", border_color="#1E2026", border_width=1, corner_radius=0, height=60)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        footer_row = ctk.CTkFrame(footer, fg_color="transparent")
        footer_row.pack(fill="x", padx=pad_x, pady=12)

        self.lbl_active_summary = ctk.CTkLabel(
            footer_row,
            text=f"Active Alerts: {alert_engine.get_active_count()}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#08B6DE",
        )
        self.lbl_active_summary.pack(side="left")

        close_btn = ctk.CTkButton(
            footer_row,
            text=" Close",
            image=IconManager.get_icon("clear", size=(13, 13)),
            compound="left",
            width=100,
            height=34,
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color="#A1A1AA",
            command=self._on_close,
        )
        close_btn.pack(side="right")

        # 2. SCROLLABLE CONTENT AREA
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=pad_x, pady=(12, 0))

        # Title Row with Sound Controls
        header_row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 10))

        title_col = ctk.CTkFrame(header_row, fg_color="transparent")
        title_col.pack(side="left")

        ctk.CTkLabel(
            title_col,
            text="Price Alerts & Sound Chimes",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_col,
            text="Custom target price alerts with approaching warnings and target hit bell sounds.",
            font=ctk.CTkFont(size=11),
            text_color="#94A3B8",
        ).pack(anchor="w")

        # Top Audio Controls Card
        audio_card = ctk.CTkFrame(self.scroll, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=10)
        audio_card.pack(fill="x", pady=(0, 12))

        audio_row = ctk.CTkFrame(audio_card, fg_color="transparent")
        audio_row.pack(fill="x", padx=12, pady=(10, 6))

        # Mute Switch
        self.sound_switch_var = ctk.BooleanVar(value=settings.sound_enabled)
        self.sound_switch = ctk.CTkSwitch(
            audio_row,
            text="Audio Alerts: Enabled" if settings.sound_enabled else "Audio Alerts: Muted",
            variable=self.sound_switch_var,
            command=self._on_sound_switch_toggled,
            font=ctk.CTkFont(size=12, weight="bold"),
            progress_color="#08B6DE",
        )
        self.sound_switch.pack(side="left")

        # Test Chimes buttons
        test_hit_btn = ctk.CTkButton(
            audio_row,
            text=" Test Bell 🔔",
            width=110,
            height=28,
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color="#F4F4F5",
            command=lambda: sound_engine.play(SoundEvent.TARGET_HIT, cooldown_sec=0.0),
        )
        test_hit_btn.pack(side="right", padx=(6, 0))

        test_appr_btn = ctk.CTkButton(
            audio_row,
            text=" Test Warning ⚠️",
            width=120,
            height=28,
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color="#E2E8F0",
            command=lambda: sound_engine.play(SoundEvent.APPROACHING, cooldown_sec=0.0),
        )
        test_appr_btn.pack(side="right")

        # Sound Theme Selector Row
        theme_row = ctk.CTkFrame(audio_card, fg_color="transparent")
        theme_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(
            theme_row,
            text="Bell Sound Style:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94A3B8",
        ).pack(side="left", padx=(0, 8))

        self._available_themes = sound_engine.get_available_bell_themes()
        theme_options = [label for label, _ in self._available_themes]
        current_theme_key = settings.sound_theme
        default_label = theme_options[0] if theme_options else "Exchange Bell (BSE/NYSE)"
        for label, key in self._available_themes:
            if key == current_theme_key:
                default_label = label
                break

        self.theme_combo = ctk.CTkComboBox(
            theme_row,
            values=theme_options,
            command=self._on_theme_changed,
            height=28,
            width=230,
            fg_color="#08080A",
            border_color="#27272A",
            text_color="#FFFFFF",
        )
        self.theme_combo.set(default_label)
        self.theme_combo.pack(side="left")

        open_folder_btn = ctk.CTkButton(
            theme_row,
            text=" 📁 Add / View Sounds",
            width=140,
            height=28,
            fg_color="#16171B",
            hover_color="#23252E",
            border_color="#27272A",
            border_width=1,
            text_color="#94A3B8",
            command=self._open_sounds_folder,
        )
        open_folder_btn.pack(side="left", padx=(8, 0))

        # 3. ADD NEW ALERT FORM CARD
        form_card = ctk.CTkFrame(self.scroll, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=10)
        form_card.pack(fill="x", pady=(0, 14))

        form_title_row = ctk.CTkFrame(form_card, fg_color="transparent")
        form_title_row.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            form_title_row,
            text="CREATE CUSTOM PRICE ALERT",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#08B6DE",
        ).pack(side="left")

        self.lbl_live_ltp = ctk.CTkLabel(
            form_title_row,
            text="Live LTP: --",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94A3B8",
        )
        self.lbl_live_ltp.pack(side="right")

        form_fields_row = ctk.CTkFrame(form_card, fg_color="transparent")
        form_fields_row.pack(fill="x", padx=14, pady=(0, 12))

        # Symbol Input
        sym_col = ctk.CTkFrame(form_fields_row, fg_color="transparent")
        sym_col.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(sym_col, text="Symbol:", font=ctk.CTkFont(size=11), text_color="#A1A1AA").pack(anchor="w")

        available_symbols = self._get_available_symbols()
        self.entry_symbol = ctk.CTkComboBox(
            sym_col,
            values=available_symbols if available_symbols else ["NIFTY 50", "RELIANCE", "CRUDEOIL"],
            height=32,
            fg_color="#08080A",
            border_color="#27272A",
            text_color="#FFFFFF",
            command=self._on_symbol_changed,
        )
        self.entry_symbol.pack(fill="x", pady=(2, 0))
        if available_symbols:
            self.entry_symbol.set(available_symbols[0])

        # Target Price Input
        tgt_col = ctk.CTkFrame(form_fields_row, fg_color="transparent")
        tgt_col.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(tgt_col, text="Target Price (₹):", font=ctk.CTkFont(size=11), text_color="#A1A1AA").pack(anchor="w")
        self.entry_target = ctk.CTkEntry(
            tgt_col,
            placeholder_text="0.00",
            width=110,
            height=32,
            fg_color="#08080A",
            border_color="#27272A",
            text_color="#FFFFFF",
        )
        self.entry_target.pack(pady=(2, 0))

        # Condition Selector (Above >= / Below <=)
        cond_col = ctk.CTkFrame(form_fields_row, fg_color="transparent")
        cond_col.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(cond_col, text="Condition:", font=ctk.CTkFont(size=11), text_color="#A1A1AA").pack(anchor="w")
        self.cond_var = ctk.StringVar(value="Above (>=)")
        self.seg_cond = ctk.CTkSegmentedButton(
            cond_col,
            values=["Above (>=)", "Below (<=)"],
            variable=self.cond_var,
            height=32,
            selected_color="#08B6DE",
            selected_hover_color="#0693b3",
        )
        self.seg_cond.pack(pady=(2, 0))

        # Buffer % Input
        buf_col = ctk.CTkFrame(form_fields_row, fg_color="transparent")
        buf_col.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(buf_col, text="Buffer (%):", font=ctk.CTkFont(size=11), text_color="#A1A1AA").pack(anchor="w")
        self.entry_buffer = ctk.CTkEntry(
            buf_col,
            width=70,
            height=32,
            fg_color="#08080A",
            border_color="#27272A",
            text_color="#FFFFFF",
        )
        self.entry_buffer.pack(pady=(2, 0))
        self.entry_buffer.insert(0, str(settings.alert_proximity_pct))

        # Add Button
        add_col = ctk.CTkFrame(form_fields_row, fg_color="transparent")
        add_col.pack(side="left", pady=(18, 0))
        self.btn_add = ctk.CTkButton(
            add_col,
            text=" Add Alert",
            image=IconManager.get_icon("add", size=(13, 13)),
            compound="left",
            width=100,
            height=32,
            fg_color="#08B6DE",
            hover_color="#0693b3",
            text_color="#FFFFFF",
            command=self._on_add_alert,
        )
        self.btn_add.pack()

        # 4. ACTIVE ALERTS LIST SECTION
        list_header = ctk.CTkFrame(self.scroll, fg_color="transparent")
        list_header.pack(fill="x", pady=(4, 6))

        ctk.CTkLabel(
            list_header,
            text="ACTIVE & TRIGGERED ALERTS",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left")

        # Container for alert cards
        self.alerts_list_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.alerts_list_frame.pack(fill="x")

        self._render_alerts_list()
        self._on_symbol_changed(self.entry_symbol.get())

    def _get_available_symbols(self) -> List[str]:
        """Fetch list of all active symbols registered in the bridge."""
        if self.market_store:
            matrix = self.market_store.get_snapshot_matrix(include_headers=False)
            symbols = [str(row[0]).strip().upper() for row in matrix if row and row[0]]
            if symbols:
                return sorted(list(set(symbols)))
        return []

    def _get_live_ltp(self, symbol: str) -> Optional[float]:
        """Fetch current LTP from market store."""
        if not self.market_store or not symbol:
            return None
        upper = symbol.strip().upper()
        item = self.market_store.get_quote_by_symbol(upper)
        if not item:
            return None

        # MarketStore.get_quote_by_symbol returns a dictionary
        if isinstance(item, dict):
            raw_ltp = item.get("ltp") or item.get("close") or item.get("prev_close")
        else:
            raw_ltp = getattr(item, "ltp", None) or getattr(item, "close", None) or getattr(item, "prev_close", None)

        try:
            if raw_ltp is not None:
                val = float(raw_ltp)
                if val > 0:
                    return val
        except (ValueError, TypeError):
            pass
        return None

    def _on_symbol_changed(self, choice: str) -> None:
        """Update live LTP label when symbol selection changes."""
        ltp = self._get_live_ltp(choice)
        if ltp is not None:
            self.lbl_live_ltp.configure(text=f"Live LTP: ₹{ltp:.2f}", text_color="#10B981")
            # If target entry is empty, auto-populate with rounded current LTP
            current_target = self.entry_target.get().strip()
            if not current_target:
                self.entry_target.insert(0, f"{ltp:.2f}")
        else:
            self.lbl_live_ltp.configure(text="Live LTP: --", text_color="#94A3B8")

    def _on_add_alert(self) -> None:
        """Validate input and register new alert."""
        sym = self.entry_symbol.get().strip().upper()
        if not sym:
            messagebox.showwarning("Missing Symbol", "Please specify a trading symbol.", parent=self)
            return

        tgt_str = self.entry_target.get().strip()
        try:
            target_val = float(tgt_str)
            if target_val <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Target", "Target price must be a valid positive number.", parent=self)
            return

        buf_str = self.entry_buffer.get().strip()
        try:
            buf_val = float(buf_str)
            if buf_val <= 0:
                buf_val = 0.25
        except ValueError:
            buf_val = 0.25

        cond = AlertCondition.ABOVE if "Above" in self.cond_var.get() else AlertCondition.BELOW

        alert = alert_engine.add_alert(
            symbol=sym,
            target_price=target_val,
            condition=cond,
            proximity_pct=buf_val,
        )

        # Clear target field for next entry
        self.entry_target.delete(0, "end")
        self._render_alerts_list()
        self.lbl_active_summary.configure(text=f"Active Alerts: {alert_engine.get_active_count()}")

    def _render_alerts_list(self) -> None:
        """Render the list of alert cards."""
        for widget in self.alerts_list_frame.winfo_children():
            widget.destroy()

        alerts = alert_engine.get_alerts()
        if not alerts:
            empty_frame = ctk.CTkFrame(self.alerts_list_frame, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=10)
            empty_frame.pack(fill="x", pady=4)
            ctk.CTkLabel(
                empty_frame,
                text="No custom alerts configured. Enter a symbol and target price above to monitor.",
                font=ctk.CTkFont(size=12),
                text_color="#64748B",
            ).pack(pady=24)
            return

        # Sort: Triggered last, Active/Approaching first
        sorted_alerts = sorted(alerts, key=lambda a: (1 if a.status == AlertStatus.TRIGGERED else 0, a.symbol))

        for alert in sorted_alerts:
            self._create_alert_card(alert)

    def _create_alert_card(self, alert: PriceAlert) -> None:
        """Create a single alert display card."""
        is_triggered = (alert.status == AlertStatus.TRIGGERED)
        is_approaching = (alert.status == AlertStatus.APPROACHING)

        border_col = "#10B981" if is_triggered else ("#F59E0B" if is_approaching else "#1E2026")
        card = ctk.CTkFrame(self.alerts_list_frame, fg_color="#101114", border_color=border_col, border_width=1, corner_radius=8)
        card.pack(fill="x", pady=4)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)

        # Symbol & Condition badge
        left_box = ctk.CTkFrame(row, fg_color="transparent")
        left_box.pack(side="left")

        sym_lbl = ctk.CTkLabel(left_box, text=alert.symbol, font=ctk.CTkFont(size=13, weight="bold"), text_color="#FFFFFF")
        sym_lbl.pack(side="left", padx=(0, 8))

        cond_text = f">= ₹{alert.target_price:.2f}" if alert.condition == AlertCondition.ABOVE else f"<= ₹{alert.target_price:.2f}"
        cond_col = "#10B981" if alert.condition == AlertCondition.ABOVE else "#EF4444"
        cond_badge = ctk.CTkLabel(
            left_box,
            text=cond_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=cond_col,
            fg_color="#18181B",
            corner_radius=4,
            padx=6,
            pady=2,
        )
        cond_badge.pack(side="left", padx=(0, 8))

        # Live LTP & Distance %
        ltp = self._get_live_ltp(alert.symbol) or alert.last_ltp
        if ltp:
            dist = abs(ltp - alert.target_price) / alert.target_price * 100
            diff = ltp - alert.target_price
            diff_str = f"+₹{diff:.2f}" if diff >= 0 else f"-₹{abs(diff):.2f}"
            price_text = f"Live: ₹{ltp:.2f} ({diff_str} | {dist:.2f}%)"
        else:
            price_text = "Live: --"

        price_lbl = ctk.CTkLabel(left_box, text=price_text, font=ctk.CTkFont(size=11), text_color="#94A3B8")
        price_lbl.pack(side="left", padx=(0, 8))

        # Right Action Buttons & Status Pill
        right_box = ctk.CTkFrame(row, fg_color="transparent")
        right_box.pack(side="right")

        # Status badge
        status_text = "BELL HIT 🔔" if is_triggered else ("APPROACHING ⚠️" if is_approaching else "ACTIVE")
        status_col = "#10B981" if is_triggered else ("#F59E0B" if is_approaching else "#08B6DE")
        status_badge = ctk.CTkLabel(
            right_box,
            text=status_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=status_col,
            fg_color="#18181B",
            corner_radius=4,
            padx=6,
            pady=2,
        )
        status_badge.pack(side="left", padx=(0, 8))

        # Reset button if triggered
        if is_triggered:
            rearm_btn = ctk.CTkButton(
                right_box,
                text="Re-Arm",
                width=65,
                height=26,
                fg_color="#1E293B",
                hover_color="#334155",
                text_color="#F8FAFC",
                command=lambda aid=alert.id: self._on_rearm_alert(aid),
            )
            rearm_btn.pack(side="left", padx=(0, 6))

        # Delete button
        del_btn = ctk.CTkButton(
            right_box,
            text="Delete",
            width=60,
            height=26,
            fg_color="#27272A",
            hover_color="#DC2626",
            text_color="#F4F4F5",
            command=lambda aid=alert.id: self._on_delete_alert(aid),
        )
        del_btn.pack(side="left")

    def _on_rearm_alert(self, alert_id: str) -> None:
        """Re-arm an alert."""
        alert_engine.reset_alert(alert_id)
        self._render_alerts_list()
        self.lbl_active_summary.configure(text=f"Active Alerts: {alert_engine.get_active_count()}")

    def _on_delete_alert(self, alert_id: str) -> None:
        """Delete an alert."""
        alert_engine.remove_alert(alert_id)
        self._render_alerts_list()
        self.lbl_active_summary.configure(text=f"Active Alerts: {alert_engine.get_active_count()}")

    def _on_sound_switch_toggled(self) -> None:
        """Handle master sound toggle switch."""
        is_on = bool(self.sound_switch_var.get())
        self.sound_switch.configure(text="Audio Alerts: Enabled" if is_on else "Audio Alerts: Muted")
        val = "1" if is_on else "0"
        os.environ["SOUND_ENABLED"] = val
        settings.config.setdefault("sound", {})["enabled"] = is_on
        env_path = settings.root_dir / ".env"
        update_env_variable("SOUND_ENABLED", val, env_path)

    def _open_sounds_folder(self) -> None:
        """Open assets/sounds/ in system file manager and refresh choices."""
        path = sound_engine.sounds_dir
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(path)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass
        self.after(1000, self._refresh_themes)

    def _refresh_themes(self) -> None:
        """Refresh theme options if user dropped new WAV files."""
        self._available_themes = sound_engine.get_available_bell_themes()
        labels = [l for l, _ in self._available_themes]
        self.theme_combo.configure(values=labels)

    def _on_theme_changed(self, choice: str) -> None:
        """Handle sound theme change and audition sound."""
        theme_key = "exchange_bell"
        for label, key in getattr(self, "_available_themes", []):
            if label == choice:
                theme_key = key
                break

        settings.sound_theme = theme_key
        env_path = settings.root_dir / ".env"
        update_env_variable("SOUND_THEME", theme_key, env_path)
        # Audition immediately
        sound_engine.play(SoundEvent.TARGET_HIT, cooldown_sec=0.0, theme=theme_key)

    def _start_live_refresh(self) -> None:
        """Periodically update distance and status in the dialog."""
        def _refresh():
            if not self.winfo_exists():
                return
            try:
                # Update header summary
                active_count = alert_engine.get_active_count()
                self.lbl_active_summary.configure(text=f"Active Alerts: {active_count}")
                # Refresh cards
                self._render_alerts_list()
            except Exception:
                pass
            self._refresh_timer_id = self.after(1500, _refresh)

        self._refresh_timer_id = self.after(1500, _refresh)

    def _on_close(self) -> None:
        """Cleanly cancel timer and close modal."""
        if self._refresh_timer_id:
            try:
                self.after_cancel(self._refresh_timer_id)
            except Exception:
                pass
        self.destroy()
