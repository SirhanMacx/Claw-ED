"""Tests for the 4-phase split generation pipeline."""
from clawed.master_content import (
    CreativeActivity,
    DoNow,
    GuidedNote,
    InstructionSection,
    MasterContent,
    PrimarySource,
    StimulusQuestion,
    VocabularyEntry,
)
from clawed.models import DifferentiationNotes
from clawed.phases.models import (
    Phase1Skeleton,
    Phase2Instruction,
    Phase3Activities,
    Phase4Assessment,
)
from clawed.phases.pipeline import (
    _fill_template,
    _render_direct_instruction_block,
    _render_direct_instruction_headings,
    _render_primary_sources_block,
    _render_vocabulary_list,
    _render_vocabulary_terms,
    merge_phases,
)

# ── Phase models ─────────────────────────────────────────────────────


def test_phase1_model_basic_fields():
    p = Phase1Skeleton(
        title="Test Lesson",
        subject="US History",
        grade_level="8th Grade",
        topic="Reform Movements",
        objective="SWBAT analyze primary sources.",
        lesson_personality="Today you're historians investigating reform.",
        lesson_format="station_rotation",
    )
    assert p.title == "Test Lesson"
    assert p.duration_minutes == 45  # default
    assert p.vocabulary == []
    assert p.primary_sources == []


def test_phase1_with_vocabulary_and_sources():
    p = Phase1Skeleton(
        title="Test",
        subject="US History",
        grade_level="8th",
        topic="Reform",
        objective="obj",
        vocabulary=[
            VocabularyEntry(
                term="Suffrage",
                definition="The right to vote",
                context_sentence="Women fought for suffrage in 1920.",
                image_spec="1913 suffrage march",
            ),
        ],
        primary_sources=[
            PrimarySource(
                id="source_a",
                title="Declaration of Sentiments",
                source_type="text_excerpt",
                content_text="We hold these truths to be self-evident...",
                attribution="Elizabeth Cady Stanton, 1848",
                image_spec="Seneca Falls 1848",
                scaffolding_questions=["Q1?", "Q2?"],
            ),
        ],
    )
    assert len(p.vocabulary) == 1
    assert len(p.primary_sources) == 1


def test_phase2_model():
    p = Phase2Instruction(
        direct_instruction=[
            InstructionSection(
                heading="The Early Reformers",
                content="Content here",
                teacher_script="What did the reformers want? Ask students.",
                key_points=["k1"],
                image_spec="reformer portrait",
                hook="Imagine you saw injustice every day.",
                transition="Now let's see what they did about it.",
            ),
        ],
        guided_notes=[
            GuidedNote(
                prompt="Reform means ________",
                answer="change",
                section_ref="The Early Reformers",
            ),
        ],
        formative_checks=["Thumbs up if you can define suffrage."],
    )
    assert len(p.direct_instruction) == 1
    assert len(p.guided_notes) == 1


def test_phase3_model():
    p = Phase3Activities(
        do_now=DoNow(
            stimulus="A Susan B. Anthony quote.",
            stimulus_type="text_excerpt",
            questions=["What does this mean?"],
            answers=["Women demand rights"],
        ),
        creative_activity=CreativeActivity(
            activity_type="role_play",
            title="Suffrage Convention",
            scenario="It's 1848 at Seneca Falls.",
            roles=["Stanton", "Douglass"],
            student_directions="Prepare a 2-min speech.",
            deliverable="Speech + notes",
            debrief="Share one insight.",
            time_minutes=15,
        ),
    )
    assert p.do_now.questions == ["What does this mean?"]
    assert p.creative_activity.activity_type == "role_play"
    assert p.jigsaw is None


def test_phase4_model():
    p = Phase4Assessment(
        exit_ticket=[
            StimulusQuestion(
                stimulus="Quote from 1848.",
                stimulus_type="text_excerpt",
                question="What does Stanton argue?",
                answer="Equality",
                cognitive_level="recall",
            ),
        ],
        differentiation=DifferentiationNotes(
            struggling=["T-chart with rows modeled"],
            advanced=["Research a second source"],
            ell=["Sentence frames"],
        ),
        homework="Interview a family member about voting.",
    )
    assert len(p.exit_ticket) == 1
    assert p.differentiation.struggling[0].startswith("T-chart")


# ── Merge ─────────────────────────────────────────────────────────────


