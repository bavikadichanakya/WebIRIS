"""
Project IRIS - Audio Capture Subsystem
Captures microphone audio using sounddevice with thread-safe ring buffering and RMS level metering.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, List, Optional
import numpy as np

logger = logging.getLogger("iris.voice.audio_capture")

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False


class AudioCapture:
    """Manages microphone input stream, audio buffering, and audio energy diagnostics."""

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1280,  # 80ms at 16kHz (openWakeWord standard)
        device_index: Optional[int] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.device_index = device_index
        self._stream: Optional[Any] = None
        self._is_running = False
        self._is_muted = False
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)
        self._lock = threading.RLock()
        self._current_rms: float = 0.0
        self._level_callbacks: List[Callable[[float], None]] = []
        self.last_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def is_muted(self) -> bool:
        with self._lock:
            return self._is_muted

    @property
    def current_rms(self) -> float:
        with self._lock:
            return self._current_rms

    def add_level_callback(self, callback: Callable[[float], None]) -> None:
        """Register callback for audio level metering: callback(rms_level_0_to_1)."""
        with self._lock:
            if callback not in self._level_callbacks:
                self._level_callbacks.append(callback)

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute microphone ingestion (used during TTS speech to prevent feedback)."""
        with self._lock:
            self._is_muted = muted
            if muted:
                # Clear pending audio in queue to prevent stale buffer processing
                while not self._audio_queue.empty():
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        break

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info: Any, status: Any
    ) -> None:
        """Internal callback invoked by sounddevice on microphone hardware thread."""
        if status:
            logger.debug(f"sounddevice stream status: {status}")

        with self._lock:
            if not self._is_running or self._is_muted:
                return

        # Convert to 1D int16 array
        # indata is float32 [-1.0, 1.0] or int16
        if indata.dtype == np.float32:
            scaled = np.clip(indata[:, 0], -1.0, 1.0)
            int16_data = (scaled * 32767).astype(np.int16)
            rms = float(np.sqrt(np.mean(scaled ** 2)))
        else:
            int16_data = indata[:, 0].astype(np.int16)
            rms = float(np.sqrt(np.mean((int16_data.astype(np.float32) / 32767.0) ** 2)))

        with self._lock:
            self._current_rms = rms

        # Forward level to listeners
        for cb in self._level_callbacks:
            try:
                cb(min(1.0, rms * 5.0))  # Normalize for UI visualizer
            except Exception:
                pass

        try:
            self._audio_queue.put_nowait(int16_data)
        except queue.Full:
            # Drop oldest chunk if pipeline is falling behind
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(int16_data)
            except Exception:
                pass

    def start(self) -> bool:
        """Start capturing microphone audio."""
        if not SD_AVAILABLE:
            logger.error("sounddevice is not available. Audio capture cannot start.")
            return False

        with self._lock:
            if self._is_running:
                return True

            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.chunk_size,
                    device=self.device_index,
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._is_running = True
                self.last_error = None
                logger.info(f"Microphone capture started: {self.sample_rate}Hz, chunk={self.chunk_size}")
                return True
            except Exception as e:
                err_str = str(e)
                self.last_error = err_str
                if "MME error 1" in err_str or "-9999" in err_str:
                    logger.warning(
                        "Windows microphone access is currently disabled or restricted in Windows Settings. "
                        "To enable voice wake-word, open Windows Settings -> Privacy & security -> Microphone "
                        "and enable 'Microphone access'."
                    )
                else:
                    logger.error(f"Failed to start audio input stream: {e}", exc_info=True)
                self._stream = None
                self._is_running = False
                return False

    def stop(self) -> None:
        """Stop capturing audio and release microphone."""
        with self._lock:
            self._is_running = False
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.debug(f"Error closing audio stream: {e}")
                self._stream = None
            logger.info("Microphone capture stopped.")

    def read_chunk(self, timeout: float = 0.5) -> Optional[np.ndarray]:
        """Read one chunk of 16-bit PCM audio from buffer."""
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @staticmethod
    def list_input_devices() -> List[Dict[str, Any]]:
        """List available microphone input devices on Windows."""
        if not SD_AVAILABLE:
            return []
        try:
            devices = sd.query_devices()
            input_devs = []
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    input_devs.append({
                        "index": idx,
                        "name": dev.get("name", f"Device {idx}"),
                        "channels": dev.get("max_input_channels", 1),
                        "default_samplerate": dev.get("default_samplerate", 16000),
                    })
            return input_devs
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
            return []
