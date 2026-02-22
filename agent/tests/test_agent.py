"""Tests for AurusVoiceAgent — mood detection, greeting building, transcript recording."""

from __future__ import annotations

from unittest.mock import patch

from src.agent import AurusVoiceAgent
from src.models import LeadMetadata, UserMood
from src.voice_sentiment import _classify_keywords


class TestDetectMood:
    """Tests for keyword-based mood detection (now in voice_sentiment module)."""

    def test_enthusiastic_keywords(self) -> None:
        """Enthusiastic keywords produce ENTHUSIASTIC mood."""
        mood, _ = _classify_keywords("Das ist super toll!")
        assert mood is UserMood.ENTHUSIASTIC

    def test_interested_keywords(self) -> None:
        """Interest keywords produce INTERESTED mood."""
        mood, _ = _classify_keywords("Das klingt interessant, erzählen Sie mehr")
        assert mood is UserMood.INTERESTED

    def test_skeptical_keywords(self) -> None:
        """Skeptical keywords produce SKEPTICAL mood."""
        mood, _ = _classify_keywords("Ich bin nicht überzeugt, weiß nicht")
        assert mood is UserMood.SKEPTICAL

    def test_frustrated_keywords(self) -> None:
        """Frustrated keywords produce FRUSTRATED mood."""
        mood, _ = _classify_keywords("Das ist nervig, keine zeit dafür")
        assert mood is UserMood.FRUSTRATED

    def test_confused_keywords(self) -> None:
        """Confused keywords produce CONFUSED mood."""
        mood, _ = _classify_keywords("Ich verstehe nicht, wie bitte?")
        assert mood is UserMood.CONFUSED

    def test_dismissive_keywords(self) -> None:
        """Dismissive keywords produce DISMISSIVE mood."""
        mood, _ = _classify_keywords("Kein interesse, auf wiedersehen")
        assert mood is UserMood.DISMISSIVE

    def test_no_keywords_returns_neutral(self) -> None:
        """Text with no mood keywords returns NEUTRAL."""
        mood, _ = _classify_keywords("Okay")
        assert mood is UserMood.NEUTRAL

    def test_empty_string_returns_neutral(self) -> None:
        """Empty text returns NEUTRAL."""
        mood, _ = _classify_keywords("")
        assert mood is UserMood.NEUTRAL

    def test_mixed_keywords_highest_score_wins(self) -> None:
        """When multiple moods match, the one with the most keyword hits wins."""
        mood, _ = _classify_keywords("Super toll großartig, aber vielleicht")
        assert mood is UserMood.ENTHUSIASTIC

    def test_case_insensitive(self) -> None:
        """Mood detection is case-insensitive."""
        mood, _ = _classify_keywords("SUPER TOLL")
        assert mood is UserMood.ENTHUSIASTIC


