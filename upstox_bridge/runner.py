"""Core orchestration runner for Upstox Live Market Data Bridge."""

from __future__ import annotations

import logging
import random
import signal
import sys
import threading
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
        self._is_simulation = False
        self._sim_thread: Optional[threading.Thread] = None
        self._last_txt_mtime: float = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_simulation(self) -> bool:
        return self._is_simulation

    @property
    def ticks_received(self) -> int:
        if self.streamer:
            return getattr(self.streamer, "ticks_count", 0)
        return 0

    @property
    def excel_status(self) -> str:
        if self.bst_syncer:
            return getattr(self.bst_syncer, "status", "Active")
        if self.excel_syncer:
            return "Active" if getattr(self.excel_syncer, "_running", False) else "Stopped"
        return "Disabled"

    @property
    def gsheet_status(self) -> str:
        if self.gsheet_syncer and self.gsheet_syncer._running:
            return f"Active ({self.gsheet_syncer.refresh_sec}s)"
        return "Disabled"

    def _detect_bst_mode(self) -> bool:
        """Detect if target sheet is a BST / trading template (with SCRIPT column) vs standard table."""
        if self.sheet_name.upper() == "BST":
            return True
        if self.excel_file.name.lower() in ("trial.xlsx", "bst.xlsx"):
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

        if self.bst_syncer:
            self.bst_syncer._last_yz_matrix = None
        if self.gsheet_syncer:
            self.gsheet_syncer._last_sent_yz = None

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

            if self.bst_syncer:
                self.bst_syncer._last_yz_matrix = None
            if self.gsheet_syncer:
                self.gsheet_syncer._last_sent_yz = None

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

    def start_services(self, interactive_login_if_needed: bool = True) -> List[str]:
        """Initialize all destinations, resolve instruments, authenticate, and start streaming."""
        self._running = True
        self._is_simulation = False

        # 1. Determine Instruments
        if self.is_bst_mode:
            logger.info(f"Mode: BST Custom Trading Sheet ({self.excel_file.name} -> '{self.sheet_name}')")
            self.bst_syncer = BSTSyncer(
                market_store=self.market_store,
                file_path=self.excel_file,
                sheet_name=self.sheet_name,
                refresh_sec=settings.excel_refresh_sec,
                on_scripts_detected=self.on_bst_scripts_detected,
            )
            self.bst_syncer.scan_scripts()
            keys = [k for k, _ in self.bst_syncer.tracked_instruments]
            logger.info(f"Found {len(keys)} instruments in SCRIPT column.")

            # Fetch previous day High/Low/Close for all instruments
            stats = self.historical_fetcher.fetch_all(keys)
            for key, (ph, pl, pc) in stats.items():
                self.market_store.update_prev_day_stats(key, prev_high=ph, prev_low=pl, prev_close=pc)
            if self.bst_syncer:
                self.bst_syncer._last_yz_matrix = None
            if self.gsheet_syncer:
                self.gsheet_syncer._last_sent_yz = None
        else:
            logger.info("Mode: Standard Live Watchlist Table")
            keys = self.initialize_instruments()

        # 2. Authenticate
        token = self.auth_manager.get_valid_token()
        if not token:
            token = attempt_totp_login()

        if not token and interactive_login_if_needed:
            print("\nNo active Upstox access token found for today.")
            token = self.auth_manager.interactive_login()

        if not token:
            self._running = False
            raise RuntimeError(
                "Unable to obtain valid Upstox access token. Please set UPSTOX_ACCESS_TOKEN in .env or Settings."
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

        # 6. Start WebSocket Streamer
        self.streamer = UpstoxFeedStreamer(
            access_token=token,
            market_store=self.market_store,
            instrument_keys=keys,
            mode=settings.upstox_mode,
        )
        self.streamer.connect()
        return keys

    def start_simulation_services(self) -> List[str]:
        """Start all destinations in simulated tick mode for testing without active market session."""
        self._running = True
        self._is_simulation = True

        default_base = {
            "NIFTY 50": 25300.0,
            "NIFTY BANK": 61500.0,
            "RELIANCE": 1335.0,
            "TCS": 2470.0,
            "HDFCBANK": 805.0,
            "INFY": 1150.0,
            "TATAMOTORS": 298.0,
            "ICICIBANK": 1570.0,
            "SBIN": 1060.0,
            "BHARTIARTL": 2100.0,
            "GOLD DEC FUT": 138200.0,
            "SILVER DEC FUT": 181700.0,
            "CRUDEOIL NOV FUT": 8080.0,
            "GOLD NOV 120000 PE": 110.0,
        }
        base_prices = {}

        if self.is_bst_mode:
            self.bst_syncer = BSTSyncer(
                market_store=self.market_store,
                file_path=self.excel_file,
                sheet_name=self.sheet_name,
                refresh_sec=settings.excel_refresh_sec,
            )
            self.bst_syncer.scan_scripts()
            symbols = [sym for _, sym in self.bst_syncer.tracked_instruments]
            keys = [k for k, _ in self.bst_syncer.tracked_instruments]

            for sym in symbols:
                key = self.instrument_master.resolve_symbol(sym)
                p = default_base.get(sym.upper(), round(random.uniform(150, 4500), 2))
                base_prices[sym] = p
                ph = round(p * 1.015, 2)
                pl = round(p * 0.985, 2)
                pc = round(p * 0.998, 2)
                self.market_store.update_prev_day_stats(key, prev_high=ph, prev_low=pl, prev_close=pc)
                self.market_store.update_quote(
                    instrument_key=key,
                    ltp=p,
                    open_price=round(p * 0.999, 2),
                    high_price=round(p * 1.006, 2),
                    low_price=round(p * 0.994, 2),
                    close_price=pc,
                    prev_high=ph,
                    prev_low=pl,
                    vwap=round(p * 0.999, 2),
                    volume=random.randint(50000, 2500000),
                )
            if settings.excel_enabled:
                self.bst_syncer.start()
        else:
            symbols = settings.watchlist_symbols or ["NIFTY 50", "NIFTY BANK", "RELIANCE"]
            keys = []
            for sym in symbols:
                key = self.instrument_master.resolve_symbol(sym)
                self.market_store.register_instrument(instrument_key=key, symbol=sym)
                base_prices[sym] = default_base.get(sym, round(random.uniform(500, 3500), 2))
                keys.append(key)

            for sym, price in base_prices.items():
                key = self.instrument_master.resolve_symbol(sym)
                self.market_store.update_quote(
                    instrument_key=key,
                    ltp=price,
                    open_price=round(price * 0.998, 2),
                    high_price=round(price * 1.005, 2),
                    low_price=round(price * 0.995, 2),
                    close_price=round(price * 0.997, 2),
                    vwap=round(price * 0.999, 2),
                    volume=150000,
                )
            if settings.excel_enabled:
                self.excel_syncer = ExcelSyncer(
                    market_store=self.market_store,
                    file_path=self.excel_file,
                    sheet_name=self.sheet_name,
                )
                self.excel_syncer.start()

        if settings.local_server_enabled:
            self.local_server = LocalFeedServer(self.market_store)
            self.local_server.start()

        if settings.gsheet_enabled and settings.gsheet_webhook_url:
            gsheet_mode = "bst" if self.is_bst_mode else "standard"
            self.gsheet_syncer = GoogleSheetWebhookSyncer(
                market_store=self.market_store,
                mode=gsheet_mode,
                bst_syncer=self.bst_syncer,
            )
            self.gsheet_syncer.start()

        # Start background simulation tick generator thread
        self._sim_thread = threading.Thread(
            target=self._run_sim_loop, args=(symbols, base_prices), daemon=True, name="SimLoopThread"
        )
        self._sim_thread.start()
        return keys

    def _run_sim_loop(self, symbols: List[str], base_prices: dict) -> None:
        """Background simulated tick stream."""
        while self._running and self._is_simulation:
            # Pick a random subset of symbols to tick
            batch = random.sample(symbols, min(len(symbols), random.randint(3, 12)))
            for sym in batch:
                key = self.instrument_master.resolve_symbol(sym)
                current = self.market_store.get_quote_item(key)
                cur_ltp = current.ltp if current and current.ltp else base_prices.get(sym, 1000.0)

                # Realistic fractional price fluctuation
                delta_pct = random.uniform(-0.002, 0.002)
                new_ltp = round(max(0.05, cur_ltp * (1.0 + delta_pct)), 2)

                high_p = max(current.high or new_ltp, new_ltp) if current else new_ltp
                low_p = min(current.low or new_ltp, new_ltp) if current else new_ltp
                new_vol = (current.volume or 1000) + random.randint(10, 500) if current else 1000

                self.market_store.update_quote(
                    instrument_key=key,
                    ltp=new_ltp,
                    high_price=high_p,
                    low_price=low_p,
                    volume=new_vol,
                )

            time.sleep(0.3)

    def start(self, interactive_login_if_needed: bool = True) -> None:
        """Start the live market data bridge and enter blocking loop (CLI mode)."""
        print("=" * 65)
        print(" UPSTOX LIVE MARKET DATA BRIDGE (Excel & Google Sheets) ")
        print("=" * 65)

        keys = self.start_services(interactive_login_if_needed=interactive_login_if_needed)
        print(f"[OK] Live bridge started for {len(keys)} instruments.")

        # Setup OS signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        if not self.is_bst_mode and settings.watchlist_txt_path.exists():
            self._last_txt_mtime = settings.watchlist_txt_path.stat().st_mtime

        print("\n[Bridge is LIVE and updating market data]")
        if self.is_bst_mode:
            print("Tip: You can add new ticker symbols directly into Column A of your Excel sheet anytime!")
        else:
            print("Tip: You can edit 'watchlist.txt' anytime while this is running to add/remove symbols!")
        print("Press Ctrl+C to stop.\n")

        # Keep main thread alive
        loop_seconds = 0
        market_notice_shown = False
        try:
            while self._running:
                time.sleep(1.0)
                loop_seconds += 1

                # Feed health monitor
                if self.streamer:
                    ticks = self.streamer.ticks_count
                    if loop_seconds == 15 and ticks == 0 and not market_notice_shown:
                        print("[Notice] 0 live market ticks received so far.")
                        print("         If markets are currently closed (weekends, holidays, or outside 09:15-15:30 IST),")
                        print("         Upstox live feed does not broadcast new price ticks.")
                        print("         Run 'python main.py simulate --file trial.xlsx --sheet BST' to test live streaming anytime!\n")
                        market_notice_shown = True
                    elif loop_seconds % 30 == 0 and ticks > 0:
                        logger.info(f"Live feed active: {ticks} market ticks processed.")

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
        self._is_simulation = False
        logger.info("Stopping Upstox Live Bridge...")

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
        if self._sim_thread and self._sim_thread.is_alive():
            self._sim_thread.join(timeout=1.0)

        logger.info("All bridge services stopped.")
