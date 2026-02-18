"""Persona manager — loads YAML configs and routes leads to optimal persona."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from .models import LeadMetadata, PersonaConfig, VoiceConfig

logger = structlog.get_logger()

DEFAULT_PERSONAS_PATH = Path(__file__).parent.parent / "personas.yaml"


class PersonaManager:
    """Loads persona definitions and routes leads to the best match."""

    def __init__(self, config_path: Path = DEFAULT_PERSONAS_PATH) -> None:
        self._config_path = config_path
        self._personas: dict[str, PersonaConfig] = {}
        self._routing: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load and validate persona configuration from YAML."""
        raw = yaml.safe_load(self._config_path.read_text())

        for key, data in raw.get("personas", {}).items():
            voice_data = data.get("voice", {})
            voice = VoiceConfig(
                cartesia_voice_id=voice_data["cartesia_voice_id"],
                speed=voice_data.get("speed", "normal"),
                emotions=voice_data.get("emotions", {}),
            )
            self._personas[key] = PersonaConfig(
                name=data["name"],
                role=data["role"],
                description=data["description"],
                target_profiles=data.get("target_profiles", []),
                voice=voice,
                system_prompt_addon=data.get("system_prompt_addon", ""),
            )

        self._routing = raw.get("routing", {})
        logger.info("personas_loaded", count=len(self._personas))

    def route(self, lead: LeadMetadata) -> PersonaConfig:
        """Select the optimal persona for a given lead."""
        # 1. Try job title matching first (highest priority)
        if lead.job_title:
            for rule in self._routing.get("title_matching", []):
                if re.search(rule["pattern"], lead.job_title, re.IGNORECASE):
                    persona_key = rule["persona"]
                    logger.info(
                        "persona_routed",
                        method="title",
                        lead=lead.name,
                        persona=persona_key,
                    )
                    return self._personas[persona_key]

        # 2. Try gender-based psychological balancing
        if lead.gender:
            gender_key = lead.gender.lower()
            gender_overrides = self._routing.get("gender_override", {})
            if gender_key in gender_overrides:
                persona_key = gender_overrides[gender_key]
                logger.info(
                    "persona_routed",
                    method="gender",
                    lead=lead.name,
                    persona=persona_key,
                )
                return self._personas[persona_key]

        # 3. Fallback to default
        default_key = self._routing.get("default", "lukas")
        logger.info("persona_routed", method="default", lead=lead.name, persona=default_key)
        return self._personas[default_key]

    def get_persona(self, key: str) -> PersonaConfig:
        """Get a specific persona by key."""
        return self._personas[key]

    def list_personas(self) -> list[str]:
        """List all available persona keys."""
        return list(self._personas.keys())
