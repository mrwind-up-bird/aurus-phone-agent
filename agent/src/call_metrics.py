"""Real-time call metrics tracking for live dashboard analytics."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .models import UserMood

# Sales conversation stages
STAGES = ["greeting", "qualification", "pitch", "objection_handling", "closing", "follow_up"]

# Stage detection keywords (German)
_STAGE_KEYWORDS: dict[str, list[str]] = {
    "greeting": ["guten tag", "hallo", "mein name", "hier ist", "spreche ich mit"],
    "qualification": ["was machen sie", "welche rolle", "wie groß", "wie viele mitarbeiter", "aktuell nutzen"],
    "pitch": ["lösung", "produkt", "angebot", "vorteil", "nutzen", "effizienz", "automatisier", "verbessern"],
    "objection_handling": ["zu teuer", "kein budget", "keine zeit", "schon haben", "brauchen nicht", "zufrieden mit"],
    "closing": ["termin", "demo", "nächster schritt", "vereinbaren", "kalender", "wann passt", "einverstanden"],
    "follow_up": ["unterlagen", "email", "zusenden", "kontaktdaten", "visitenkarte", "auf wiedersehen"],
}


@dataclass
class CallMetrics:
    """Tracks all metrics for a single call."""

    start_time: float = field(default_factory=time.time)
    user_turns: int = 0
    agent_turns: int = 0
    objection_count: int = 0
    mood_history: list[str] = field(default_factory=list)
    stage: str = "greeting"
    response_times: list[float] = field(default_factory=list)
    _last_user_speech_time: float = 0.0
    _last_agent_speech_time: float = 0.0

    @property
    def duration_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def turn_count(self) -> int:
        return self.user_turns + self.agent_turns

    @property
    def avg_response_time_ms(self) -> float:
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times) * 1000

    @property
    def lead_score(self) -> int:
        """Calculate lead score (0-100) based on mood trajectory and engagement."""
        if not self.mood_history:
            return 50

        score = 50  # base

        # Mood scoring
        mood_scores: dict[str, int] = {
            "enthusiastic": 20,
            "interested": 15,
            "neutral": 0,
            "skeptical": -5,
            "confused": -5,
            "frustrated": -15,
            "dismissive": -25,
        }

        # Weight recent moods more heavily
        for i, mood in enumerate(self.mood_history):
            weight = 0.5 + 0.5 * (i / max(len(self.mood_history) - 1, 1))
            score += mood_scores.get(mood, 0) * weight

        # Engagement bonus (more turns = more engaged)
        if self.user_turns >= 3:
            score += 5
        if self.user_turns >= 6:
            score += 5

        # Stage progression bonus
        stage_idx = STAGES.index(self.stage) if self.stage in STAGES else 0
        score += stage_idx * 3

        # Objection penalty (but handled objections show engagement)
        if self.objection_count > 0 and self.user_turns > self.objection_count * 2:
            score += 5  # They stayed despite objections

        return max(0, min(100, int(score)))

    @property
    def mood_trajectory(self) -> str:
        """Determine if mood is improving, declining, or stable."""
        if len(self.mood_history) < 2:
            return "stable"

        mood_values: dict[str, int] = {
            "enthusiastic": 3,
            "interested": 2,
            "neutral": 1,
            "skeptical": 0,
            "confused": -1,
            "frustrated": -2,
            "dismissive": -3,
        }

        recent = self.mood_history[-3:]
        values = [mood_values.get(m, 0) for m in recent]

        if len(values) >= 2:
            trend = values[-1] - values[0]
            if trend > 0:
                return "improving"
            elif trend < 0:
                return "declining"
        return "stable"

    def record_user_turn(self, text: str, mood: str) -> None:
        """Record a user speech turn."""
        self.user_turns += 1
        self.mood_history.append(mood)
        self._last_user_speech_time = time.time()
        self._detect_stage(text, "user")
        self._detect_objection(text)

    def record_agent_turn(self) -> None:
        """Record an agent speech turn and measure response time."""
        self.agent_turns += 1
        now = time.time()
        self._last_agent_speech_time = now
        if self._last_user_speech_time > 0:
            response_time = now - self._last_user_speech_time
            if response_time < 30:  # Sanity check
                self.response_times.append(response_time)

    def _detect_stage(self, text: str, speaker: str) -> None:
        """Detect conversation stage from text."""
        lower = text.lower()
        best_stage = self.stage
        best_score = 0

        for stage, keywords in _STAGE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in lower)
            if score > best_score:
                best_score = score
                best_stage = stage

        # Only advance stages (don't go backwards) unless we're in objection_handling
        if best_score > 0:
            current_idx = STAGES.index(self.stage) if self.stage in STAGES else 0
            new_idx = STAGES.index(best_stage) if best_stage in STAGES else 0
            if new_idx >= current_idx or best_stage == "objection_handling":
                self.stage = best_stage

    def _detect_objection(self, text: str) -> None:
        """Detect if user raised an objection."""
        objection_phrases = [
            "zu teuer",
            "kein budget",
            "keine zeit",
            "brauchen wir nicht",
            "haben wir schon",
            "kein interesse",
            "nicht interessiert",
            "nicht überzeugt",
            "zu kompliziert",
            "funktioniert nicht",
        ]
        lower = text.lower()
        if any(phrase in lower for phrase in objection_phrases):
            self.objection_count += 1

    def snapshot(self) -> dict:
        """Return current metrics as a dict for frontend publishing."""
        return {
            "duration_seconds": round(self.duration_seconds, 1),
            "turn_count": self.turn_count,
            "user_turns": self.user_turns,
            "agent_turns": self.agent_turns,
            "lead_score": self.lead_score,
            "current_stage": self.stage,
            "objection_count": self.objection_count,
            "avg_response_time_ms": round(self.avg_response_time_ms),
            "mood_trajectory": self.mood_trajectory,
        }
