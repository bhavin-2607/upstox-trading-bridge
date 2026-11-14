"""Tests for Web Dashboard HTTP endpoints and UI rendering."""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from upstox_bridge.gui.web_dashboard import WebDashboardHandler, DASHBOARD_HTML


class FakeSocket:
    def __init__(self, request_bytes):
        self.rfile = io.BytesIO(request_bytes)
        self.wfile = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "r" in mode:
            return self.rfile
        return self.wfile


class TestWebDashboard(unittest.TestCase):
    def test_dashboard_html_contents(self):
        self.assertIn("<title>Upstox Live Trading Bridge</title>", DASHBOARD_HTML)
        self.assertIn("btn-start-live", DASHBOARD_HTML)
        self.assertIn("btn-start-sim", DASHBOARD_HTML)
        self.assertIn("btn-stop", DASHBOARD_HTML)
        self.assertIn("/api/status", DASHBOARD_HTML)
        self.assertIn("/api/quotes", DASHBOARD_HTML)

    def test_handler_api_status(self):
        mock_runner = MagicMock()
        mock_runner.is_running = True
        mock_runner.is_simulation = False
        mock_runner.ticks_received = 1234
        mock_runner.market_store.count.return_value = 10
        mock_runner.excel_status = "Connected"
        mock_runner.excel_file.name = "bst.xlsx"
        mock_runner.sheet_name = "BST"
        mock_runner.bst_syncer.last_sync_time = 0.0
        mock_runner.gsheet_status = "Active (3.0s)"
        mock_runner.streamer.state = "Connected"

        WebDashboardHandler.runner = mock_runner

        req = b"GET /api/status HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        sock = FakeSocket(req)

        # Mock send_response / headers
        with patch.object(WebDashboardHandler, "send_response") as mock_resp, \
             patch.object(WebDashboardHandler, "send_header") as mock_hdr, \
             patch.object(WebDashboardHandler, "end_headers"):

            handler = WebDashboardHandler.__new__(WebDashboardHandler)
            handler.rfile = sock.rfile
            handler.wfile = sock.wfile
            handler.path = "/api/status"
            handler.headers = {}
            handler.do_GET()

            mock_resp.assert_called_with(200)
            written = sock.wfile.getvalue().decode("utf-8")
            data = json.loads(written)
            self.assertTrue(data["running"])
            self.assertEqual(data["ticks"], 1234)
            self.assertEqual(data["excel_status"], "Connected")

    def test_handler_api_quotes(self):
        mock_runner = MagicMock()
        mock_runner.market_store.get_all_quotes_dict.return_value = {
            "RELIANCE": {"ltp": 2500.0, "high": 2520.0, "low": 2490.0, "close": 2495.0, "volume": 50000}
        }
        WebDashboardHandler.runner = mock_runner

        sock = FakeSocket(b"GET /api/quotes HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        with patch.object(WebDashboardHandler, "send_response") as mock_resp, \
             patch.object(WebDashboardHandler, "send_header"), \
             patch.object(WebDashboardHandler, "end_headers"):

            handler = WebDashboardHandler.__new__(WebDashboardHandler)
            handler.rfile = sock.rfile
            handler.wfile = sock.wfile
            handler.path = "/api/quotes"
            handler.headers = {}
            handler.do_GET()

            mock_resp.assert_called_with(200)
            data = json.loads(sock.wfile.getvalue().decode("utf-8"))
            self.assertIn("RELIANCE", data)
            self.assertEqual(data["RELIANCE"]["ltp"], 2500.0)


if __name__ == "__main__":
    unittest.main()
