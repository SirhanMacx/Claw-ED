"""Tests for the unified full_ingest pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from clawed.ingestor import full_ingest

# ── Return shape ────────────────────────────────────────────────────


def test_full_ingest_returns_dict_with_all_keys(tmp_path):
    """full_ingest always returns a dict with every expected key."""
    # Create a minimal text file so parsing succeeds
    (tmp_path / "lesson.txt").write_text(
        "The water cycle describes how water moves through the environment.",
        encoding="utf-8",
    )

    # Patch heavy downstream steps so the test stays fast and isolated
    with patch("clawed.ingestor.extract_rich", return_value=None), \
         patch("clawed.asset_registry.AssetRegistry.register_asset", return_value=1):
        result = full_ingest(tmp_path, teacher_id="test-teacher")

    assert isinstance(result, dict)
    expected_keys = {
        "docs_parsed",
        "assets_registered",
        "images_extracted",
        "chunks_indexed",
        "kg_entities",
        "kg_triples",
        "wiki_articles",
        "errors",
    }
    assert set(result.keys()) == expected_keys
    assert result["docs_parsed"] >= 1
    assert isinstance(result["errors"], list)


# ── Empty directory ─────────────────────────────────────────────────


def test_full_ingest_on_empty_directory(tmp_path):
    """An empty directory parses zero docs and short-circuits cleanly."""
    result = full_ingest(tmp_path, teacher_id="test-teacher")

    assert isinstance(result, dict)
    assert result["docs_parsed"] == 0
    # With zero docs, downstream steps are skipped
    assert result["assets_registered"] == 0
    assert result["chunks_indexed"] == 0
    assert result["kg_entities"] == 0
    assert result["kg_triples"] == 0
    assert result["wiki_articles"] == 0


# ── Nonexistent path ───────────────────────────────────────────────


def test_full_ingest_on_nonexistent_path(tmp_path):
    """A path that does not exist raises FileNotFoundError from ingest_path."""
    bad_path = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        full_ingest(bad_path, teacher_id="test-teacher")
