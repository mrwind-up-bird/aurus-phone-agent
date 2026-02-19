"""Tests for CallMetrics — lead scoring, mood tracking, stage detection."""

from __future__ import annotations

import time
from unittest.mock import patch

from src.call_metrics import STAGES, CallMetrics


class TestLeadScore:
    """Tests for the lead_score property."""

    def test_default_score_is_50(self) -> None:
        """Empty mood history returns base score of 50."""
        m = CallMetrics()
        assert m.lead_score == 50

    def test_enthusiastic_history_boosts_score(self) -> None:
        """All enthusiastic moods push score well above 50."""
        m = CallMetrics()
        m.mood_history = ["enthusiastic"] * 5
        assert m.lead_score > 70

    def test_dismissive_history_lowers_score(self) -> None:
        """All dismissive moods push score well below 50."""
        m = CallMetrics()
        m.mood_history = ["dismissive"] * 5
        assert m.lead_score < 30

    def test_score_capped_at_0(self) -> None:
        """Score never goes below 0."""
        m = CallMetrics()
        m.mood_history = ["dismissive"] * 20
        assert m.lead_score >= 0

    def test_score_capped_at_100(self) -> None:
        """Score never goes above 100."""
        m = CallMetrics()
        m.mood_history = ["enthusiastic"] * 20
        m.user_turns = 10
        m.stage = "closing"
        assert m.lead_score <= 100

    def test_engagement_bonus_at_3_turns(self) -> None:
        """Score increases when user_turns >= 3."""
        m1 = CallMetrics()
        m1.mood_history = ["neutral"]
        m1.user_turns = 2

        m2 = CallMetrics()
        m2.mood_history = ["neutral"]
        m2.user_turns = 3

        assert m2.lead_score > m1.lead_score

    def test_engagement_bonus_at_6_turns(self) -> None:
        """Score increases further when user_turns >= 6."""
        m1 = CallMetrics()
        m1.mood_history = ["neutral"]
        m1.user_turns = 5

        m2 = CallMetrics()
        m2.mood_history = ["neutral"]
        m2.user_turns = 6

        assert m2.lead_score > m1.lead_score

    def test_stage_progression_bonus(self) -> None:
        """Later stages yield higher scores."""
        m1 = CallMetrics()
        m1.mood_history = ["neutral"]
        m1.stage = "greeting"

        m2 = CallMetrics()
        m2.mood_history = ["neutral"]
        m2.stage = "closing"

        assert m2.lead_score > m1.lead_score

    def test_objection_handling_bonus_when_stayed(self) -> None:
        """User staying after objections adds bonus."""
        m = CallMetrics()
        m.mood_history = ["neutral"]
        m.objection_count = 1
        m.user_turns = 5  # More than objection_count * 2
        score_with_objections = m.lead_score

        m2 = CallMetrics()
        m2.mood_history = ["neutral"]
        m2.objection_count = 0
        m2.user_turns = 5
        score_without = m2.lead_score

        assert score_with_objections > score_without

    def test_single_mood_entry(self) -> None:
        """Single mood entry still produces valid score."""
        m = CallMetrics()
        m.mood_history = ["interested"]
        score = m.lead_score
        assert 50 <= score <= 100


