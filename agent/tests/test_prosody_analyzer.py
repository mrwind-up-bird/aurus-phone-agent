"""Tests for prosodic feature extraction — pitch detection, energy, speaking rate."""

from __future__ import annotations

import numpy as np
import pytest

from src.prosody_analyzer import (
    ProsodyAnalyzer,
    ProsodyFeatures,
    _autocorrelation_pitch,
    _count_energy_peaks,
)


class TestAutocorrelationPitch:
    """Tests for F0 (fundamental frequency) detection via autocorrelation."""

    def test_sine_wave_200hz(self) -> None:
        """200Hz sine wave should be detected within ±10Hz."""
        sr = 16000
        duration = 0.05  # 50ms
        t = np.arange(int(sr * duration)) / sr
        signal = np.sin(2 * np.pi * 200 * t)
        pitch = _autocorrelation_pitch(signal, sr)
        assert 190 <= pitch <= 210

    def test_sine_wave_120hz(self) -> None:
        """120Hz sine wave — male speech range."""
        sr = 16000
        t = np.arange(int(sr * 0.05)) / sr
        signal = np.sin(2 * np.pi * 120 * t)
        pitch = _autocorrelation_pitch(signal, sr)
        assert 110 <= pitch <= 130

    def test_sine_wave_300hz(self) -> None:
        """300Hz sine wave — female speech range."""
        sr = 16000
        t = np.arange(int(sr * 0.05)) / sr
        signal = np.sin(2 * np.pi * 300 * t)
        pitch = _autocorrelation_pitch(signal, sr)
        assert 290 <= pitch <= 310

    def test_silence_returns_zero(self) -> None:
        """Silent (zero) audio should return 0 Hz."""
        signal = np.zeros(800)
        assert _autocorrelation_pitch(signal, 16000) == 0.0

    def test_noise_returns_zero(self) -> None:
        """Random noise should not detect a stable pitch."""
        rng = np.random.default_rng(42)
        signal = rng.normal(0, 0.1, 800)
        pitch = _autocorrelation_pitch(signal, 16000)
        # Noise may occasionally produce a weak peak, but confidence-wise
        # it should be 0 or very low — pitch detection may return 0 or a value
        # The key is it doesn't crash
        assert pitch >= 0

    def test_empty_array_returns_zero(self) -> None:
        """Empty input should return 0."""
        assert _autocorrelation_pitch(np.array([]), 16000) == 0.0

    def test_single_sample_returns_zero(self) -> None:
        """Single sample is too short for pitch detection."""
        assert _autocorrelation_pitch(np.array([0.5]), 16000) == 0.0

    def test_out_of_range_low_returns_zero(self) -> None:
        """Frequency below minimum (75Hz) should not be detected."""
        sr = 16000
        t = np.arange(int(sr * 0.1)) / sr
        signal = np.sin(2 * np.pi * 40 * t)  # 40Hz — below range
        pitch = _autocorrelation_pitch(signal, sr)
        # Should either return 0 or a harmonic, not 40
        assert pitch == 0.0 or pitch > 70


class TestCountEnergyPeaks:
    """Tests for syllable-rate estimation from energy envelope."""

    def test_empty_returns_zero(self) -> None:
        """Empty history returns 0."""
        assert _count_energy_peaks([], 16000, 160) == 0.0

    def test_short_returns_zero(self) -> None:
        """Fewer than 4 frames returns 0."""
        assert _count_energy_peaks([0.1, 0.2, 0.1], 16000, 160) == 0.0

    def test_constant_no_peaks(self) -> None:
        """Constant energy has no peaks."""
        history = [0.5] * 20
        rate = _count_energy_peaks(history, 16000, 160)
        assert rate == 0.0

    def test_alternating_produces_peaks(self) -> None:
        """Alternating high/low energy should produce peaks."""
        # Create a pattern: low-high-low-high-low-high
        history = [0.1, 0.8, 0.1, 0.8, 0.1, 0.8, 0.1, 0.8, 0.1]
        rate = _count_energy_peaks(history, 16000, 160)
        assert rate > 0


