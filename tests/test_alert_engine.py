"""Unit tests for AlertEngine 2-stage price alert and signal system."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from upstox_bridge.core.alert_engine import AlertCondition, AlertEngine, AlertStatus, AlertType
from upstox_bridge.core.config import settings
from upstox_bridge.core.sound_engine import SoundEvent


class TestAlertEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_file = Path(self.temp_dir.name) / "test_alerts.json"
        self.engine = AlertEngine(storage_path=self.storage_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_and_remove_alert(self):
        alert = self.engine.add_alert(
            symbol="RELIANCE",
            target_price=1350.0,
            condition="ABOVE",
            proximity_pct=0.25,
            note="Breakout",
        )
        self.assertEqual(alert.symbol, "RELIANCE")
        self.assertEqual(alert.target_price, 1350.0)
        self.assertEqual(alert.condition, "ABOVE")
        self.assertEqual(alert.status, AlertStatus.ACTIVE)

        alerts = self.engine.get_alerts()
        self.assertEqual(len(alerts), 1)

        # Persistence check
        self.assertTrue(self.storage_file.exists())

        # Remove
        removed = self.engine.remove_alert(alert.id)
        self.assertTrue(removed)
        self.assertEqual(len(self.engine.get_alerts()), 0)

    @patch("upstox_bridge.core.alert_engine.sound_engine.play")
    def test_two_stage_alert_lifecycle_above(self, mock_sound):
        """Test Stage 1 (Approaching) then Stage 2 (Target Hit) for an ABOVE alert."""
        alert = self.engine.add_alert(
            symbol="TCS",
            target_price=2500.0,
            condition="ABOVE",
            proximity_pct=0.25,  # 0.25% of 2500 is 6.25 -> buffer is 2493.75 to 2500
            current_ltp=2480.0,
        )

        # 1. Price is far below buffer (2485.0) -> No event
        transitions = self.engine.evaluate_tick("TCS", 2485.0)
        self.assertEqual(len(transitions), 0)
        self.assertEqual(alert.status, AlertStatus.ACTIVE)
        mock_sound.assert_not_called()

        # 2. Price enters proximity buffer (2495.0, distance = 0.2% <= 0.25%) -> Stage 1: APPROACHING
        transitions = self.engine.evaluate_tick("TCS", 2495.0)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0][1], "APPROACHING")
        self.assertEqual(alert.status, AlertStatus.APPROACHING)
        mock_sound.assert_called_with(SoundEvent.APPROACHING)

        mock_sound.reset_mock()

        # 3. Price hovers in buffer (2497.0) -> Does not re-fire approaching sound
        transitions = self.engine.evaluate_tick("TCS", 2497.0)
        self.assertEqual(len(transitions), 0)
        self.assertEqual(alert.status, AlertStatus.APPROACHING)
        mock_sound.assert_not_called()

        # 4. Price touches or crosses target (2500.50) -> Stage 2: TRIGGERED
        transitions = self.engine.evaluate_tick("TCS", 2500.50)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0][1], "TRIGGERED")
        self.assertEqual(alert.status, AlertStatus.TRIGGERED)
        self.assertIsNotNone(alert.triggered_at)
        mock_sound.assert_called_with(SoundEvent.TARGET_HIT)

        mock_sound.reset_mock()

        # 5. Price continues fluctuating past target -> No duplicate firing
        transitions = self.engine.evaluate_tick("TCS", 2505.0)
        self.assertEqual(len(transitions), 0)
        mock_sound.assert_not_called()

    @patch("upstox_bridge.core.alert_engine.sound_engine.play")
    def test_two_stage_alert_lifecycle_below(self, mock_sound):
        """Test Stage 1 (Approaching) then Stage 2 (Target Hit) for a BELOW alert (Support / Target)."""
        alert = self.engine.add_alert(
            symbol="INFY",
            target_price=1000.0,
            condition="BELOW",
            proximity_pct=0.5,  # buffer: 1000 to 1005
            current_ltp=1020.0,
        )

        # 1. Approaching buffer from above (1004.0)
        transitions = self.engine.evaluate_tick("INFY", 1004.0)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0][1], "APPROACHING")
        self.assertEqual(alert.status, AlertStatus.APPROACHING)
        mock_sound.assert_called_with(SoundEvent.APPROACHING)

        mock_sound.reset_mock()

        # 2. Target hit (999.0)
        transitions = self.engine.evaluate_tick("INFY", 999.0)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0][1], "TRIGGERED")
        self.assertEqual(alert.status, AlertStatus.TRIGGERED)
        mock_sound.assert_called_with(SoundEvent.TARGET_HIT)

    @patch("upstox_bridge.core.alert_engine.sound_engine.play")
    def test_hysteresis_reset_when_price_retreats(self, mock_sound):
        """Test that if price enters approaching buffer then pulls back significantly, status resets to ACTIVE."""
        alert = self.engine.add_alert(
            symbol="SBIN",
            target_price=1000.0,
            condition="ABOVE",
            proximity_pct=0.25,  # 0.25% buffer is 997.5 to 1000. 1.5x hysteresis threshold is 996.25
        )

        # Enter buffer (998.0) -> APPROACHING
        self.engine.evaluate_tick("SBIN", 998.0)
        self.assertEqual(alert.status, AlertStatus.APPROACHING)

        # Price pulls back safely below 996.0 (distance > 0.375%) -> Resets to ACTIVE
        self.engine.evaluate_tick("SBIN", 994.0)
        self.assertEqual(alert.status, AlertStatus.ACTIVE)

        mock_sound.reset_mock()

        # Price returns to buffer (998.5) -> Can approach again
        transitions = self.engine.evaluate_tick("SBIN", 998.5)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(alert.status, AlertStatus.APPROACHING)
        mock_sound.assert_called_with(SoundEvent.APPROACHING)

    @patch("upstox_bridge.core.alert_engine.sound_engine.play")
    def test_bst_auto_target_monitoring(self, mock_sound):
        """Test automatic BST sheet SL and TGT1 monitoring when enabled."""
        with patch.dict(os.environ, {"ALERT_AUTO_BST_ENABLED": "true"}):
            self.engine.update_bst_targets(
                symbol="HDFCBANK",
                entry=800.0,
                sl=790.0,
                tgt1=815.0,
            )

            # Hit Stop Loss at 789.0
            transitions = self.engine.evaluate_tick("HDFCBANK", 789.0)
            self.assertTrue(any(a.alert_type == AlertType.BST_SL for a, _ in transitions))
            mock_sound.assert_called_with(SoundEvent.STOP_LOSS)

    @patch("upstox_bridge.core.alert_engine.sound_engine.play")
    def test_trading_signal_flips(self, mock_sound):
        """Test SUPER and INTRA signal changes trigger BUY and SELL sounds."""
        with patch.dict(os.environ, {"SOUND_SIGNALS_ENABLED": "true"}):
            # 1. Flip to BUY
            self.engine.evaluate_signal_change("RELIANCE", super_sig="BUY", intra_sig="WAIT")
            mock_sound.assert_called_with(SoundEvent.SIGNAL_BUY)

            mock_sound.reset_mock()

            # 2. Same signal again -> No duplicate sound
            self.engine.evaluate_signal_change("RELIANCE", super_sig="BUY", intra_sig="WAIT")
            mock_sound.assert_not_called()

            # 3. Flip to SELL
            self.engine.evaluate_signal_change("RELIANCE", super_sig="SELL", intra_sig="WAIT")
            mock_sound.assert_called_with(SoundEvent.SIGNAL_SELL)


if __name__ == "__main__":
    unittest.main()
