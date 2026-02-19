"""Tests for ConversationStore — save, load, list, slugify, summary generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.conversation_store import (
    ConversationRecord,
    ConversationStore,
    TranscriptItem,
    _generate_summary,
    _slugify,
)


class TestSlugify:
    """Tests for the _slugify helper function."""

    def test_basic_text(self) -> None:
        """Simple text is lowercased and cleaned."""
        assert _slugify("Hello World") == "hello_world"

    def test_special_chars_removed(self) -> None:
        """Special characters are stripped, but unicode word chars are preserved."""
        assert _slugify("Max Müller!@#$") == "max_müller"

    def test_empty_string(self) -> None:
        """Empty string returns 'unknown'."""
        assert _slugify("") == "unknown"

    def test_whitespace_only(self) -> None:
        """Whitespace-only string returns 'unknown'."""
        assert _slugify("   ") == "unknown"

    def test_unicode_handling(self) -> None:
        """Unicode word characters (e.g. umlauts) are preserved by \\w."""
        result = _slugify("Ärger mit Öl")
        assert result == "ärger_mit_öl"

    def test_multiple_spaces(self) -> None:
        """Multiple spaces collapse to single underscore."""
        assert _slugify("hello   world") == "hello_world"

    def test_leading_trailing_underscores_stripped(self) -> None:
        """Leading/trailing underscores are stripped."""
        assert _slugify("_test_") == "test"


class TestGenerateSummary:
    """Tests for the _generate_summary function."""

    def test_empty_transcript(self) -> None:
        """Empty transcript returns 'No exchanges recorded.'"""
        assert _generate_summary([]) == "No exchanges recorded."

    def test_short_transcript(self) -> None:
        """Short transcript includes all entries."""
        items = [
            TranscriptItem(speaker="agent", text="Hallo", timestamp=1.0),
            TranscriptItem(speaker="user", text="Hi", timestamp=2.0),
        ]
        summary = _generate_summary(items)
        assert "2 exchanges" in summary
        assert "Agent: Hallo" in summary
        assert "User: Hi" in summary

    def test_single_exchange(self) -> None:
        """Single exchange uses singular form."""
        items = [TranscriptItem(speaker="agent", text="Hallo", timestamp=1.0)]
        summary = _generate_summary(items)
        assert "1 exchange." in summary

    def test_long_transcript_shows_last_six(self) -> None:
        """Transcripts longer than 6 show only last 6 turns."""
        items = [
            TranscriptItem(speaker="agent", text=f"Turn {i}", timestamp=float(i))
            for i in range(10)
        ]
        summary = _generate_summary(items)
        assert "10 exchanges" in summary
        assert "Last 6 turns shown" in summary
        assert "Turn 9" in summary
        assert "Turn 4" in summary

    def test_long_utterances_truncated(self) -> None:
        """Utterances longer than 120 chars are truncated with ellipsis."""
        long_text = "A" * 200
        items = [TranscriptItem(speaker="user", text=long_text, timestamp=1.0)]
        summary = _generate_summary(items)
        assert "..." in summary


class TestConversationStoreSave:
    """Tests for ConversationStore.save method."""

    @pytest.mark.asyncio
    async def test_save_creates_file(self, tmp_conversations_dir: Path) -> None:
        """Saving a record creates a JSON file."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            lead_metadata={"name": "Test Lead"},
            persona_used="lukas",
            started_at="2025-01-15T10:30:00+00:00",
        )
        filepath = await store.save(record)
        assert filepath.exists()
        assert filepath.suffix == ".json"

    @pytest.mark.asyncio
    async def test_save_filename_format(self, tmp_conversations_dir: Path) -> None:
        """Saved file has expected timestamp_slug format."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            lead_metadata={"name": "Max Test"},
            persona_used="sarah",
            started_at="2025-06-20T14:00:00+00:00",
        )
        filepath = await store.save(record)
        assert "20250620_140000" in filepath.name
        assert "max_test" in filepath.name

    @pytest.mark.asyncio
    async def test_save_auto_generates_summary(self, tmp_conversations_dir: Path) -> None:
        """Save auto-generates summary when none is set."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            lead_metadata={"name": "Lead"},
            transcript=[
                TranscriptItem(speaker="agent", text="Hallo", timestamp=1.0),
            ],
        )
        await store.save(record)
        assert record.summary != ""
        assert "1 exchange" in record.summary

    @pytest.mark.asyncio
    async def test_save_preserves_existing_summary(self, tmp_conversations_dir: Path) -> None:
        """Save does not overwrite an existing summary."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            lead_metadata={"name": "Lead"},
            summary="Custom summary",
        )
        await store.save(record)
        assert record.summary == "Custom summary"


class TestConversationStoreLoad:
    """Tests for ConversationStore.load method."""

    @pytest.mark.asyncio
    async def test_load_by_id(self, tmp_conversations_dir: Path) -> None:
        """Load returns the correct record by ID."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            id="abc123",
            lead_metadata={"name": "Load Test"},
            started_at="2025-01-01T00:00:00+00:00",
        )
        await store.save(record)

        loaded = await store.load("abc123")
        assert loaded is not None
        assert loaded.id == "abc123"

    @pytest.mark.asyncio
    async def test_load_nonexistent_id(self, tmp_conversations_dir: Path) -> None:
        """Load returns None for unknown ID."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        result = await store.load("nonexistent")
        assert result is None


class TestConversationStoreListAll:
    """Tests for ConversationStore.list_all method."""

    @pytest.mark.asyncio
    async def test_list_all_empty(self, tmp_conversations_dir: Path) -> None:
        """list_all returns empty list when no records exist."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        result = await store.list_all()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_all_returns_newest_first(self, tmp_conversations_dir: Path) -> None:
        """list_all returns records sorted by filename (newest first)."""
        store = ConversationStore(base_dir=tmp_conversations_dir)

        r1 = ConversationRecord(
            id="old",
            lead_metadata={"name": "First"},
            started_at="2025-01-01T00:00:00+00:00",
        )
        r2 = ConversationRecord(
            id="new",
            lead_metadata={"name": "Second"},
            started_at="2025-12-31T23:59:59+00:00",
        )
        await store.save(r1)
        await store.save(r2)

        records = await store.list_all()
        assert len(records) == 2
        # Newest first (sorted reverse by filename)
        assert records[0].id == "new"
        assert records[1].id == "old"


