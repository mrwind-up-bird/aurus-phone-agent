"""Tonality mapper — translates LLM emotion output to Cartesia TTS parameters."""

from __future__ import annotations

import structlog

from .models import PersonaConfig, RequiredTone

logger = structlog.get_logger()

# Fallback Cartesia emotions when persona doesn't define a specific tone
FALLBACK_EMOTIONS: dict[RequiredTone, list[str]] = {
    RequiredTone.NEUTRAL: ["Neutral"],
    RequiredTone.REASSURING: ["Trust", "Calm"],
    RequiredTone.ENTHUSIASTIC: ["Enthusiastic", "Excited"],
    RequiredTone.EMPATHETIC: ["Sympathetic", "Affectionate"],
    RequiredTone.PROFESSIONAL: ["Confident", "Determined"],
    RequiredTone.URGENT: ["Determined", "Anticipation"],
}

# Speed overrides per tone (Cartesia literal speeds)
SPEED_OVERRIDES: dict[RequiredTone, str] = {
    RequiredTone.REASSURING: "slow",
    RequiredTone.URGENT: "fast",
}


class TonalityMapper:
    """Maps required_tone from LLM output to Cartesia TTS parameters."""

    def __init__(self, persona: PersonaConfig) -> None:
        self._persona = persona

    def map_tone(self, tone: RequiredTone) -> dict:
        """Return Cartesia-compatible voice settings for the given tone.

        Returns a dict with:
            - voice_id: str
            - speed: str (Cartesia speed literal)
            - emotions: list[str] (Cartesia emotion strings)
        """
        tone_key = tone.value
        if tone_key in self._persona.voice.emotions:
            emotions = self._persona.voice.emotions[tone_key]
        elif tone in FALLBACK_EMOTIONS:
            emotions = FALLBACK_EMOTIONS[tone]
        else:
            emotions = ["Neutral"]

        # Use tone-specific speed override, otherwise persona default
        speed = SPEED_OVERRIDES.get(tone, self._persona.voice.speed)

        result = {
            "voice_id": self._persona.voice.cartesia_voice_id,
            "speed": speed,
            "emotions": emotions,
        }

        logger.debug("tonality_mapped", tone=tone.value, speed=speed, emotions=emotions)
        return result

    def update_persona(self, persona: PersonaConfig) -> None:
        """Switch to a different persona mid-call."""
        self._persona = persona
        logger.info("persona_switched", new_persona=persona.name)
