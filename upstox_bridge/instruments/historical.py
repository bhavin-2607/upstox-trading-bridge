"""Historical Daily Candle fetcher for Previous Day High, Low, and Close."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

from upstox_bridge.core.config import settings

logger = logging.getLogger("HistoricalStats")


class HistoricalStatsFetcher:
    """
    Fetches previous day's High, Low, and Close for instruments from Upstox Historical Candle API.
    Caches results per trading day to avoid unnecessary API requests.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or settings.data_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "historical_prev_stats_cache.json"
        self._stats: Dict[str, Tuple[float, float, float]] = {}  # key -> (prev_high, prev_low, prev_close)

    def _load_cache(self) -> bool:
        """Load cache if it matches today's date."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if not self.cache_file.exists():
            return False

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == today_str:
                self._stats = {k: tuple(v) for k, v in data.get("stats", {}).items()}
                logger.info(f"Loaded {len(self._stats)} previous day stats from today's cache.")
                return True
        except Exception as e:
            logger.debug(f"Failed to read historical cache: {e}")
        return False

    def _save_cache(self) -> None:
        """Persist stats cache to disk."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            payload = {
                "date": today_str,
                "updated_at": datetime.now().isoformat(),
                "stats": {k: list(v) for k, v in self._stats.items()},
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save historical cache: {e}")

    def fetch_single(self, instrument_key: str) -> Tuple[str, Optional[float], Optional[float], Optional[float]]:
        """Fetch previous day's high, low, close for a single instrument key."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        from_str = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/day/{today_str}/{from_str}"
        headers = {"Accept": "application/json"}
        if settings.upstox_access_token:
            headers["Authorization"] = f"Bearer {settings.upstox_access_token}"

        try:
            resp = requests.get(url, headers=headers, timeout=6)
            if resp.status_code == 200:
                candles = resp.json().get("data", {}).get("candles", [])
                if candles:
                    # Candle: [timestamp, open, high, low, close, volume, open_interest]
                    # If candle[0] timestamp starts with today's date, then candle[1] is yesterday
                    c0_date = candles[0][0][:10]
                    target_candle = candles[1] if (c0_date == today_str and len(candles) > 1) else candles[0]
                    high_p = float(target_candle[2])
                    low_p = float(target_candle[3])
                    close_p = float(target_candle[4])
                    return instrument_key, high_p, low_p, close_p
        except Exception as e:
            logger.debug(f"Could not fetch historical candle for {instrument_key}: {e}")

        return instrument_key, None, None, None

    def fetch_all(
        self, instrument_keys: List[str], max_workers: int = 15
    ) -> Dict[str, Tuple[float, float, float]]:
        """
        Fetch previous day stats for all keys in parallel using thread pool.
        Uses cached values when available.
        """
        self._load_cache()

        needed_keys = [k for k in instrument_keys if k not in self._stats]
        if not needed_keys:
            return self._stats

        logger.info(f"Fetching previous day High/Low stats for {len(needed_keys)} instrument(s)...")
        start_t = time.time()
        success_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_key = {executor.submit(self.fetch_single, key): key for key in needed_keys}
            for future in as_completed(future_to_key):
                key, high_p, low_p, close_p = future.result()
                if high_p is not None and low_p is not None and close_p is not None:
                    self._stats[key] = (high_p, low_p, close_p)
                    success_count += 1

        elapsed = time.time() - start_t
        logger.info(f"Retrieved {success_count}/{len(needed_keys)} historical stats in {elapsed:.2f}s.")
        self._save_cache()
        return self._stats

    def get_stats(self, instrument_key: str) -> Optional[Tuple[float, float, float]]:
        """Get cached previous day (high, low, close) for an instrument."""
        return self._stats.get(instrument_key)
