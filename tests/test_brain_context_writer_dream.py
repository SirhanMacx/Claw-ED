"""Tests for clawed.brain.context, writer, and dream modules."""
from pathlib import Path

import pytest

from clawed.brain.context import build_brain_context
from clawed.brain.dream import (
    DreamReport,
    _detect_gaps,
    _find_consolidation_candidates,
    dream_cycle,
)
from clawed.brain.store import BrainPage, BrainStore


@pytest.fixture
def seeded_store(tmp_path: Path) -> BrainStore:
    """BrainStore seeded with a topic, student, original, and past lesson."""
    store = BrainStore(root=tmp_path / "brain")

    store.save(
        BrainPage(
            slug="industrial-revolution",
            page_type="topic",
            title="Industrial Revolution",
            compiled_truth=(
                "## What Works\n\n"
                "Stations better than jigsaws for Bentley testimony."
            ),
            metadata={"updated": "2026-04-01"},
        )
    )

    student_page = BrainPage(
        slug="julia-m",
        page_type="student",
        title="Julia M.",
        compiled_truth=(
            "Strong reader, weak writer. Needs sentence starters."
        ),
        metadata={"tier": "1", "updated": "2026-04-01"},
    )
    store.save(student_page)

    store.save(
        BrainPage(
            slug="claim-evidence-framework",
            page_type="original",
            title="Claim and Evidence Framework",
            compiled_truth=(
                "Students need cognitive verbs defined explicitly before "
                "using them in assessments. 'Explain' means make plain."
            ),
        )
    )

    # Past lesson
    past_lesson = BrainPage(
        slug="2026-03-27-industrial-rev-day-1",
        page_type="lesson",
        title="Industrial Revolution Day 1",
        compiled_truth=(
            "Engels reading was too complex for Period 5. "
            "Bentley testimony landed well with all classes."
        ),
        metadata={"topic": "Industrial Revolution", "updated": "2026-03-27"},
    )
    past_lesson.add_timeline(
        "Period 5 struggled with Engels — need vocab pre-teach",
        date="2026-03-27",
    )
    store.save(past_lesson)

    return store


# ── build_brain_context ──────────────────────────────────────────────────


def test_build_brain_context_finds_topic(seeded_store: BrainStore):
    ctx = build_brain_context(
        topic="Industrial Revolution",
        store=seeded_store,
    )
    assert "Stations better than jigsaws" in ctx.topic_history
    assert any(
        c.source_type == "brain-topic" and c.reference == "industrial-revolution"
        for c in ctx.citations
    )


def test_build_brain_context_includes_tier1_students(seeded_store: BrainStore):
    ctx = build_brain_context(
        topic="Industrial Revolution",
        store=seeded_store,
    )
    assert any("Julia M." in s for s in ctx.relevant_students)


def test_build_brain_context_empty_when_no_match(tmp_path: Path):
    empty_store = BrainStore(root=tmp_path / "empty")
    ctx = build_brain_context(topic="Nonexistent Topic", store=empty_store)
    assert ctx.topic_history == ""
    assert ctx.relevant_students == []


def test_brain_context_renders_for_prompt(seeded_store: BrainStore):
    ctx = build_brain_context(
        topic="Industrial Revolution",
        store=seeded_store,
    )
    prompt = ctx.render_for_prompt()
    assert "Brain Context" in prompt
    assert "What worked before" in prompt


def test_brain_context_renders_empty_when_no_data():
    from clawed.master_content import BrainContext
    ctx = BrainContext()
    assert ctx.render_for_prompt() == ""


# ── write_lesson_to_brain ────────────────────────────────────────────────


def test_write_lesson_to_brain_creates_lesson_page(tmp_path: Path):
    from clawed.brain.writer import write_lesson_to_brain
    from clawed.master_content import (
        DoNow,
        GuidedNote,
        InstructionSection,
        MasterContent,
        PrimarySource,
        StimulusQuestion,
    )
    from clawed.models import DifferentiationNotes

    store = BrainStore(root=tmp_path / "brain")

    master = MasterContent(
        title="The Voice of Freedom: Frederick Douglass",
        subject="US History",
        grade_level="8th Grade",
        topic="Abolition Movement",
        standards=["NYS 8.7c"],
        objective="SWBAT analyze Douglass's speech",
        duration_minutes=40,
        vocabulary=[],
        primary_sources=[
            PrimarySource(
                id="source_a",
                title="What to the Slave is the Fourth of July?",
                source_type="text_excerpt",
                content_text="What, to the American slave, is your 4th of July?",
                attribution="Frederick Douglass, 1852",
                image_spec="Frederick Douglass portrait 1852",
            ),
        ],
        do_now=DoNow(
            stimulus="A quote from Douglass",
            stimulus_type="text_excerpt",
            questions=["Q1"],
            answers=["A1"],
        ),
        direct_instruction=[
            InstructionSection(
                heading="Who was Douglass",
                content="A born-enslaved abolitionist",
                teacher_script="Say: Who was Frederick Douglass? (wait)",
                key_points=["p1"],
                image_spec="Frederick Douglass portrait",
            ),
        ],
        guided_notes=[
            GuidedNote(
                prompt="Douglass escaped ________.",
                answer="slavery",
                section_ref="Who was Douglass",
            ),
        ],
        exit_ticket=[
            StimulusQuestion(
                stimulus="Douglass said 'your 4th of July'",
                stimulus_type="text_excerpt",
                question="What does 'your' imply?",
                answer="Exclusion",
                cognitive_level="analysis",
            ),
        ],
        differentiation=DifferentiationNotes(
            struggling=["sentence starter bookmarks"],
            advanced=["research another Douglass speech"],
            ell=["bilingual glossary with cognates"],
        ),
    )

    written = write_lesson_to_brain(
        master=master,
        unit_title="The Fight for Equality",
        lesson_number=1,
        store=store,
    )

    assert len(written["lessons"]) == 1
    lesson_slug = written["lessons"][0]
    lesson_page = store.get("lesson", lesson_slug)
    assert lesson_page is not None
    assert "Frederick Douglass" in lesson_page.title
    assert "Voice of Freedom" in lesson_page.compiled_truth or "Frederick Douglass" in lesson_page.compiled_truth
    assert len(lesson_page.timeline) >= 1


