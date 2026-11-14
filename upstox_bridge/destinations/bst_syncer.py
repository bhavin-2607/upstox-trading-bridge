"""Specialized In-Place Excel Syncer for trading sheets with existing formulas (e.g. BST in trial.xlsx)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
import openpyxl

from upstox_bridge.core.config import settings
from upstox_bridge.core.market_store import MarketStore, QuoteItem
from upstox_bridge.instruments.master import InstrumentMaster

logger = logging.getLogger("BSTSyncer")


class BSTSyncer:
    """
    Synchronizes real-time quotes into a custom trading workbook (like BST in trial.xlsx).
    - Reads symbols dynamically from the SCRIPT column.
    - Writes ONLY to data columns: LTP (C), OPEN (D), HIGH (E), LOW (F), P.CLOSE (G), P HIGH (Y), P. LOW (Z), vol (AF).
    - Leaves all formula columns (TREND, ENTRY, SL, TARGETS, PIVOTS, etc.) completely intact.
    """

    # Column letter to 1-based index mapping in BST sheet
    COL_SCRIPT = 1   # Col A
    COL_LTP = 3      # Col C
    COL_OPEN = 4     # Col D
    COL_HIGH = 5     # Col E
    COL_LOW = 6      # Col F
    COL_PCLOSE = 7   # Col G
    COL_PHIGH = 25   # Col Y
    COL_PLOW = 26    # Col Z
    COL_VOL = 32     # Col AF

    STATE_DISCONNECTED = "Disconnected"
    STATE_CONNECTED = "Connected"
    STATE_WAITING = "Waiting for Excel"
    STATE_EDIT_MODE = "Excel in Edit Mode"

    def __init__(
        self,
        market_store: MarketStore,
        file_path: Optional[Path] = None,
        sheet_name: str = "BST",
        refresh_sec: float = 0.5,
        start_row: int = 3,
        on_scripts_detected: Optional[Callable[[List[str]], None]] = None,
    ):
        self.market_store = market_store
        self.file_path = (file_path or Path("bst.xlsx")).resolve()
        self.sheet_name = sheet_name
        self.refresh_sec = refresh_sec
        self.start_row = start_row
        self.on_scripts_detected = on_scripts_detected
        self.instrument_master = InstrumentMaster()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._row_map: Dict[int, Tuple[str, str]] = {}  # row_idx -> (instrument_key, clean_symbol)
        self._known_scripts_raw: Dict[int, str] = {}    # row_idx -> raw_script_string
        self._last_scan_time = 0.0
        self._stats_written = False
        self._last_yz_matrix: Optional[List[List[Optional[float]]]] = None
        self._last_reconnect_attempt = 0.0

        self.status: str = self.STATE_DISCONNECTED
        self.last_sync_time: float = 0.0
        self.last_error: str = ""

        self._use_xlwings = False
        self._xw_book = None
        self._xw_sheet = None
        self._xw_app = None

    def _connect_xlwings(self) -> bool:
        """Connect to active Excel workbook via xlwings."""
        try:
            import xlwings as xw

            if not self.file_path.exists():
                logger.error(f"Target workbook not found: {self.file_path}")
                return False

            filename = self.file_path.name
            target_str = str(self.file_path)
            target_book = None

            # 1. Try finding already open workbook by filename
            try:
                target_book = xw.Book(filename)
                self._xw_app = target_book.app
            except Exception:
                pass

            # 2. Try by full path
            if not target_book:
                try:
                    target_book = xw.Book(target_str)
                    self._xw_app = target_book.app
                except Exception:
                    pass

            # 3. Launch Excel and open file if not already running
            if not target_book:
                self._xw_app = xw.App(visible=True)
                target_book = self._xw_app.books.open(target_str)

            self._xw_book = target_book

            # Find target sheet
            sheet_names = [s.name for s in target_book.sheets]
            if self.sheet_name not in sheet_names:
                logger.error(f"Sheet '{self.sheet_name}' not found in {filename}! Available: {sheet_names}")
                return False

            self._xw_sheet = target_book.sheets[self.sheet_name]
            logger.info(f"Connected to Excel via xlwings: [{filename}] Sheet: '{self.sheet_name}'")
            return True
        except Exception as e:
            logger.warning(f"Could not connect via xlwings (will use openpyxl fallback): {e}")
            return False

    def scan_scripts(self) -> List[str]:
        """
        Scan Column A (SCRIPT) starting at start_row to discover all instruments.
        Returns list of newly discovered instrument keys.
        """
        new_keys: List[str] = []
        discovered_rows: Dict[int, str] = {}

        if self._use_xlwings and self._xw_sheet:
            try:
                # Read Column A from start_row down to row 1000 in one batch
                raw_col_vals = self._xw_sheet.range(f"A{self.start_row}:A1000").value
                if isinstance(raw_col_vals, list):
                    for idx, val in enumerate(raw_col_vals):
                        row_idx = self.start_row + idx
                        if val is not None and str(val).strip():
                            discovered_rows[row_idx] = str(val).strip()
            except Exception as e:
                logger.debug(f"xlwings scan error: {e}")
        else:
            # Fallback to openpyxl
            try:
                wb = openpyxl.load_workbook(self.file_path, data_only=True)
                if self.sheet_name in wb.sheetnames:
                    ws = wb[self.sheet_name]
                    max_r = ws.max_row or 1000
                    for r in range(self.start_row, max_r + 1):
                        val = ws.cell(r, self.COL_SCRIPT).value
                        if val is not None and str(val).strip():
                            discovered_rows[r] = str(val).strip()
                wb.close()
            except Exception as e:
                logger.debug(f"openpyxl scan error: {e}")

        # Check for changes in scripts
        changed = False
        for row_idx, raw_val in discovered_rows.items():
            if self._known_scripts_raw.get(row_idx) != raw_val:
                changed = True
                self._known_scripts_raw[row_idx] = raw_val
                clean_sym = self.instrument_master.clean_script_symbol(raw_val)
                key = self.instrument_master.resolve_symbol(raw_val)
                self._row_map[row_idx] = (key, clean_sym)
                self.market_store.register_instrument(key, clean_sym)
                new_keys.append(key)

                # If raw_val had Google Finance or broker prefixes, auto-clean it in the sheet
                if clean_sym != raw_val and self._use_xlwings and self._xw_sheet:
                    try:
                        self._xw_sheet.range(f"A{row_idx}").value = clean_sym
                    except Exception:
                        pass

        # Check for deleted rows
        for old_row in list(self._row_map.keys()):
            if old_row not in discovered_rows:
                changed = True
                del self._row_map[old_row]
                self._known_scripts_raw.pop(old_row, None)

        if changed:
            self._last_yz_matrix = None

        if changed and new_keys and self.on_scripts_detected:
            all_keys = [k for k, _ in self._row_map.values()]
            self.on_scripts_detected(all_keys)

        return new_keys

    def inject_scripts_from_external(self, external_scripts: List[Tuple[int, str]]) -> List[str]:
        """
        Inject or synchronize scripts received from Google Sheets into local BST syncer & Excel.
        Returns list of newly discovered instrument keys.
        """
        new_keys: List[str] = []
        excel_updates: List[Tuple[int, str]] = []

        for row_idx, raw_val in external_scripts:
            cleaned_val = str(raw_val).strip()
            if not cleaned_val:
                continue

            if self._known_scripts_raw.get(row_idx) != cleaned_val:
                self._known_scripts_raw[row_idx] = cleaned_val
                clean_sym = self.instrument_master.clean_script_symbol(cleaned_val)
                key = self.instrument_master.resolve_symbol(cleaned_val)
                self._row_map[row_idx] = (key, clean_sym)
                self.market_store.register_instrument(key, clean_sym)
                new_keys.append(key)
                excel_updates.append((row_idx, clean_sym))

        if excel_updates:
            self._last_yz_matrix = None
            logger.info(f"Writing {len(excel_updates)} new/updated scripts from Google Sheets into local Excel...")
            if self._use_xlwings and self._xw_sheet:
                try:
                    for r, val in excel_updates:
                        self._xw_sheet.range(f"A{r}").value = val
                except Exception as e:
                    logger.debug(f"xlwings external inject error: {e}")
            else:
                try:
                    wb = openpyxl.load_workbook(self.file_path, data_only=False)
                    if self.sheet_name in wb.sheetnames:
                        ws = wb[self.sheet_name]
                        for r, val in excel_updates:
                            ws.cell(r, self.COL_SCRIPT, val)
                        wb.save(self.file_path)
                    wb.close()
                except Exception as e:
                    logger.debug(f"openpyxl external inject error: {e}")

        return new_keys

    def _sync_cycle_xlwings(self) -> None:
        """High-speed batch slice update in active Excel via xlwings."""
        if not self._row_map or not self._xw_sheet:
            return

        min_row = min(self._row_map.keys())
        max_row = max(self._row_map.keys())
        num_rows = max_row - min_row + 1

        # Prepare 2D matrix buffers
        # 1. Block C to G: [LTP, OPEN, HIGH, LOW, P.CLOSE]
        block_cg: List[List[Optional[float]]] = []
        # 2. Block Y to Z: [P HIGH, P. LOW]
        block_yz: List[List[Optional[float]]] = []
        # 3. Block AF: [vol]
        block_af: List[List[Optional[int]]] = []

        for r in range(min_row, max_row + 1):
            if r in self._row_map:
                key, _ = self._row_map[r]
                item = self.market_store.get_quote_item(key)
                if item:
                    ltp = round(item.ltp, 2) if item.ltp else 0.0
                    open_p = round(item.open, 2) if item.open else 0.0
                    high_p = round(item.high, 2) if item.high else 0.0
                    low_p = round(item.low, 2) if item.low else 0.0
                    close_p = round(item.close, 2) if item.close else 0.0
                    vol = int(item.volume)

                    block_cg.append([ltp, open_p, high_p, low_p, close_p])
                    block_af.append([vol])
                    block_yz.append([
                        round(item.prev_high, 2) if item.prev_high else None,
                        round(item.prev_low, 2) if item.prev_low else None,
                    ])
                else:
                    block_cg.append([0.0, 0.0, 0.0, 0.0, 0.0])
                    block_af.append([0])
                    block_yz.append([None, None])
            else:
                block_cg.append([None, None, None, None, None])
                block_af.append([None])
                block_yz.append([None, None])

        try:
            # 1. Update live price block C:G (5 contiguous columns)
            self._xw_sheet.range(f"C{min_row}:G{max_row}").value = block_cg

            # 2. Update live volume block AF (1 column)
            self._xw_sheet.range(f"AF{min_row}:AF{max_row}").value = block_af

            # 3. Update previous day high/low block Y:Z (written when values arrive or change)
            if block_yz != self._last_yz_matrix and any(any(v is not None and v > 0 for v in row) for row in block_yz):
                self._xw_sheet.range(f"Y{min_row}:Z{max_row}").value = block_yz
                self._last_yz_matrix = [row[:] for row in block_yz]
                self._stats_written = True

            self.status = self.STATE_CONNECTED
            self.last_sync_time = time.time()
            self.last_error = ""

        except Exception as e:
            err_msg = str(e)
            if "0x80010001" in err_msg or "rejected by callee" in err_msg:
                self.status = self.STATE_EDIT_MODE
                logger.debug("Excel is currently in cell-edit mode; buffered update will apply on next tick.")
            else:
                self.last_error = err_msg
                # If Excel was closed/disconnected, mark waiting and trigger watchdog re-connect
                if any(x in err_msg.lower() for x in ("disconnected", "cannot find", "rpc server", "failed to connect", "com_error", "object has no attribute")):
                    self.status = self.STATE_WAITING
                    now = time.time()
                    if now - self._last_reconnect_attempt > 2.0:
                        self._last_reconnect_attempt = now
                        logger.info("Excel disconnected or closed. Watchdog waiting to re-attach...")
                        if self._connect_xlwings():
                            self.status = self.STATE_CONNECTED
                            logger.info("Watchdog successfully re-attached to Excel workbook!")
                else:
                    logger.warning(f"xlwings sync cycle error: {e}")

    def _sync_cycle_openpyxl(self) -> None:
        """Atomic openpyxl fallback updating only data cells."""
        if not self._row_map or not self.file_path.exists():
            return

        try:
            wb = openpyxl.load_workbook(self.file_path, data_only=False)
            if self.sheet_name not in wb.sheetnames:
                return
            ws = wb[self.sheet_name]

            for r, (key, _) in self._row_map.items():
                item = self.market_store.get_quote_item(key)
                if not item:
                    continue

                if item.ltp:
                    ws.cell(r, self.COL_LTP, round(item.ltp, 2))
                if item.open:
                    ws.cell(r, self.COL_OPEN, round(item.open, 2))
                if item.high:
                    ws.cell(r, self.COL_HIGH, round(item.high, 2))
                if item.low:
                    ws.cell(r, self.COL_LOW, round(item.low, 2))
                if item.close:
                    ws.cell(r, self.COL_PCLOSE, round(item.close, 2))
                if item.prev_high is not None and item.prev_high > 0:
                    ws.cell(r, self.COL_PHIGH, round(item.prev_high, 2))
                if item.prev_low is not None and item.prev_low > 0:
                    ws.cell(r, self.COL_PLOW, round(item.prev_low, 2))
                if item.volume:
                    ws.cell(r, self.COL_VOL, int(item.volume))

            wb.save(self.file_path)
            wb.close()
            self.status = self.STATE_CONNECTED
            self.last_sync_time = time.time()
            self.last_error = ""
        except Exception as e:
            self.last_error = str(e)
            logger.debug(f"openpyxl sync error: {e}")

    def sync_once(self) -> None:
        """Execute a single sync iteration."""
        # Periodically scan Column A for changes in scripts
        now = time.time()
        if now - self._last_scan_time > 2.5:
            self.scan_scripts()
            self._last_scan_time = now

        if self._use_xlwings:
            self._sync_cycle_xlwings()
        else:
            self._sync_cycle_openpyxl()

    def start(self) -> None:
        """Start background sync loop."""
        if self._running:
            return

        self._use_xlwings = self._connect_xlwings()
        # Initial scan of scripts in sheet
        self.scan_scripts()

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BSTSyncerThread")
        self._thread.start()
        logger.info(f"BST Syncer started (refresh: {self.refresh_sec}s, tracked: {len(self._row_map)} rows).")

    def _run_loop(self) -> None:
        import sys
        if sys.platform == "win32":
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception as e:
                logger.debug(f"pythoncom.CoInitialize error: {e}")

        # On Windows, re-acquire COM handle in this thread so calls belong to this apartment
        if self._use_xlwings and sys.platform == "win32":
            self._connect_xlwings()

        try:
            while self._running:
                try:
                    self.sync_once()
                except Exception as e:
                    logger.warning(f"Error in BST sync loop: {e}")
                time.sleep(self.refresh_sec)
        finally:
            if sys.platform == "win32":
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def stop(self) -> None:
        """Stop background sync loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("BST Syncer stopped.")

    @property
    def tracked_instruments(self) -> List[Tuple[str, str]]:
        """Return list of (instrument_key, symbol) currently tracked."""
        return list(self._row_map.values())
