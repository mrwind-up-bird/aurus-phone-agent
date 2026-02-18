"""Conversation persistence — saves and loads conversation records as JSON files."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

DEFAULT_CONVERSATIONS_DIR = Path(__file__).parent.parent / "data" / "conversations"


class TranscriptItem(BaseModel):
    """A single turn in the conversation transcript."""

    speaker: str  # "user" or "agent"
    text: str
    timestamp: float
    mood: str = "neutral"


class ConversationRecord(BaseModel):
    """Full conversation record persisted to disk."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    lead_metadata: dict[str, str] = Field(default_factory=dict)
    persona_used: str = ""
    transcript: list[TranscriptItem] = Field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    outcome: str = "end_call"  # continue | schedule | end_call
    summary: str = ""


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "_", text)
    return text.strip("_") or "unknown"


def _generate_summary(transcript: list[TranscriptItem]) -> str:
    """Auto-generate a brief summary from the last few exchanges."""
    if not transcript:
        return "No exchanges recorded."

    # Take up to the last 6 turns for context
    recent = transcript[-6:]
    parts: list[str] = []

    for item in recent:
        label = "Agent" if item.speaker == "agent" else "User"
        # Truncate long utterances
        text = item.text[:120] + "..." if len(item.text) > 120 else item.text
        parts.append(f"{label}: {text}")

    total = len(transcript)
    header = f"Conversation with {total} exchange{'s' if total != 1 else ''}."
    if len(transcript) > 6:
        header += f" Last {len(recent)} turns shown."

    return header + "\n" + "\n".join(parts)


class ConversationStore:
    """JSON-file-based conversation storage."""

    def __init__(self, base_dir: Path = DEFAULT_CONVERSATIONS_DIR) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        logger.info("conversation_store_initialized", path=str(self._base_dir))

    def _build_filename(self, record: ConversationRecord) -> str:
        """Build filename as {timestamp}_{lead_name_slug}.json."""
        ts = record.started_at or datetime.now(tz=timezone.utc).isoformat()
        # Use a compact timestamp for the filename
        try:
            dt = datetime.fromisoformat(ts)
            ts_slug = dt.strftime("%Y%m%d_%H%M%S")
        except (ValueError, TypeError):
            ts_slug = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

        lead_name = record.lead_metadata.get("name", "unknown")
        name_slug = _slugify(lead_name)
        return f"{ts_slug}_{name_slug}.json"

    async def save(self, record: ConversationRecord) -> Path:
        """Persist a conversation record to disk as JSON.

        Auto-generates a summary if none is set.
        """
        if not record.summary:
            record.summary = _generate_summary(record.transcript)

        filename = self._build_filename(record)
        filepath = self._base_dir / filename

        filepath.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        logger.info(
            "conversation_saved",
            id=record.id,
            file=filename,
            turns=len(record.transcript),
        )
        return filepath

    async def load(self, conversation_id: str) -> ConversationRecord | None:
        """Load a conversation by its id from any file in the store."""
        for filepath in self._base_dir.glob("*.json"):
            try:
                record = ConversationRecord.model_validate_json(
                    filepath.read_text(encoding="utf-8")
                )
                if record.id == conversation_id:
                    return record
            except Exception as exc:
                logger.warning(
                    "conversation_load_error",
                    file=filepath.name,
                    error=str(exc),
                )
        return None

    async def list_all(self) -> list[ConversationRecord]:
        """Load and return all saved conversations, newest first."""
        records: list[ConversationRecord] = []
        for filepath in sorted(self._base_dir.glob("*.json"), reverse=True):
            try:
                record = ConversationRecord.model_validate_json(
                    filepath.read_text(encoding="utf-8")
                )
                records.append(record)
            except Exception as exc:
                logger.warning(
                    "conversation_load_error",
                    file=filepath.name,
                    error=str(exc),
                )
        return records

    async def list_by_lead(self, lead_name: str) -> list[ConversationRecord]:
        """Return conversations filtered by lead name (case-insensitive)."""
        all_records = await self.list_all()
        target = lead_name.lower()
        return [
            r
            for r in all_records
            if r.lead_metadata.get("name", "").lower() == target
        ]
