"""Core orchestration runner for Upstox Live Market Data Bridge."""

from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path
from typing import List, Optional

from upstox_bridge.auth.oauth import UpstoxAuthManager
from upstox_bridge.auth.totp_login import attempt_totp_login
from upstox_bridge.core.config import settings
from upstox_bridge.core.market_store import MarketStore
from upstox_bridge.destinations.bst_syncer import BSTSyncer
from upstox_bridge.destinations.excel_syncer import ExcelSyncer
from upstox_bridge.destinations.gsheet_webhook import GoogleSheetWebhookSyncer
from upstox_bridge.destinations.local_feed_server import LocalFeedServer
from upstox_bridge.feed.streamer import UpstoxFeedStreamer
from upstox_bridge.instruments.historical import HistoricalStatsFetcher
from upstox_bridge.instruments.master import InstrumentMaster

logger = logging.getLogger("BridgeRunner")


class BridgeRunner:
    """Coordinates authentication, feed streaming, and live synchronization to destinations."""

    def __init__(
        self,
        custom_file: Optional[Path] = None,
        custom_sheet: Optional[str] = None,
    ):
        self.market_store = MarketStore()
        self.instrument_master = InstrumentMaster()
        self.auth_manager = UpstoxAuthManager()
        self.historical_fetcher = HistoricalStatsFetcher()

        self.excel_file = (custom_file or settings.excel_file_path).resolve()
        self.sheet_name = custom_sheet or settings.excel_sheet_name

        self.is_bst_mode = self._detect_bst_mode()

        self.streamer: Optional[UpstoxFeedStreamer] = None
        self.excel_syncer: Optional[ExcelSyncer] = None
        self.bst_syncer: Optional[BSTSyncer] = None
        self.gsheet_syncer: Optional[GoogleSheetWebhookSyncer] = None
        self.local_server: Optional[LocalFeedServer] = None

        self._running = False
        self._last_txt_mtime: float = 0.0

    def _detect_bst_mode(self) -> bool:
        """Detect if target sheet is a BST / trading template (with SCRIPT column) vs standard table."""
        if self.sheet_name.upper() == "BST":
            return True
        if self.excel_file.name.lower() == "trial.xlsx":
            return True

        if self.excel_file.exists():
            try:
                import openpyxl
                wb = openpyxl.load_workbook(self.excel_file, read_only=True)
                if self.sheet_name in wb.sheetnames:
                    ws = wb[self.sheet_name]
                    v1 = str(ws.cell(1, 1).value or "").upper()
                    v2 = str(ws.cell(2, 1).value or "").upper()
                    wb.close()
                    if "SCRIPT" in v1 or "SCRIPT" in v2:
                        return True
                wb.close()
            except Exception:
                pass
        return False

    def initialize_instruments(self, symbol_list: Optional[List[str]] = None) -> List[str]:
        """Resolve human symbols to instrument keys and register them in store."""
        symbols = symbol_list or settings.watchlist_symbols
        if not symbols:
            symbols = ["NIFTY 50", "NIFTY BANK", "RELIANCE"]

        logger.info(f"Resolving {len(symbols)} symbols from watchlist...")
        resolved_keys: List[str] = []

        pairs = []
        for sym in symbols:
            key = self.instrument_master.resolve_symbol(sym)
            pairs.append((key, sym))
            resolved_keys.append(key)
            logger.info(f"  -> {sym:12} => {key}")

        self.market_store.sync_watchlist(pairs)
        return resolved_keys

    def on_bst_scripts_detected(self, all_keys: List[str]) -> None:
        """Callback when BST syncer detects new or updated scripts in Column A."""
        logger.info(f"BST sheet script change detected! Tracking {len(all_keys)} instruments.")

        # Fetch previous day stats for any newly added keys
        stats = self.historical_fetcher.fetch_all(all_keys)
        for key, (ph, pl, pc) in stats.items():
            self.market_store.update_prev_day_stats(key, prev_high=ph, prev_low=pl, prev_close=pc)

        if self.streamer and self.streamer.is_connected:
            current_keys = set(self.streamer.subscribed_keys)
            to_add = [k for k in all_keys if k not in current_keys]
            if to_add:
                self.streamer.subscribe(to_add)
                logger.info(f"Dynamically subscribed to {len(to_add)} newly added keys from BST sheet.")

    def on_gsheet_scripts_received(self, gsheet_scripts: List[tuple[int, str]]) -> None:
        """Callback when Google Sheet webhook returns current scripts from Column A (Bidirectional Sync)."""
        if not self.is_bst_mode or not self.bst_syncer:
            return

        new_keys = self.bst_syncer.inject_scripts_from_external(gsheet_scripts)
        if new_keys:
            logger.info(f"[Google Sheets -> Excel] Discovered {len(new_keys)} new symbol(s) added from Google Sheet: {new_keys}")
            stats = self.historical_fetcher.fetch_all(new_keys)
            for key, (ph, pl, pc) in stats.items():
                self.market_store.update_prev_day_stats(key, prev_high=ph, prev_low=pl, prev_close=pc)

            if self.streamer and self.streamer.is_connected:
                self.streamer.subscribe(new_keys)

    def reload_from_watchlist_txt(self) -> None:
        """Dynamically reload symbols from watchlist.txt when user edits the file."""
        new_symbols = settings.read_watchlist_txt()
        if not new_symbols:
            return

        logger.info(f"Detected change in watchlist.txt! Syncing {len(new_symbols)} symbols...")
        pairs = []
        new_keys = []
        for sym in new_symbols:
            key = self.instrument_master.resolve_symbol(sym)
            pairs.append((key, sym))
            new_keys.append(key)

        self.market_store.sync_watchlist(pairs)

        if self.streamer and self.streamer.is_connected:
            current_keys = set(self.streamer.subscribed_keys)
            to_add = [k for k in new_keys if k not in current_keys]
            to_remove = [k for k in current_keys if k not in new_keys]

            if to_remove:
                self.streamer.unsubscribe(to_remove)
            if to_add:
                self.streamer.subscribe(to_add)

        print(f"\n[Watchlist Live Updated from watchlist.txt] Active symbols ({len(new_symbols)}): {', '.join(new_symbols)}")

    def on_excel_watchlist_updated(self, new_symbols: List[str]) -> None:
        """Callback when user edits symbols in Excel 'Watchlist' sheet (Standard mode)."""
        if not new_symbols:
            return

        new_keys: List[str] = []
        for sym in new_symbols:
            key = self.instrument_master.resolve_symbol(sym)
            self.market_store.register_instrument(instrument_key=key, symbol=sym)
            new_keys.append(key)

        if self.streamer and self.streamer.is_connected:
            self.streamer.subscribe(new_keys)
            logger.info(f"Dynamically subscribed to {len(new_keys)} symbols from Excel.")

    def start(self, interactive_login_if_needed: bool = True) -> None:
        """Start the live market data bridge."""
        self._running = True

        print("=" * 65)
        print(" UPSTOX LIVE MARKET DATA BRIDGE (Excel & Google Sheets) ")
        print("=" * 65)

        # 1. Determine Instruments
        if self.is_bst_mode:
            print(f"[*] Mode: BST Custom Trading Sheet ({self.excel_file.name} -> '{self.sheet_name}')")
            print("[*] Reading instruments directly from SCRIPT column (Col A)...")
            self.bst_syncer = BSTSyncer(
                market_store=self.market_store,
                file_path=self.excel_file,
                sheet_name=self.sheet_name,
                refresh_sec=settings.excel_refresh_sec,
                on_scripts_detected=self.on_bst_scripts_detected,
            )
            # Scan initial scripts from sheet
            self.bst_syncer.scan_scripts()
            keys = [k for k, _ in self.bst_syncer.tracked_instruments]
            print(f"[OK] Found {len(keys)} instruments in SCRIPT column.")

            # Fetch previous day High/Low/Close for all instruments
            print("[*] Fetching previous day High/Low/Close stats...")
            stats = self.historical_fetcher.fetch_all(keys)
            for key, (ph, pl, pc) in stats.items():
                self.market_store.update_prev_day_stats(key, prev_high=ph, prev_low=pl, prev_close=pc)
            print(f"[OK] Loaded previous day stats for {len(stats)} instruments.")
        else:
            print("[*] Mode: Standard Live Watchlist Table")
            keys = self.initialize_instruments()

        # 2. Authenticate
        token = self.auth_manager.get_valid_token()
        if not token:
            # Try headless TOTP if configured
            token = attempt_totp_login()

        if not token and interactive_login_if_needed:
            print("\nNo active Upstox access token found for today.")
            token = self.auth_manager.interactive_login()

        if not token:
            raise RuntimeError(
                "Unable to obtain valid Upstox access token. Please run 'python main.py login' or check your .env"
            )

        # 3. Start Local Live Feed Server
        if settings.local_server_enabled:
            self.local_server = LocalFeedServer(self.market_store)
            self.local_server.start()

        # 4. Start Excel Syncer
        if settings.excel_enabled:
            if self.is_bst_mode:
                self.bst_syncer.start()
            else:
                self.excel_syncer = ExcelSyncer(
                    market_store=self.market_store,
                    file_path=self.excel_file,
                    sheet_name=self.sheet_name,
                    on_watchlist_change=self.on_excel_watchlist_updated,
                )
                self.excel_syncer.start()

        # 5. Start Google Sheets Syncer
        if settings.gsheet_enabled and settings.gsheet_webhook_url:
            gsheet_mode = "bst" if self.is_bst_mode else "standard"
            self.gsheet_syncer = GoogleSheetWebhookSyncer(
                market_store=self.market_store,
                mode=gsheet_mode,
                bst_syncer=self.bst_syncer,
                on_gsheet_scripts_detected=self.on_gsheet_scripts_received,
            )
            self.gsheet_syncer.start()
        elif settings.gsheet_enabled and not settings.gsheet_webhook_url:
            logger.info("Google Sheets push skipped (no webhook URL provided).")

        # 6. Start WebSocket Streamer
        self.streamer = UpstoxFeedStreamer(
            access_token=token,
            market_store=self.market_store,
            instrument_keys=keys,
            mode=settings.upstox_mode,
        )
        self.streamer.connect()

        # Setup OS signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Record initial mtime of watchlist.txt (for standard mode)
        if not self.is_bst_mode and settings.watchlist_txt_path.exists():
            self._last_txt_mtime = settings.watchlist_txt_path.stat().st_mtime

        print("\n[Bridge is LIVE and updating market data]")
        if self.is_bst_mode:
            print("Tip: You can add new ticker symbols directly into Column A of your Excel sheet anytime!")
        else:
            print("Tip: You can edit 'watchlist.txt' anytime while this is running to add/remove symbols!")
        print("Press Ctrl+C to stop.\n")

        # Keep main thread alive
        try:
            while self._running:
                time.sleep(1.0)
                if not self.is_bst_mode and settings.watchlist_txt_path.exists():
                    current_mtime = settings.watchlist_txt_path.stat().st_mtime
                    if self._last_txt_mtime and current_mtime != self._last_txt_mtime:
                        self._last_txt_mtime = current_mtime
                        self.reload_from_watchlist_txt()
                    elif not self._last_txt_mtime:
                        self._last_txt_mtime = current_mtime
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def _handle_shutdown(self, signum, frame):
        logger.info("Shutdown signal received.")
        self.stop()
        sys.exit(0)

    def stop(self) -> None:
        """Stop all background syncers and disconnect feed."""
        if not self._running:
            return
        self._running = False
        print("\nShutting down Upstox Live Bridge...")

        if self.streamer:
            self.streamer.disconnect()
        if self.excel_syncer:
            self.excel_syncer.stop()
        if self.bst_syncer:
            self.bst_syncer.stop()
        if self.gsheet_syncer:
            self.gsheet_syncer.stop()
        if self.local_server:
            self.local_server.stop()

        print("Shutdown complete.")
