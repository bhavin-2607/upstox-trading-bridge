"""Upstox WebSocket V3 Feed Streamer with auto-reconnect and MarketStore integration."""

from __future__ import annotations

import logging
from typing import Callable, List, Optional
import upstox_client
from upstox_client.feeder.market_data_streamer_v3 import MarketDataStreamerV3

from upstox_bridge.core.config import settings
from upstox_bridge.core.market_store import MarketStore

logger = logging.getLogger("FeedStreamer")


class UpstoxFeedStreamer:
    """Manages connection to Upstox WebSocket market feed."""

    def __init__(
        self,
        access_token: str,
        market_store: MarketStore,
        instrument_keys: Optional[List[str]] = None,
        mode: str = "full",
        on_tick_callback: Optional[Callable[[str], None]] = None,
    ):
        self.access_token = access_token
        self.market_store = market_store
        self.subscribed_keys = set(instrument_keys or [])
        self.mode = mode.lower() if mode.lower() in ("full", "ltpc") else "full"
        self.on_tick_callback = on_tick_callback

        # Configure Upstox API Client
        config = upstox_client.Configuration()
        config.access_token = self.access_token
        self.api_client = upstox_client.ApiClient(config)

        # Initialize Upstox V3 Market Data Streamer
        feed_mode = MarketDataStreamerV3.Mode["FULL"] if self.mode == "full" else MarketDataStreamerV3.Mode["LTPC"]
        self.streamer = MarketDataStreamerV3(
            api_client=self.api_client,
            instrumentKeys=list(self.subscribed_keys),
            mode=feed_mode,
        )

        self._is_connected = False
        self._bind_events()

    def _bind_events(self) -> None:
        """Attach event handlers to Upstox streamer."""
        self.streamer.on(MarketDataStreamerV3.Event["OPEN"], self._on_open)
        self.streamer.on(MarketDataStreamerV3.Event["CLOSE"], self._on_close)
        self.streamer.on(MarketDataStreamerV3.Event["ERROR"], self._on_error)
        self.streamer.on(MarketDataStreamerV3.Event["MESSAGE"], self._on_message)

    def _on_open(self, *args, **kwargs) -> None:
        self._is_connected = True
        logger.info(f"WebSocket connected to Upstox. Subscribed to {len(self.subscribed_keys)} instruments.")

    def _on_close(self, *args, **kwargs) -> None:
        self._is_connected = False
        logger.warning(f"WebSocket connection closed. Args: {args}")

    def _on_error(self, *args, **kwargs) -> None:
        logger.error(f"WebSocket error: {args}")

    def _on_message(self, message_dict: dict) -> None:
        """Process incoming decoded tick dictionary."""
        try:
            feeds = message_dict.get("feeds", {})
            if not isinstance(feeds, dict):
                return

            for key, feed_data in feeds.items():
                ltp, open_p, high_p, low_p, close_p, vol, vwap, ltt = None, None, None, None, None, None, None, None

                # 1. Full Feed (Index or Stock)
                full_feed = feed_data.get("fullFeed", {})
                ff_data = full_feed.get("marketFF") or full_feed.get("indexFF") or {}

                # 2. LTPC block
                ltpc = ff_data.get("ltpc") or feed_data.get("ltpc") or {}
                ltp = ltpc.get("ltp")
                close_p = ltpc.get("cp")  # Official Previous Close from Upstox
                ltt = ltpc.get("ltt")

                # 3. Volume & VWAP (ATP)
                vol = ff_data.get("vtt", 0)
                vwap = ff_data.get("atp") or feed_data.get("atp")

                # 4. OHLC candles (prioritize daily 1d candle for Day Open, High, Low, Prev Close)
                ohlc_list = ff_data.get("marketOHLC", {}).get("ohlc", [])
                for candle in ohlc_list:
                    interval = candle.get("interval")
                    if interval == "1d":
                        if candle.get("open") is not None:
                            open_p = candle.get("open")
                        if candle.get("high") is not None:
                            high_p = candle.get("high")
                        if candle.get("low") is not None:
                            low_p = candle.get("low")
                        if candle.get("close") is not None and not close_p:
                            close_p = candle.get("close")
                        if candle.get("vol") is not None and not vol:
                            vol = candle.get("vol")
                    elif interval == "I1" and open_p is None:
                        open_p = candle.get("open")
                        high_p = candle.get("high")
                        low_p = candle.get("low")

                # Update in-memory store
                self.market_store.update_quote(
                    instrument_key=key,
                    ltp=ltp,
                    open_price=open_p,
                    high_price=high_p,
                    low_price=low_p,
                    close_price=close_p,
                    volume=vol,
                    vwap=vwap,
                    ltt=ltt,
                )

                if self.on_tick_callback:
                    self.on_tick_callback(key)

        except Exception as e:
            logger.debug(f"Error parsing market message: {e}")

    def connect(self) -> None:
        """Connect WebSocket to Upstox."""
        logger.info("Connecting to Upstox live feed...")
        self.streamer.connect()

    def disconnect(self) -> None:
        """Disconnect WebSocket."""
        if self._is_connected:
            self.streamer.disconnect()

    def subscribe(self, instrument_keys: List[str]) -> None:
        """Dynamically subscribe to new instrument keys."""
        new_keys = [k for k in instrument_keys if k not in self.subscribed_keys]
        if not new_keys:
            return

        feed_mode = MarketDataStreamerV3.Mode["FULL"] if self.mode == "full" else MarketDataStreamerV3.Mode["LTPC"]
        self.streamer.subscribe(new_keys, feed_mode)
        self.subscribed_keys.update(new_keys)
        logger.info(f"Subscribed to {len(new_keys)} new instrument(s): {new_keys}")

    def unsubscribe(self, instrument_keys: List[str]) -> None:
        """Unsubscribe from instrument keys."""
        if not instrument_keys:
            return
        self.streamer.unsubscribe(instrument_keys)
        self.subscribed_keys.difference_update(instrument_keys)

    @property
    def is_connected(self) -> bool:
        return self._is_connected
