"""Tests for PersonaManager — YAML loading and lead routing."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models import LeadMetadata
from src.persona_manager import PersonaManager


class TestYamlLoading:
    """Tests for persona YAML configuration loading."""

    def test_loads_personas_from_yaml(self, sample_persona_yaml: Path) -> None:
        """PersonaManager loads all personas from YAML."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        assert "alpha" in pm.list_personas()
        assert "beta" in pm.list_personas()

    def test_persona_fields(self, sample_persona_yaml: Path) -> None:
        """Loaded persona has correct fields from YAML."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        alpha = pm.get_persona("alpha")
        assert alpha.name == "Alpha"
        assert alpha.role == "The Tester"
        assert alpha.voice.cartesia_voice_id == "voice-alpha-id"
        assert alpha.voice.speed == "normal"
        assert "reassuring" in alpha.voice.emotions

    def test_loads_real_personas_yaml(self) -> None:
        """PersonaManager loads the real personas.yaml from the project."""
        pm = PersonaManager()
        personas = pm.list_personas()
        assert "lukas" in personas
        assert "sarah" in personas
        assert "marcus" in personas

    def test_real_persona_voice_ids(self) -> None:
        """Real personas have correct Cartesia voice IDs."""
        pm = PersonaManager()
        lukas = pm.get_persona("lukas")
        assert "e00dd3df" in lukas.voice.cartesia_voice_id


class TestRouting:
    """Tests for persona routing logic."""

    def test_route_ceo_to_alpha(self, sample_persona_yaml: Path) -> None:
        """CEO job title routes to alpha persona."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        lead = LeadMetadata(name="Test CEO", job_title="CEO")
        result = pm.route(lead)
        assert result.name == "Alpha"

    def test_route_developer_to_beta(self, sample_persona_yaml: Path) -> None:
        """Developer job title routes to beta persona."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        lead = LeadMetadata(name="Test Dev", job_title="Software Developer")
        result = pm.route(lead)
        assert result.name == "Beta"

    def test_route_by_gender_male(self, sample_persona_yaml: Path) -> None:
        """Male gender routes to beta when no title match."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        lead = LeadMetadata(name="Test Male", gender="male")
        result = pm.route(lead)
        assert result.name == "Beta"

    def test_route_by_gender_female(self, sample_persona_yaml: Path) -> None:
        """Female gender routes to alpha when no title match."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        lead = LeadMetadata(name="Test Female", gender="female")
        result = pm.route(lead)
        assert result.name == "Alpha"

    def test_title_takes_priority_over_gender(self, sample_persona_yaml: Path) -> None:
        """Job title matching has higher priority than gender."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        lead = LeadMetadata(name="Test", job_title="Developer", gender="female")
        result = pm.route(lead)
        assert result.name == "Beta"  # title match wins over gender

    def test_route_default_fallback(self, sample_persona_yaml: Path) -> None:
        """Lead with no matching title or gender uses default."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        lead = LeadMetadata(name="Nobody Special")
        result = pm.route(lead)
        assert result.name == "Alpha"  # default in test YAML

    def test_real_routing_cto_to_marcus(self) -> None:
        """CTO routes to Marcus in the real personas.yaml."""
        pm = PersonaManager()
        lead = LeadMetadata(name="Tech Person", job_title="CTO")
        result = pm.route(lead)
        assert result.name == "Marcus"

    def test_real_routing_hr_to_sarah(self) -> None:
        """HR Manager routes to Sarah in the real personas.yaml."""
        pm = PersonaManager()
        lead = LeadMetadata(name="HR Person", job_title="HR Manager")
        result = pm.route(lead)
        assert result.name == "Sarah"

    def test_real_routing_ceo_to_lukas(self) -> None:
        """CEO routes to Lukas in the real personas.yaml."""
        pm = PersonaManager()
        lead = LeadMetadata(name="Boss Person", job_title="CEO")
        result = pm.route(lead)
        assert result.name == "Lukas"


class TestGetPersona:
    """Tests for get_persona method."""

    def test_valid_key(self, sample_persona_yaml: Path) -> None:
        """Fetching a valid persona key succeeds."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        persona = pm.get_persona("alpha")
        assert persona.name == "Alpha"

    def test_invalid_key_raises(self, sample_persona_yaml: Path) -> None:
        """Fetching an invalid persona key raises KeyError."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        with pytest.raises(KeyError):
            pm.get_persona("nonexistent")


class TestListPersonas:
    """Tests for list_personas method."""

    def test_returns_all_keys(self, sample_persona_yaml: Path) -> None:
        """list_personas returns all persona keys."""
        pm = PersonaManager(config_path=sample_persona_yaml)
        keys = pm.list_personas()
        assert set(keys) == {"alpha", "beta"}

    def test_real_personas_count(self) -> None:
        """Real config has 3 personas."""
        pm = PersonaManager()
        assert len(pm.list_personas()) == 3
