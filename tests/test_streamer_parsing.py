"""Unit tests for WebSocket feed message parsing."""

import unittest
from upstox_bridge.core.market_store import MarketStore
from upstox_bridge.feed.streamer import UpstoxFeedStreamer


class TestFeedParsing(unittest.TestCase):
    def setUp(self):
        self.store = MarketStore()
        # Mock streamer without connecting
        self.streamer = UpstoxFeedStreamer.__new__(UpstoxFeedStreamer)
        self.streamer.market_store = self.store
        self.streamer.on_tick_callback = None

    def test_parse_index_full_feed(self):
        message = {
            "type": "live_feed",
            "feeds": {
                "NSE_INDEX|Nifty 50": {
                    "fullFeed": {
                        "indexFF": {
                            "ltpc": {"ltp": 24250.75, "cp": 24100.0, "ltt": 1700000000},
                            "marketOHLC": {
                                "ohlc": [
                                    {"interval": "1d", "open": 24120.0, "high": 24280.0, "low": 24090.0, "close": 24100.0}
                                ]
                            },
                        }
                    }
                }
            },
        }

        self.streamer._on_message(message)
        q = self.store.get_quote_by_symbol("NSE_INDEX|Nifty 50")
        self.assertIsNotNone(q)
        self.assertEqual(q["ltp"], 24250.75)
        self.assertEqual(q["open"], 24120.0)
        self.assertEqual(q["high"], 24280.0)
        self.assertEqual(q["low"], 24090.0)
        self.assertEqual(q["close"], 24100.0)
        self.assertEqual(q["change"], 150.75)

    def test_parse_market_full_feed(self):
        message = {
            "type": "live_feed",
            "feeds": {
                "NSE_EQ|INE002A01018": {
                    "fullFeed": {
                        "marketFF": {
                            "ltpc": {"ltp": 3010.5, "cp": 2980.0, "ltt": 1700000000},
                            "marketOHLC": {
                                "ohlc": [
                                    {
                                        "interval": "1d",
                                        "open": 2985.0,
                                        "high": 3020.0,
                                        "low": 2975.0,
                                        "close": 2980.0,
                                        "vol": 850000,
                                    }
                                ]
                            },
                            "vtt": 850000,
                            "atp": 3005.0,
                        }
                    }
                }
            },
        }

        self.streamer._on_message(message)
        q = self.store.get_quote_by_symbol("NSE_EQ|INE002A01018")
        self.assertIsNotNone(q)
        self.assertEqual(q["ltp"], 3010.5)
        self.assertEqual(q["volume"], 850000)
        self.assertEqual(q["vwap"], 3005.0)
        self.assertEqual(q["change"], 30.5)


if __name__ == "__main__":
    unittest.main()