class TestMoodTrajectory:
    """Tests for the mood_trajectory property."""

    def test_stable_with_empty_history(self) -> None:
        """Empty history returns stable."""
        m = CallMetrics()
        assert m.mood_trajectory == "stable"

    def test_stable_with_single_entry(self) -> None:
        """Single entry returns stable."""
        m = CallMetrics()
        m.mood_history = ["neutral"]
        assert m.mood_trajectory == "stable"

    def test_improving_trajectory(self) -> None:
        """Going from frustrated to enthusiastic is improving."""
        m = CallMetrics()
        m.mood_history = ["frustrated", "neutral", "enthusiastic"]
        assert m.mood_trajectory == "improving"

    def test_declining_trajectory(self) -> None:
        """Going from enthusiastic to frustrated is declining."""
        m = CallMetrics()
        m.mood_history = ["enthusiastic", "neutral", "frustrated"]
        assert m.mood_trajectory == "declining"

    def test_stable_same_moods(self) -> None:
        """Same mood repeated is stable."""
        m = CallMetrics()
        m.mood_history = ["neutral", "neutral", "neutral"]
        assert m.mood_trajectory == "stable"

    def test_uses_last_three_entries(self) -> None:
        """Only the last 3 entries matter for trajectory."""
        m = CallMetrics()
        m.mood_history = ["dismissive", "dismissive", "neutral", "interested", "enthusiastic"]
        assert m.mood_trajectory == "improving"


class TestRecordUserTurn:
    """Tests for record_user_turn method."""

    def test_increments_turn_count(self) -> None:
        """User turn count increments."""
        m = CallMetrics()
        m.record_user_turn("hallo", "neutral")
        assert m.user_turns == 1
        m.record_user_turn("ja", "interested")
        assert m.user_turns == 2

    def test_appends_mood(self) -> None:
        """Mood is appended to history."""
        m = CallMetrics()
        m.record_user_turn("text", "interested")
        assert m.mood_history == ["interested"]

    def test_detects_stage_from_text(self) -> None:
        """Stage detection runs on user text."""
        m = CallMetrics()
        m.record_user_turn("wann passt Ihnen ein Termin?", "interested")
        assert m.stage == "closing"

    def test_detects_objection(self) -> None:
        """Objection count increments on objection phrases."""
        m = CallMetrics()
        m.record_user_turn("Das ist zu teuer fuer uns", "skeptical")
        assert m.objection_count == 1


class TestRecordAgentTurn:
    """Tests for record_agent_turn method."""

    def test_increments_agent_turns(self) -> None:
        """Agent turn count increments."""
        m = CallMetrics()
        m.record_agent_turn()
        assert m.agent_turns == 1

    def test_measures_response_time(self) -> None:
        """Response time is recorded after a user turn."""
        m = CallMetrics()
        m._last_user_speech_time = time.time() - 0.5  # 500ms ago
        m.record_agent_turn()
        assert len(m.response_times) == 1
        assert 0.3 < m.response_times[0] < 2.0  # reasonable range

    def test_skips_response_time_without_user_turn(self) -> None:
        """No response time recorded if no prior user speech."""
        m = CallMetrics()
        m.record_agent_turn()
        assert m.response_times == []

    def test_skips_stale_response_time(self) -> None:
        """Response times over 30s are discarded as stale."""
        m = CallMetrics()
        m._last_user_speech_time = time.time() - 35  # 35s ago
        m.record_agent_turn()
        assert m.response_times == []


class TestDetectStage:
    """Tests for _detect_stage method."""

    def test_greeting_detected(self) -> None:
        """Greeting keywords trigger greeting stage."""
        m = CallMetrics()
        m._detect_stage("Guten Tag, mein Name ist Lukas", "agent")
        assert m.stage == "greeting"

    def test_pitch_detected(self) -> None:
        """Pitch keywords advance stage."""
        m = CallMetrics()
        m.stage = "qualification"  # must be past greeting
        m._detect_stage("unsere Loesung bietet viele Vorteile", "agent")
        assert m.stage == "pitch"

    def test_closing_detected(self) -> None:
        """Closing keywords advance stage."""
        m = CallMetrics()
        m.stage = "pitch"
        m._detect_stage("wann passt Ihnen ein Termin fuer eine Demo?", "user")
        assert m.stage == "closing"

    def test_no_backward_progression(self) -> None:
        """Stage does not go backwards (except objection_handling)."""
        m = CallMetrics()
        m.stage = "closing"
        m._detect_stage("guten tag", "agent")  # greeting keyword
        assert m.stage == "closing"

    def test_objection_handling_can_go_back(self) -> None:
        """Objection handling is allowed even from a later stage."""
        m = CallMetrics()
        m.stage = "closing"
        m._detect_stage("das ist zu teuer, kein budget dafuer", "user")
        assert m.stage == "objection_handling"

    def test_no_match_keeps_current_stage(self) -> None:
        """Text with no keywords keeps current stage."""
        m = CallMetrics()
        m.stage = "pitch"
        m._detect_stage("xyz abc", "user")
        assert m.stage == "pitch"


