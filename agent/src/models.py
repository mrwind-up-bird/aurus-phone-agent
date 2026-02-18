"""Pydantic models for structured LLM output and configuration."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class UserMood(str, Enum):
    """Detected mood of the user during conversation."""

    NEUTRAL = "neutral"
    INTERESTED = "interested"
    SKEPTICAL = "skeptical"
    FRUSTRATED = "frustrated"
    ENTHUSIASTIC = "enthusiastic"
    CONFUSED = "confused"
    DISMISSIVE = "dismissive"


class RequiredTone(str, Enum):
    """Tone the agent should adopt in response."""

    NEUTRAL = "neutral"
    REASSURING = "reassuring"
    ENTHUSIASTIC = "enthusiastic"
    EMPATHETIC = "empathetic"
    PROFESSIONAL = "professional"
    URGENT = "urgent"


class AgentAction(str, Enum):
    """Action the agent should take after responding."""

    CONTINUE = "continue"
    SCHEDULE = "schedule"
    TRANSFER = "transfer"
    END_CALL = "end_call"
    ESCALATE = "escalate"


class LLMResponse(BaseModel):
    """Structured JSON output from GPT-4o."""

    response_text: str = Field(description="The German text to speak")
    detected_user_mood: UserMood = Field(default=UserMood.NEUTRAL)
    required_tone: RequiredTone = Field(default=RequiredTone.NEUTRAL)
    action: AgentAction = Field(default=AgentAction.CONTINUE)


class VoiceConfig(BaseModel):
    """Voice configuration for a persona — uses Cartesia emotion strings."""

    cartesia_voice_id: str
    speed: str = Field(default="normal")  # Cartesia: fastest/fast/normal/slow/slowest
    emotions: dict[str, list[str]] = Field(default_factory=dict)  # tone -> Cartesia emotions


class PersonaConfig(BaseModel):
    """Configuration for a single persona."""

    name: str
    role: str
    description: str
    target_profiles: list[str] = Field(default_factory=list)
    voice: VoiceConfig
    system_prompt_addon: str = ""


class LeadMetadata(BaseModel):
    """Metadata about the lead being called."""

    name: str
    company: str = ""
    job_title: str = ""
    gender: str = ""
    phone: str = ""
    notes: str = ""
