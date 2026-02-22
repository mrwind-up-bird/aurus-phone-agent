"""Hybrid voice sentiment detector — combines prosodic analysis with keyword matching.

Priority: prosody (voice tone) > keywords (text) > neutral fallback.
Maintains a sliding window of recent assessments for temporal smoothing.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass

import structlog

from .models import UserMood
from .prosody_analyzer import ProsodyFeatures

logger = structlog.get_logger()

# German keyword patterns for mood detection (lowercase)
_MOOD_KEYWORDS: dict[UserMood, list[str]] = {
    UserMood.ENTHUSIASTIC: [
        "super", "toll", "großartig", "perfekt", "genial", "fantastisch", "wunderbar",
        "ausgezeichnet", "klasse", "mega", "spitze", "ja gerne", "auf jeden fall",
        "unbedingt", "begeistert", "freue mich", "klingt super",
    ],
    UserMood.INTERESTED: [
        "interessant", "erzählen sie", "mehr dazu", "wie funktioniert", "klingt gut",
        "spannend", "neugierig", "gerne mehr", "wie genau", "was genau", "können sie",
        "zeigen sie", "erklären", "details", "klingt interessant",
    ],
    UserMood.SKEPTICAL: [
        "weiß nicht", "bin mir nicht sicher", "eher nicht", "glaube nicht", "skeptisch",
        "nicht überzeugt", "woher wissen", "beweis", "nachweis",
        "garantie", "hm naja", "mal sehen", "vielleicht",
    ],
    UserMood.FRUSTRATED: [
        "nervig", "schon wieder", "keine zeit", "aufhören", "lassen sie mich",
        "ruhe", "genervt", "ärgerlich", "schlecht", "unverschämt", "frechheit",
        "beschwerde", "problem", "funktioniert nicht",
    ],
    UserMood.CONFUSED: [
        "verstehe nicht", "was meinen sie", "wie bitte", "unklar", "verwirrt",
        "nochmal", "wiederholen", "häh", "ich folge nicht", "zu schnell",
        "langsamer", "kompliziert",
    ],
    UserMood.DISMISSIVE: [
        "kein interesse", "nein danke", "brauche ich nicht", "auf wiedersehen",
        "auflegen", "tschüss", "nicht interessiert", "lassen sie es", "vergessen sie es",
        "zeitverschwendung", "rufen sie nicht",
    ],
}


@dataclass
class SentimentScore:
    """Weighted sentiment assessment with confidence."""

    mood: UserMood
    confidence: float  # 0.0 - 1.0
    source: str  # "prosody", "keyword", "hybrid"
    prosody_mood: UserMood | None = None
    keyword_mood: UserMood | None = None


# Prosody thresholds for mood classification
# Based on speech emotion research: Scherer (2003), Juslin & Laukka (2003)
#
# Feature ranges (normalized to speaker baseline):
#   energy_ratio: <0.7 = quiet, 0.7-1.3 = normal, >1.3 = loud
#   pitch_hz:     relative to speaker mean (baseline adapts)
#   pitch_variance: <15 = monotone, 15-40 = normal, >40 = expressive
#   speaking_rate:  <2 = slow, 2-5 = normal, >5 = fast

def _classify_prosody(features: ProsodyFeatures) -> tuple[UserMood, float]:
    """Map prosodic features to mood with confidence score.

    Returns (mood, confidence) where confidence is 0.0-1.0.
    Higher confidence = stronger prosodic signal.
    """
    if not features.is_voiced:
        return UserMood.NEUTRAL, 0.0

    e = features.energy_ratio
    pv = features.pitch_variance
    rate = features.speaking_rate

    # Frustrated/Angry: high energy + high pitch variance + fast
    if e > 1.5 and pv > 45 and rate > 4.5:
        confidence = min(1.0, (e - 1.3) * 0.5 + (pv - 35) * 0.01)
        return UserMood.FRUSTRATED, confidence

    # Enthusiastic/Excited: high energy + high pitch variance + fast
    if e > 1.2 and pv > 30 and rate > 3.5:
        confidence = min(1.0, (e - 1.0) * 0.4 + (pv - 25) * 0.01)
        return UserMood.ENTHUSIASTIC, confidence

    # Interested/Engaged: above-average energy + moderate-high variance
    if e > 1.0 and pv > 20 and rate > 2.5:
        confidence = min(0.8, (e - 0.9) * 0.3 + (pv - 15) * 0.008)
        return UserMood.INTERESTED, confidence

    # Dismissive/Bored: low energy + low variance + slow
    if e < 0.6 and pv < 12 and rate < 2.0:
        confidence = min(1.0, (0.7 - e) * 0.5 + (15 - pv) * 0.02)
        return UserMood.DISMISSIVE, confidence

    # Skeptical: below-average energy + low-moderate variance
    if e < 0.85 and pv < 18:
        confidence = min(0.7, (0.9 - e) * 0.4 + (20 - pv) * 0.01)
        return UserMood.SKEPTICAL, confidence

    # Confused: moderate energy + high pitch (questions tend to rise)
    if features.pitch_hz > 200 and pv > 25 and e > 0.8:
        confidence = min(0.6, (pv - 20) * 0.01)
        return UserMood.CONFUSED, confidence

    return UserMood.NEUTRAL, 0.1


def _keyword_match(text: str, keyword: str) -> bool:
    """Match keyword with word boundary awareness to avoid German compound false positives."""
    return bool(re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text))


def _classify_keywords(text: str) -> tuple[UserMood, float]:
    """Detect mood from German text using keyword matching.

    Returns (mood, confidence) where confidence scales with match count.
    """
    lower = text.lower()
    best_mood = UserMood.NEUTRAL
    best_score = 0

    for mood, keywords in _MOOD_KEYWORDS.items():
        score = sum(1 for kw in keywords if _keyword_match(lower, kw))
        if score > best_score:
            best_score = score
            best_mood = mood

    # Confidence based on number of keyword hits
    if best_score == 0:
        return UserMood.NEUTRAL, 0.0
    confidence = min(1.0, best_score * 0.35)
    return best_mood, confidence


# Mood priority for conflict resolution (higher = stronger signal)
_MOOD_STRENGTH: dict[UserMood, int] = {
    UserMood.FRUSTRATED: 5,
    UserMood.DISMISSIVE: 4,
    UserMood.ENTHUSIASTIC: 3,
    UserMood.CONFUSED: 2,
    UserMood.SKEPTICAL: 2,
    UserMood.INTERESTED: 1,
    UserMood.NEUTRAL: 0,
}


class VoiceSentimentDetector:
    """Hybrid voice + text sentiment detector with temporal smoothing.

    Combines prosodic analysis (voice tone) with keyword matching (text content)
    using confidence-weighted fusion. Maintains a sliding window of recent
    assessments for stable mood tracking.
    """

    def __init__(self, window_size: int = 5) -> None:
        self._history: deque[SentimentScore] = deque(maxlen=window_size)
        self._prosody_weight: float = 0.65  # Voice tone weighted higher
        self._keyword_weight: float = 0.35

    def detect(
        self,
        text: str,
        prosody: ProsodyFeatures | None = None,
    ) -> SentimentScore:
        """Detect mood from text and optional prosodic features.

        Args:
            text: Transcribed user speech (German).
            prosody: Aggregated prosodic features for this utterance.

        Returns:
            SentimentScore with detected mood, confidence, and source.
        """
        # Keyword-based detection
        kw_mood, kw_conf = _classify_keywords(text)

        # Prosody-based detection
        if prosody and prosody.is_voiced:
            pr_mood, pr_conf = _classify_prosody(prosody)
        else:
            pr_mood, pr_conf = UserMood.NEUTRAL, 0.0

        # Fusion strategy
        if pr_conf > 0.3 and kw_conf > 0.3:
            # Both signals present — weighted fusion
            if pr_mood == kw_mood:
                # Agreement: boost confidence
                final_mood = pr_mood
                final_conf = min(1.0, pr_conf * 0.5 + kw_conf * 0.5 + 0.2)
                source = "hybrid"
            else:
                # Conflict: use stronger signal, consider mood severity
                pr_strength = _MOOD_STRENGTH.get(pr_mood, 0)
                kw_strength = _MOOD_STRENGTH.get(kw_mood, 0)

                pr_score = pr_conf * self._prosody_weight + pr_strength * 0.1
                kw_score = kw_conf * self._keyword_weight + kw_strength * 0.1

                if pr_score >= kw_score:
                    final_mood = pr_mood
                    final_conf = pr_conf * 0.8
                    source = "prosody"
                else:
                    final_mood = kw_mood
                    final_conf = kw_conf * 0.8
                    source = "keyword"
        elif pr_conf > 0.3:
            # Only prosody signal
            final_mood = pr_mood
            final_conf = pr_conf
            source = "prosody"
        elif kw_conf > 0.2:
            # Only keyword signal
            final_mood = kw_mood
            final_conf = kw_conf
            source = "keyword"
        else:
            final_mood = UserMood.NEUTRAL
            final_conf = 0.1
            source = "keyword"

        score = SentimentScore(
            mood=final_mood,
            confidence=final_conf,
            source=source,
            prosody_mood=pr_mood if pr_conf > 0 else None,
            keyword_mood=kw_mood if kw_conf > 0 else None,
        )
        self._history.append(score)

        logger.debug(
            "sentiment_detected",
            mood=final_mood.value,
            confidence=round(final_conf, 2),
            source=source,
            prosody_mood=pr_mood.value if pr_conf > 0 else None,
            keyword_mood=kw_mood.value if kw_conf > 0 else None,
        )

        return score

    def get_smoothed_mood(self) -> UserMood:
        """Get temporally smoothed mood from recent history.

        Uses weighted voting: more recent assessments and higher confidence
        get more weight. Prevents mood flickering.
        """
        if not self._history:
            return UserMood.NEUTRAL

        # Weighted vote — recent entries weighted more
        votes: dict[UserMood, float] = {}
        total = len(self._history)

        for i, score in enumerate(self._history):
            recency_weight = 0.5 + 0.5 * (i / max(total - 1, 1))
            vote_weight = score.confidence * recency_weight
            votes[score.mood] = votes.get(score.mood, 0.0) + vote_weight

        if not votes:
            return UserMood.NEUTRAL

        return max(votes, key=lambda m: votes[m])

    def reset(self) -> None:
        """Clear history — call on new conversation."""
        self._history.clear()
