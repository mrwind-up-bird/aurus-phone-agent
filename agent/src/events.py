"""Event models for real-time frontend communication via LiveKit data channels."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events sent to the frontend."""

    AGENT_STATE = "agent_state"
    MOOD_UPDATE = "mood_update"
    PERSONA_CHANGE = "persona_change"
    TRANSCRIPT = "transcript"
    METRICS = "metrics"


class AgentState(str, Enum):
    """Current state of the agent pipeline."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    FILLER = "filler"


class AgentEvent(BaseModel):
    """Event payload sent to the frontend via LiveKit data channel."""

    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = 0.0


class MoodUpdateEvent(BaseModel):
    """Mood detection event for the sentiment graph."""

    mood: str
    confidence: float = 1.0
    tone: str = ""


class TranscriptEvent(BaseModel):
    """Transcript event for conversation display."""

    speaker: str  # "user" or "agent"
    text: str
    is_final: bool = True
