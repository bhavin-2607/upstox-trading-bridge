"""Unit tests for MarketStore."""

import unittest
from upstox_bridge.core.market_store import MarketStore


class TestMarketStore(unittest.TestCase):
    def setUp(self):
        self.store = MarketStore()

    def test_register_instrument(self):
        item = self.store.register_instrument("NSE_INDEX|Nifty 50", symbol="NIFTY 50")
        self.assertEqual(item.symbol, "NIFTY 50")
        self.assertEqual(item.instrument_key, "NSE_INDEX|Nifty 50")
        self.assertEqual(self.store.count(), 1)

    def test_update_quote_and_change_calc(self):
        key = "NSE_EQ|INE002A01018"
        self.store.register_instrument(key, symbol="RELIANCE")

        # Update with open=2900, close=2900, ltp=2950, vwap=2935
        self.store.update_quote(
            instrument_key=key,
            ltp=2950.0,
            open_price=2910.0,
            high_price=2960.0,
            low_price=2900.0,
            close_price=2900.0,
            vwap=2935.0,
            volume=500000,
        )

        q = self.store.get_quote_by_symbol("RELIANCE")
        self.assertIsNotNone(q)
        self.assertEqual(q["ltp"], 2950.0)
        self.assertEqual(q["change"], 50.0)
        self.assertEqual(q["vwap"], 2935.0)
        self.assertEqual(q["volume"], 500000)

    def test_snapshot_matrix_formatting(self):
        self.store.register_instrument("NSE_INDEX|Nifty 50", symbol="NIFTY 50")
        self.store.update_quote("NSE_INDEX|Nifty 50", ltp=24000.0, close_price=23900.0)

        matrix = self.store.get_snapshot_matrix(include_headers=True)
        self.assertEqual(len(matrix), 2)  # Header + 1 row
        self.assertEqual(matrix[0], MarketStore.HEADERS)
        self.assertEqual(matrix[1][0], "NIFTY 50")
        self.assertEqual(matrix[1][2], 24000.0)
        self.assertEqual(matrix[1][3], 100.0)


if __name__ == "__main__":
    unittest.main()
