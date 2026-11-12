"""Thread-safe in-memory market store for Upstox live tick and OHLC quotes."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


class QuoteItem:
    """Represents the market quote for a single instrument."""

    __slots__ = (
        "symbol",
        "instrument_key",
        "name",
        "ltp",
        "open",
        "high",
        "low",
        "close",
        "prev_close",
        "prev_high",
        "prev_low",
        "change",
        "vwap",
        "volume",
        "ltt",
        "updated_at",
        "last_update_ts",
    )

    def __init__(self, instrument_key: str, symbol: str = "", name: str = ""):
        self.instrument_key = instrument_key
        self.symbol = symbol or instrument_key
        self.name = name or self.symbol
        self.ltp: float = 0.0
        self.open: float = 0.0
        self.high: float = 0.0
        self.low: float = 0.0
        self.close: float = 0.0  # Previous close
        self.prev_close: float = 0.0
        self.prev_high: float = 0.0
        self.prev_low: float = 0.0
        self.change: float = 0.0
        self.vwap: float = 0.0
        self.volume: int = 0
        self.ltt: int = 0
        self.updated_at: str = "--:--:--"
        self.last_update_ts: float = 0.0

    def to_row(self) -> List[Any]:
        """Format as a row for Excel / Google Sheets grid."""
        return [
            self.symbol,
            self.instrument_key,
            round(self.ltp, 2) if self.ltp else 0.0,
            round(self.change, 2) if self.change else 0.0,
            round(self.vwap, 2) if self.vwap else 0.0,
            round(self.open, 2) if self.open else 0.0,
            round(self.high, 2) if self.high else 0.0,
            round(self.low, 2) if self.low else 0.0,
            round(self.close, 2) if self.close else 0.0,
            int(self.volume),
            self.updated_at,
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert quote to dictionary for JSON APIs."""
        return {
            "symbol": self.symbol,
            "instrument_key": self.instrument_key,
            "ltp": round(self.ltp, 2),
            "change": round(self.change, 2),
            "vwap": round(self.vwap, 2),
            "open": round(self.open, 2),
            "high": round(self.high, 2),
            "low": round(self.low, 2),
            "close": round(self.close, 2),
            "prev_high": round(self.prev_high, 2),
            "prev_low": round(self.prev_low, 2),
            "volume": int(self.volume),
            "updated_at": self.updated_at,
            "ltt": self.ltt,
        }


