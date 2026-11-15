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
            publish_mode="formulas",
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
        self.assertEqual(payload["a_data"][0][0], "NIFTY 50")
        self.assertEqual(len(payload["cg_data"]), 1)
        self.assertEqual(payload["cg_data"][0][0], 24150.0)  # LTP

    @patch("requests.post")
    def test_sync_bst_matrix_mode(self, mock_post):
        """Verify Option 1: Formula masking pushes bst_matrix with pure values."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "success", "mode": "bst_matrix"}'
        mock_post.return_value = mock_resp

        mock_bst = MagicMock()
        mock_bst._row_map = {3: ("NSE_INDEX|Nifty 50", "NIFTY 50")}
        mock_bst.get_evaluated_matrix.return_value = [
            ["NIFTY 50", "UP", 24150.0, 24000.0, 24200.0, 23950.0, 24000.0, 25.5, 24100.0, "BUY", "BUY"]
        ]

        bst_gsyncer = GoogleSheetWebhookSyncer(
            market_store=self.store,
            webhook_url="https://script.google.com/macros/s/TEST/exec",
            sheet_name="BST",
            mode="bst",
            publish_mode="values",
            bst_syncer=mock_bst,
        )

        success = bst_gsyncer.sync_once()
        self.assertTrue(success)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["mode"], "bst_matrix")
        self.assertEqual(payload["sheet_name"], "BST")
        self.assertEqual(payload["start_row"], 3)
        self.assertIn("matrix", payload)
        self.assertEqual(payload["matrix"][0][0], "NIFTY 50")
        self.assertEqual(payload["matrix"][0][1], "UP")
        self.assertEqual(payload["matrix"][0][9], "BUY")

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
            publish_mode="formulas",
            bst_syncer=mock_bst,
            on_gsheet_scripts_detected=on_scripts,
        )

        bst_gsyncer.sync_once()
        self.assertEqual(len(received_scripts), 2)
        self.assertEqual(received_scripts[1], (4, "NSE:TCS"))

    @patch("requests.post")
    def test_sync_bst_mode_deletion_detected(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "mode": "bst",
            "scripts": [[3, "INDEXNSE:NIFTY_50"]],  # row 4 was deleted!
        }
        mock_post.return_value = mock_resp

        mock_bst = MagicMock()
        mock_bst._row_map = {3: ("NSE_INDEX|Nifty 50", "NIFTY 50")}

        deleted_rows = []
        def on_delete(row_idx):
            deleted_rows.append(row_idx)

        bst_gsyncer = GoogleSheetWebhookSyncer(
            market_store=self.store,
            webhook_url="https://script.google.com/macros/s/TEST/exec",
            sheet_name="BST",
            mode="bst",
            publish_mode="formulas",
            bst_syncer=mock_bst,
            on_gsheet_script_deleted=on_delete,
        )
        # Seed known scripts
        bst_gsyncer._known_gsheet_scripts = {3: "INDEXNSE:NIFTY_50", 4: "NSE:TCS"}

        bst_gsyncer.sync_once()
        self.assertEqual(deleted_rows, [4])
        self.assertNotIn(4, bst_gsyncer._known_gsheet_scripts)

    @patch("requests.post")
    def test_connection_safe_ping(self, mock_post):
        """Verify test_connection sends non-destructive ping without writing fake data."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "success", "mode": "ping"}'
        mock_resp.json.return_value = {"status": "success", "mode": "ping"}
        mock_post.return_value = mock_resp

        res = self.syncer.test_connection()
        self.assertTrue(res["success"])
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["mode"], "ping")
        self.assertEqual(payload["sheet_name"], "LiveMarket")
        self.assertNotIn("data", payload)  # No fake rows written!

    @patch("requests.post")
    def test_restore_bst_template(self, mock_post):
        """Verify restore_bst_template in values mode strips all formulas for public sharing."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "success", "mode": "init_bst"}'
        mock_resp.json.return_value = {"status": "success", "mode": "init_bst"}
        mock_post.return_value = mock_resp

        bst_gsyncer = GoogleSheetWebhookSyncer(
            market_store=self.store,
            webhook_url="https://script.google.com/macros/s/TEST/exec",
            sheet_name="BST",
            mode="bst",
            publish_mode="values",
        )
        res = bst_gsyncer.restore_bst_template("trial.xlsx")
        self.assertTrue(res["success"])
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["mode"], "init_bst")
        self.assertEqual(payload["sheet_name"], "BST")
        self.assertIn("headers_row1", payload)
        self.assertIn("headers_row2", payload)
        self.assertIn("rows", payload)
        self.assertGreater(len(payload["rows"]), 200)

        # STRICT VERIFICATION: In values mode, ZERO cells start with '='!
        has_any_formula = any(
            any(str(cell).startswith("=") for cell in row)
            for row in payload["rows"]
        )
        self.assertFalse(has_any_formula, "Formulas must NOT be present in values mode!")

    @patch("requests.post")
    def test_restore_bst_template_formulas_mode(self, mock_post):
        """Verify restore_bst_template in formulas mode retains formulas."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "success", "mode": "init_bst"}'
        mock_resp.json.return_value = {"status": "success", "mode": "init_bst"}
        mock_post.return_value = mock_resp

        bst_gsyncer = GoogleSheetWebhookSyncer(
            market_store=self.store,
            webhook_url="https://script.google.com/macros/s/TEST/exec",
            sheet_name="BST",
            mode="bst",
            publish_mode="formulas",
        )
        res = bst_gsyncer.restore_bst_template("trial.xlsx")
        self.assertTrue(res["success"])
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]

        has_any_formula = any(
            any(str(cell).startswith("=") for cell in row)
            for row in payload["rows"]
        )
        self.assertTrue(has_any_formula, "Formulas SHOULD be present in formulas mode!")

    def test_empty_webhook_url_error(self):
        empty_syncer = GoogleSheetWebhookSyncer(market_store=self.store, webhook_url="")
        with self.assertRaises(ValueError):
            empty_syncer.sync_once()


if __name__ == "__main__":
    unittest.main()
