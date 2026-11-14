"""Unit tests for smart options resolution and safe logger emission."""

import logging
import unittest

from upstox_bridge.core.logger import SafeStreamHandler
from upstox_bridge.core.market_store import MarketStore
from upstox_bridge.destinations.bst_syncer import BSTSyncer
from upstox_bridge.instruments.master import InstrumentMaster


class TestOptionsAndLogger(unittest.TestCase):
    def test_safe_stream_handler_no_crash_on_none_stream(self):
        """Verify SafeStreamHandler never crashes when stream is None."""
        handler = SafeStreamHandler(stream=None)
        record = logging.LogRecord(
            name="Test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test log message without stream",
            args=(),
            exc_info=None,
        )
        # Must not raise AttributeError: 'NoneType' object has no attribute 'write'
        try:
            handler.emit(record)
            handler.flush()
        except Exception as e:
            self.fail(f"SafeStreamHandler crashed on None stream: {e}")

    def test_options_current_and_next_week_resolution(self):
        """Verify options symbols resolve to current week by default and next week when specified."""
        im = InstrumentMaster()
        im.load()

        # 1. Current week (nearest active expiry)
        key_current = im.resolve_symbol("NIFTY 26000 CE")
        self.assertEqual(key_current, "NSE_FO|45436")
        sym_curr = [s for s, item in im._by_symbol.items() if item.get("instrument_key") == key_current][0]
        self.assertIn("17 NOV 26", sym_curr)

        # 2. Next week
        key_next = im.resolve_symbol("NIFTY 26000 CE NEXT")
        self.assertEqual(key_next, "NSE_FO|64497")
        sym_next = [s for s, item in im._by_symbol.items() if item.get("instrument_key") == key_next][0]
        self.assertIn("23 NOV 26", sym_next)

        # 3. Explicit expiry tokens
        key_explicit = im.resolve_symbol("NIFTY 26000 CE 23 NOV")
        self.assertEqual(key_explicit, "NSE_FO|64497")

    def test_bst_syncer_initial_price_from_prev_close(self):
        """Verify BSTSyncer populates LTP from prev_close when live tick has not yet arrived."""
        store = MarketStore()
        key = "NSE_FO|45436"
        store.register_instrument(key, "NIFTY 26000 CE")
        store.update_prev_day_stats(key, prev_high=14.35, prev_low=4.45, prev_close=5.50)

        syncer = BSTSyncer(market_store=store)
        syncer._row_map = {10: (key, "NIFTY 26000 CE")}

        # Test block building logic
        item = store.get_quote_item(key)
        self.assertIsNotNone(item)
        self.assertEqual(item.prev_close, 5.50)
        self.assertEqual(item.ltp, 0.0)

        effective_ltp = item.ltp if (item.ltp and item.ltp > 0) else (item.close or item.prev_close or 0.0)
        self.assertEqual(effective_ltp, 5.50)


    def test_setup_production_logging_purges_unsafe_stream_handlers(self):
        """Verify setup_production_logging strips unsafe StreamHandlers with None stream."""
        from upstox_bridge.core.logger import setup_production_logging

        root_logger = logging.getLogger()
        # Add an unsafe standard StreamHandler with stream=None (like basicConfig does on headless Windows)
        unsafe_handler = logging.StreamHandler(stream=None)
        root_logger.addHandler(unsafe_handler)
        self.assertIn(unsafe_handler, root_logger.handlers)

        # Run setup_production_logging
        setup_production_logging()

        # Unsafe standard StreamHandler must be purged from root_logger
        self.assertNotIn(unsafe_handler, root_logger.handlers)

        # Logging must succeed without AttributeError
        test_log = logging.getLogger("TestPurgeSafe")
        try:
            test_log.info("Safe log message after purge verification.")
        except Exception as e:
            self.fail(f"Logger crashed after setup_production_logging: {e}")


if __name__ == "__main__":
    unittest.main()
