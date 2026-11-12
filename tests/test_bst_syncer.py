"""Unit tests for BST Custom Trading Sheet Syncer and Symbol Normalization."""

import shutil
import tempfile
import unittest
from pathlib import Path
import openpyxl

from upstox_bridge.core.market_store import MarketStore
from upstox_bridge.destinations.bst_syncer import BSTSyncer
from upstox_bridge.instruments.master import InstrumentMaster


class TestBSTSyncer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.trial_source = Path(__file__).resolve().parent.parent / "trial.xlsx"
        self.test_excel = Path(self.temp_dir) / "trial.xlsx"
        shutil.copy(self.trial_source, self.test_excel)

        self.store = MarketStore()
        self.master = InstrumentMaster()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clean_script_symbols(self):
        """Test stripping Google Finance and exchange prefixes."""
        self.assertEqual(self.master.clean_script_symbol("INDEXNSE:NIFTY_50"), "NIFTY 50")
        self.assertEqual(self.master.clean_script_symbol("INDEXNSE:NIFTY_BANK"), "NIFTY BANK")
        self.assertEqual(self.master.clean_script_symbol("NSE:AARTIIND"), "AARTIIND")
        self.assertEqual(self.master.clean_script_symbol("NSE:RELIANCE"), "RELIANCE")
        self.assertEqual(self.master.clean_script_symbol("BSE:TCS"), "TCS")
        self.assertEqual(self.master.clean_script_symbol("GOLD DEC FUT"), "GOLD DEC FUT")

    def test_resolve_bst_symbols(self):
        """Test resolving Google Finance formatted symbols to Upstox instrument keys."""
        k1 = self.master.resolve_symbol("INDEXNSE:NIFTY_50")
        self.assertEqual(k1, "NSE_INDEX|Nifty 50")

        k2 = self.master.resolve_symbol("INDEXNSE:NIFTY_BANK")
        self.assertEqual(k2, "NSE_INDEX|Nifty Bank")

        k3 = self.master.resolve_symbol("NSE:RELIANCE")
        self.assertEqual(k3, "NSE_EQ|INE002A01018")

    def test_scan_scripts_from_trial(self):
        """Test scanning scripts from trial.xlsx BST sheet."""
        syncer = BSTSyncer(
            market_store=self.store,
            file_path=self.test_excel,
            sheet_name="BST",
        )
        keys = syncer.scan_scripts()
        # trial.xlsx has 228 rows of scripts starting at row 3
        self.assertEqual(len(keys), 228)
        self.assertIn("NSE_INDEX|Nifty 50", keys)
        self.assertIn("NSE_INDEX|Nifty Bank", keys)

    def test_sync_preserves_formulas(self):
        """Test that sync_cycle updates data cells while leaving formulas intact."""
        syncer = BSTSyncer(
            market_store=self.store,
            file_path=self.test_excel,
            sheet_name="BST",
        )
        syncer.scan_scripts()

        # Update a quote for NIFTY 50 (Row 3 in BST)
        key_nifty = "NSE_INDEX|Nifty 50"
        self.store.update_quote(
            instrument_key=key_nifty,
            ltp=25350.50,
            open_price=25220.00,
            high_price=25400.00,
            low_price=25150.00,
            close_price=25255.05,
            prev_high=25424.35,
            prev_low=25095.35,
            volume=500000,
        )

        # Run openpyxl sync cycle
        syncer._sync_cycle_openpyxl()

        # Verify values in row 3
        wb = openpyxl.load_workbook(self.test_excel, data_only=False)
        ws = wb["BST"]

        # 1. Verify updated data cells
        self.assertEqual(ws.cell(3, 3).value, 25350.50)  # LTP (Col C)
        self.assertEqual(ws.cell(3, 4).value, 25220.00)  # OPEN (Col D)
        self.assertEqual(ws.cell(3, 5).value, 25400.00)  # HIGH (Col E)
        self.assertEqual(ws.cell(3, 6).value, 25150.00)  # LOW (Col F)
        self.assertEqual(ws.cell(3, 7).value, 25255.05)  # P.CLOSE (Col G)
        self.assertEqual(ws.cell(3, 25).value, 25424.35) # P HIGH (Col Y)
        self.assertEqual(ws.cell(3, 26).value, 25095.35) # P. LOW (Col Z)

        # 2. Verify formula cells are completely intact
        trend_formula = ws.cell(3, 2).value  # TREND (Col B)
        self.assertTrue(str(trend_formula).startswith("=if"), f"Formula corrupted: {trend_formula}")

        intra_formula = ws.cell(3, 10).value # INTRA (Col J)
        self.assertTrue(str(intra_formula).startswith("=if"), f"Formula corrupted: {intra_formula}")

        entry_formula = ws.cell(3, 12).value # ENTRY (Col L)
        self.assertTrue(str(entry_formula).startswith("=IF"), f"Formula corrupted: {entry_formula}")

        diff_formula = ws.cell(3, 21).value  # DIFF (Col U)
        self.assertEqual(diff_formula, "=$Y3-$Z3")

        wb.close()


if __name__ == "__main__":
    unittest.main()
