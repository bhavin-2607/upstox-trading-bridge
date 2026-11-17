"""Cross-platform non-blocking Sound Engine for trading alerts and chimes."""

from __future__ import annotations

import logging
import math
import os
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from upstox_bridge.core.config import settings

logger = logging.getLogger("SoundEngine")


class SoundEvent:
    """Standardized sound event identifiers."""
    TARGET_HIT = "target_hit"
    APPROACHING = "approaching"
    STOP_LOSS = "stop_loss"
    SIGNAL_BUY = "signal_buy"
    SIGNAL_SELL = "signal_sell"
    CONNECTED = "connected"
    DISCONNECTED = "error"
    SCRIPT_ADDED = "script_added"


class SoundEngine:
    """
    High-performance, non-blocking asynchronous audio alert engine.
    - Plays custom synthesized WAV chimes or native OS system sounds.
    - Zero external heavy audio dependencies (uses standard library wave, struct, winsound on Windows, afplay on macOS).
    - Runs in a background daemon thread with rate limiting to ensure zero GUI or COM lag.
    """

    _instance: Optional["SoundEngine"] = None

    def __init__(self, sounds_dir: Optional[Path] = None):
        self.sounds_dir = sounds_dir or (settings.root_dir / "assets" / "sounds")
        self._queue: queue.Queue[str] = queue.Queue()
        self._running = True
        self._last_played: Dict[str, float] = {}
        self._sound_paths: Dict[str, Path] = {}

        # Ensure sounds directory exists and generate pristine synthesized waves if needed
        self._init_sounds()

        # Start background worker thread
        self._thread = threading.Thread(target=self._worker, daemon=True, name="SoundEngineWorker")
        self._thread.start()

    @classmethod
    def get_instance(cls) -> "SoundEngine":
        """Get or initialize singleton instance."""
        if cls._instance is None:
            cls._instance = SoundEngine()
        return cls._instance

    def _init_sounds(self) -> None:
        """Initialize or dynamically synthesize alert WAV files."""
        try:
            self.sounds_dir.mkdir(parents=True, exist_ok=True)
            target_dir = self.sounds_dir
        except Exception:
            # Fallback to temp folder if assets/ is write-protected
            target_dir = Path(tempfile.gettempdir()) / "bsa_trading_sounds"
            target_dir.mkdir(parents=True, exist_ok=True)

        # Sound definitions: (filename, [(freq, start_sec, end_sec, decay_rate)])
        sound_recipes: Dict[str, List[Tuple[float, float, float, float]]] = {
            # 1. Target Hit: Bright dual-tone bell chime (A5 + E6 harmonics)
            SoundEvent.TARGET_HIT: [
                (880.0, 0.0, 0.85, 3.8),
                (1320.0, 0.0, 0.85, 4.5),
                (1760.0, 0.0, 0.65, 6.0),
            ],
            # 2. Approaching: Gentle two-tone warning chime (D5 -> A5)
            SoundEvent.APPROACHING: [
                (587.33, 0.0, 0.16, 6.5),
                (880.0, 0.12, 0.55, 4.5),
            ],
            # 3. Stop-Loss: Urgent dual low-tone warning (F4 -> C4)
            SoundEvent.STOP_LOSS: [
                (349.23, 0.0, 0.20, 6.0),
                (261.63, 0.14, 0.55, 4.5),
            ],
            # 4. Signal Buy: Ascending major triad arpeggio (C5 -> E5 -> G5)
            SoundEvent.SIGNAL_BUY: [
                (523.25, 0.0, 0.14, 6.0),
                (659.25, 0.10, 0.24, 6.0),
                (783.99, 0.18, 0.52, 4.5),
            ],
            # 5. Signal Sell: Descending triad chime (G5 -> E5 -> C5)
            SoundEvent.SIGNAL_SELL: [
                (783.99, 0.0, 0.14, 6.0),
                (659.25, 0.10, 0.24, 6.0),
                (523.25, 0.18, 0.52, 4.5),
            ],
            # 6. Connected / Added: Quick crisp confirmation ping (E5 -> A5)
            SoundEvent.CONNECTED: [
                (659.25, 0.0, 0.14, 7.0),
                (880.0, 0.09, 0.42, 5.0),
            ],
            SoundEvent.SCRIPT_ADDED: [
                (659.25, 0.0, 0.14, 7.0),
                (880.0, 0.09, 0.42, 5.0),
            ],
            # 7. Error: Low warning tone
            SoundEvent.DISCONNECTED: [
                (329.63, 0.0, 0.18, 6.5),
                (220.0, 0.12, 0.45, 5.0),
            ],
        }

        for event_name, notes in sound_recipes.items():
            wav_path = target_dir / f"{event_name}.wav"
            self._sound_paths[event_name] = wav_path
            if not wav_path.exists() or wav_path.stat().st_size < 100:
                try:
                    self._synthesize_wav(wav_path, notes, duration=0.85)
                except Exception as e:
                    logger.debug(f"Could not synthesize {wav_path.name}: {e}")

    @staticmethod
    def _synthesize_wav(
        filepath: Path,
        notes: List[Tuple[float, float, float, float]],
        duration: float = 0.8,
        sample_rate: int = 44100,
    ) -> None:
        """Synthesize a studio-quality 16-bit PCM mono WAV file using pure math and wave module."""
        num_samples = int(duration * sample_rate)
        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            data = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                sample_val = 0.0
                for freq, start_t, end_t, decay_rate in notes:
                    if start_t <= t <= end_t:
                        note_t = t - start_t
                        env = math.exp(-decay_rate * note_t)
                        # Add warm natural harmonics
                        val = (
                            math.sin(2 * math.pi * freq * note_t) * 0.75
                            + math.sin(4 * math.pi * freq * note_t) * 0.18
                            + math.sin(6 * math.pi * freq * note_t) * 0.07
                        )
                        sample_val += val * env
                sample_val = max(-1.0, min(1.0, sample_val * 0.75))
                data.extend(struct.pack("<h", int(sample_val * 32767)))
            wf.writeframes(data)

    def play(self, event_name: str, cooldown_sec: float = 0.8) -> None:
        """
        Asynchronously play a sound event with anti-spam cooldown.
        Thread-safe and returns immediately.
        """
        if not settings.sound_enabled:
            return

        # Check category-specific settings
        if event_name in (SoundEvent.TARGET_HIT, SoundEvent.APPROACHING, SoundEvent.STOP_LOSS):
            if not settings.sound_price_alerts_enabled:
                return
        elif event_name in (SoundEvent.SIGNAL_BUY, SoundEvent.SIGNAL_SELL):
            if not settings.sound_signals_enabled:
                return
        elif event_name in (SoundEvent.CONNECTED, SoundEvent.DISCONNECTED, SoundEvent.SCRIPT_ADDED):
            if not settings.sound_system_enabled:
                return

        now = time.time()
        last_t = self._last_played.get(event_name, 0.0)
        if now - last_t < cooldown_sec:
            return

        self._last_played[event_name] = now
        try:
            self._queue.put_nowait(event_name)
        except Exception:
            pass

    def _worker(self) -> None:
        """Background worker thread consuming audio events and playing sound."""
        while self._running:
            try:
                event_name = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._play_sync(event_name)
            except Exception as e:
                logger.debug(f"Audio playback error for {event_name}: {e}")
            finally:
                self._queue.task_done()

    def _play_sync(self, event_name: str) -> None:
        """Execute platform-native sound playback."""
        wav_path = self._sound_paths.get(event_name)

        # 1. Windows: Native winsound API
        if sys.platform == "win32":
            try:
                import winsound
                if wav_path and wav_path.exists():
                    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
                else:
                    alias = "SystemAsterisk" if event_name != SoundEvent.DISCONNECTED else "SystemExclamation"
                    winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_NODEFAULT)
                return
            except Exception as e:
                logger.debug(f"winsound error: {e}")

        # 2. macOS: Built-in afplay command
        elif sys.platform == "darwin":
            try:
                target_file = str(wav_path) if (wav_path and wav_path.exists()) else "/System/Library/Sounds/Glass.aiff"
                subprocess.run(["afplay", target_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
                return
            except Exception as e:
                logger.debug(f"afplay error: {e}")

        # 3. Linux: aplay / paplay or terminal bell fallback
        elif sys.platform.startswith("linux"):
            try:
                if wav_path and wav_path.exists():
                    subprocess.run(["aplay", "-q", str(wav_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
                return
            except Exception:
                pass

        # 4. Fallback bell
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

    def stop(self) -> None:
        """Stop background worker."""
        self._running = False


# Global default instance
sound_engine = SoundEngine.get_instance()
