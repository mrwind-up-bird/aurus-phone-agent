"""Tests for Pydantic models and enums."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.models import (
    AgentAction,
    LeadMetadata,
    LLMResponse,
    PersonaConfig,
    RequiredTone,
    UserMood,
    VoiceConfig,
)


class TestUserMood:
    """Tests for the UserMood enum."""

    def test_all_values_exist(self) -> None:
        """All expected mood values are present."""
        expected = {"neutral", "interested", "skeptical", "frustrated", "enthusiastic", "confused", "dismissive"}
        actual = {m.value for m in UserMood}
        assert actual == expected

    def test_string_access(self) -> None:
        """Moods can be accessed by string value."""
        assert UserMood("neutral") is UserMood.NEUTRAL
        assert UserMood("enthusiastic") is UserMood.ENTHUSIASTIC

    def test_invalid_value_raises(self) -> None:
        """Invalid mood value raises ValueError."""
        with pytest.raises(ValueError):
            UserMood("angry")


class TestRequiredTone:
    """Tests for the RequiredTone enum."""

    def test_all_values_exist(self) -> None:
        """All expected tone values are present."""
        expected = {"neutral", "reassuring", "enthusiastic", "empathetic", "professional", "urgent"}
        actual = {t.value for t in RequiredTone}
        assert actual == expected

    def test_invalid_value_raises(self) -> None:
        """Invalid tone value raises ValueError."""
        with pytest.raises(ValueError):
            RequiredTone("aggressive")


class TestAgentAction:
    """Tests for the AgentAction enum."""

    def test_all_values_exist(self) -> None:
        """All expected action values are present."""
        expected = {"continue", "schedule", "transfer", "end_call", "escalate"}
        actual = {a.value for a in AgentAction}
        assert actual == expected

    def test_invalid_value_raises(self) -> None:
        """Invalid action value raises ValueError."""
        with pytest.raises(ValueError):
            AgentAction("hangup")


class TestLLMResponse:
    """Tests for the LLMResponse model."""

    def test_defaults(self) -> None:
        """LLMResponse uses correct defaults when only response_text is given."""
        resp = LLMResponse(response_text="Hallo")
        assert resp.response_text == "Hallo"
        assert resp.detected_user_mood is UserMood.NEUTRAL
        assert resp.required_tone is RequiredTone.NEUTRAL
        assert resp.action is AgentAction.CONTINUE

    def test_full_construction(self) -> None:
        """LLMResponse constructs correctly with all fields."""
        resp = LLMResponse(
            response_text="Toll!",
            detected_user_mood=UserMood.ENTHUSIASTIC,
            required_tone=RequiredTone.ENTHUSIASTIC,
            action=AgentAction.SCHEDULE,
        )
        assert resp.response_text == "Toll!"
        assert resp.detected_user_mood is UserMood.ENTHUSIASTIC
        assert resp.required_tone is RequiredTone.ENTHUSIASTIC
        assert resp.action is AgentAction.SCHEDULE

    def test_json_serialization(self) -> None:
        """LLMResponse serializes to and from JSON correctly."""
        resp = LLMResponse(
            response_text="Test",
            detected_user_mood=UserMood.INTERESTED,
            required_tone=RequiredTone.REASSURING,
            action=AgentAction.TRANSFER,
        )
        data = json.loads(resp.model_dump_json())
        assert data["response_text"] == "Test"
        assert data["detected_user_mood"] == "interested"
        assert data["required_tone"] == "reassuring"
        assert data["action"] == "transfer"

        restored = LLMResponse.model_validate(data)
        assert restored == resp

    def test_empty_response_text(self) -> None:
        """LLMResponse accepts empty string for response_text."""
        resp = LLMResponse(response_text="")
        assert resp.response_text == ""

    def test_missing_response_text_raises(self) -> None:
        """LLMResponse requires response_text."""
        with pytest.raises(ValidationError):
            LLMResponse()  # type: ignore[call-arg]


class TestVoiceConfig:
    """Tests for the VoiceConfig model."""

    def test_defaults(self) -> None:
        """VoiceConfig uses correct defaults."""
        vc = VoiceConfig(cartesia_voice_id="abc123")
        assert vc.cartesia_voice_id == "abc123"
        assert vc.speed == "normal"
        assert vc.emotions == {}

    def test_full_construction(self) -> None:
        """VoiceConfig with all fields set."""
        vc = VoiceConfig(
            cartesia_voice_id="xyz",
            speed="fast",
            emotions={"default": ["Confident"], "reassuring": ["Calm", "Trust"]},
        )
        assert vc.speed == "fast"
        assert vc.emotions["default"] == ["Confident"]
        assert len(vc.emotions["reassuring"]) == 2


class TestPersonaConfig:
    """Tests for the PersonaConfig model."""

    def test_defaults(self) -> None:
        """PersonaConfig uses correct defaults for optional fields."""
        voice = VoiceConfig(cartesia_voice_id="v1")
        pc = PersonaConfig(name="Test", role="Tester", description="A test persona", voice=voice)
        assert pc.target_profiles == []
        assert pc.system_prompt_addon == ""

    def test_full_construction(self) -> None:
        """PersonaConfig constructs correctly with all fields."""
        voice = VoiceConfig(cartesia_voice_id="v1", speed="slow")
        pc = PersonaConfig(
            name="Alpha",
            role="Closer",
            description="The closer",
            target_profiles=["CEO", "CFO"],
            voice=voice,
            system_prompt_addon="Be assertive.",
        )
        assert pc.name == "Alpha"
        assert len(pc.target_profiles) == 2
        assert pc.system_prompt_addon == "Be assertive."

    def test_missing_required_fields_raises(self) -> None:
        """PersonaConfig requires name, role, description, and voice."""
        with pytest.raises(ValidationError):
            PersonaConfig(name="X", role="Y", description="Z")  # type: ignore[call-arg]


class TestLeadMetadata:
    """Tests for the LeadMetadata model."""

    def test_defaults(self) -> None:
        """LeadMetadata uses correct defaults for optional fields."""
        lead = LeadMetadata(name="Alice")
        assert lead.company == ""
        assert lead.job_title == ""
        assert lead.gender == ""
        assert lead.phone == ""
        assert lead.notes == ""

    def test_full_construction(self, sample_lead: LeadMetadata) -> None:
        """LeadMetadata constructs correctly with all fields."""
        assert sample_lead.name == "Max Mustermann"
        assert sample_lead.company == "ACME GmbH"
        assert sample_lead.job_title == "CTO"
        assert sample_lead.gender == "male"

    def test_missing_name_raises(self) -> None:
        """LeadMetadata requires name."""
        with pytest.raises(ValidationError):
            LeadMetadata()  # type: ignore[call-arg]

    def test_json_round_trip(self, sample_lead: LeadMetadata) -> None:
        """LeadMetadata survives JSON serialization round-trip."""
        data = json.loads(sample_lead.model_dump_json())
        restored = LeadMetadata.model_validate(data)
        assert restored == sample_lead
