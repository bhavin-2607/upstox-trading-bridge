"""Zero-GCP Google Sheets Syncer using Apps Script Webhook."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional
import requests

from upstox_bridge.core.config import settings
from upstox_bridge.core.market_store import MarketStore

logger = logging.getLogger("GoogleSheetSyncer")


class GoogleSheetWebhookSyncer:
    """Synchronizes live market quotes to Google Sheets via standard HTTP POST to Apps Script Webhook."""

    def __init__(
        self,
        market_store: MarketStore,
        webhook_url: Optional[str] = None,
        sheet_name: Optional[str] = None,
        refresh_sec: Optional[float] = None,
    ):
        self.market_store = market_store
        self.webhook_url = webhook_url if webhook_url is not None else settings.gsheet_webhook_url
        self.sheet_name = sheet_name or settings.gsheet_sheet_name
        self.refresh_sec = refresh_sec if refresh_sec is not None else settings.gsheet_refresh_sec

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_sync_time: float = 0.0
        self._sync_count: int = 0
        self._error_count: int = 0

    def start(self) -> None:
        """Start background sync thread."""
        if not self.webhook_url:
            logger.warning("GOOGLE_SHEET_WEBHOOK_URL is not set. Google Sheets sync is disabled.")
            return

        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="GSheetSyncWorker", daemon=True)
        self._thread.start()
        logger.info(f"Google Sheet syncer started (Interval: {self.refresh_sec}s).")

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

        matrix = self.market_store.get_snapshot_matrix(include_headers=True)
        if len(matrix) <= 1:
            # Only headers, no data yet
            return True

        payload = {
            "sheet_name": self.sheet_name,
            "data": matrix,
        }

        start_t = time.time()
        resp = requests.post(
            self.webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=8.0,
            allow_redirects=True,  # Google Apps Script redirects with 302 to output
        )
        latency_ms = (time.time() - start_t) * 1000

        if resp.status_code == 200:
            self._last_sync_time = time.time()
            self._sync_count += 1
            logger.debug(f"Google Sheet updated ({len(matrix)-1} symbols) in {latency_ms:.0f}ms.")
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
        """Test the Webhook connection and return diagnosis."""
        if not self.webhook_url:
            return {
                "success": False,
                "error": "GOOGLE_SHEET_WEBHOOK_URL is empty in .env. Please configure it first.",
            }

        try:
            sample_data = [
                MarketStore.HEADERS,
                ["TEST_NIFTY", "NSE_INDEX|Nifty 50", 24000.0, 100.0, "+0.42%", 23900.0, 24050.0, 23850.0, 23900.0, 100000, "TEST"],
            ]
            resp = requests.post(
                self.webhook_url,
                json={"sheet_name": self.sheet_name, "data": sample_data},
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
                    "message": "Google Sheet Webhook responded successfully! Live row written.",
                }
            else:
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": resp.text,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
