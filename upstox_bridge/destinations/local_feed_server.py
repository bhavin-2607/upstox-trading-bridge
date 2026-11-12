"""Universal embedded HTTP Live Feed Server for cross-platform spreadsheet feeds."""

from __future__ import annotations

import csv
import io
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from threading import Thread
from typing import Optional
import urllib.parse

from upstox_bridge.core.config import settings
from upstox_bridge.core.market_store import MarketStore

logger = logging.getLogger("LocalFeedServer")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    daemon_threads = True


class LocalFeedServer:
    """Embedded zero-dependency HTTP server providing live CSV and JSON endpoints for Excel & other tools."""

    def __init__(
        self,
        market_store: MarketStore,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        self.market_store = market_store
        self.host = host or settings.local_server_host
        self.port = port or settings.local_server_port
        self._server: Optional[ThreadedHTTPServer] = None
        self._thread: Optional[Thread] = None
        self._running = False

    def start(self) -> None:
        """Start the HTTP server on configured host and port."""
        if not settings.local_server_enabled:
            return

        store = self.market_store

        class RequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress logging every tick request

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path.rstrip("/")

                if path in ("", "/health"):
                    self._send_json(200, {
                        "status": "online",
                        "symbols_count": store.count(),
                        "endpoints": ["/live.csv", "/live.json", "/quote/<symbol>"],
                    })

                elif path == "/live.json":
                    quotes = store.get_all_quotes_dict()
                    self._send_json(200, quotes)

                elif path == "/live.csv":
                    matrix = store.get_snapshot_matrix(include_headers=True)
                    out = io.StringIO()
                    writer = csv.writer(out)
                    for row in matrix:
                        writer.writerow(row)
                    data_bytes = out.getvalue().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Length", str(len(data_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data_bytes)

                elif path.startswith("/quote"):
                    # /quote/NIFTY 50 or /quote?symbol=NIFTY 50
                    symbol = ""
                    if "/" in path.lstrip("/quote"):
                        symbol = path.split("/quote/", 1)[-1]
                    else:
                        qs = urllib.parse.parse_qs(parsed.query)
                        symbol = qs.get("symbol", [""])[0]

                    symbol = urllib.parse.unquote(symbol)
                    q = store.get_quote_by_symbol(symbol)
                    if q:
                        self._send_json(200, q)
                    else:
                        self._send_json(404, {"error": f"Symbol '{symbol}' not found in live feed"})

                else:
                    self._send_json(404, {"error": "Not found"})

            def _send_json(self, status: int, data: dict):
                body = json.dumps(data, indent=2).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

        try:
            self._server = ThreadedHTTPServer((self.host, self.port), RequestHandler)
            self._running = True
            self._thread = Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            logger.info(f"Local Live Feed HTTP Server running at http://{self.host}:{self.port}/")
        except Exception as e:
            logger.warning(f"Could not start local HTTP feed server on port {self.port}: {e}")

    def stop(self) -> None:
        """Shutdown the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        self._running = False
        logger.info("Local Live Feed HTTP Server stopped.")
