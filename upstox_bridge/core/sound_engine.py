"""Ultra-lightweight, non-blocking asynchronous Sound Engine for trading alerts and chimes."""

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
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class SoundEngine:
    """
    High-performance, non-blocking asynchronous audio alert engine.
    - Plays custom synthesized WAV chimes or native OS system sounds.
    - Zero external heavy audio dependencies (uses standard library wave, struct, winsound on Windows, afplay on macOS).
    - Windows audio is strictly non-blocking (winsound.SND_ASYNC) with a bounded queue (maxsize=1)
      and 1.5s global rate limiting to ensure absolutely zero PC or UI lag.
    """

    _instance: Optional["SoundEngine"] = None

    def __init__(self, sounds_dir: Optional[Path] = None):
        self.sounds_dir = sounds_dir or (settings.root_dir / "assets" / "sounds")
        # Strict bounded queue: maxsize=1 prevents backlog of audio events
        self._queue: queue.Queue[str] = queue.Queue(maxsize=1)
        self._running = True
        self._last_played_time: float = 0.0
        self._last_event_time: Dict[str, float] = {}
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

        # Sound recipes: (freq, start_sec, end_sec, decay_rate)
        sound_recipes: Dict[str, List[Tuple[float, float, float, float]]] = {
            # 1. Target Hit: Bright bell chime with triple harmonics (A5 + E6 + A6)
            SoundEvent.TARGET_HIT: [
                (880.0, 0.0, 0.65, 4.0),
                (1320.0, 0.0, 0.65, 4.8),
                (1760.0, 0.0, 0.50, 6.5),
            ],
            # 2. Approaching: Gentle two-tone soft warning chime (D5 -> A5)
            SoundEvent.APPROACHING: [
                (587.33, 0.0, 0.16, 6.5),
                (880.0, 0.12, 0.45, 4.8),
            ],
            # 3. Connected: Crisp upbeat confirmation ping (E5 -> A5)
            SoundEvent.CONNECTED: [
                (659.25, 0.0, 0.14, 7.0),
                (880.0, 0.09, 0.35, 5.2),
            ],
            # 4. Disconnected / Error: Subtle low warning chime (E4 -> A3)
            SoundEvent.DISCONNECTED: [
                (329.63, 0.0, 0.18, 6.5),
                (220.0, 0.12, 0.40, 5.0),
            ],
        }

        for event_name, notes in sound_recipes.items():
            wav_path = target_dir / f"{event_name}.wav"
            self._sound_paths[event_name] = wav_path
            if not wav_path.exists() or wav_path.stat().st_size < 100:
                try:
                    self._synthesize_wav(wav_path, notes, duration=0.65)
                except Exception as e:
                    logger.debug(f"Could not synthesize {wav_path.name}: {e}")

    @staticmethod
    def _synthesize_wav(
        filepath: Path,
        notes: List[Tuple[float, float, float, float]],
        duration: float = 0.65,
        sample_rate: int = 44100,
    ) -> None:
        """Synthesize a studio-quality 16-bit PCM mono WAV file using pure math and standard library wave."""
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
                        # Warm natural harmonics
                        val = (
                            math.sin(2 * math.pi * freq * note_t) * 0.75
                            + math.sin(4 * math.pi * freq * note_t) * 0.18
                            + math.sin(6 * math.pi * freq * note_t) * 0.07
                        )
                        sample_val += val * env
                sample_val = max(-1.0, min(1.0, sample_val * 0.75))
                data.extend(struct.pack("<h", int(sample_val * 32767)))
            wf.writeframes(data)

    def play(self, event_name: str, cooldown_sec: float = 1.5) -> None:
        """
        Asynchronously play a sound event with anti-spam rate limiting.
        Thread-safe, strictly non-blocking, and returns in < 0.1ms.
        """
        if not settings.sound_enabled:
            return

        # Check category-specific settings
        if event_name in (SoundEvent.TARGET_HIT, SoundEvent.APPROACHING):
            if not settings.sound_price_alerts_enabled:
                return
        elif event_name in (SoundEvent.CONNECTED, SoundEvent.DISCONNECTED):
            if not settings.sound_system_enabled:
                return

        now = time.time()
        # Global debounce: minimum 1.2s between ANY sounds to prevent audio stutter
        if now - self._last_played_time < 1.2:
            return

        # Event-specific cooldown
        last_event_t = self._last_event_time.get(event_name, 0.0)
        if now - last_event_t < cooldown_sec:
            return

        self._last_played_time = now
        self._last_event_time[event_name] = now

        # Non-blocking bounded queue insert; drop if busy
        try:
            self._queue.put_nowait(event_name)
        except queue.Full:
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
        """Execute platform-native non-blocking sound playback."""
        wav_path = self._sound_paths.get(event_name)

        # 1. Windows: Native winsound API with SND_ASYNC (0.05ms execution, zero lag)
        if sys.platform == "win32":
            try:
                import winsound
                flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
                if wav_path and wav_path.exists():
                    winsound.PlaySound(str(wav_path), flags)
                else:
                    alias_flags = winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT
                    alias = "SystemAsterisk" if event_name != SoundEvent.DISCONNECTED else "SystemExclamation"
                    winsound.PlaySound(alias, alias_flags)
                return
            except Exception as e:
                logger.debug(f"winsound error: {e}")

        # 2. macOS: Built-in afplay command
        elif sys.platform == "darwin":
            try:
                target_file = str(wav_path) if (wav_path and wav_path.exists()) else "/System/Library/Sounds/Glass.aiff"
                subprocess.Popen(["afplay", target_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception as e:
                logger.debug(f"afplay error: {e}")

        # 3. Linux: aplay / paplay fallback
        elif sys.platform.startswith("linux"):
            try:
                if wav_path and wav_path.exists():
                    subprocess.Popen(["aplay", "-q", str(wav_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
