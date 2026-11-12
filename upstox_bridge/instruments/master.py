"""Upstox Instrument Master downloader and Symbol Resolver."""

from __future__ import annotations

import gzip
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from upstox_bridge.core.config import settings

logger = logging.getLogger("InstrumentMaster")

UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"

# Fallback common mapping if network/download is unavailable
COMMON_INDEX_MAP = {
    "NIFTY 50": "NSE_INDEX|Nifty 50",
    "NIFTY": "NSE_INDEX|Nifty 50",
    "NIFTY50": "NSE_INDEX|Nifty 50",
    "NIFTY BANK": "NSE_INDEX|Nifty Bank",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
    "NIFTY IT": "NSE_INDEX|Nifty IT",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
    "SENSEX": "BSE_INDEX|SENSEX",
}

COMMON_EQUITY_MAP = {
    "RELIANCE": "NSE_EQ|INE002A01018",
    "TCS": "NSE_EQ|INE467B01029",
    "HDFCBANK": "NSE_EQ|INE040A01034",
    "INFY": "NSE_EQ|INE009A01021",
    "ICICIBANK": "NSE_EQ|INE090A01021",
    "TATAMOTORS": "NSE_EQ|INE155A01022",
    "SBIN": "NSE_EQ|INE062A01020",
    "BHARTIARTL": "NSE_EQ|INE397D01024",
    "ITC": "NSE_EQ|INE154A01025",
    "LT": "NSE_EQ|INE018A01030",
}


class InstrumentMaster:
    """Manages downloading, caching, and searching Upstox instrument keys."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or settings.data_dir
        self.cache_path = self.cache_dir / "instruments_master.json"
        self._by_key: Dict[str, Dict[str, Any]] = {}
        self._by_symbol: Dict[str, Dict[str, Any]] = {}  # trading_symbol -> record
        self._is_loaded = False

    def load(self, force_refresh: bool = False) -> None:
        """Load instrument data from local cache or download if expired."""
        if self._is_loaded and not force_refresh:
            return

        cache_age_hours = 9999.0
        if self.cache_path.exists():
            mtime = self.cache_path.stat().st_mtime
            cache_age_hours = (time.time() - mtime) / 3600.0

        if force_refresh or not self.cache_path.exists() or cache_age_hours > settings.instrument_cache_hours:
            self._download_and_cache()

        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._index_instruments(data)
                    self._is_loaded = True
                    return
            except Exception as e:
                logger.warning(f"Failed to read cache {self.cache_path}: {e}")

        # Fallback index if download fails
        self._load_fallback_index()
        self._is_loaded = True

    def _download_and_cache(self) -> None:
        """Download complete.json.gz from Upstox CDN and write uncompressed cache."""
        try:
            logger.info("Downloading Upstox complete instrument master (~15MB compressed)...")
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(UPSTOX_INSTRUMENTS_URL, headers=headers, timeout=30)
            if resp.status_code == 200:
                decompressed = gzip.decompress(resp.content)
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.cache_path, "wb") as f:
                    f.write(decompressed)
                logger.info("Instrument master downloaded and cached successfully.")
            else:
                logger.warning(f"Download returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Could not download instrument master from Upstox: {e}")

    def _index_instruments(self, records: List[Dict[str, Any]]) -> None:
        """Build in-memory fast lookup tables."""
        for item in records:
            key = item.get("instrument_key")
            symbol = item.get("trading_symbol")
            if not key:
                continue

            self._by_key[key] = item

            if symbol:
                clean_sym = symbol.upper().strip()
                # Prioritize NSE_EQ or NSE_INDEX when multiple symbols share tradingsymbol
                if clean_sym not in self._by_symbol or "NSE_EQ" in key or "NSE_INDEX" in key:
                    self._by_symbol[clean_sym] = item

    def _load_fallback_index(self) -> None:
        """Populate common defaults if no internet or cache available."""
        for sym, key in {**COMMON_INDEX_MAP, **COMMON_EQUITY_MAP}.items():
            record = {
                "instrument_key": key,
                "trading_symbol": sym,
                "name": sym,
            }
            self._by_key[key] = record
            self._by_symbol[sym.upper()] = record

    def resolve_symbol(self, symbol_or_key: str) -> str:
        """
        Convert human trading symbol (e.g. 'RELIANCE', 'NIFTY 50', 'GOLD DEC FUT') into exact instrument key.
        If already an instrument key (contains '|'), returns as is.
        """
        clean = symbol_or_key.strip()
        if "|" in clean:
            return clean

        upper = clean.upper()

        # 1. Check common index aliases
        if upper in COMMON_INDEX_MAP:
            return COMMON_INDEX_MAP[upper]

        # 2. Check common equities fallback
        if upper in COMMON_EQUITY_MAP:
            return COMMON_EQUITY_MAP[upper]

        # 3. Check loaded instrument index for exact trading_symbol match
        self.load()
        if upper in self._by_symbol:
            return self._by_symbol[upper].get("instrument_key", clean)

        # 4. Smart token-based fuzzy resolver (e.g. 'GOLD DEC FUT' -> 'MCX_FO|495213')
        fuzzy_match = self._smart_fuzzy_resolve(upper)
        if fuzzy_match:
            return fuzzy_match

        # 5. Default assumption: MCX for commodities, NSE_EQ for equities
        is_commodity = any(c in upper for c in ["GOLD", "SILVER", "CRUDE", "NATURALGAS", "COPPER", "ZINC"])
        if is_commodity:
            return f"MCX_FO|{clean}"
        return f"NSE_EQ|{clean}"

    def _smart_fuzzy_resolve(self, query: str) -> Optional[str]:
        """Fuzzy/token-based matching for commodities, futures, and options."""
        import re
        query_tokens = set(re.findall(r"\w+", query.upper()))
        if not query_tokens:
            return None

        best_key = None
        best_score = -1

        is_commodity = any(c in query_tokens for c in [
            "GOLD", "SILVER", "CRUDEOIL", "CRUDE", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD"
        ])

        for sym_upper, item in self._by_symbol.items():
            item_tokens = set(re.findall(r"\w+", sym_upper))
            if query_tokens.issubset(item_tokens):
                score = 100 - len(item_tokens)
                if is_commodity and item.get("exchange") == "MCX":
                    score += 50
                if score > best_score:
                    best_score = score
                    best_key = item.get("instrument_key")

        return best_key

    def search_symbols(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Search instruments by partial trading symbol or name."""
        self.load()
        q = query.strip().upper()
        results: List[Dict[str, Any]] = []

        for symbol, item in self._by_symbol.items():
            name = (item.get("name") or "").upper()
            if q in symbol or q in name:
                results.append(item)
                if len(results) >= limit:
                    break

        return results
