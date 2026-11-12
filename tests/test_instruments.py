"""Unit tests for InstrumentMaster and symbol resolver."""

import unittest
from upstox_bridge.instruments.master import InstrumentMaster


class TestInstrumentMaster(unittest.TestCase):
    def setUp(self):
        self.master = InstrumentMaster()

    def test_resolve_raw_instrument_key(self):
        raw = "NSE_INDEX|Nifty 50"
        self.assertEqual(self.master.resolve_symbol(raw), raw)

    def test_resolve_common_indices(self):
        self.assertEqual(self.master.resolve_symbol("NIFTY 50"), "NSE_INDEX|Nifty 50")
        self.assertEqual(self.master.resolve_symbol("nifty 50"), "NSE_INDEX|Nifty 50")
        self.assertEqual(self.master.resolve_symbol("BANKNIFTY"), "NSE_INDEX|Nifty Bank")
        self.assertEqual(self.master.resolve_symbol("FINNIFTY"), "NSE_INDEX|Nifty Fin Service")

    def test_resolve_common_equities(self):
        self.assertEqual(self.master.resolve_symbol("RELIANCE"), "NSE_EQ|INE002A01018")
        self.assertEqual(self.master.resolve_symbol("TCS"), "NSE_EQ|INE467B01029")
        self.assertEqual(self.master.resolve_symbol("INFY"), "NSE_EQ|INE009A01021")


if __name__ == "__main__":
    unittest.main()