def test_write_lesson_to_brain_creates_topic_timeline(tmp_path: Path):
    from clawed.brain.writer import write_lesson_to_brain
    from clawed.master_content import (
        DoNow,
        GuidedNote,
        InstructionSection,
        MasterContent,
        StimulusQuestion,
    )
    from clawed.models import DifferentiationNotes

    store = BrainStore(root=tmp_path / "brain")

    master = MasterContent(
        title="Renaissance Art Day 1",
        subject="Global History",
        grade_level="9th Grade",
        topic="Renaissance Art",
        standards=["NYS 9.1"],
        objective="SWBAT analyze Renaissance paintings",
        do_now=DoNow(
            stimulus="A Michelangelo image",
            stimulus_type="image",
            questions=["Q1"],
            answers=["A1"],
        ),
        direct_instruction=[
            InstructionSection(
                heading="Humanism",
                content="Shift from God to human focus",
                teacher_script="What changed? Ask students.",
                key_points=["p1"],
                image_spec="Renaissance painting",
            ),
        ],
        guided_notes=[
            GuidedNote(
                prompt="Humanism means ________.",
                answer="human-centered",
                section_ref="Humanism",
            ),
        ],
        exit_ticket=[
            StimulusQuestion(
                stimulus="A quote",
                stimulus_type="text_excerpt",
                question="What does it mean?",
                answer="It means...",
                cognitive_level="analysis",
            ),
        ],
        differentiation=DifferentiationNotes(
            struggling=["visual vocabulary cards"],
            advanced=["research Leonardo"],
            ell=["image-heavy handout"],
        ),
    )

    written = write_lesson_to_brain(
        master=master,
        unit_title="Renaissance",
        lesson_number=2,
        store=store,
    )

    # Topic page should now exist with a timeline entry
    assert "renaissance-art" in written["topics"]
    topic_page = store.get("topic", "renaissance-art")
    assert topic_page is not None
    assert len(topic_page.timeline) >= 1


# ── Dream cycle ──────────────────────────────────────────────────────────


def test_dream_report_renders():
    report = DreamReport(
        started_at="2026-04-10T10:00:00",
        finished_at="2026-04-10T10:05:00",
        pages_scanned=20,
        pages_consolidated=3,
        gaps_detected=["Test gap"],
    )
    rendered = report.render()
    assert "Dream Cycle Report" in rendered
    assert "Pages scanned:** 20" in rendered
    assert "Test gap" in rendered


def test_find_consolidation_candidates(seeded_store: BrainStore):
    # Create a page with many timeline entries newer than "updated"
    hot_page = BrainPage(
        slug="hot-topic",
        page_type="topic",
        title="Hot Topic",
        compiled_truth="Old synthesis",
    )
    for i in range(10):
        hot_page.add_timeline(
            f"Event {i}", date=f"2026-03-{i+10:02d}",
        )
    # Override the updated date to be BEFORE the timeline entries
    hot_page.metadata["updated"] = "2026-01-01"
    seeded_store.save(hot_page)

    pages = [seeded_store.get("topic", "hot-topic")]
    candidates = _find_consolidation_candidates(pages)
    assert len(candidates) >= 1
    assert candidates[0].slug == "hot-topic"


def test_detect_gaps_finds_thin_pages(tmp_path: Path):
    store = BrainStore(root=tmp_path / "brain")
    thin = BrainPage(slug="thin", page_type="student", title="Thin")
    store.save(thin)
    pages = [store.get("student", "thin")]
    gaps = _detect_gaps(pages)
    assert any("empty" in g or "thin" in g.lower() for g in gaps)


@pytest.mark.asyncio
async def test_dream_cycle_runs(seeded_store: BrainStore):
    """Dream cycle should complete without errors even in dry-run mode."""
    report = await dream_cycle(
        store=seeded_store,
        consolidate=False,  # skip LLM calls
        dry_run=True,
    )
    assert report.pages_scanned > 0
    assert report.started_at
    assert report.finished_at
