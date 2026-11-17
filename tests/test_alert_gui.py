"""Unit tests for Audio and Price Alert GUI components."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from upstox_bridge.core.alert_engine import AlertCondition, AlertEngine, AlertStatus, PriceAlert
from upstox_bridge.core.config import settings
from upstox_bridge.core.sound_engine import SoundEvent


class TestAlertGui(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = Path(self.temp_dir.name) / "test_gui_alerts.json"
        self.engine = AlertEngine(storage_path=self.storage)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_alert_engine_listener_notification(self):
        """Verify GUI listener is called with proper arguments when an alert hits."""
        received = []

        def _callback(alert, event, ltp):
            received.append((alert.symbol, event, ltp))

        self.engine.add_listener(_callback)
        alert = self.engine.add_alert(
            symbol="RELIANCE",
            target_price=1300.0,
            condition="ABOVE",
            proximity_pct=0.25,
        )

        with patch("upstox_bridge.core.alert_engine.sound_engine.play"):
            self.engine.evaluate_tick("RELIANCE", 1301.0)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], ("RELIANCE", "TRIGGERED", 1301.0))

        # Test remove listener
        self.engine.remove_listener(_callback)
        with patch("upstox_bridge.core.alert_engine.sound_engine.play"):
            self.engine.evaluate_tick("RELIANCE", 1302.0)
        self.assertEqual(len(received), 1)

    def test_signal_listener_notification(self):
        """Verify signal listener receives flips."""
        signals_received = []

        def _sig_callback(sym, s_type, s_val):
            signals_received.append((sym, s_type, s_val))

        self.engine.add_signal_listener(_sig_callback)

        with patch.dict(os.environ, {"SOUND_SIGNALS_ENABLED": "true"}):
            with patch("upstox_bridge.core.alert_engine.sound_engine.play"):
                self.engine.evaluate_signal_change("BANKNIFTY", super_sig="BUY", intra_sig="")

        self.assertEqual(len(signals_received), 1)
        self.assertEqual(signals_received[0], ("BANKNIFTY", "SUPER", "BUY"))


if __name__ == "__main__":
    unittest.main()
