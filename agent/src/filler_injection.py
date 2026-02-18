"""Filler injection — plays cached German fillers to mask LLM latency."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import structlog

logger = structlog.get_logger()

FILLER_DIR = Path(__file__).parent.parent / "assets" / "fillers"

# German fillers with their approximate durations (ms)
FILLER_PHRASES = [
    "hmm",
    "ja",
    "verstehe",
    "genau",
    "okay",
    "moment",
    "absolut",
    "richtig",
]


class FillerInjector:
    """Manages filler audio injection to bridge LLM processing gaps.

    Plays a random cached filler immediately when VAD detects end-of-speech,
    creating the perception of instant response while the LLM processes.
    """

    def __init__(self) -> None:
        self._filler_cache: dict[str, bytes] = {}
        self._last_filler: str | None = None
        self._enabled: bool = True

    async def preload(self) -> None:
        """Load all filler audio files into memory for instant playback."""
        if not FILLER_DIR.exists():
            logger.warning("filler_dir_missing", path=str(FILLER_DIR))
            return

        for filler in FILLER_PHRASES:
            audio_path = FILLER_DIR / f"{filler}.wav"
            if audio_path.exists():
                self._filler_cache[filler] = await asyncio.to_thread(
                    audio_path.read_bytes
                )
                logger.debug("filler_loaded", name=filler)

        logger.info("fillers_preloaded", count=len(self._filler_cache))

    def pick_filler(self) -> tuple[str, bytes] | None:
        """Select a random filler, avoiding consecutive repeats.

        Returns a tuple of (filler_name, audio_bytes) or None if no fillers loaded.
        """
        if not self._filler_cache or not self._enabled:
            return None

        available = [f for f in self._filler_cache if f != self._last_filler]
        if not available:
            available = list(self._filler_cache.keys())

        chosen = random.choice(available)
        self._last_filler = chosen
        return chosen, self._filler_cache[chosen]

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable filler injection."""
        self._enabled = enabled
        logger.info("filler_injection_toggled", enabled=enabled)
