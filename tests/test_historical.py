"""Unit tests for Historical Daily Candle fetcher and cache."""

import json
import tempfile
import unittest
from pathlib import Path

from upstox_bridge.instruments.historical import HistoricalStatsFetcher


class TestHistoricalFetcher(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fetcher = HistoricalStatsFetcher(cache_dir=Path(self.temp_dir))

    def test_cache_roundtrip(self):
        """Test persisting and reloading stats cache."""
        self.fetcher._stats = {
            "NSE_INDEX|Nifty 50": (25424.35, 25095.35, 25255.05),
            "NSE_INDEX|Nifty Bank": (61394.3, 60376.1, 60792.4),
        }
        self.fetcher._save_cache()

        new_fetcher = HistoricalStatsFetcher(cache_dir=Path(self.temp_dir))
        loaded = new_fetcher._load_cache()
        self.assertTrue(loaded)
        stats = new_fetcher.get_stats("NSE_INDEX|Nifty 50")
        self.assertEqual(stats, (25424.35, 25095.35, 25255.05))


if __name__ == "__main__":
    unittest.main()
