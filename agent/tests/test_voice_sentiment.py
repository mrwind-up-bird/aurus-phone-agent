"""Tests for hybrid voice sentiment detection — prosody + keyword fusion."""

from __future__ import annotations

from src.models import UserMood
from src.prosody_analyzer import ProsodyFeatures
from src.voice_sentiment import (
    SentimentScore,
    VoiceSentimentDetector,
    _classify_keywords,
    _classify_prosody,
    _keyword_match,
)


class TestKeywordMatch:
    """Tests for word-boundary-aware keyword matching."""

    def test_exact_match(self) -> None:
        """Exact word matches."""
        assert _keyword_match("das ist super", "super")

    def test_no_substring_match(self) -> None:
        """'super' should NOT match inside 'supermarkt'."""
        assert not _keyword_match("ich gehe zum supermarkt", "super")

    def test_compound_word_no_match(self) -> None:
        """'problem' should NOT match inside 'problemlos'."""
        assert not _keyword_match("das war problemlos", "problem")

    def test_multi_word_keyword(self) -> None:
        """Multi-word keywords like 'kein interesse' match."""
        assert _keyword_match("ich habe kein interesse daran", "kein interesse")

    def test_case_handled_by_caller(self) -> None:
        """Keyword match is case-sensitive — caller lowercases."""
        assert not _keyword_match("SUPER toll", "super")
        assert _keyword_match("super toll", "super")


class TestClassifyKeywords:
    """Tests for German keyword-based mood classification."""

    def test_enthusiastic(self) -> None:
        mood, conf = _classify_keywords("Das ist super toll!")
        assert mood is UserMood.ENTHUSIASTIC
        assert conf > 0

    def test_interested(self) -> None:
        mood, conf = _classify_keywords("Das klingt interessant")
        assert mood is UserMood.INTERESTED
        assert conf > 0

    def test_skeptical(self) -> None:
        mood, conf = _classify_keywords("Ich weiß nicht, bin mir nicht sicher")
        assert mood is UserMood.SKEPTICAL
        assert conf > 0

    def test_frustrated(self) -> None:
        mood, conf = _classify_keywords("Das ist nervig, schon wieder")
        assert mood is UserMood.FRUSTRATED
        assert conf > 0

    def test_confused(self) -> None:
        mood, conf = _classify_keywords("Ich verstehe nicht, wie bitte")
        assert mood is UserMood.CONFUSED
        assert conf > 0

    def test_dismissive(self) -> None:
        mood, conf = _classify_keywords("Kein interesse, auf wiedersehen")
        assert mood is UserMood.DISMISSIVE
        assert conf > 0

    def test_neutral_no_keywords(self) -> None:
        mood, conf = _classify_keywords("Okay alles klar")
        assert mood is UserMood.NEUTRAL
        assert conf == 0.0

    def test_empty_text(self) -> None:
        mood, conf = _classify_keywords("")
        assert mood is UserMood.NEUTRAL
        assert conf == 0.0

    def test_confidence_scales_with_hits(self) -> None:
        """More keyword hits = higher confidence."""
        _, conf_one = _classify_keywords("super")
        _, conf_three = _classify_keywords("super toll perfekt")
        assert conf_three > conf_one

    def test_confidence_capped_at_one(self) -> None:
        """Confidence never exceeds 1.0."""
        _, conf = _classify_keywords(
            "super toll großartig perfekt genial fantastisch wunderbar ausgezeichnet"
        )
        assert conf <= 1.0


class TestClassifyProsody:
    """Tests for prosodic feature to mood classification."""

    def test_unvoiced_returns_neutral(self) -> None:
        """Unvoiced features return NEUTRAL with 0 confidence."""
        features = ProsodyFeatures(is_voiced=False)
        mood, conf = _classify_prosody(features)
        assert mood is UserMood.NEUTRAL
        assert conf == 0.0

    def test_frustrated_high_energy_fast(self) -> None:
        """High energy + high variance + fast = FRUSTRATED."""
        features = ProsodyFeatures(
            energy_ratio=1.8, pitch_variance=50, speaking_rate=5.0, is_voiced=True
        )
        mood, conf = _classify_prosody(features)
        assert mood is UserMood.FRUSTRATED
        assert conf > 0.3

    def test_enthusiastic_moderate_high(self) -> None:
        """Above-average energy + variance + rate = ENTHUSIASTIC."""
        features = ProsodyFeatures(
            energy_ratio=1.3, pitch_variance=35, speaking_rate=4.0, is_voiced=True
        )
        mood, conf = _classify_prosody(features)
        assert mood is UserMood.ENTHUSIASTIC
        assert conf > 0

    def test_dismissive_low_energy_slow(self) -> None:
        """Low energy + low variance + slow = DISMISSIVE."""
        features = ProsodyFeatures(
            energy_ratio=0.4, pitch_variance=8, speaking_rate=1.5, is_voiced=True
        )
        mood, conf = _classify_prosody(features)
        assert mood is UserMood.DISMISSIVE
        assert conf > 0

    def test_skeptical_below_average(self) -> None:
        """Below-average energy + low variance = SKEPTICAL."""
        features = ProsodyFeatures(
            energy_ratio=0.7, pitch_variance=12, speaking_rate=3.0, is_voiced=True
        )
        mood, conf = _classify_prosody(features)
        assert mood is UserMood.SKEPTICAL
        assert conf > 0

    def test_neutral_fallback(self) -> None:
        """Average features that don't match any pattern = NEUTRAL."""
        features = ProsodyFeatures(
            energy_ratio=1.0, pitch_variance=15, speaking_rate=3.0,
            pitch_hz=150, is_voiced=True
        )
        mood, conf = _classify_prosody(features)
        assert mood is UserMood.NEUTRAL


