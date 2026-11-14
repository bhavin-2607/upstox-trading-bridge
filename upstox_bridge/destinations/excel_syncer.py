"""Universal Local Excel Syncer supporting xlwings (Mac & Windows) and openpyxl atomic fallback (Linux & Headless)."""

from __future__ import annotations

import logging
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional
import openpyxl

from upstox_bridge.core.config import settings
from upstox_bridge.core.market_store import MarketStore

logger = logging.getLogger("ExcelSyncer")


class ExcelSyncer:
    """Synchronizes real-time market quotes to local Excel on the user's machine."""

    def __init__(
        self,
        market_store: MarketStore,
        file_path: Optional[Path] = None,
        sheet_name: Optional[str] = None,
        refresh_sec: Optional[float] = None,
        on_watchlist_change: Optional[Callable[[List[str]], None]] = None,
    ):
        self.market_store = market_store
        self.file_path = file_path or settings.excel_file_path
        self.sheet_name = sheet_name or settings.excel_sheet_name
        self.refresh_sec = refresh_sec if refresh_sec is not None else settings.excel_refresh_sec
        self.on_watchlist_change = on_watchlist_change

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_watchlist: List[str] = []
        self._previous_row_count: int = 0
        self._use_xlwings = False
        self._xw_book = None
        self._xw_sheet = None
        self._xw_app = None

    def _ensure_workbook_exists(self) -> None:
        """Ensure destination Excel file exists; build automatically if missing."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            from templates.create_template import generate_styled_template
            generate_styled_template(self.file_path)
            logger.info(f"Automatically created pre-styled live workbook at: {self.file_path}")

    def _connect_xlwings(self) -> bool:
        """Attempt to connect to Microsoft Excel via xlwings (Mac & Windows)."""
        try:
            import xlwings as xw

            self._ensure_workbook_exists()
            target_str = str(self.file_path.resolve())
            filename = self.file_path.name

            target_book = None
            # 1. Try attaching to already open workbook by filename
            try:
                target_book = xw.Book(filename)
                self._xw_app = target_book.app
            except Exception:
                pass

            # 2. Try attaching by full path
            if not target_book:
                try:
                    target_book = xw.Book(target_str)
                    self._xw_app = target_book.app
                except Exception:
                    pass

            # 3. If not already open, launch Excel and open file
            if not target_book:
                self._xw_app = xw.App(visible=True)
                target_book = self._xw_app.books.open(target_str)

            self._xw_book = target_book

            # Get or create LiveMarket sheet
            sheet_names = [s.name for s in target_book.sheets]
            if self.sheet_name not in sheet_names:
                self._xw_sheet = target_book.sheets.add(self.sheet_name, before=target_book.sheets[0])
            else:
                self._xw_sheet = target_book.sheets[self.sheet_name]

            logger.info("Successfully connected to active Microsoft Excel application via xlwings.")
            return True
        except Exception as e:
            logger.warning(f"Could not connect via xlwings (using atomic file mode): {e}")
            return False

    def start(self) -> None:
        """Start Excel sync background loop."""
        if not settings.excel_enabled:
            return

        self._ensure_workbook_exists()

        # Check if xlwings is supported and requested
        if settings.excel_mode in ("auto", "xlwings") and sys.platform in ("darwin", "win32"):
            self._use_xlwings = self._connect_xlwings()
        else:
            self._use_xlwings = False

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="ExcelSyncWorker", daemon=True)
        self._thread.start()
        logger.info(f"Excel syncer running (Engine: {'xlwings' if self._use_xlwings else 'openpyxl'}, Interval: {self.refresh_sec}s).")

    def stop(self) -> None:
        """Stop Excel sync background loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Excel syncer stopped.")

    def sync_once(self) -> None:
        """Perform a single update of the Excel sheet."""
        matrix = self.market_store.get_snapshot_matrix(include_headers=True)
        if len(matrix) <= 1:
            return

        if self._use_xlwings and self._xw_sheet:
            try:
                # If rows shrank, clear trailing old rows
                if self._previous_row_count > len(matrix):
                    self._xw_sheet.range(f"A{len(matrix)+1}:K{self._previous_row_count+10}").clear_contents()

                # High-speed batch matrix write
                self._xw_sheet.range("A1").value = matrix
                self._previous_row_count = len(matrix)
            except Exception as e:
                logger.warning(f"xlwings write error, reconnecting: {e}")
                self._use_xlwings = self._connect_xlwings()
        else:
            self._write_atomic_openpyxl(matrix)

    def _write_atomic_openpyxl(self, matrix: List[List[Any]]) -> None:
        """Atomic write using openpyxl (writing to temp file and replacing)."""
        temp_file = self.file_path.with_suffix(".tmp.xlsx")
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = self.sheet_name

            for row in matrix:
                ws.append(row)

            # Preserve or write Watchlist sheet
            ws_watch = wb.create_sheet(title="Watchlist")
            ws_watch.append(["Trading Symbol"])
            for sym in settings.watchlist_symbols:
                ws_watch.append([sym])

            wb.save(temp_file)
            temp_file.replace(self.file_path)
        except Exception as e:
            logger.debug(f"Atomic openpyxl write error: {e}")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def check_excel_watchlist(self) -> List[str]:
        """Read trading symbols from the Watchlist tab in Excel if available."""
        if not self._use_xlwings or not self._xw_book:
            return []

        try:
            sheets = [s.name.lower() for s in self._xw_book.sheets]
            if "watchlist" not in sheets:
                return []

            watch_sheet = self._xw_book.sheets["Watchlist"]
            # Read column A from row 2 down to last non-empty row
            vals = watch_sheet.range("A2:A100").value
            if not vals:
                return []

            symbols = [str(v).strip().upper() for v in vals if v and str(v).strip()]
            return symbols
        except Exception:
            return []

    def _run_loop(self) -> None:
        """Background synchronization loop."""
        if sys.platform == "win32":
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

        if self._use_xlwings and sys.platform == "win32":
            self._connect_xlwings()

        counter = 0
        try:
            while self._running:
                try:
                    self.sync_once()

                    # Every ~10 iterations, check for watchlist updates in Excel
                    counter += 1
                    if counter % 10 == 0 and settings.sync_watchlist_from_excel:
                        new_symbols = self.check_excel_watchlist()
                        if new_symbols and new_symbols != self._last_watchlist:
                            self._last_watchlist = list(new_symbols)
                            if self.on_watchlist_change:
                                self.on_watchlist_change(new_symbols)

                except Exception as e:
                    logger.debug(f"Excel sync loop error: {e}")

                time.sleep(self.refresh_sec)
        finally:
            if sys.platform == "win32":
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
