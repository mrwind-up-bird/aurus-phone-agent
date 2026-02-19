"""Tests for TonalityMapper — tone-to-TTS parameter mapping."""

from __future__ import annotations

from src.models import PersonaConfig, RequiredTone, VoiceConfig
from src.tonality_mapper import FALLBACK_EMOTIONS, SPEED_OVERRIDES, TonalityMapper


def _make_persona(
    voice_id: str = "test-voice",
    speed: str = "normal",
    emotions: dict[str, list[str]] | None = None,
) -> PersonaConfig:
    """Helper to build a PersonaConfig for testing."""
    return PersonaConfig(
        name="TestPersona",
        role="Tester",
        description="A test persona.",
        voice=VoiceConfig(
            cartesia_voice_id=voice_id,
            speed=speed,
            emotions=emotions or {},
        ),
    )


class TestMapTone:
    """Tests for the map_tone method."""

    def test_returns_dict_with_correct_keys(self) -> None:
        """Result dict has voice_id, speed, and emotions keys."""
        persona = _make_persona()
        mapper = TonalityMapper(persona)
        result = mapper.map_tone(RequiredTone.NEUTRAL)
        assert set(result.keys()) == {"voice_id", "speed", "emotions"}

    def test_voice_id_from_persona(self) -> None:
        """Voice ID comes from persona config."""
        persona = _make_persona(voice_id="my-voice-123")
        mapper = TonalityMapper(persona)
        result = mapper.map_tone(RequiredTone.NEUTRAL)
        assert result["voice_id"] == "my-voice-123"

    def test_persona_specific_emotions_used(self) -> None:
        """Persona-specific emotions take precedence over fallback."""
        persona = _make_persona(emotions={"neutral": ["Custom1", "Custom2"]})
        mapper = TonalityMapper(persona)
        result = mapper.map_tone(RequiredTone.NEUTRAL)
        assert result["emotions"] == ["Custom1", "Custom2"]

    def test_fallback_emotions_used(self) -> None:
        """Fallback emotions are used when persona does not define the tone."""
        persona = _make_persona(emotions={})  # no tone-specific emotions
        mapper = TonalityMapper(persona)
        result = mapper.map_tone(RequiredTone.ENTHUSIASTIC)
        assert result["emotions"] == FALLBACK_EMOTIONS[RequiredTone.ENTHUSIASTIC]

    def test_all_tones_have_fallback(self) -> None:
        """Every RequiredTone has a fallback emotion mapping."""
        for tone in RequiredTone:
            assert tone in FALLBACK_EMOTIONS, f"Missing fallback for {tone}"

    def test_all_tones_produce_valid_output(self) -> None:
        """map_tone works for every RequiredTone value."""
        persona = _make_persona()
        mapper = TonalityMapper(persona)
        for tone in RequiredTone:
            result = mapper.map_tone(tone)
            assert isinstance(result["emotions"], list)
            assert len(result["emotions"]) > 0
            assert isinstance(result["speed"], str)

    def test_speed_override_reassuring(self) -> None:
        """REASSURING tone overrides speed to slow."""
        persona = _make_persona(speed="normal")
        mapper = TonalityMapper(persona)
        result = mapper.map_tone(RequiredTone.REASSURING)
        assert result["speed"] == "slow"

    def test_speed_override_urgent(self) -> None:
        """URGENT tone overrides speed to fast."""
        persona = _make_persona(speed="normal")
        mapper = TonalityMapper(persona)
        result = mapper.map_tone(RequiredTone.URGENT)
        assert result["speed"] == "fast"

    def test_no_speed_override_for_neutral(self) -> None:
        """NEUTRAL tone uses persona default speed."""
        persona = _make_persona(speed="slow")
        mapper = TonalityMapper(persona)
        result = mapper.map_tone(RequiredTone.NEUTRAL)
        assert result["speed"] == "slow"

    def test_speed_overrides_match_expected(self) -> None:
        """Verify the speed overrides dict contents."""
        assert SPEED_OVERRIDES[RequiredTone.REASSURING] == "slow"
        assert SPEED_OVERRIDES[RequiredTone.URGENT] == "fast"
        assert len(SPEED_OVERRIDES) == 2


class TestUpdatePersona:
    """Tests for the update_persona method."""

    def test_changes_voice_id(self) -> None:
        """After update, map_tone uses the new persona's voice ID."""
        persona1 = _make_persona(voice_id="voice-1")
        persona2 = _make_persona(voice_id="voice-2")
        mapper = TonalityMapper(persona1)

        result1 = mapper.map_tone(RequiredTone.NEUTRAL)
        assert result1["voice_id"] == "voice-1"

        mapper.update_persona(persona2)

        result2 = mapper.map_tone(RequiredTone.NEUTRAL)
        assert result2["voice_id"] == "voice-2"

    def test_changes_emotions(self) -> None:
        """After update, persona-specific emotions from the new persona are used."""
        persona1 = _make_persona(emotions={"neutral": ["Old"]})
        persona2 = _make_persona(emotions={"neutral": ["New1", "New2"]})
        mapper = TonalityMapper(persona1)

        mapper.update_persona(persona2)
        result = mapper.map_tone(RequiredTone.NEUTRAL)
        assert result["emotions"] == ["New1", "New2"]

    def test_changes_default_speed(self) -> None:
        """After update, persona default speed changes."""
        persona1 = _make_persona(speed="normal")
        persona2 = _make_persona(speed="fast")
        mapper = TonalityMapper(persona1)

        mapper.update_persona(persona2)
        result = mapper.map_tone(RequiredTone.NEUTRAL)  # no speed override
        assert result["speed"] == "fast"
