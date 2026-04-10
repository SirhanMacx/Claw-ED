"""Tests for clawed.brain.search — hybrid search and RRF fusion."""
from pathlib import Path

import pytest

from clawed.brain.search import (
    SearchResult,
    brain_keyword_search,
    reciprocal_rank_fusion,
)
from clawed.brain.store import BrainPage, BrainStore


@pytest.fixture
def seeded_store(tmp_path: Path) -> BrainStore:
    """BrainStore with a handful of pages."""
    store = BrainStore(root=tmp_path / "brain")
    store.save(
        BrainPage(
            slug="julia-m",
            page_type="student",
            title="Julia M.",
            compiled_truth=(
                "Strong reader, weak writer. Responds well to sentence "
                "starters. Needs extended time per IEP."
            ),
        )
    )
    store.save(
        BrainPage(
            slug="pedro-r",
            page_type="student",
            title="Pedro R.",
            compiled_truth=(
                "Excellent at primary source analysis. Visual learner. "
                "Needs scaffolding for extended writing."
            ),
        )
    )
    store.save(
        BrainPage(
            slug="industrial-revolution",
            page_type="topic",
            title="Industrial Revolution",
            compiled_truth=(
                "Stations work better than jigsaws. Period 3 engages with "
                "Bentley testimony. Engels slums reading is complex for 8th."
            ),
        )
    )
    store.save(
        BrainPage(
            slug="claim-evidence-framework",
            page_type="original",
            title="Claim and Evidence Framework",
            compiled_truth=(
                "My students need to see the cognitive verb defined "
                "explicitly before they can use it on assessments."
            ),
        )
    )
    return store


# ── Keyword search ───────────────────────────────────────────────────────


def test_keyword_search_finds_matches(seeded_store: BrainStore):
    results = brain_keyword_search(seeded_store, "sentence starters")
    assert len(results) >= 1
    assert any(r.slug == "julia-m" for r in results)


def test_keyword_search_snippet_shows_match_context(seeded_store: BrainStore):
    results = brain_keyword_search(seeded_store, "Bentley")
    assert len(results) >= 1
    assert "Bentley" in results[0].snippet


def test_keyword_search_filters_by_type(seeded_store: BrainStore):
    results = brain_keyword_search(
        seeded_store, "scaffolding", page_type="student",
    )
    assert all(r.page_type == "student" for r in results)


def test_keyword_search_ranks_results(seeded_store: BrainStore):
    results = brain_keyword_search(seeded_store, "writing")
    assert len(results) >= 1
    # First result should have rank 1
    assert results[0].rank == 1


# ── Reciprocal Rank Fusion ───────────────────────────────────────────────


def test_rrf_fuses_two_lists():
    list_a = [
        SearchResult(source="a", slug="x", page_type="student",
                     title="X", snippet="", rank=1),
        SearchResult(source="a", slug="y", page_type="student",
                     title="Y", snippet="", rank=2),
    ]
    list_b = [
        SearchResult(source="b", slug="y", page_type="student",
                     title="Y", snippet="", rank=1),
        SearchResult(source="b", slug="z", page_type="student",
                     title="Z", snippet="", rank=2),
    ]
    fused = reciprocal_rank_fusion([list_a, list_b])

    # Y should rank highest — appears in both lists
    assert len(fused) == 3
    assert fused[0].slug == "y"


def test_rrf_empty_lists_returns_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_single_list_preserves_order():
    results = [
        SearchResult(source="a", slug=f"slug-{i}", page_type="student",
                     title=f"T{i}", snippet="", rank=i)
        for i in range(1, 4)
    ]
    fused = reciprocal_rank_fusion([results])
    assert [r.slug for r in fused] == ["slug-1", "slug-2", "slug-3"]


def test_rrf_scales_with_k():
    """Higher rank should mean lower score."""
    results = [
        SearchResult(source="a", slug="x", page_type="student",
                     title="X", snippet="", rank=1),
        SearchResult(source="a", slug="y", page_type="student",
                     title="Y", snippet="", rank=10),
    ]
    fused = reciprocal_rank_fusion([results])
    # x (rank 1) should have higher score than y (rank 10)
    assert fused[0].slug == "x"
    assert fused[0].score > fused[1].score


# ── Hybrid search integration ────────────────────────────────────────────


def test_hybrid_search_returns_brain_results(seeded_store: BrainStore):
    """Hybrid search should find brain pages even without vector model."""
    from clawed.brain.search import hybrid_search

    results = hybrid_search(
        "sentence starters",
        store=seeded_store,
        include_corpus=False,
    )
    assert len(results) >= 1
    # Should find Julia M. (contains "sentence starters")
    slugs = {r.slug for r in results}
    assert "julia-m" in slugs


def test_hybrid_search_deduplicates_across_sources(seeded_store: BrainStore):
    """When the same page appears in multiple sources, dedup by (type, slug)."""
    from clawed.brain.search import hybrid_search

    results = hybrid_search(
        "Industrial Revolution",
        store=seeded_store,
        include_corpus=False,
    )
    slugs = [(r.page_type, r.slug) for r in results]
    # Each (type, slug) should appear at most once
    assert len(slugs) == len(set(slugs))
