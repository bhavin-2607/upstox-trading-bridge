"""Unit tests for UI/UX Cockpit helpers, market session clock, and token health."""

import time
import base64
import json
import unittest

from upstox_bridge.gui.app import get_market_sessions, get_token_health
from upstox_bridge.destinations.bst_syncer import BSTSyncer
from upstox_bridge.core.market_store import MarketStore


class TestUIUXComponents(unittest.TestCase):
    def test_market_sessions_calculation(self):
        """Verify market session status returns valid values and formatted clock."""
        session_txt, clock_txt, col, bg, border = get_market_sessions()
        self.assertIsInstance(session_txt, str)
        self.assertIn("IST", clock_txt)
        self.assertTrue(col.startswith("#"))
        self.assertTrue(bg.startswith("#"))
        self.assertTrue(border.startswith("#"))

    def test_token_health_decoding(self):
        """Verify JWT expiration is correctly decoded into remaining hours."""
        # 1. No token
        txt, col, bg, border = get_token_health("")
        self.assertIn("No Token", txt)
        self.assertEqual(col, "#EF4444")

        # 2. Mock valid JWT with 5 hours validity
        now = int(time.time())
        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').decode("utf-8").rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({"exp": now + 18060}).encode("utf-8")).decode("utf-8").rstrip("=")
        mock_token = f"{header}.{payload}.MOCK_SIGNATURE"

        txt_valid, col_valid, _, _ = get_token_health(mock_token)
        self.assertIn("5h", txt_valid)
        self.assertEqual(col_valid, "#00E676")

        # 3. Mock expired JWT
        payload_exp = base64.urlsafe_b64encode(json.dumps({"exp": now - 3600}).encode("utf-8")).decode("utf-8").rstrip("=")
        mock_exp = f"{header}.{payload_exp}.MOCK_SIGNATURE"
        txt_exp, col_exp, _, _ = get_token_health(mock_exp)
        self.assertIn("Expired", txt_exp)
        self.assertEqual(col_exp, "#FF334B")

    def test_bst_syncer_append_script_logic(self):
        """Verify append_script accurately finds row and updates internal map."""
        store = MarketStore()
        syncer = BSTSyncer(market_store=store)
        syncer._row_map = {10: ("NSE_EQ|INE002A01018", "RELIANCE")}

        # Test duplicate prevention
        success, msg, row = syncer.append_script("RELIANCE")
        self.assertFalse(success)
        self.assertIn("already tracked", msg)


if __name__ == "__main__":
    unittest.main()