class MarketStore:
    """Thread-safe centralized store for real-time market data quotes."""

    HEADERS = [
        "Symbol",
        "Instrument Key",
        "LTP",
        "Change",
        "VWAP",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "Updated At",
    ]

    def __init__(self):
        self._lock = threading.Lock()
        self._quotes: Dict[str, QuoteItem] = {}  # key: instrument_key
        self._key_by_symbol: Dict[str, str] = {}  # key: upper symbol -> instrument_key
        self._ordered_keys: List[str] = []

    def register_instrument(self, instrument_key: str, symbol: str = "", name: str = "") -> QuoteItem:
        """Register an instrument key in the store preserving insertion order."""
        with self._lock:
            clean_sym = symbol or instrument_key
            if instrument_key not in self._quotes:
                item = QuoteItem(instrument_key=instrument_key, symbol=clean_sym, name=name)
                self._quotes[instrument_key] = item
                self._ordered_keys.append(instrument_key)
            else:
                item = self._quotes[instrument_key]
                if clean_sym and not item.symbol:
                    item.symbol = clean_sym

            self._key_by_symbol[clean_sym.upper()] = instrument_key
            return item

    def sync_watchlist(self, instrument_pairs: List[tuple[str, str]]) -> None:
        """
        Synchronize store instruments with a new list of (instrument_key, symbol) pairs.
        Removes any keys not present in the new list, adds new ones, and maintains order.
        """
        with self._lock:
            new_keys = [pair[0] for pair in instrument_pairs]
            # Remove keys that are no longer in watchlist
            for old_key in list(self._quotes.keys()):
                if old_key not in new_keys:
                    item = self._quotes.pop(old_key, None)
                    if item:
                        self._key_by_symbol.pop(item.symbol.upper(), None)

            # Rebuild ordered keys
            self._ordered_keys = []
            for key, sym in instrument_pairs:
                clean_sym = sym or key
                if key not in self._quotes:
                    self._quotes[key] = QuoteItem(instrument_key=key, symbol=clean_sym)
                else:
                    self._quotes[key].symbol = clean_sym
                self._ordered_keys.append(key)
                self._key_by_symbol[clean_sym.upper()] = key

    def update_quote(
        self,
        instrument_key: str,
        ltp: Optional[float] = None,
        open_price: Optional[float] = None,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
        close_price: Optional[float] = None,
        volume: Optional[int] = None,
        vwap: Optional[float] = None,
        ltt: Optional[int] = None,
        prev_high: Optional[float] = None,
        prev_low: Optional[float] = None,
    ) -> None:
        """Update a quote item with latest tick/feed information."""
        with self._lock:
            if instrument_key not in self._quotes:
                self._quotes[instrument_key] = QuoteItem(instrument_key)
                self._ordered_keys.append(instrument_key)

            q = self._quotes[instrument_key]
            now_ts = time.time()
            q.last_update_ts = now_ts
            q.updated_at = datetime.now().strftime("%H:%M:%S")

            if ltt:
                try:
                    q.ltt = int(ltt)
                except (ValueError, TypeError):
                    pass
            if ltp is not None:
                try:
                    val = float(ltp)
                    if val > 0:
                        q.ltp = val
                except (ValueError, TypeError):
                    pass
            if open_price is not None:
                try:
                    val = float(open_price)
                    if val > 0:
                        q.open = val
                except (ValueError, TypeError):
                    pass
            if high_price is not None:
                try:
                    val = float(high_price)
                    if val > 0:
                        q.high = val
                except (ValueError, TypeError):
                    pass
            if low_price is not None:
                try:
                    val = float(low_price)
                    if val > 0:
                        q.low = val
                except (ValueError, TypeError):
                    pass
            if close_price is not None:
                try:
                    val = float(close_price)
                    if val > 0:
                        q.close = val
                        q.prev_close = val
                except (ValueError, TypeError):
                    pass
            if prev_high is not None:
                try:
                    val = float(prev_high)
                    if val > 0:
                        q.prev_high = val
                except (ValueError, TypeError):
                    pass
            if prev_low is not None:
                try:
                    val = float(prev_low)
                    if val > 0:
                        q.prev_low = val
                except (ValueError, TypeError):
                    pass
            if volume is not None:
                try:
                    val = int(float(volume))
                    if val >= 0:
                        q.volume = val
                except (ValueError, TypeError):
                    pass
            if vwap is not None:
                try:
                    val = float(vwap)
                    if val > 0:
                        q.vwap = val
                except (ValueError, TypeError):
                    pass

            # Recompute Change if we have LTP and Previous Close
            ref_close = q.close or q.prev_close
            if q.ltp > 0 and ref_close > 0:
                q.change = q.ltp - ref_close
            elif q.ltp > 0 and q.open > 0:
                q.change = q.ltp - q.open

    def update_prev_day_stats(
        self,
        instrument_key: str,
        prev_high: Optional[float] = None,
        prev_low: Optional[float] = None,
        prev_close: Optional[float] = None,
    ) -> None:
        """Update historical previous day stats (P HIGH, P. LOW, P.CLOSE)."""
        with self._lock:
            if instrument_key not in self._quotes:
                self._quotes[instrument_key] = QuoteItem(instrument_key)
                self._ordered_keys.append(instrument_key)
            q = self._quotes[instrument_key]
            if prev_high is not None and prev_high > 0:
                q.prev_high = float(prev_high)
            if prev_low is not None and prev_low > 0:
                q.prev_low = float(prev_low)
            if prev_close is not None and prev_close > 0:
                q.close = float(prev_close)
                q.prev_close = float(prev_close)

    def get_quote_item(self, key_or_symbol: str) -> Optional[QuoteItem]:
        """Return the internal QuoteItem reference by instrument_key or symbol."""
        with self._lock:
            if key_or_symbol in self._quotes:
                return self._quotes[key_or_symbol]
            key = self._key_by_symbol.get(key_or_symbol.upper())
            if key and key in self._quotes:
                return self._quotes[key]
            return None

    def get_snapshot_matrix(self, include_headers: bool = True) -> List[List[Any]]:
        """Get 2D table representing all registered quotes for Excel or Google Sheets."""
        with self._lock:
            matrix: List[List[Any]] = []
            if include_headers:
                matrix.append(list(self.HEADERS))

            for key in self._ordered_keys:
                item = self._quotes.get(key)
                if item:
                    matrix.append(item.to_row())

            return matrix

    def get_all_quotes_dict(self) -> Dict[str, Dict[str, Any]]:
        """Get all quotes as dictionary keyed by symbol."""
        with self._lock:
            return {item.symbol: item.to_dict() for item in self._quotes.values()}

    def get_quote_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Lookup quote by symbol name or instrument key."""
        with self._lock:
            # Check by symbol lookup
            key = self._key_by_symbol.get(symbol.upper())
            if key and key in self._quotes:
                return self._quotes[key].to_dict()
            # Check directly by instrument_key
            if symbol in self._quotes:
                return self._quotes[symbol].to_dict()
            return None

    def get_registered_keys(self) -> List[str]:
        """Return list of all registered instrument keys."""
        with self._lock:
            return list(self._ordered_keys)

    def count(self) -> int:
        with self._lock:
            return len(self._quotes)
