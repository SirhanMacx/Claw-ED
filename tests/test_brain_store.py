"""Tests for clawed.brain.store — BrainPage, TimelineEntry, BrainStore."""
from pathlib import Path

import pytest

from clawed.brain.store import BrainPage, BrainStore, TimelineEntry


@pytest.fixture
def tmp_store(tmp_path: Path) -> BrainStore:
    """Isolated BrainStore rooted in a temp directory."""
    return BrainStore(root=tmp_path / "brain")


# ── TimelineEntry ─────────────────────────────────────────────────────────


def test_timeline_entry_render_with_source():
    entry = TimelineEntry(
        date="2026-04-09",
        body="Exit Q3 on Douglass: 3/4",
        source="Lesson Industrial Revolution, exit ticket",
    )
    rendered = entry.render()
    assert "2026-04-09" in rendered
    assert "Exit Q3 on Douglass: 3/4" in rendered
    assert "[Source: Lesson Industrial Revolution" in rendered


def test_timeline_entry_render_without_source():
    entry = TimelineEntry(date="2026-04-09", body="Struggled with CRQ")
    rendered = entry.render()
    assert "[Source:" not in rendered
    assert "Struggled with CRQ" in rendered


def test_timeline_entry_parse_with_source():
    line = (
        "- **2026-04-09** | Exit Q3: 2/4 "
        "[Source: Lesson Douglass, exit ticket]"
    )
    entry = TimelineEntry.parse(line)
    assert entry is not None
    assert entry.date == "2026-04-09"
    assert "Exit Q3" in entry.body
    assert "Lesson Douglass" in entry.source


def test_timeline_entry_parse_without_source():
    line = "- **2026-04-08** | Did good work today"
    entry = TimelineEntry.parse(line)
    assert entry is not None
    assert entry.date == "2026-04-08"
    assert entry.body == "Did good work today"
    assert entry.source == ""


def test_timeline_entry_parse_rejects_non_timeline():
    assert TimelineEntry.parse("not a timeline line") is None
    assert TimelineEntry.parse("## Timeline") is None
    assert TimelineEntry.parse("") is None


# ── BrainPage ─────────────────────────────────────────────────────────────


def test_brain_page_render_roundtrip():
    page = BrainPage(
        slug="julia-m",
        page_type="student",
        title="Julia M.",
        compiled_truth=(
            "## Compiled Truth\n\n"
            "Strong reader, weak writer. Responds to sentence starters.\n\n"
            "## Strengths\n- Primary source analysis"
        ),
        metadata={"tier": "1", "created": "2026-04-01"},
    )
    page.add_timeline(
        "First observation",
        source="Lesson test",
        date="2026-04-09",
    )
    rendered = page.render()

    # Verify structure
    assert rendered.startswith("---\n")
    assert "type: student" in rendered
    assert "slug: julia-m" in rendered
    assert "tier: 1" in rendered
    assert "# Julia M." in rendered
    assert "## Compiled Truth" in rendered
    assert "## Timeline" in rendered
    assert "2026-04-09" in rendered
    assert "First observation" in rendered


def test_brain_page_parse_preserves_data():
    original = BrainPage(
        slug="industrial-revolution",
        page_type="topic",
        title="Industrial Revolution",
        compiled_truth=(
            "## Compiled Truth\n\n"
            "Stations work better than jigsaws for this text."
        ),
    )
    original.add_timeline(
        "Period 3 strong discussion",
        source="Observation 2026-04-09",
        date="2026-04-09",
    )
    original.add_timeline(
        "Period 5 jigsaw failed — too complex",
        source="Observation 2026-03-27",
        date="2026-03-27",
    )

    # Render and re-parse
    rendered = original.render()
    parsed = BrainPage.parse(rendered)

    assert parsed.slug == "industrial-revolution"
    assert parsed.page_type == "topic"
    assert parsed.title == "Industrial Revolution"
    assert "Stations work better" in parsed.compiled_truth
    assert len(parsed.timeline) == 2
    # Should be sorted reverse-chronologically
    assert parsed.timeline[0].date >= parsed.timeline[1].date


def test_brain_page_add_timeline_updates_metadata():
    page = BrainPage(slug="test", page_type="student", title="Test")
    assert "updated" not in page.metadata
    page.add_timeline("Something happened")
    assert "updated" in page.metadata


# ── BrainStore ────────────────────────────────────────────────────────────


def test_store_creates_subdirectories(tmp_store: BrainStore):
    assert (tmp_store.root / "students").is_dir()
    assert (tmp_store.root / "topics").is_dir()
    assert (tmp_store.root / "lessons").is_dir()
    assert (tmp_store.root / "originals").is_dir()


