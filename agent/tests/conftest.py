"""Shared fixtures for Aurus Voice Agent tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.conversation_store import TranscriptItem
from src.models import LeadMetadata


@pytest.fixture()
def tmp_conversations_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for ConversationStore tests."""
    d = tmp_path / "conversations"
    d.mkdir()
    return d


@pytest.fixture()
def sample_lead() -> LeadMetadata:
    """Provide a fully-populated LeadMetadata fixture."""
    return LeadMetadata(
        name="Max Mustermann",
        company="ACME GmbH",
        job_title="CTO",
        gender="male",
        phone="+49 123 456789",
        notes="Interested in automation",
    )


@pytest.fixture()
def sample_persona_yaml(tmp_path: Path) -> Path:
    """Create a temporary personas YAML file for testing."""
    content = textwrap.dedent("""\
        personas:
          alpha:
            name: "Alpha"
            role: "The Tester"
            description: "Test persona alpha."
            target_profiles:
              - "CEO"
              - "CFO"
            voice:
              cartesia_voice_id: "voice-alpha-id"
              speed: "normal"
              emotions:
                default: ["Confident"]
                reassuring: ["Trust", "Calm"]
                enthusiastic: ["Enthusiastic"]
            system_prompt_addon: "Du bist Alpha."
          beta:
            name: "Beta"
            role: "The Helper"
            description: "Test persona beta."
            target_profiles:
              - "Developer"
            voice:
              cartesia_voice_id: "voice-beta-id"
              speed: "fast"
              emotions:
                default: ["Curious"]
            system_prompt_addon: "Du bist Beta."

        routing:
          gender_override:
            male: "beta"
            female: "alpha"
          title_matching:
            - pattern: "CEO|CFO"
              persona: "alpha"
            - pattern: "Developer|Engineer"
              persona: "beta"
          default: "alpha"
    """)
    yaml_path = tmp_path / "personas.yaml"
    yaml_path.write_text(content)
    return yaml_path


@pytest.fixture()
def sample_transcript() -> list[TranscriptItem]:
    """Provide a multi-turn transcript fixture."""
    return [
        TranscriptItem(speaker="agent", text="Guten Tag, hier ist Lukas von Aurus.", timestamp=1000.0, mood="neutral"),
        TranscriptItem(speaker="user", text="Hallo, was genau bieten Sie an?", timestamp=1005.0, mood="interested"),
        TranscriptItem(speaker="agent", text="Wir bieten KI-Vertriebsautomatisierung.", timestamp=1008.0, mood="neutral"),
        TranscriptItem(speaker="user", text="Klingt interessant, erzaehlen Sie mehr.", timestamp=1015.0, mood="interested"),
        TranscriptItem(speaker="agent", text="Unsere Loesung spart 15 Stunden pro Woche.", timestamp=1018.0, mood="neutral"),
        TranscriptItem(speaker="user", text="Das ist zu teuer fuer uns.", timestamp=1025.0, mood="skeptical"),
        TranscriptItem(speaker="agent", text="Unsere Kunden sehen ROI in 30 Tagen.", timestamp=1028.0, mood="neutral"),
        TranscriptItem(speaker="user", text="Okay, schicken Sie mir Unterlagen.", timestamp=1035.0, mood="interested"),
    ]