class TestBuildGreeting:
    """Tests for _build_greeting static method."""

    def test_morning_greeting(self) -> None:
        """Before noon, greeting starts with 'Guten Morgen'."""
        from datetime import datetime as real_dt

        mock_dt = real_dt(2025, 1, 15, 9, 0)
        lead = LeadMetadata(name="Max Test")
        with patch("src.agent.datetime") as dt_mock:
            dt_mock.now.return_value = mock_dt
            greeting = AurusVoiceAgent._build_greeting(lead, "Lukas")
        assert "Guten Morgen" in greeting

    def test_afternoon_greeting(self) -> None:
        """Between noon and 6pm, greeting starts with 'Guten Tag'."""
        from datetime import datetime as real_dt

        mock_dt = real_dt(2025, 1, 15, 14, 0)
        lead = LeadMetadata(name="Max Test")
        with patch("src.agent.datetime") as dt_mock:
            dt_mock.now.return_value = mock_dt
            greeting = AurusVoiceAgent._build_greeting(lead, "Sarah")
        assert "Guten Tag" in greeting

    def test_evening_greeting(self) -> None:
        """After 6pm, greeting starts with 'Guten Abend'."""
        from datetime import datetime as real_dt

        mock_dt = real_dt(2025, 1, 15, 20, 0)
        lead = LeadMetadata(name="Max Test")
        with patch("src.agent.datetime") as dt_mock:
            dt_mock.now.return_value = mock_dt
            greeting = AurusVoiceAgent._build_greeting(lead, "Marcus")
        assert "Guten Abend" in greeting

    def test_greeting_includes_persona_name(self) -> None:
        """Greeting mentions the persona name."""
        lead = LeadMetadata(name="Test Lead")
        greeting = AurusVoiceAgent._build_greeting(lead, "Lukas")
        assert "Lukas" in greeting
        assert "Aurus" in greeting

    def test_greeting_with_male_gender(self) -> None:
        """Male lead is addressed as 'Herr {last_name}'."""
        lead = LeadMetadata(name="Max Mustermann", gender="male")
        greeting = AurusVoiceAgent._build_greeting(lead, "Sarah")
        assert "Herr Mustermann" in greeting

    def test_greeting_with_female_gender(self) -> None:
        """Female lead is addressed as 'Frau {last_name}'."""
        lead = LeadMetadata(name="Anna Schmidt", gender="female")
        greeting = AurusVoiceAgent._build_greeting(lead, "Lukas")
        assert "Frau Schmidt" in greeting

    def test_greeting_with_herr_gender(self) -> None:
        """Gender 'herr' is recognized as male."""
        lead = LeadMetadata(name="Max Test", gender="herr")
        greeting = AurusVoiceAgent._build_greeting(lead, "Sarah")
        assert "Herr Test" in greeting

    def test_greeting_without_gender(self) -> None:
        """Without gender, greeting uses first name."""
        lead = LeadMetadata(name="Max Mustermann")
        greeting = AurusVoiceAgent._build_greeting(lead, "Sarah")
        assert "Max" in greeting
        assert "Herr" not in greeting
        assert "Frau" not in greeting

    def test_greeting_with_company(self) -> None:
        """Greeting includes company mention when provided."""
        lead = LeadMetadata(name="Max Test", company="ACME GmbH")
        greeting = AurusVoiceAgent._build_greeting(lead, "Lukas")
        assert "ACME GmbH" in greeting
        assert "bezüglich" in greeting

    def test_greeting_without_company(self) -> None:
        """No company reference when company is empty."""
        lead = LeadMetadata(name="Max Test", company="")
        greeting = AurusVoiceAgent._build_greeting(lead, "Lukas")
        assert "bezüglich" not in greeting

    def test_greeting_unknown_lead(self) -> None:
        """Unknown lead name is not included in greeting."""
        lead = LeadMetadata(name="Unknown Lead")
        greeting = AurusVoiceAgent._build_greeting(lead, "Lukas")
        assert "Unknown Lead" not in greeting

    def test_greeting_ends_with_question(self) -> None:
        """Greeting ends with a question mark (asking if lead has time)."""
        lead = LeadMetadata(name="Test")
        greeting = AurusVoiceAgent._build_greeting(lead, "Lukas")
        assert greeting.endswith("?")


class TestRecordTranscript:
    """Tests for _record_transcript method."""

    def test_appends_entry(self) -> None:
        """_record_transcript appends a TranscriptItem."""
        agent = AurusVoiceAgent.__new__(AurusVoiceAgent)
        agent._transcript = []
        agent._record_transcript("user", "Hallo", mood="interested")
        assert len(agent._transcript) == 1
        assert agent._transcript[0].speaker == "user"
        assert agent._transcript[0].text == "Hallo"
        assert agent._transcript[0].mood == "interested"

    def test_multiple_entries(self) -> None:
        """Multiple calls append in order."""
        agent = AurusVoiceAgent.__new__(AurusVoiceAgent)
        agent._transcript = []
        agent._record_transcript("agent", "Guten Tag")
        agent._record_transcript("user", "Hi")
        agent._record_transcript("agent", "Wie kann ich helfen?")
        assert len(agent._transcript) == 3
        assert agent._transcript[0].speaker == "agent"
        assert agent._transcript[1].speaker == "user"
        assert agent._transcript[2].speaker == "agent"

    def test_default_mood(self) -> None:
        """Default mood is 'neutral'."""
        agent = AurusVoiceAgent.__new__(AurusVoiceAgent)
        agent._transcript = []
        agent._record_transcript("agent", "Test")
        assert agent._transcript[0].mood == "neutral"

    def test_timestamp_set(self) -> None:
        """Transcript entry has a positive timestamp."""
        agent = AurusVoiceAgent.__new__(AurusVoiceAgent)
        agent._transcript = []
        agent._record_transcript("user", "Test")
        assert agent._transcript[0].timestamp > 0