def test_store_slugify(tmp_store: BrainStore):
    assert tmp_store.slugify("Julia M.") == "julia-m"
    assert tmp_store.slugify("Industrial Revolution") == "industrial-revolution"
    assert tmp_store.slugify("Mr. Maccarello's Class") == "mr-maccarellos-class"
    # Punctuation stripped
    assert tmp_store.slugify("2026-04-09 Lesson!") == "2026-04-09-lesson"


def test_store_save_and_get(tmp_store: BrainStore):
    page = BrainPage(
        slug="julia-m",
        page_type="student",
        title="Julia M.",
        compiled_truth="Strong reader.",
    )
    path = tmp_store.save(page)
    assert path.exists()

    loaded = tmp_store.get("student", "julia-m")
    assert loaded is not None
    assert loaded.title == "Julia M."
    assert "Strong reader" in loaded.compiled_truth


def test_store_get_missing_returns_none(tmp_store: BrainStore):
    assert tmp_store.get("student", "nonexistent") is None


def test_store_exists(tmp_store: BrainStore):
    assert not tmp_store.exists("student", "julia-m")
    page = BrainPage(slug="julia-m", page_type="student", title="Julia")
    tmp_store.save(page)
    assert tmp_store.exists("student", "julia-m")


def test_store_list_pages(tmp_store: BrainStore):
    for slug in ["alice", "bob", "charlie"]:
        tmp_store.save(
            BrainPage(slug=slug, page_type="student", title=slug.title())
        )
    pages = tmp_store.list_pages("student")
    assert pages == ["alice", "bob", "charlie"]


def test_store_search_finds_matches(tmp_store: BrainStore):
    page1 = BrainPage(
        slug="douglass-lesson",
        page_type="topic",
        title="Frederick Douglass",
        compiled_truth="Douglass speeches work best with stations.",
    )
    page2 = BrainPage(
        slug="lincoln-lesson",
        page_type="topic",
        title="Abraham Lincoln",
        compiled_truth="Gettysburg address discussion.",
    )
    tmp_store.save(page1)
    tmp_store.save(page2)

    results = tmp_store.search("Douglass")
    assert len(results) == 1
    assert results[0].slug == "douglass-lesson"


def test_store_search_filters_by_type(tmp_store: BrainStore):
    tmp_store.save(
        BrainPage(
            slug="civil-war",
            page_type="topic",
            title="Civil War",
            compiled_truth="Key battles",
        )
    )
    tmp_store.save(
        BrainPage(
            slug="civil-war-lesson-1",
            page_type="lesson",
            title="Civil War L1",
            compiled_truth="Key battles",
        )
    )
    topics = tmp_store.search("battles", page_type="topic")
    assert len(topics) == 1
    assert topics[0].page_type == "topic"


def test_store_append_timeline_creates_page(tmp_store: BrainStore):
    ok = tmp_store.append_timeline(
        "student",
        "new-student",
        "First observation",
        source="Lesson 1",
    )
    assert ok
    page = tmp_store.get("student", "new-student")
    assert page is not None
    assert len(page.timeline) == 1
    assert "First observation" in page.timeline[0].body


def test_store_append_timeline_existing_page(tmp_store: BrainStore):
    page = BrainPage(slug="julia", page_type="student", title="Julia")
    page.add_timeline("Earlier event", date="2026-04-01")
    tmp_store.save(page)

    tmp_store.append_timeline(
        "student", "julia", "Later event", date="2026-04-09",
    )
    loaded = tmp_store.get("student", "julia")
    assert len(loaded.timeline) == 2


def test_store_update_compiled_truth(tmp_store: BrainStore):
    page = BrainPage(
        slug="julia", page_type="student", title="Julia",
        compiled_truth="Old synthesis",
    )
    tmp_store.save(page)

    ok = tmp_store.update_compiled_truth(
        "student", "julia", "New synthesis based on recent evidence",
    )
    assert ok
    loaded = tmp_store.get("student", "julia")
    assert "New synthesis" in loaded.compiled_truth


def test_store_update_compiled_truth_missing_page(tmp_store: BrainStore):
    ok = tmp_store.update_compiled_truth(
        "student", "nonexistent", "New truth"
    )
    assert ok is False


def test_store_stats(tmp_store: BrainStore):
    tmp_store.save(
        BrainPage(slug="a", page_type="student", title="A")
    )
    tmp_store.save(
        BrainPage(slug="b", page_type="student", title="B")
    )
    tmp_store.save(
        BrainPage(slug="topic-a", page_type="topic", title="Topic A")
    )
    stats = tmp_store.stats()
    assert stats["student"] == 2
    assert stats["topic"] == 1
    assert stats["lesson"] == 0
