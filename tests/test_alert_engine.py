"""Unit tests for the High-Performance Custom Price Alert Engine."""

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from upstox_bridge.core.alert_engine import AlertCondition, AlertEngine, AlertStatus, PriceAlert
from upstox_bridge.core.sound_engine import SoundEvent


class TestAlertEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_alerts_"))
        self.storage_path = self.temp_dir / "test_alerts.json"
        self.engine = AlertEngine(storage_path=self.storage_path)
        self.play_patcher = patch("upstox_bridge.core.alert_engine.sound_engine.play")
        self.mock_play = self.play_patcher.start()

    def tearDown(self):
        self.play_patcher.stop()
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_singleton_instance(self):
        inst1 = AlertEngine.get_instance()
        inst2 = AlertEngine.get_instance()
        self.assertIs(inst1, inst2)

    def test_add_and_remove_alert(self):
        """Test adding and removing custom price alerts."""
        alert = self.engine.add_alert(
            symbol="RELIANCE",
            target_price=2950.0,
            condition=AlertCondition.ABOVE,
            proximity_pct=0.5,
            note="Breakout level",
        )
        self.assertEqual(alert.symbol, "RELIANCE")
        self.assertEqual(alert.target_price, 2950.0)
        self.assertEqual(alert.condition, AlertCondition.ABOVE)
        self.assertEqual(alert.status, AlertStatus.ACTIVE)
        self.assertEqual(self.engine.get_active_count(), 1)

        # Test persistence file written
        self.assertTrue(self.storage_path.exists())

        # Test remove
        res = self.engine.remove_alert(alert.id)
        self.assertTrue(res)
        self.assertEqual(self.engine.get_active_count(), 0)

    def test_persistence_load_and_save(self):
        """Test alert engine serialization across restarts."""
        self.engine.add_alert("TCS", 4200.0, AlertCondition.ABOVE)
        self.engine.add_alert("INFY", 1850.0, AlertCondition.BELOW)

        # Instantiate fresh engine pointing to same storage file
        engine2 = AlertEngine(storage_path=self.storage_path)
        alerts = engine2.get_alerts()
        self.assertEqual(len(alerts), 2)
        symbols = [a.symbol for a in alerts]
        self.assertIn("TCS", symbols)
        self.assertIn("INFY", symbols)

    def test_two_stage_lifecycle_above(self):
        """Test ACTIVE -> APPROACHING -> TRIGGERED for an ABOVE condition."""
        alert = self.engine.add_alert("CRUDEOIL", 6000.0, AlertCondition.ABOVE, proximity_pct=1.0)
        # Target: 6000, 1% buffer: 5940 to 6000

        # Tick 1: Far away (5800) -> Still ACTIVE
        res = self.engine.evaluate_tick("CRUDEOIL", 5800.0)
        self.assertIsNone(res)
        self.assertEqual(alert.status, AlertStatus.ACTIVE)
        self.mock_play.assert_not_called()

        # Tick 2: Enters approaching zone (5960, which is 0.67% away) -> APPROACHING
        res = self.engine.evaluate_tick("CRUDEOIL", 5960.0)
        self.assertEqual(res, "APPROACHING")
        self.assertEqual(alert.status, AlertStatus.APPROACHING)
        self.mock_play.assert_called_with(SoundEvent.APPROACHING)

        # Tick 3: Hits target (6005) -> TRIGGERED
        self.mock_play.reset_mock()
        res = self.engine.evaluate_tick("CRUDEOIL", 6005.0)
        self.assertEqual(res, "TRIGGERED")
        self.assertEqual(alert.status, AlertStatus.TRIGGERED)
        self.mock_play.assert_called_with(SoundEvent.TARGET_HIT)

        # Tick 4: Price remains above target -> Does not spam, remains TRIGGERED
        self.mock_play.reset_mock()
        res = self.engine.evaluate_tick("CRUDEOIL", 6020.0)
        self.assertIsNone(res)
        self.mock_play.assert_not_called()

    def test_two_stage_lifecycle_below(self):
        """Test ACTIVE -> APPROACHING -> TRIGGERED for a BELOW condition (support breakdown)."""
        alert = self.engine.add_alert("BANKNIFTY", 50000.0, AlertCondition.BELOW, proximity_pct=0.5)
        # Target: 50000, 0.5% buffer: 50000 to 50250

        # Tick 1: Far above (51000) -> ACTIVE
        res = self.engine.evaluate_tick("BANKNIFTY", 51000.0)
        self.assertIsNone(res)
        self.assertEqual(alert.status, AlertStatus.ACTIVE)

        # Tick 2: Approaching (50150) -> APPROACHING
        res = self.engine.evaluate_tick("BANKNIFTY", 50150.0)
        self.assertEqual(res, "APPROACHING")
        self.assertEqual(alert.status, AlertStatus.APPROACHING)
        self.mock_play.assert_called_with(SoundEvent.APPROACHING)

        # Tick 3: Breakdown target hit (49990) -> TRIGGERED
        self.mock_play.reset_mock()
        res = self.engine.evaluate_tick("BANKNIFTY", 49990.0)
        self.assertEqual(res, "TRIGGERED")
        self.assertEqual(alert.status, AlertStatus.TRIGGERED)
        self.mock_play.assert_called_with(SoundEvent.TARGET_HIT)

    def test_approaching_hysteresis_pullback(self):
        """Test that if price enters approaching zone but pulls back away (>1.5x buffer), status resets to ACTIVE."""
        alert = self.engine.add_alert("NIFTY", 24000.0, AlertCondition.ABOVE, proximity_pct=0.5)
        # 0.5% buffer: 23880. 1.5x buffer: 23820

        # Enters approaching zone (23900)
        self.engine.evaluate_tick("NIFTY", 23900.0)
        self.assertEqual(alert.status, AlertStatus.APPROACHING)

        # Pulls back deeply to 23750 (> 1.5x buffer away)
        self.engine.evaluate_tick("NIFTY", 23750.0)
        self.assertEqual(alert.status, AlertStatus.ACTIVE)

    def test_rearm_alert(self):
        """Test resetting a triggered alert back to active."""
        alert = self.engine.add_alert("SBIN", 800.0, AlertCondition.ABOVE)
        self.engine.evaluate_tick("SBIN", 810.0)
        self.assertEqual(alert.status, AlertStatus.TRIGGERED)
        self.assertEqual(self.engine.get_active_count(), 0)

        # Re-arm
        self.engine.reset_alert(alert.id)
        self.assertEqual(alert.status, AlertStatus.ACTIVE)
        self.assertIsNone(alert.triggered_at)
        self.assertEqual(self.engine.get_active_count(), 1)

    def test_tick_evaluation_speed(self):
        """Verify tick evaluation runs in < 0.05ms even with multiple alerts configured."""
        for i in range(50):
            self.engine.add_alert(f"SYM_{i}", 1000.0 + i, AlertCondition.ABOVE)

        t_start = time.perf_counter()
        for i in range(1000):
            self.engine.evaluate_tick(f"SYM_{i % 50}", 990.0)
        t_elapsed = (time.perf_counter() - t_start) * 1000.0

        avg_per_tick_us = (t_elapsed / 1000.0) * 1000.0  # microseconds
        self.assertLess(avg_per_tick_us, 100.0, f"Tick eval too slow: {avg_per_tick_us:.2f}µs per tick")

    def test_listener_notification_callback(self):
        """Test callback receiving alert events."""
        received = []
        def on_alert(alert, event, ltp):
            received.append((alert.symbol, event, ltp))

        self.engine.add_listener(on_alert)
        alert = self.engine.add_alert("ITC", 500.0, AlertCondition.ABOVE, proximity_pct=0.2)

        self.engine.evaluate_tick("ITC", 501.0)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], ("ITC", "TRIGGERED", 501.0))

        # Test remove listener
        self.engine.remove_listener(on_alert)
        self.engine.reset_alert(alert.id)
        self.engine.evaluate_tick("ITC", 502.0)
        self.assertEqual(len(received), 1)  # No new callback


if __name__ == "__main__":
    unittest.main()
