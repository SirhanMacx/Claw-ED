"""Pydantic models for each phase of MasterContent generation.

Each phase has its own model with ONLY the fields that phase produces.
This gives the LLM a smaller, clearer schema per call and keeps
validation strict.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from clawed.master_content import (
    CreativeActivity,
    DoNow,
    GuidedNote,
    IndependentWork,
    InstructionSection,
    JigsawStructure,
    PrimarySource,
    StationDocument,
    StimulusQuestion,
    VocabularyEntry,
)
from clawed.models import DifferentiationNotes

# ══════════════════════════════════════════════════════════════════════
# Phase 1 — Skeleton + Primary Sources
# ══════════════════════════════════════════════════════════════════════


class Phase1Skeleton(BaseModel):
    """Phase 1: establishes the foundation of the lesson.

    What this phase produces:
    - Lesson metadata (title, subject, grade, standards, objective)
    - The VOICE of the lesson (lesson_personality)
    - Vocabulary terms that will be taught
    - The primary sources that will drive analysis (full text included)
    - Misconceptions to watch for
    - Prerequisite skills students need
    - Lesson format (jigsaw, station_rotation, etc.)
    - Materials the teacher needs to gather

    Downstream phases will reference THESE primary sources and
    vocabulary, so Phase 1 establishes the content backbone.
    """

    title: str
    subject: str
    grade_level: str
    topic: str
    standards: list[str] = Field(default_factory=list)
    objective: str
    duration_minutes: int = 45

    vocabulary: list[VocabularyEntry] = Field(default_factory=list)
    primary_sources: list[PrimarySource] = Field(default_factory=list)

    misconceptions: list[str] = Field(default_factory=list)
    prerequisite_skills: list[str] = Field(default_factory=list)

    lesson_format: str = "document_analysis"
    lesson_personality: str = ""
    materials_needed: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — Direct Instruction + Guided Notes
# ══════════════════════════════════════════════════════════════════════


class Phase2Instruction(BaseModel):
    """Phase 2: the TEACHING part of the lesson.

    What this phase produces:
    - Direct instruction sections (2-3)
    - Guided notes (10-12)
    - Formative checks

    Internally split into Phase 2a (direct_instruction) and Phase 2b
    (guided_notes + formative_checks) to prevent token exhaustion on
    long teacher_scripts that was causing guided_notes to drop to 0.
    """

    direct_instruction: list[InstructionSection] = Field(default_factory=list)
    guided_notes: list[GuidedNote] = Field(default_factory=list)
    formative_checks: list[str] = Field(default_factory=list)


class Phase2aDirectInstruction(BaseModel):
    """Phase 2a: just direct_instruction sections (no guided_notes).

    Splitting Phase 2 prevents token exhaustion — when the model has
    to produce both long teacher_scripts AND 10+ guided notes in one
    response, it often drops the guided notes.
    """

    direct_instruction: list[InstructionSection] = Field(default_factory=list)


class Phase2bGuidedNotes(BaseModel):
    """Phase 2b: guided_notes + formative_checks only.

    Generated AFTER Phase 2a so it can reference the actual section
    headings via section_ref.
    """

    guided_notes: list[GuidedNote] = Field(default_factory=list)
    formative_checks: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════
# Phase 3 — Activities (Do Now, Stations, Creative, Jigsaw)
# ══════════════════════════════════════════════════════════════════════


class Phase3Activities(BaseModel):
    """Phase 3: the ACTIVE engagement parts of the lesson.

    What this phase produces:
    - Do Now (stimulus-based opener, often previewing a primary source)
    - Stations (3-4 with full student directions AND answer keys,
      referencing Phase 1 primary sources by id)
    - Jigsaw structure (required if lesson_format is "jigsaw")
    - Creative activity (role play, debate, podcast, etc. — always)
    - Independent work
    - Minute-by-minute pacing (times summing to duration_minutes)

    This phase SEES Phase 1 + Phase 2 in its context, so activities
    can reference the primary sources AND the direct instruction.
    """

    do_now: DoNow
    stations: list[StationDocument] = Field(default_factory=list)
    jigsaw: JigsawStructure | None = None
    creative_activity: CreativeActivity | None = None
    independent_work: IndependentWork | None = None
    minute_by_minute: list[dict] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════
# Phase 4 — Assessment + Differentiation
# ══════════════════════════════════════════════════════════════════════


class Phase4Assessment(BaseModel):
    """Phase 4: the ASSESSMENT and SUPPORT parts of the lesson.

    What this phase produces:
    - Exit ticket (3 questions with Bloom progression: recall →
      application → analysis, each with a stimulus and sentence starters
      matching the teacher's writing framework)
    - Differentiation (struggling/advanced/ELL with SPECIFIC scaffolds,
      not generic "provide extra time")
    - Homework (AI-resistant task connecting to student's life outside school)

    This phase SEES Phase 1 (primary sources, vocabulary) and Phase 2
    (direct_instruction) in context so the assessment references what
    was actually taught.
    """

    exit_ticket: list[StimulusQuestion] = Field(default_factory=list)
    differentiation: DifferentiationNotes
    homework: str | None = None