class TestDetectObjection:
    """Tests for _detect_objection method."""

    def test_all_objection_phrases(self) -> None:
        """Each known objection phrase increments the counter."""
        phrases = [
            "zu teuer", "kein budget", "keine zeit", "brauchen wir nicht",
            "haben wir schon", "kein interesse", "nicht interessiert",
            "nicht überzeugt", "zu kompliziert", "funktioniert nicht",
        ]
        for phrase in phrases:
            m = CallMetrics()
            m._detect_objection(f"Also, {phrase} ehrlich gesagt.")
            assert m.objection_count == 1, f"Failed for: {phrase}"

    def test_no_objection_in_clean_text(self) -> None:
        """Normal text does not trigger objection detection."""
        m = CallMetrics()
        m._detect_objection("Klingt spannend, erzaehlen Sie mehr!")
        assert m.objection_count == 0

    def test_case_insensitive_detection(self) -> None:
        """Objection detection is case-insensitive."""
        m = CallMetrics()
        m._detect_objection("Das ist ZU TEUER!")
        assert m.objection_count == 1


class TestSnapshot:
    """Tests for the snapshot method."""

    def test_all_keys_present(self) -> None:
        """Snapshot dict contains all expected keys."""
        m = CallMetrics()
        snap = m.snapshot()
        expected_keys = {
            "duration_seconds", "turn_count", "user_turns", "agent_turns",
            "lead_score", "current_stage", "objection_count",
            "avg_response_time_ms", "mood_trajectory",
        }
        assert set(snap.keys()) == expected_keys

    def test_snapshot_types(self) -> None:
        """Snapshot values have expected types."""
        m = CallMetrics()
        m.record_user_turn("hallo", "neutral")
        snap = m.snapshot()
        assert isinstance(snap["duration_seconds"], float)
        assert isinstance(snap["turn_count"], int)
        assert isinstance(snap["lead_score"], int)
        assert isinstance(snap["current_stage"], str)
        assert isinstance(snap["avg_response_time_ms"], (int, float))
        assert isinstance(snap["mood_trajectory"], str)

    def test_snapshot_reflects_state(self) -> None:
        """Snapshot accurately reflects current metrics state."""
        m = CallMetrics()
        m.record_user_turn("guten tag", "neutral")
        m.record_user_turn("klingt gut", "interested")
        m.record_agent_turn()

        snap = m.snapshot()
        assert snap["user_turns"] == 2
        assert snap["agent_turns"] == 1
        assert snap["turn_count"] == 3


class TestProperties:
    """Tests for computed properties."""

    def test_turn_count(self) -> None:
        """Turn count is user + agent turns."""
        m = CallMetrics()
        m.user_turns = 3
        m.agent_turns = 2
        assert m.turn_count == 5

    def test_avg_response_time_empty(self) -> None:
        """Average response time is 0 with no data."""
        m = CallMetrics()
        assert m.avg_response_time_ms == 0.0

    def test_avg_response_time_calculation(self) -> None:
        """Average response time converts seconds to milliseconds."""
        m = CallMetrics()
        m.response_times = [0.5, 1.0, 1.5]
        assert m.avg_response_time_ms == 1000.0

    def test_duration_seconds(self) -> None:
        """Duration is positive and grows over time."""
        m = CallMetrics(start_time=1000.0)
        with patch("src.call_metrics.time.time", return_value=1005.0):
            assert abs(m.duration_seconds - 5.0) < 0.01
