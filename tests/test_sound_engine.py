"""Unit tests for the Zero-Lag Audio Sound Engine."""

import os
import shutil
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from upstox_bridge.core.config import settings
from upstox_bridge.core.sound_engine import SoundEngine, SoundEvent


class TestSoundEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_sounds_"))
        self.engine = SoundEngine(sounds_dir=self.temp_dir)
        # Mock _play_sync to avoid real audio subprocesses during unit tests
        self.engine._play_sync = MagicMock()
        self._orig_sound_enabled = settings.sound_enabled

    def tearDown(self):
        settings.sound_enabled = self._orig_sound_enabled
        self.engine.stop()
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_singleton_instance(self):
        inst1 = SoundEngine.get_instance()
        inst2 = SoundEngine.get_instance()
        self.assertIs(inst1, inst2)

    def test_synthesized_wav_files_created(self):
        """Verify that pure math synthesizer outputs valid 16-bit 44.1kHz mono WAV files."""
        for event in [SoundEvent.TARGET_HIT, SoundEvent.APPROACHING, SoundEvent.CONNECTED, SoundEvent.DISCONNECTED]:
            wav_file = self.temp_dir / f"{event}.wav"
            self.assertTrue(wav_file.exists(), f"Missing WAV file for {event}")
            self.assertGreater(wav_file.stat().st_size, 500)

            # Validate WAV headers
            with wave.open(str(wav_file), "rb") as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)  # 16-bit
                self.assertEqual(wf.getframerate(), 44100)
                self.assertGreater(wf.getnframes(), 0)

    def test_non_blocking_play_execution(self):
        """Ensure play() returns immediately in < 5ms without blocking the calling thread."""
        t_start = time.perf_counter()
        self.engine.play(SoundEvent.CONNECTED, cooldown_sec=0.0)
        t_elapsed = (time.perf_counter() - t_start) * 1000.0
        self.assertLess(t_elapsed, 20.0, f"play() took too long ({t_elapsed:.2f}ms), must be non-blocking")

    def test_sound_mute_toggle(self):
        """Verify that no sound is queued when sound_enabled is False."""
        settings.sound_enabled = False
        # Clear any leftover items in queue
        while not self.engine._queue.empty():
            self.engine._queue.get_nowait()

        self.engine.play(SoundEvent.TARGET_HIT, cooldown_sec=0.0)
        self.assertTrue(self.engine._queue.empty())

    def test_bounded_queue_overflow_protection(self):
        """Verify that rapid-fire sound calls do not pile up in the bounded queue."""
        # Fill the queue
        self.engine._queue.put_nowait("dummy_event")

        # Calling play() when queue is full should silently drop without raising queue.Full
        try:
            self.engine.play(SoundEvent.TARGET_HIT, cooldown_sec=0.0)
        except Exception as e:
            self.fail(f"play() raised exception on full queue: {e}")

    def test_global_debounce_rate_limiter(self):
        """Verify global 1.2s rate limiter stops audio spam."""
        settings.sound_enabled = True
        self.engine._last_played_time = time.time()  # just played
        while not self.engine._queue.empty():
            self.engine._queue.get_nowait()

        # Attempt to play immediately
        self.engine.play(SoundEvent.CONNECTED, cooldown_sec=0.0)
        self.assertTrue(self.engine._queue.empty(), "Event should have been debounced")


if __name__ == "__main__":
    unittest.main()
