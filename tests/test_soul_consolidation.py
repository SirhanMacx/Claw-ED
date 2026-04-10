"""Tests for SOUL.md deduplication and consolidation (v2.3.3 Phase 5)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from clawed.workspace import (
    _deduplicate_entry,
    consolidate_soul,
)

# ── _deduplicate_entry ───────────────────────────────────────────────────


class TestDeduplicateEntrySubstringMatch:
    """Same text (ignoring date prefixes) is caught as a duplicate."""

    def test_detects_exact_substring(self):
        content = (
            "## Agent Observations\n"
            "\n"
            "*(2026-03-01)* Voice patterns: calls students 'friends'\n"
            "*(2026-03-05)* Uses think-pair-share regularly\n"
        )
        new_entry = "Voice patterns: calls students 'friends'"
        assert _deduplicate_entry(content, new_entry, "## Agent Observations") is True

    def test_detects_substring_with_date_in_new_entry(self):
        content = "## Agent Observations\n\n*(2026-03-01)* Voice patterns: calls students 'friends'\n"
        # New entry also has a date prefix — should still be caught
        new_entry = "(2026-03-15) Voice patterns: calls students 'friends'"
        assert _deduplicate_entry(content, new_entry, "## Agent Observations") is True


class TestDeduplicateEntryAllowsNew:
    """Genuinely new content is allowed through."""

    def test_allows_new_content(self):
        content = "## Agent Observations\n\n*(2026-03-01)* Voice patterns: calls students 'friends'\n"
        new_entry = "Prefers exit tickets with open-ended reflection prompts"
        assert _deduplicate_entry(content, new_entry, "## Agent Observations") is False

    def test_allows_when_section_missing(self):
        content = "## My Voice\n\nSome voice notes.\n"
        new_entry = "Something totally new"
        assert _deduplicate_entry(content, new_entry, "## Agent Observations") is False


class TestDeduplicateEntryWordOverlap:
    """>70% word overlap with any existing line is caught."""

    def test_detects_high_word_overlap(self):
        content = "## Agent Observations\n\n*(2026-03-01)* Voice patterns: teacher calls students 'friends' often\n"
        # Rephrased but >70% word overlap
        new_entry = "Voice patterns: teacher calls students 'friends' frequently"
        assert _deduplicate_entry(content, new_entry, "## Agent Observations") is True

    def test_allows_low_word_overlap(self):
        content = "## Agent Observations\n\n*(2026-03-01)* Voice patterns: calls students 'friends'\n"
        # Only a few shared words, not enough for >70%
        new_entry = "Assessment approach: uses rubric-based grading with detailed feedback criteria"
        assert _deduplicate_entry(content, new_entry, "## Agent Observations") is False

    def test_empty_new_entry(self):
        content = "## Agent Observations\n\nSome text here.\n"
        assert _deduplicate_entry(content, "", "## Agent Observations") is False


# ── consolidate_soul ─────────────────────────────────────────────────────


class TestConsolidateSoulBackup:
    """Backup file is created before consolidation overwrites SOUL.md."""

    def test_creates_backup(self, tmp_path, monkeypatch):
        # Set up a SOUL.md over the threshold
        ws = tmp_path / "workspace"
        ws.mkdir(parents=True)
        soul = ws / "soul.md"
        big_content = "# Teaching Soul\n" + ("x " * 2000)  # well over 3000 chars
        soul.write_text(big_content, encoding="utf-8")

        monkeypatch.setattr("clawed.workspace.SOUL_PATH", soul)

        consolidated_text = "# Teaching Soul\n\nConsolidated version."
        with patch(
            "clawed.workspace._llm_consolidate_soul",
            new_callable=AsyncMock,
            return_value=consolidated_text,
        ):
            result = asyncio.run(consolidate_soul())

        assert result is True
        backup = soul.with_suffix(".md.bak")
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == big_content
        assert soul.read_text(encoding="utf-8") == consolidated_text


class TestConsolidateSoulSkipsSmall:
    """Files under the threshold are not consolidated."""

    def test_skips_small_file(self, tmp_path, monkeypatch):
        ws = tmp_path / "workspace"
        ws.mkdir(parents=True)
        soul = ws / "soul.md"
        small_content = "# Teaching Soul\n\nShort file."
        soul.write_text(small_content, encoding="utf-8")

        monkeypatch.setattr("clawed.workspace.SOUL_PATH", soul)

        result = asyncio.run(consolidate_soul())
        assert result is False
        # No backup should be created
        assert not soul.with_suffix(".md.bak").exists()

    def test_skips_missing_file(self, tmp_path, monkeypatch):
        soul = tmp_path / "workspace" / "soul.md"
        monkeypatch.setattr("clawed.workspace.SOUL_PATH", soul)

        result = asyncio.run(consolidate_soul())
        assert result is False


class TestConsolidateSoulRestoresOnFailure:
    """If LLM fails, original content is restored from backup."""

    def test_restores_backup_on_llm_failure(self, tmp_path, monkeypatch):
        ws = tmp_path / "workspace"
        ws.mkdir(parents=True)
        soul = ws / "soul.md"
        big_content = "# Teaching Soul\n" + ("x " * 2000)
        soul.write_text(big_content, encoding="utf-8")

        monkeypatch.setattr("clawed.workspace.SOUL_PATH", soul)

        with patch(
            "clawed.workspace._llm_consolidate_soul",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            result = asyncio.run(consolidate_soul())

        assert result is False
        # Original content should be restored
        assert soul.read_text(encoding="utf-8") == big_content

    def test_restores_on_empty_result(self, tmp_path, monkeypatch):
        ws = tmp_path / "workspace"
        ws.mkdir(parents=True)
        soul = ws / "soul.md"
        big_content = "# Teaching Soul\n" + ("x " * 2000)
        soul.write_text(big_content, encoding="utf-8")

        monkeypatch.setattr("clawed.workspace.SOUL_PATH", soul)

        with patch(
            "clawed.workspace._llm_consolidate_soul",
            new_callable=AsyncMock,
            return_value="",
        ):
            result = asyncio.run(consolidate_soul())

        assert result is False
        assert soul.read_text(encoding="utf-8") == big_content