class TestVoiceSentimentDetector:
    """Tests for the hybrid fusion detector."""

    def test_keyword_only_detection(self) -> None:
        """Without prosody, falls back to keyword detection."""
        detector = VoiceSentimentDetector()
        score = detector.detect("Das ist super toll!")
        assert score.mood is UserMood.ENTHUSIASTIC
        assert score.source == "keyword"

    def test_prosody_only_detection(self) -> None:
        """Strong prosody with neutral text uses prosody."""
        detector = VoiceSentimentDetector()
        prosody = ProsodyFeatures(
            energy_ratio=1.8, pitch_variance=50, speaking_rate=5.0, is_voiced=True
        )
        score = detector.detect("ja okay", prosody=prosody)
        assert score.mood is UserMood.FRUSTRATED
        assert score.source == "prosody"

    def test_hybrid_agreement_boosts_confidence(self) -> None:
        """When prosody and keywords agree, confidence is boosted."""
        detector = VoiceSentimentDetector()
        # Strong prosody signal to exceed 0.3 confidence threshold
        prosody = ProsodyFeatures(
            energy_ratio=1.5, pitch_variance=45, speaking_rate=4.5, is_voiced=True
        )
        score = detector.detect("Das ist super toll perfekt!", prosody=prosody)
        assert score.mood is UserMood.ENTHUSIASTIC
        assert score.source == "hybrid"
        assert score.confidence > 0.5

    def test_neutral_with_no_signal(self) -> None:
        """No keywords and no prosody = NEUTRAL."""
        detector = VoiceSentimentDetector()
        score = detector.detect("okay")
        assert score.mood is UserMood.NEUTRAL

    def test_history_accumulates(self) -> None:
        """Detector maintains history of detections."""
        detector = VoiceSentimentDetector(window_size=3)
        detector.detect("super toll!")
        detector.detect("perfekt genial!")
        detector.detect("fantastisch!")
        assert len(detector._history) == 3

    def test_smoothed_mood_reflects_majority(self) -> None:
        """Smoothed mood returns the dominant mood in recent window."""
        detector = VoiceSentimentDetector(window_size=5)
        # 3 enthusiastic, 1 neutral, 1 skeptical
        detector.detect("super toll!")
        detector.detect("okay")
        detector.detect("perfekt genial!")
        detector.detect("weiß nicht")
        detector.detect("fantastisch wunderbar!")
        smoothed = detector.get_smoothed_mood()
        assert smoothed is UserMood.ENTHUSIASTIC

    def test_smoothed_empty_returns_neutral(self) -> None:
        """No history returns NEUTRAL."""
        detector = VoiceSentimentDetector()
        assert detector.get_smoothed_mood() is UserMood.NEUTRAL

    def test_reset_clears_history(self) -> None:
        """Reset empties the history."""
        detector = VoiceSentimentDetector()
        detector.detect("super toll!")
        detector.detect("perfekt!")
        assert len(detector._history) > 0
        detector.reset()
        assert len(detector._history) == 0

    def test_score_has_source_info(self) -> None:
        """SentimentScore includes prosody_mood and keyword_mood."""
        detector = VoiceSentimentDetector()
        prosody = ProsodyFeatures(
            energy_ratio=1.3, pitch_variance=35, speaking_rate=4.0, is_voiced=True
        )
        score = detector.detect("super toll!", prosody=prosody)
        assert score.keyword_mood is not None
        assert score.prosody_mood is not None

    def test_window_size_respected(self) -> None:
        """History respects window_size limit."""
        detector = VoiceSentimentDetector(window_size=2)
        detector.detect("super!")
        detector.detect("toll!")
        detector.detect("perfekt!")
        assert len(detector._history) == 2
