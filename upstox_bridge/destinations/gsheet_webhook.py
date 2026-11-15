"""Zero-GCP Google Sheets Syncer using Apps Script Webhook."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import requests

from upstox_bridge.core.config import settings
from upstox_bridge.core.market_store import MarketStore

logger = logging.getLogger("GoogleSheetSyncer")


class GoogleSheetWebhookSyncer:
    """
    Synchronizes live market quotes to Google Sheets via standard HTTP POST to Apps Script Webhook.
    Supports both standard LiveMarket tables and in-place BST sheet updates (zero formula damage).
    """

    def __init__(
        self,
        market_store: MarketStore,
        webhook_url: Optional[str] = None,
        sheet_name: Optional[str] = None,
        refresh_sec: Optional[float] = None,
        mode: str = "standard",
        bst_syncer: Optional[Any] = None,
        on_gsheet_scripts_detected: Optional[Callable[[List[Tuple[int, str]]], None]] = None,
    ):
        self.market_store = market_store
        self.webhook_url = webhook_url if webhook_url is not None else settings.gsheet_webhook_url
        self.sheet_name = sheet_name or settings.gsheet_sheet_name
        self.refresh_sec = refresh_sec if refresh_sec is not None else settings.gsheet_refresh_sec
        self.mode = mode
        self.bst_syncer = bst_syncer
        self.on_gsheet_scripts_detected = on_gsheet_scripts_detected

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_sync_time: float = 0.0
        self._sync_count: int = 0
        self._error_count: int = 0
        self._last_sent_a: Optional[List[List[str]]] = None
        self._last_sent_yz: Optional[List[List[float]]] = None

    def start(self) -> None:
        """Start background sync thread."""
        if not self.webhook_url:
            logger.info("Google Sheets sync disabled (no webhook URL provided).")
            return

        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="GSheetSyncWorker", daemon=True)
        self._thread.start()
        logger.info(f"Google Sheet syncer started (Mode: {self.mode}, Interval: {self.refresh_sec}s).")

    def stop(self) -> None:
        """Stop background sync thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Google Sheet syncer stopped.")

    def sync_once(self) -> bool:
        """Perform a single synchronous push to Google Sheets."""
        if not self.webhook_url:
            raise ValueError("GOOGLE_SHEET_WEBHOOK_URL is not configured in .env")

        if self.mode == "bst" and self.bst_syncer:
            return self._sync_bst_mode()
        else:
            return self._sync_standard_mode()

    def _sync_bst_mode(self) -> bool:
        """In-place slice update to Google Sheets BST sheet."""
        row_map = self.bst_syncer._row_map if self.bst_syncer else {}
        if not row_map:
            return True

        min_row = min(row_map.keys())
        max_row = max(row_map.keys())

        a_data: List[List[str]] = []
        cg_data: List[List[float]] = []
        yz_data: List[List[float]] = []
        vol_data: List[List[int]] = []

        for r in range(min_row, max_row + 1):
            if r in row_map:
                key, clean_sym = row_map[r]
                a_data.append([clean_sym])
                item = self.market_store.get_quote_item(key)
                if item:
                    ltp = round(item.ltp, 2) if item.ltp else 0.0
                    open_p = round(item.open, 2) if item.open else 0.0
                    high_p = round(item.high, 2) if item.high else 0.0
                    low_p = round(item.low, 2) if item.low else 0.0
                    close_p = round(item.close, 2) if item.close else 0.0
                    cg_data.append([ltp, open_p, high_p, low_p, close_p])
                    yz_data.append([
                        round(item.prev_high, 2) if item.prev_high else 0.0,
                        round(item.prev_low, 2) if item.prev_low else 0.0,
                    ])
                    vol_data.append([int(item.volume)])
                else:
                    cg_data.append([0.0, 0.0, 0.0, 0.0, 0.0])
                    yz_data.append([0.0, 0.0])
                    vol_data.append([0])
            else:
                a_data.append([""])
                cg_data.append([0.0, 0.0, 0.0, 0.0, 0.0])
                yz_data.append([0.0, 0.0])
                vol_data.append([0])

        payload: Dict[str, Any] = {
            "mode": "bst",
            "sheet_name": self.sheet_name,
            "start_row": min_row,
            "cg_data": cg_data,
            "vol_data": vol_data,
        }

        # Send script names in Column A on initial cycles (first 3), every 30 cycles (~90s), or when list changes
        if self._sync_count < 3 or (self._sync_count % 30 == 0) or a_data != self._last_sent_a:
            payload["a_data"] = a_data

        # Send previous day high/low on first 3 cycles or when data changes
        if (self._sync_count < 3 or yz_data != self._last_sent_yz) and any(any(v > 0 for v in row) for row in yz_data):
            payload["yz_data"] = yz_data

        # Request script list from Google Sheet every 3rd cycle (~9s) to reduce Apps Script execution time
        if self._sync_count % 3 == 0:
            payload["sync_scripts"] = True

        return self._send_payload(payload, len(cg_data))

    def _sync_standard_mode(self) -> bool:
        """Standard full-table sync to Google Sheets."""
        matrix = self.market_store.get_snapshot_matrix(include_headers=True)
        if len(matrix) <= 1:
            return True

        payload = {
            "mode": "standard",
            "sheet_name": self.sheet_name,
            "data": matrix,
        }

        return self._send_payload(payload, len(matrix) - 1)

    def _send_payload(self, payload: dict, count: int) -> bool:
        start_t = time.time()
        resp = requests.post(
            self.webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15.0,
            allow_redirects=True,
        )
        latency_ms = (time.time() - start_t) * 1000

        if resp.status_code == 200:
            self._last_sync_time = time.time()
            self._sync_count += 1
            if "a_data" in payload:
                self._last_sent_a = [row[:] for row in payload["a_data"]]
            if "yz_data" in payload:
                self._last_sent_yz = [row[:] for row in payload["yz_data"]]
            logger.debug(f"Google Sheet updated ({count} rows) in {latency_ms:.0f}ms.")

            # Bidirectional sync: Parse scripts returned from Google Sheets
            if self.mode == "bst" and self.on_gsheet_scripts_detected:
                try:
                    res_json = resp.json()
                    scripts_raw = res_json.get("scripts", [])
                    if scripts_raw:
                        scripts = [(int(item[0]), str(item[1])) for item in scripts_raw if len(item) >= 2]
                        self.on_gsheet_scripts_detected(scripts)
                except Exception as e:
                    logger.debug(f"Could not parse scripts from Google Sheet response: {e}")

            return True
        else:
            self._error_count += 1
            logger.warning(f"Google Sheet sync HTTP {resp.status_code}: {resp.text[:200]}")
            return False

    def _run_loop(self) -> None:
        """Main loop pushing batched data at configured intervals."""
        while self._running:
            try:
                self.sync_once()
            except Exception as e:
                self._error_count += 1
                logger.warning(f"Error updating Google Sheet: {e}")

            time.sleep(self.refresh_sec)

    def test_connection(self) -> dict:
        """Test the Webhook connection safely with zero sheet writes or formula modification."""
        if not self.webhook_url:
            return {
                "success": False,
                "error": "GOOGLE_SHEET_WEBHOOK_URL is empty in .env. Please configure it first.",
            }

        try:
            resp = requests.post(
                self.webhook_url,
                json={"mode": "ping", "sheet_name": self.sheet_name},
                headers={"Content-Type": "application/json"},
                timeout=10.0,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                if "Script function not found" in resp.text:
                    return {
                        "success": False,
                        "status_code": 200,
                        "error": "Google Apps Script returned: 'Script function not found: doPost'. In the Apps Script editor, make sure you pasted the code from scripts/google_apps_script.js, click Save (Cmd+S), then click Deploy -> Manage Deployments -> Edit (pencil icon) -> select 'New version' -> click Deploy.",
                    }
                try:
                    res_json = resp.json()
                    if res_json.get("status") == "error":
                        return {
                            "success": False,
                            "error": f"Apps Script error: {res_json.get('error')}",
                        }
                except Exception:
                    pass

                return {
                    "success": True,
                    "status_code": resp.status_code,
                    "response": resp.text[:300],
                    "message": "Google Sheet Webhook responded successfully! Verified with zero sheet writes.",
                }
            else:
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Connection failed: {str(e)}",
            }

    def restore_bst_template(self, excel_path: Optional[str | Path] = None) -> dict:
        """
        Extract Row 1 headers, Row 2 headers, Column A scripts, and column formulas
        from the local Excel workbook (trial.xlsx / bst.xlsx) and upload them to Google Sheets
        to cleanly initialize or restore the BST trading sheet.
        """
        import openpyxl

        if not self.webhook_url:
            return {
                "success": False,
                "error": "GOOGLE_SHEET_WEBHOOK_URL is empty. Please configure it in Settings first.",
            }

        file_path = Path(excel_path) if excel_path else (
            getattr(self.bst_syncer, "file_path", None) or settings.excel_file_path
        )
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            return {
                "success": False,
                "error": f"Excel workbook not found at: {file_path}",
            }

        try:
            wb = openpyxl.load_workbook(file_path, data_only=False)
            target_sheet = self.sheet_name if self.sheet_name in wb.sheetnames else "BST"
            if target_sheet not in wb.sheetnames:
                target_sheet = wb.sheetnames[0]
            ws = wb[target_sheet]

            max_col = min(ws.max_column or 50, 50)
            if max_col < 30:
                max_col = 50

            r1 = [ws.cell(1, c).value or "" for c in range(1, max_col + 1)]
            r2 = [ws.cell(2, c).value or "" for c in range(1, max_col + 1)]

            rows: List[List[Any]] = []
            for r in range(3, ws.max_row + 1):
                sym = ws.cell(r, 1).value
                if not sym and not ws.cell(r, 2).value:
                    continue
                row_vals: List[Any] = []
                for c in range(1, max_col + 1):
                    val = ws.cell(r, c).value
                    if val is None:
                        row_vals.append("")
                    elif str(val).startswith("="):
                        # Clean Excel dummy function wrapper for Google Sheets formulas
                        clean_f = re.sub(r'__XLUDF\.DUMMYFUNCTION\("([^"]+)"\)', r"\1", str(val))
                        row_vals.append(clean_f)
                    else:
                        row_vals.append(val)
                rows.append(row_vals)

            wb.close()

            payload: Dict[str, Any] = {
                "mode": "init_bst",
                "sheet_name": self.sheet_name,
                "headers_row1": r1,
                "headers_row2": r2,
                "rows": rows,
            }

            logger.info(f"Uploading BST template to Google Sheets '{self.sheet_name}' ({len(rows)} rows, {max_col} cols)...")
            resp = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=45.0,
                allow_redirects=True,
            )

            if resp.status_code == 200:
                try:
                    res_json = resp.json()
                    if res_json.get("status") == "error":
                        return {"success": False, "error": f"Apps Script error: {res_json.get('error')}"}
                except Exception:
                    pass

                # Reset cache so next live sync reliably detects and refreshes
                self._last_sent_a = None
                self._last_sent_yz = None

                return {
                    "success": True,
                    "rows_restored": len(rows),
                    "message": f"Successfully restored '{self.sheet_name}' on Google Sheets with {len(rows)} scripts, headers, and formulas!",
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:250]}",
                }
        except Exception as e:
            logger.error(f"Error restoring BST template to Google Sheet: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Restoration failed: {str(e)}",
            }
