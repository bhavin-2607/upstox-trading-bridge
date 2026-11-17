"""Unit tests for SoundEngine audio playback and synthesis."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from upstox_bridge.core.config import settings
from upstox_bridge.core.sound_engine import SoundEngine, SoundEvent


class TestSoundEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sounds_path = Path(self.temp_dir.name)
        self.engine = SoundEngine(sounds_dir=self.sounds_path)

    def tearDown(self):
        self.engine.stop()
        self.temp_dir.cleanup()

    def test_synthesized_wav_files_created(self):
        """Verify all standard sound event WAV files are generated and valid."""
        expected_events = [
            SoundEvent.TARGET_HIT,
            SoundEvent.APPROACHING,
            SoundEvent.STOP_LOSS,
            SoundEvent.SIGNAL_BUY,
            SoundEvent.SIGNAL_SELL,
            SoundEvent.CONNECTED,
            SoundEvent.SCRIPT_ADDED,
            SoundEvent.DISCONNECTED,
        ]
        for evt in expected_events:
            wav_file = self.sounds_path / f"{evt}.wav"
            self.assertTrue(wav_file.exists(), f"Missing WAV for {evt}")
            self.assertGreater(wav_file.stat().st_size, 1000, f"WAV file too small for {evt}")

    @patch.object(SoundEngine, "_play_sync")
    def test_play_dispatches_to_queue(self, mock_play):
        """Verify play method enqueues events without blocking."""
        self.engine.play(SoundEvent.TARGET_HIT, cooldown_sec=0.0)
        # Give worker a split-second to process
        import time
        time.sleep(0.1)
        mock_play.assert_called_with(SoundEvent.TARGET_HIT)

    @patch.object(SoundEngine, "_play_sync")
    def test_cooldown_rate_limiting(self, mock_play):
        """Verify cooldown suppresses rapid repetitive sounds."""
        self.engine.play(SoundEvent.APPROACHING, cooldown_sec=2.0)
        self.engine.play(SoundEvent.APPROACHING, cooldown_sec=2.0)
        import time
        time.sleep(0.1)
        self.assertEqual(mock_play.call_count, 1)


if __name__ == "__main__":
    unittest.main()