def test_merge_phases_produces_complete_master():
    p1 = Phase1Skeleton(
        title="Test",
        subject="US History",
        grade_level="8th",
        topic="Reform",
        objective="obj",
    )
    p2 = Phase2Instruction(
        direct_instruction=[
            InstructionSection(
                heading="h1",
                content="c1",
                teacher_script="What? Why?",
                key_points=["k"],
                image_spec="img",
            ),
        ],
        guided_notes=[
            GuidedNote(
                prompt="The ________ began in 1848.",
                answer="movement",
                section_ref="h1",
            ),
        ],
    )
    p3 = Phase3Activities(
        do_now=DoNow(
            stimulus="s",
            stimulus_type="text_excerpt",
            questions=["q"],
            answers=["a"],
        ),
    )
    p4 = Phase4Assessment(
        exit_ticket=[
            StimulusQuestion(
                stimulus="s",
                stimulus_type="text_excerpt",
                question="q?",
                answer="a",
                cognitive_level="recall",
            ),
        ],
        differentiation=DifferentiationNotes(
            struggling=["s1"],
            advanced=["a1"],
            ell=["e1"],
        ),
    )
    master = merge_phases(p1, p2, p3, p4)
    assert isinstance(master, MasterContent)
    assert master.title == "Test"
    assert len(master.direct_instruction) == 1
    assert len(master.guided_notes) == 1
    assert len(master.exit_ticket) == 1


# ── Prompt rendering helpers ─────────────────────────────────────────


def test_render_vocabulary_list():
    vocab = [
        VocabularyEntry(
            term="Reform",
            definition="Change for the better",
            context_sentence="Reform movements fought for justice.",
        ),
        VocabularyEntry(
            term="Suffrage",
            definition="The right to vote",
            context_sentence="Women won suffrage in 1920.",
        ),
    ]
    rendered = _render_vocabulary_list(vocab)
    assert "Reform" in rendered
    assert "Suffrage" in rendered
    assert "Change for the better" in rendered


def test_render_vocabulary_list_empty():
    rendered = _render_vocabulary_list([])
    assert "no vocabulary" in rendered.lower()


def test_render_primary_sources_block():
    sources = [
        PrimarySource(
            id="source_a",
            title="Test Source",
            source_type="text_excerpt",
            content_text="A long excerpt with significant content about the Industrial Revolution.",
            attribution="Author, 1832",
            image_spec="test image",
        ),
    ]
    rendered = _render_primary_sources_block(sources)
    assert "source_a" in rendered
    assert "Test Source" in rendered
    # Compressed rendering omits attribution to save tokens
    assert "Industrial Revolution" in rendered


def test_render_primary_sources_truncates_long_content():
    """Ensure primary source block aggressively caps content (compressed for downstream phases)."""
    long_text = "x" * 2000
    sources = [
        PrimarySource(
            id="source_a",
            title="Long Source",
            source_type="text_excerpt",
            content_text=long_text,
            attribution="Author, 2000",
            image_spec="img",
        ),
    ]
    rendered = _render_primary_sources_block(sources)
    # Compressed to ~150 chars per source
    assert len(rendered) < 500
    assert "..." in rendered


def test_render_direct_instruction_block():
    sections = [
        InstructionSection(
            heading="Intro",
            content="Introduction content",
            teacher_script="Ask? Say?",
            key_points=["k1"],
            image_spec="img",
        ),
    ]
    rendered = _render_direct_instruction_block(sections)
    assert "Intro" in rendered
    assert "Introduction content" in rendered


def test_render_direct_instruction_headings():
    sections = [
        InstructionSection(
            heading="Part 1",
            content="c",
            teacher_script="s?",
            key_points=["k"],
            image_spec="i",
        ),
        InstructionSection(
            heading="Part 2",
            content="c",
            teacher_script="s?",
            key_points=["k"],
            image_spec="i",
        ),
    ]
    rendered = _render_direct_instruction_headings(sections)
    assert "Part 1" in rendered
    assert "Part 2" in rendered


def test_fill_template_handles_literal_json_braces():
    """Regression test: template with literal JSON {} must not break."""
    template = (
        "Topic: {topic}\n\n"
        "Respond with JSON like:\n"
        '{"title": "X", "standards": ["Y"]}\n'
    )
    result = _fill_template(template, topic="Reform Movements")
    assert "Reform Movements" in result
    assert '"title"' in result
    assert '"standards"' in result


def test_fill_template_only_replaces_named_keys():
    template = "{name}: {value} — {note}"
    result = _fill_template(template, name="A", value="1")
    # Unreplaced {note} stays as-is (not a KeyError)
    assert "A: 1" in result
    assert "{note}" in result


def test_fill_template_ignores_unknown_braces():
    template = "Hello {name}, use {dict_var} format: {key: value}"
    result = _fill_template(template, name="World")
    assert "Hello World" in result
    assert "{dict_var}" in result
    assert "{key: value}" in result


def test_render_vocabulary_terms_comma_separated():
    vocab = [
        VocabularyEntry(term="A", definition="d", context_sentence="s"),
        VocabularyEntry(term="B", definition="d", context_sentence="s"),
        VocabularyEntry(term="C", definition="d", context_sentence="s"),
    ]
    rendered = _render_vocabulary_terms(vocab)
    assert "A" in rendered
    assert "B" in rendered
    assert "C" in rendered
    assert "," in rendered  # comma-separated
