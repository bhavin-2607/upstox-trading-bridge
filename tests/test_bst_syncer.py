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
        """Test resolving both normal human symbols and Google Finance formatted symbols."""
        # Normal human symbols (no prefixes needed!)
        self.assertEqual(self.master.resolve_symbol("NIFTY 50"), "NSE_INDEX|Nifty 50")
        self.assertEqual(self.master.resolve_symbol("NIFTY BANK"), "NSE_INDEX|Nifty Bank")
        self.assertEqual(self.master.resolve_symbol("RELIANCE"), "NSE_EQ|INE002A01018")
        self.assertEqual(self.master.resolve_symbol("GOLD DEC FUT"), "MCX_FO|495213")
        self.assertEqual(self.master.resolve_symbol("SILVER DEC FUT"), "MCX_FO|495214")
        self.assertEqual(self.master.resolve_symbol("CRUDEOIL NOV FUT"), "MCX_FO|573422")
        self.assertEqual(self.master.resolve_symbol("GOLD NOV 120000 PE"), "MCX_FO|579333")

        # Backward compatibility with Google Finance prefixes
        self.assertEqual(self.master.resolve_symbol("INDEXNSE:NIFTY_50"), "NSE_INDEX|Nifty 50")
        self.assertEqual(self.master.resolve_symbol("INDEXNSE:NIFTY_BANK"), "NSE_INDEX|Nifty Bank")
        self.assertEqual(self.master.resolve_symbol("NSE:RELIANCE"), "NSE_EQ|INE002A01018")

    def test_scan_scripts_from_trial(self):
        """Test scanning scripts from trial.xlsx BST sheet."""
        syncer = BSTSyncer(
            market_store=self.store,
            file_path=self.test_excel,
            sheet_name="BST",
        )
        keys = syncer.scan_scripts()
        # trial.xlsx has 232 rows of scripts starting at row 3 (including 4 MCX commodities)
        self.assertEqual(len(keys), 232)
        self.assertIn("NSE_INDEX|Nifty 50", keys)
        self.assertIn("NSE_INDEX|Nifty Bank", keys)
        self.assertIn("MCX_FO|495213", keys)
        self.assertIn("MCX_FO|495214", keys)

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
        self.assertTrue(str(trend_formula).lower().startswith("=if"), f"Formula corrupted: {trend_formula}")

        intra_formula = ws.cell(3, 10).value # INTRA (Col J)
        self.assertTrue(str(intra_formula).lower().startswith("=if"), f"Formula corrupted: {intra_formula}")

        entry_formula = ws.cell(3, 12).value # ENTRY (Col L)
        self.assertTrue(str(entry_formula).lower().startswith("=if"), f"Formula corrupted: {entry_formula}")

        diff_formula = ws.cell(3, 21).value  # DIFF (Col U)
        self.assertEqual(diff_formula, "=$Y3-$Z3")

        wb.close()

    def test_mcx_commodity_stats_and_formulas(self):
        """Test that MCX commodity rows (231-234) have P.HIGH, P.LOW and intact formulas."""
        syncer = BSTSyncer(
            market_store=self.store,
            file_path=self.test_excel,
            sheet_name="BST",
        )
        syncer.scan_scripts()

        # Update quotes for GOLD DEC FUT (Row 231) and GOLD NOV 120000 PE (Row 234)
        gold_fut_key = "MCX_FO|495213"
        self.store.update_quote(
            instrument_key=gold_fut_key,
            ltp=140500.0,
            open_price=139800.0,
            high_price=141200.0,
            low_price=139500.0,
            close_price=139716.0,
            prev_high=141990.0,
            prev_low=139569.0,
            volume=45000,
        )

        syncer._sync_cycle_openpyxl()

        wb = openpyxl.load_workbook(self.test_excel, data_only=False)
        ws = wb["BST"]

        # Check Row 231 (GOLD DEC FUT)
        self.assertEqual(ws.cell(231, 1).value, "GOLD DEC FUT")
        self.assertEqual(ws.cell(231, 3).value, 140500.0)   # LTP
        self.assertEqual(ws.cell(231, 7).value, 139716.0)   # P.CLOSE
        self.assertEqual(ws.cell(231, 25).value, 141990.0)  # P HIGH
        self.assertEqual(ws.cell(231, 26).value, 139569.0)  # P. LOW
        self.assertEqual(ws.cell(231, 32).value, 45000)     # VOL

        # Verify formulas in row 231
        formula_b = ws.cell(231, 2).value
        formula_h = ws.cell(231, 8).value
        self.assertTrue(str(formula_b).lower().startswith("=if"), f"Formula B corrupted: {formula_b}")
        self.assertEqual(formula_h, "=($Y231-$Z231)*11.8%")

        wb.close()


if __name__ == "__main__":
    unittest.main()
