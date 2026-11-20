"""Upstox Instrument Master downloader and Symbol Resolver."""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from upstox_bridge.core.config import settings

logger = logging.getLogger("InstrumentMaster")

UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
}

COMMODITY_SYMBOLS = {
    "GOLD", "GOLDM", "SILVER", "SILVERM", "SILVERMIC", "CRUDEOIL", "CRUDE", "CRUDEOILM",
    "NATURALGAS", "NATGASMINI", "COPPER", "ZINC", "ZINCMINI", "ALUMINIUM", "ALUMINI",
    "LEAD", "LEADMINI", "NICKEL", "COTTON", "MENTHAOIL"
}

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
        self._by_underlying: Dict[str, List[Dict[str, Any]]] = {}
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
            resp = requests.get(UPSTOX_INSTRUMENTS_URL, headers=headers, timeout=5)
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
        self._by_key.clear()
        self._by_symbol.clear()
        self._by_underlying.clear()

        def _item_priority(item: Dict[str, Any]) -> int:
            k = item.get("instrument_key", "")
            ex = item.get("exchange", "")
            if "NSE_EQ" in k or "NSE_INDEX" in k:
                return 100
            if "MCX_FO" in k or ex == "MCX":
                return 90
            if "NSE_FO" in k:
                return 80
            if "BSE_EQ" in k or "BSE_INDEX" in k:
                return 50
            if "NSE_COM" in k:
                return 40
            return 10

        for item in records:
            key = item.get("instrument_key")
            symbol = item.get("trading_symbol")
            if not key:
                continue

            self._by_key[key] = item

            if symbol:
                clean_sym = symbol.upper().strip()
                existing = self._by_symbol.get(clean_sym)
                if existing is None or _item_priority(item) > _item_priority(existing):
                    self._by_symbol[clean_sym] = item

            # Index by underlying / asset / name / first token for fast lookup
            underlyings = set()
            for field in ("name", "underlying_symbol", "asset_symbol"):
                val = item.get(field)
                if val and isinstance(val, str):
                    underlyings.add(val.upper().strip())
            if symbol:
                first = symbol.upper().strip().split()[0]
                if first:
                    underlyings.add(first)
            for u in underlyings:
                self._by_underlying.setdefault(u, []).append(item)

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
            self._by_underlying.setdefault(sym.upper(), []).append(record)

    @staticmethod
    def clean_script_symbol(raw_symbol: str) -> str:
        """
        Strip Google Finance or broker prefixes (e.g. 'INDEXNSE:NIFTY_50' -> 'NIFTY 50',
        'NSE:AARTIIND' -> 'AARTIIND', 'NSE:RELIANCE' -> 'RELIANCE').
        """
        clean = raw_symbol.strip()
        if "|" in clean:
            return clean

        upper_raw = clean.upper()
        for prefix in ("INDEXNSE:", "INDEXBSE:", "NSE:", "BSE:", "MCX:"):
            if upper_raw.startswith(prefix):
                clean = clean[len(prefix):]
                break

        # Common index formatting from Google Finance
        upper_clean = clean.upper().strip()
        if upper_clean == "NIFTY_50":
            return "NIFTY 50"
        if upper_clean == "NIFTY_BANK":
            return "NIFTY BANK"
        if upper_clean == "NIFTY_IT":
            return "NIFTY IT"
        if upper_clean == "NIFTY_FIN_SERVICE":
            return "FINNIFTY"

        return clean.strip()

    def resolve_symbol(self, symbol_or_key: str) -> str:
        """
        Convert human trading symbol (e.g. 'RELIANCE', 'NIFTY 50', 'GOLD DEC FUT',
        'MCX COPPER FUT', 'NIFTY 29 DEC 24000 PE', or Google Finance 'INDEXNSE:NIFTY_50')
        into exact instrument key. If already an instrument key (contains '|'), returns as is.
        """
        clean = self.clean_script_symbol(symbol_or_key)
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

        # 4. Check for exchange prefix (e.g. 'MCX COPPER FUT' or 'MCX:COPPER FUT' or 'NSE RELIANCE')
        target_exchange = None
        stripped_query = upper
        for ex in ("MCX", "NSE", "BSE"):
            if upper.startswith((f"{ex}:", f"{ex} ")):
                target_exchange = ex
                stripped_query = upper[len(ex) + 1:].strip()
                break

        if stripped_query in self._by_symbol:
            item = self._by_symbol[stripped_query]
            if target_exchange is None or item.get("exchange") == target_exchange:
                return item.get("instrument_key", clean)

        # 5. Smart options resolver (e.g. 'NIFTY 29 DEC 24000 PE', 'NIFTY 29 DEC 24000 CE', 'NIFTY 24000 PE')
        opt_key = self._resolve_option_query(stripped_query, target_exchange=target_exchange)
        if opt_key:
            return opt_key

        # 6. Smart futures resolver (e.g. 'MCX COPPER FUT', 'COPPER FUT', 'COPPER DEC FUT', 'GOLD DEC FUT')
        fut_key = self._resolve_future_query(stripped_query, target_exchange=target_exchange)
        if fut_key:
            return fut_key

        # 7. Smart token-based fuzzy resolver fallback
        fuzzy_match = self._smart_fuzzy_resolve(stripped_query, target_exchange=target_exchange)
        if fuzzy_match:
            return fuzzy_match

        # 8. Default assumption: MCX for commodities, NSE_EQ for equities
        is_commodity = any(c in upper for c in COMMODITY_SYMBOLS)
        if is_commodity or target_exchange == "MCX":
            return f"MCX_FO|{stripped_query}"
        return f"NSE_EQ|{stripped_query}"

    def _resolve_option_query(self, query: str, target_exchange: Optional[str] = None) -> Optional[str]:
        """
        Directly parse and resolve options queries in formats such as:
        - SYMBOL EXPIRY STRIKE CE/PE (e.g. 'NIFTY 29 DEC 24000 PE', 'NIFTY 29 DEC 24000 CE')
        - SYMBOL STRIKE CE/PE EXPIRY (e.g. 'NIFTY 24000 PE 29 DEC', 'NIFTY 26000 CE 23 NOV')
        - SYMBOL STRIKE CE/PE (e.g. 'NIFTY 24000 PE', 'NIFTY 26000 CE', 'NIFTY 26000 CE NEXT')
        """
        tokens = re.findall(r"[A-Za-z0-9]+", query.upper())
        if not tokens:
            return None

        opt_type = None
        for t in tokens:
            if t in ("CE", "CALL"):
                opt_type = "CE"
            elif t in ("PE", "PUT"):
                opt_type = "PE"
        if not opt_type:
            return None

        want_next_week = any(t in ("NEXT", "NEXTWEEK") for t in tokens)
        clean_tokens = [t for t in tokens if t not in ("CE", "PE", "CALL", "PUT", "NEXT", "NEXTWEEK", "WEEK", "CURRENT", "THIS")]

        if clean_tokens and clean_tokens[0] in ("MCX", "NSE", "BSE"):
            if not target_exchange:
                target_exchange = clean_tokens[0]
            clean_tokens = clean_tokens[1:]

        exp_month = None
        month_idx = None
        for i, t in enumerate(clean_tokens):
            if t in MONTHS:
                exp_month = t
                month_idx = i
                break

        exp_day = None
        exp_year = None
        rem = [t for i, t in enumerate(clean_tokens) if i != month_idx]

        if month_idx is not None:
            if month_idx > 0 and clean_tokens[month_idx - 1].isdigit():
                val = int(clean_tokens[month_idx - 1])
                if 1 <= val <= 31:
                    exp_day = val
                    rem = [t for t in rem if t != clean_tokens[month_idx - 1]]
            elif month_idx + 1 < len(clean_tokens) and clean_tokens[month_idx + 1].isdigit():
                val = int(clean_tokens[month_idx + 1])
                if 1 <= val <= 31:
                    exp_day = val
                    rem = [t for t in rem if t != clean_tokens[month_idx + 1]]

        num_tokens = []
        text_tokens = []
        for t in rem:
            if t.isdigit():
                num_tokens.append(int(t))
            else:
                text_tokens.append(t)

        strike = None
        if num_tokens:
            if len(num_tokens) == 1:
                strike = float(num_tokens[0])
            else:
                num_tokens.sort()
                strike = float(num_tokens[-1])
                if num_tokens[0] in range(24, 35) or num_tokens[0] in range(2024, 2035):
                    exp_year = num_tokens[0]

        underlying = " ".join(text_tokens) if text_tokens else None
        if not underlying:
            return None

        cands = self._by_underlying.get(underlying, [])
        cands = [c for c in cands if c.get("instrument_type") == opt_type]
        if target_exchange:
            cands = [c for c in cands if c.get("exchange") == target_exchange]
        if strike is not None:
            cands = [c for c in cands if abs(float(c.get("strike_price", 0)) - strike) < 0.01]

        matched = []
        now_ms = time.time() * 1000
        for c in cands:
            exp_ms = c.get("expiry")
            if not exp_ms:
                continue
            dt = datetime.fromtimestamp(exp_ms / 1000)
            if exp_month and dt.month != MONTHS[exp_month]:
                continue
            if exp_day and dt.day != exp_day:
                continue
            if exp_year:
                yr = dt.year % 100 if exp_year < 100 else dt.year
                tgt_yr = exp_year % 100 if exp_year < 100 else exp_year
                if yr != tgt_yr:
                    continue
            matched.append((c, exp_ms))

        if not matched:
            return None

        matched.sort(key=lambda x: x[1])
        active = [x for x in matched if x[1] >= (now_ms - 86400000)] or matched
        if want_next_week and len(active) > 1:
            return active[1][0].get("instrument_key")
        return active[0][0].get("instrument_key")

    def _resolve_future_query(self, query: str, target_exchange: Optional[str] = None) -> Optional[str]:
        """
        Directly parse and resolve futures queries (commodities, index, stock futures) such as:
        - 'MCX COPPER FUT' -> active MCX COPPER future
        - 'COPPER FUT' -> active MCX COPPER future
        - 'MCX COPPER DEC FUT' -> active MCX COPPER Dec future
        - 'GOLD DEC FUT' -> active MCX GOLD Dec future
        """
        tokens = re.findall(r"[A-Za-z0-9]+", query.upper())
        if not tokens:
            return None

        if tokens[0] in ("MCX", "NSE", "BSE"):
            if not target_exchange:
                target_exchange = tokens[0]
            tokens = tokens[1:]

        is_fut = any(t in ("FUT", "FUTURE", "FUTURES") for t in tokens)
        clean_tokens = [t for t in tokens if t not in ("FUT", "FUTURE", "FUTURES")]

        underlying = None
        month = None
        day = None
        for t in clean_tokens:
            if t in MONTHS:
                month = t
            elif t.isdigit() and 1 <= int(t) <= 31:
                day = int(t)
            else:
                underlying = t

        if not underlying:
            return None

        # If not explicitly FUT, only treat as future if underlying in COMMODITY_SYMBOLS or is_fut
        if not is_fut and underlying not in COMMODITY_SYMBOLS:
            return None

        if not target_exchange:
            target_exchange = "MCX" if underlying in COMMODITY_SYMBOLS else "NSE"

        cands = self._by_underlying.get(underlying, [])
        fut_cands = [
            c for c in cands
            if c.get("instrument_type") in ("FUT", "FUTCOM", "FUTIDX", "FUTSTK")
            and (c.get("exchange") == target_exchange or target_exchange in c.get("segment", ""))
        ]

        matched = []
        now_ms = time.time() * 1000
        for c in fut_cands:
            exp_ms = c.get("expiry")
            if not exp_ms:
                continue
            dt = datetime.fromtimestamp(exp_ms / 1000)
            if month and dt.month != MONTHS[month]:
                continue
            if day and dt.day != day:
                continue
            matched.append((c, exp_ms))

        if not matched:
            return None

        matched.sort(key=lambda x: x[1])
        active = [x for x in matched if x[1] >= (now_ms - 86400000)] or matched
        return active[0][0].get("instrument_key")

    def _smart_fuzzy_resolve(self, query: str, target_exchange: Optional[str] = None) -> Optional[str]:
        """Fuzzy/token-based matching for commodities, futures, and options with smart expiry ranking."""
        raw_tokens = [t for t in re.findall(r"\w+", query.upper())]
        if not raw_tokens:
            return None

        want_next_week = any(t in ("NEXT", "NEXTWEEK") for t in raw_tokens)
        clean_tokens = set([t for t in raw_tokens if t not in ("NEXT", "WEEK", "CURRENT", "THIS")])
        if not clean_tokens:
            return None

        is_commodity = any(c in clean_tokens for c in COMMODITY_SYMBOLS)
        is_option = any(t in clean_tokens for t in ("CE", "PE", "CALL", "PUT"))
        is_future = any(t in clean_tokens for t in ("FUT", "FUTURE", "FUTURES"))

        # Explicit underlying index matching to avoid NIFTY matching FINNIFTY or BANKNIFTY
        underlying = None
        for idx in ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTY"):
            if idx in clean_tokens:
                underlying = idx
                break

        now_ms = time.time() * 1000
        candidates = []

        for sym_upper, item in self._by_symbol.items():
            if target_exchange and item.get("exchange") != target_exchange:
                continue
            item_tokens = set(re.findall(r"\w+", sym_upper))
            if clean_tokens.issubset(item_tokens):
                if underlying:
                    if underlying == "NIFTY" and any(x in item_tokens for x in ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")):
                        continue
                    if underlying != "NIFTY" and underlying not in item_tokens:
                        continue

                candidates.append((sym_upper, item))

        if not candidates:
            return None

        # For Options and Futures: Rank by expiry date (current week = earliest, next week = second)
        if is_option or is_future:
            with_exp = []
            for sym, item in candidates:
                exp = item.get("expiry")
                if exp and isinstance(exp, (int, float)):
                    with_exp.append((sym, item, float(exp)))

            if with_exp:
                # Sort in ascending order of expiry timestamp
                with_exp.sort(key=lambda x: x[2])
                # Filter active contracts (within 24 hours of today or later)
                active = [x for x in with_exp if x[2] >= (now_ms - 86400000)] or with_exp

                if want_next_week and len(active) > 1:
                    return active[1][1].get("instrument_key")
                return active[0][1].get("instrument_key")

        # Standard token score matching fallback
        best_key = None
        best_score = -1
        for sym_upper, item in candidates:
            item_tokens = set(re.findall(r"\w+", sym_upper))
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