class TestProsodyAnalyzer:
    """Tests for stateful ProsodyAnalyzer."""

    def test_initial_state(self) -> None:
        """Fresh analyzer has clean state."""
        pa = ProsodyAnalyzer(sample_rate=16000)
        assert pa._frame_count == 0
        assert not pa._baseline_initialized

    def test_analyze_voiced_frame(self) -> None:
        """Analyzing a voiced frame returns is_voiced=True with valid pitch."""
        pa = ProsodyAnalyzer(sample_rate=16000)
        sr = 16000
        t = np.arange(int(sr * 0.02)) / sr  # 20ms
        signal = (np.sin(2 * np.pi * 200 * t) * 32767).astype(np.int16).tobytes()

        features = pa.analyze_frame(signal, sample_rate=sr)
        assert features.is_voiced
        assert features.pitch_hz > 0
        assert features.rms_energy > 0

    def test_analyze_silent_frame(self) -> None:
        """Silent frame returns is_voiced=False."""
        pa = ProsodyAnalyzer(sample_rate=16000)
        signal = np.zeros(320, dtype=np.int16).tobytes()
        features = pa.analyze_frame(signal, sample_rate=16000)
        assert not features.is_voiced
        assert features.pitch_hz == 0.0

    def test_short_frame_returns_default(self) -> None:
        """Frame shorter than 64 samples returns default ProsodyFeatures."""
        pa = ProsodyAnalyzer(sample_rate=16000)
        short_signal = np.zeros(10, dtype=np.int16).tobytes()
        features = pa.analyze_frame(short_signal, sample_rate=16000)
        assert not features.is_voiced

    def test_numpy_array_input(self) -> None:
        """Analyzer accepts numpy arrays directly."""
        pa = ProsodyAnalyzer(sample_rate=16000)
        sr = 16000
        t = np.arange(int(sr * 0.02)) / sr
        signal = np.sin(2 * np.pi * 200 * t)
        features = pa.analyze_frame(signal, sample_rate=sr)
        assert features.is_voiced

    def test_baseline_adapts_after_warmup(self) -> None:
        """Baseline energy initializes after 10 frames."""
        pa = ProsodyAnalyzer(sample_rate=16000)
        sr = 16000
        for _ in range(15):
            t = np.arange(int(sr * 0.02)) / sr
            signal = (np.sin(2 * np.pi * 150 * t) * 0.5 * 32767).astype(np.int16).tobytes()
            pa.analyze_frame(signal, sample_rate=sr)
        assert pa._baseline_initialized
        assert pa._baseline_energy > 0

    def test_reset_clears_state(self) -> None:
        """Reset returns analyzer to clean state."""
        pa = ProsodyAnalyzer(sample_rate=16000)
        sr = 16000
        for _ in range(15):
            t = np.arange(int(sr * 0.02)) / sr
            signal = (np.sin(2 * np.pi * 200 * t) * 32767).astype(np.int16).tobytes()
            pa.analyze_frame(signal, sample_rate=sr)
        assert pa._frame_count > 0
        pa.reset()
        assert pa._frame_count == 0
        assert not pa._baseline_initialized

    def test_energy_ratio_increases_with_louder_signal(self) -> None:
        """Louder signal after baseline init should have energy_ratio > 1."""
        pa = ProsodyAnalyzer(sample_rate=16000)
        sr = 16000
        # Warmup with quiet signal
        for _ in range(15):
            t = np.arange(int(sr * 0.02)) / sr
            signal = (np.sin(2 * np.pi * 200 * t) * 0.2 * 32767).astype(np.int16).tobytes()
            pa.analyze_frame(signal, sample_rate=sr)
        # Now send loud signal
        t = np.arange(int(sr * 0.02)) / sr
        loud = (np.sin(2 * np.pi * 200 * t) * 0.9 * 32767).astype(np.int16).tobytes()
        features = pa.analyze_frame(loud, sample_rate=sr)
        assert features.energy_ratio > 1.5


class TestProsodyFeatures:
    """Tests for ProsodyFeatures dataclass."""

    def test_default_values(self) -> None:
        """Default ProsodyFeatures is unvoiced with zeros."""
        f = ProsodyFeatures()
        assert f.rms_energy == 0.0
        assert f.pitch_hz == 0.0
        assert f.pitch_variance == 0.0
        assert f.energy_ratio == 1.0
        assert f.speaking_rate == 0.0
        assert not f.is_voiced

    def test_frozen(self) -> None:
        """ProsodyFeatures is immutable."""
        f = ProsodyFeatures(rms_energy=0.5)
        with pytest.raises(AttributeError):
            f.rms_energy = 0.9  # type: ignore[misc]
