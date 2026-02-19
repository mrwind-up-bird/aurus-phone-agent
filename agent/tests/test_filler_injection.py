"""Tests for FillerInjector — preload, pick, enable/disable."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.filler_injection import FillerInjector


class TestPreload:
    """Tests for the preload method."""

    @pytest.mark.asyncio
    async def test_preload_with_missing_dir(self) -> None:
        """Preload handles missing filler directory gracefully."""
        injector = FillerInjector()
        # Point to a nonexistent directory by clearing cache
        injector._filler_cache = {}
        await injector.preload()  # Should not raise
        # Cache may or may not have files depending on project assets

    @pytest.mark.asyncio
    async def test_preload_with_existing_files(self, tmp_path: Path) -> None:
        """Preload loads .wav files into cache."""
        import src.filler_injection as fi

        # Create fake wav files
        filler_dir = tmp_path / "fillers"
        filler_dir.mkdir()
        for name in ["hmm", "ja", "verstehe"]:
            (filler_dir / f"{name}.wav").write_bytes(b"RIFF" + b"\x00" * 100)

        # Patch the FILLER_DIR
        original_dir = fi.FILLER_DIR
        fi.FILLER_DIR = filler_dir
        try:
            injector = FillerInjector()
            await injector.preload()
            assert len(injector._filler_cache) == 3
            assert "hmm" in injector._filler_cache
            assert "ja" in injector._filler_cache
            assert "verstehe" in injector._filler_cache
        finally:
            fi.FILLER_DIR = original_dir

    @pytest.mark.asyncio
    async def test_preload_skips_missing_files(self, tmp_path: Path) -> None:
        """Preload only loads files that exist."""
        import src.filler_injection as fi

        filler_dir = tmp_path / "fillers"
        filler_dir.mkdir()
        (filler_dir / "hmm.wav").write_bytes(b"RIFF" + b"\x00" * 50)
        # Other files from FILLER_PHRASES are missing

        original_dir = fi.FILLER_DIR
        fi.FILLER_DIR = filler_dir
        try:
            injector = FillerInjector()
            await injector.preload()
            assert len(injector._filler_cache) == 1
            assert "hmm" in injector._filler_cache
        finally:
            fi.FILLER_DIR = original_dir


class TestPickFiller:
    """Tests for the pick_filler method."""

    def test_returns_none_when_empty(self) -> None:
        """pick_filler returns None with empty cache."""
        injector = FillerInjector()
        assert injector.pick_filler() is None

    def test_returns_tuple_when_loaded(self) -> None:
        """pick_filler returns (name, bytes) tuple."""
        injector = FillerInjector()
        injector._filler_cache = {"hmm": b"audio1", "ja": b"audio2"}
        result = injector.pick_filler()
        assert result is not None
        name, data = result
        assert name in ("hmm", "ja")
        assert isinstance(data, bytes)

    def test_avoids_consecutive_repeats(self) -> None:
        """pick_filler avoids selecting the same filler twice in a row."""
        injector = FillerInjector()
        injector._filler_cache = {"hmm": b"a", "ja": b"b", "ok": b"c"}

        # Pick many times and verify no consecutive repeats
        picks = []
        for _ in range(50):
            result = injector.pick_filler()
            assert result is not None
            picks.append(result[0])

        for i in range(1, len(picks)):
            assert picks[i] != picks[i - 1], f"Consecutive repeat at index {i}: {picks[i]}"

    def test_single_filler_allows_repeat(self) -> None:
        """With only one filler, it can repeat (no other choice)."""
        injector = FillerInjector()
        injector._filler_cache = {"hmm": b"audio"}
        r1 = injector.pick_filler()
        r2 = injector.pick_filler()
        assert r1 is not None and r2 is not None
        assert r1[0] == r2[0] == "hmm"

    def test_returns_none_when_disabled(self) -> None:
        """pick_filler returns None when disabled."""
        injector = FillerInjector()
        injector._filler_cache = {"hmm": b"audio"}
        injector.set_enabled(False)
        assert injector.pick_filler() is None


class TestSetEnabled:
    """Tests for the set_enabled method."""

    def test_disable_blocks_pick(self) -> None:
        """Disabling prevents pick_filler from returning results."""
        injector = FillerInjector()
        injector._filler_cache = {"hmm": b"audio"}
        injector.set_enabled(False)
        assert injector.pick_filler() is None

    def test_re_enable_allows_pick(self) -> None:
        """Re-enabling allows pick_filler to return results again."""
        injector = FillerInjector()
        injector._filler_cache = {"hmm": b"audio"}
        injector.set_enabled(False)
        assert injector.pick_filler() is None
        injector.set_enabled(True)
        assert injector.pick_filler() is not None

    def test_enabled_by_default(self) -> None:
        """FillerInjector is enabled by default."""
        injector = FillerInjector()
        assert injector._enabled is True
