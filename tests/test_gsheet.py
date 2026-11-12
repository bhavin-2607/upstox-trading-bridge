"""Unit tests for GoogleSheetWebhookSyncer."""

import unittest
from unittest.mock import MagicMock, patch
from upstox_bridge.core.market_store import MarketStore
from upstox_bridge.destinations.gsheet_webhook import GoogleSheetWebhookSyncer


class TestGoogleSheetWebhookSyncer(unittest.TestCase):
    def setUp(self):
        self.store = MarketStore()
        self.store.register_instrument("NSE_INDEX|Nifty 50", symbol="NIFTY 50")
        self.store.update_quote("NSE_INDEX|Nifty 50", ltp=24150.0, close_price=24000.0)
        self.syncer = GoogleSheetWebhookSyncer(
            market_store=self.store,
            webhook_url="https://script.google.com/macros/s/TEST/exec",
            sheet_name="LiveMarket",
        )

    @patch("requests.post")
    def test_sync_once_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "success"}'
        mock_post.return_value = mock_resp

        success = self.syncer.sync_once()
        self.assertTrue(success)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://script.google.com/macros/s/TEST/exec")
        payload = kwargs["json"]
        self.assertEqual(payload["sheet_name"], "LiveMarket")
        self.assertEqual(len(payload["data"]), 2)  # headers + 1 row
        self.assertEqual(payload["data"][1][0], "NIFTY 50")

    @patch("requests.post")
    def test_sync_bst_mode(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "success", "mode": "bst"}'
        mock_post.return_value = mock_resp

        mock_bst = MagicMock()
        mock_bst._row_map = {3: ("NSE_INDEX|Nifty 50", "NIFTY 50")}

        bst_gsyncer = GoogleSheetWebhookSyncer(
            market_store=self.store,
            webhook_url="https://script.google.com/macros/s/TEST/exec",
            sheet_name="BST",
            mode="bst",
            bst_syncer=mock_bst,
        )

        success = bst_gsyncer.sync_once()
        self.assertTrue(success)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["mode"], "bst")
        self.assertEqual(payload["sheet_name"], "BST")
        self.assertEqual(payload["start_row"], 3)
        self.assertEqual(len(payload["cg_data"]), 1)
        self.assertEqual(payload["cg_data"][0][0], 24150.0)  # LTP

    @patch("requests.post")
    def test_sync_bst_mode_bidirectional(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "mode": "bst",
            "scripts": [[3, "INDEXNSE:NIFTY_50"], [4, "NSE:TCS"]],
        }
        mock_post.return_value = mock_resp

        mock_bst = MagicMock()
        mock_bst._row_map = {3: ("NSE_INDEX|Nifty 50", "NIFTY 50")}

        received_scripts = []
        def on_scripts(scripts):
            received_scripts.extend(scripts)

        bst_gsyncer = GoogleSheetWebhookSyncer(
            market_store=self.store,
            webhook_url="https://script.google.com/macros/s/TEST/exec",
            sheet_name="BST",
            mode="bst",
            bst_syncer=mock_bst,
            on_gsheet_scripts_detected=on_scripts,
        )

        bst_gsyncer.sync_once()
        self.assertEqual(len(received_scripts), 2)
        self.assertEqual(received_scripts[1], (4, "NSE:TCS"))

    def test_empty_webhook_url_error(self):
        empty_syncer = GoogleSheetWebhookSyncer(market_store=self.store, webhook_url="")
        with self.assertRaises(ValueError):
            empty_syncer.sync_once()


if __name__ == "__main__":
    unittest.main()