class TestConversationStoreListByLead:
    """Tests for ConversationStore.list_by_lead method."""

    @pytest.mark.asyncio
    async def test_filters_by_lead_name(self, tmp_conversations_dir: Path) -> None:
        """list_by_lead returns only records matching the lead name."""
        store = ConversationStore(base_dir=tmp_conversations_dir)

        r1 = ConversationRecord(
            id="a",
            lead_metadata={"name": "Alice"},
            started_at="2025-01-01T00:00:00+00:00",
        )
        r2 = ConversationRecord(
            id="b",
            lead_metadata={"name": "Bob"},
            started_at="2025-01-02T00:00:00+00:00",
        )
        r3 = ConversationRecord(
            id="c",
            lead_metadata={"name": "Alice"},
            started_at="2025-01-03T00:00:00+00:00",
        )
        await store.save(r1)
        await store.save(r2)
        await store.save(r3)

        results = await store.list_by_lead("Alice")
        assert len(results) == 2
        assert all(r.lead_metadata.get("name") == "Alice" for r in results)

    @pytest.mark.asyncio
    async def test_case_insensitive_filter(self, tmp_conversations_dir: Path) -> None:
        """list_by_lead is case-insensitive."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            id="x",
            lead_metadata={"name": "Alice"},
            started_at="2025-01-01T00:00:00+00:00",
        )
        await store.save(record)

        results = await store.list_by_lead("alice")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_no_matches(self, tmp_conversations_dir: Path) -> None:
        """list_by_lead returns empty list when no matches."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            id="y",
            lead_metadata={"name": "Bob"},
            started_at="2025-01-01T00:00:00+00:00",
        )
        await store.save(record)

        results = await store.list_by_lead("Charlie")
        assert len(results) == 0


class TestBuildFilename:
    """Tests for ConversationStore._build_filename."""

    def test_filename_format(self, tmp_conversations_dir: Path) -> None:
        """Filename follows {timestamp}_{slug}.json format."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            lead_metadata={"name": "Max Mustermann"},
            started_at="2025-03-15T09:30:00+00:00",
        )
        filename = store._build_filename(record)
        assert filename == "20250315_093000_max_mustermann.json"

    def test_filename_fallback_for_missing_name(self, tmp_conversations_dir: Path) -> None:
        """Filename uses 'unknown' when lead name is missing."""
        store = ConversationStore(base_dir=tmp_conversations_dir)
        record = ConversationRecord(
            lead_metadata={},
            started_at="2025-01-01T00:00:00+00:00",
        )
        filename = store._build_filename(record)
        assert "unknown" in filename
