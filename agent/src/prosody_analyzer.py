"""Real-time prosodic feature extraction from audio frames.

Uses only numpy — no external ML dependencies. Designed for <10ms per frame
at 16kHz mono. Extracts pitch (F0), energy (RMS), speaking rate, and pitch
variance for voice-based emotion detection.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import structlog

logger = structlog.get_logger()

# Pitch detection bounds (Hz) — covers male + female speech range
_MIN_PITCH_HZ = 75
_MAX_PITCH_HZ = 500

# Sliding window sizes
_PITCH_WINDOW = 20  # Number of frames to keep for variance calculation
_ENERGY_BASELINE_WINDOW = 50  # Frames for adaptive baseline
_RATE_WINDOW_SEC = 2.0  # Seconds for speaking rate estimation


@dataclass(frozen=True)
class ProsodyFeatures:
    """Extracted prosodic features from a chunk of audio."""

    rms_energy: float = 0.0  # Root mean square energy (0.0 - 1.0 normalized)
    pitch_hz: float = 0.0  # Fundamental frequency in Hz (0 = unvoiced)
    pitch_variance: float = 0.0  # Std dev of pitch over recent window
    energy_ratio: float = 1.0  # Current energy / baseline energy
    speaking_rate: float = 0.0  # Estimated syllable-like events per second
    is_voiced: bool = False  # Whether the frame contains voiced speech


def _autocorrelation_pitch(samples: np.ndarray, sample_rate: int) -> float:
    """Estimate fundamental frequency using autocorrelation method.

    Fast numpy-only implementation. Returns 0.0 for unvoiced segments.
    """
    n = len(samples)
    if n < 2:
        return 0.0

    # Apply Hamming window to reduce spectral leakage
    windowed = samples * np.hamming(n)

    # Compute autocorrelation via FFT (much faster than direct)
    fft = np.fft.rfft(windowed, n=2 * n)
    acf = np.fft.irfft(fft * np.conj(fft))[:n]

    # Normalize
    if acf[0] == 0:
        return 0.0
    acf = acf / acf[0]

    # Search for first peak in valid pitch range
    min_lag = int(sample_rate / _MAX_PITCH_HZ)
    max_lag = min(int(sample_rate / _MIN_PITCH_HZ), n - 1)

    if min_lag >= max_lag or max_lag >= len(acf):
        return 0.0

    segment = acf[min_lag:max_lag]
    if len(segment) == 0:
        return 0.0

    # Find the peak
    peak_idx = np.argmax(segment)
    peak_val = segment[peak_idx]

    # Voicing threshold — autocorrelation peak must be strong enough
    if peak_val < 0.25:
        return 0.0

    lag = min_lag + peak_idx
    if lag == 0:
        return 0.0

    # Parabolic interpolation for sub-sample accuracy
    if 0 < peak_idx < len(segment) - 1:
        a = segment[peak_idx - 1]
        b = segment[peak_idx]
        c = segment[peak_idx + 1]
        denom = 2.0 * (2.0 * b - a - c)
        if abs(denom) > 1e-10:
            correction = (a - c) / denom
            lag = min_lag + peak_idx + correction

    return sample_rate / lag


def _count_energy_peaks(
    energy_history: list[float], sample_rate: int, frame_size: int
) -> float:
    """Estimate speaking rate from energy envelope peaks (syllable-like events)."""
    if len(energy_history) < 4:
        return 0.0

    arr = np.array(energy_history)

    # Smooth the energy envelope
    kernel_size = min(3, len(arr))
    kernel = np.ones(kernel_size) / kernel_size
    smoothed = np.convolve(arr, kernel, mode="same")

    # Find peaks (local maxima above threshold)
    threshold = np.mean(smoothed) * 0.5
    peaks = 0
    for i in range(1, len(smoothed) - 1):
        if (
            smoothed[i] > smoothed[i - 1]
            and smoothed[i] > smoothed[i + 1]
            and smoothed[i] > threshold
        ):
            peaks += 1

    # Convert to rate (peaks per second)
    duration_sec = len(energy_history) * frame_size / sample_rate
    if duration_sec <= 0:
        return 0.0

    return peaks / duration_sec


class ProsodyAnalyzer:
    """Stateful prosodic analyzer that processes audio frames incrementally.

    Maintains adaptive baselines and sliding windows for robust feature
    extraction across varying speakers and conditions.
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._pitch_history: deque[float] = deque(maxlen=_PITCH_WINDOW)
        self._energy_history: deque[float] = deque(maxlen=_ENERGY_BASELINE_WINDOW)
        self._rate_energy_history: deque[float] = deque(
            maxlen=int(_RATE_WINDOW_SEC * sample_rate / 160)  # ~100 frames for 2s
        )
        self._baseline_energy: float = 0.0
        self._baseline_initialized: bool = False
        self._frame_count: int = 0
        self._last_frame_size: int = 160  # Default for 10ms at 16kHz

    def analyze_frame(self, audio_data: bytes | np.ndarray, sample_rate: int | None = None) -> ProsodyFeatures:
        """Analyze a single audio frame and return prosodic features.

        Args:
            audio_data: Raw PCM audio as bytes (int16 LE) or numpy array (float64).
            sample_rate: Override sample rate if different from init.

        Returns:
            ProsodyFeatures with extracted values.
        """
        sr = sample_rate or self._sample_rate

        # Convert bytes to float samples
        if isinstance(audio_data, bytes):
            if len(audio_data) < 4:
                return ProsodyFeatures()
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float64)
            samples = samples / 32768.0  # Normalize to [-1, 1]
        elif isinstance(audio_data, np.ndarray):
            samples = audio_data.astype(np.float64)
            if samples.max() > 1.0 or samples.min() < -1.0:
                max_val = max(abs(samples.max()), abs(samples.min()), 1.0)
                samples = samples / max_val
        else:
            return ProsodyFeatures()

        if len(samples) < 64:
            return ProsodyFeatures()

        self._last_frame_size = len(samples)
        self._frame_count += 1

        # 1. RMS Energy
        rms = float(np.sqrt(np.mean(samples**2)))
        self._energy_history.append(rms)
        self._rate_energy_history.append(rms)

        # Update adaptive baseline (exponential moving average)
        if not self._baseline_initialized and self._frame_count >= 10:
            self._baseline_energy = float(np.mean(list(self._energy_history)))
            self._baseline_initialized = True
        elif self._baseline_initialized:
            # Slow adaptation (alpha=0.01) to track speaker changes
            self._baseline_energy = 0.99 * self._baseline_energy + 0.01 * rms

        # Energy ratio
        energy_ratio = rms / max(self._baseline_energy, 1e-6) if self._baseline_initialized else 1.0

        # 2. Pitch (F0) via autocorrelation
        pitch_hz = _autocorrelation_pitch(samples, sr)
        is_voiced = pitch_hz > 0

        if is_voiced:
            self._pitch_history.append(pitch_hz)

        # 3. Pitch variance over window
        pitch_variance = 0.0
        if len(self._pitch_history) >= 3:
            pitch_arr = np.array(list(self._pitch_history))
            pitch_variance = float(np.std(pitch_arr))

        # 4. Speaking rate from energy envelope
        speaking_rate = _count_energy_peaks(
            list(self._rate_energy_history), sr, self._last_frame_size
        )

        return ProsodyFeatures(
            rms_energy=rms,
            pitch_hz=pitch_hz,
            pitch_variance=pitch_variance,
            energy_ratio=energy_ratio,
            speaking_rate=speaking_rate,
            is_voiced=is_voiced,
        )

    def reset(self) -> None:
        """Reset all state — call when a new speaker starts."""
        self._pitch_history.clear()
        self._energy_history.clear()
        self._rate_energy_history.clear()
        self._baseline_energy = 0.0
        self._baseline_initialized = False
        self._frame_count = 0
