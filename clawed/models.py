"""Pydantic data models for Claw-ED."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DocType(str, Enum):
    """Supported document types."""

    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    TXT = "txt"
    MD = "md"
    NOTEBOOK = "notebook"
    XBK = "xbk"
    FLIPCHART = "flipchart"
    UNKNOWN = "unknown"


class Document(BaseModel):
    """A single ingested document with extracted text."""

    title: str
    content: str
    doc_type: DocType
    source_path: Optional[str] = None
    page_count: Optional[int] = None
    tags: list[str] = Field(default_factory=list)


class TeachingStyle(str, Enum):
    SOCRATIC = "socratic"
    DIRECT_INSTRUCTION = "direct_instruction"
    INQUIRY_BASED = "inquiry_based"
    PROJECT_BASED = "project_based"
    BLENDED = "blended"
    LECTURE_DISCUSSION = "lecture_discussion"
    WORKSHOP = "workshop"
    FLIPPED = "flipped"
    COOPERATIVE = "cooperative"
    DIFFERENTIATED = "differentiated"


class VocabularyLevel(str, Enum):
    ELEMENTARY = "elementary"
    GRADE_APPROPRIATE = "grade_appropriate"
    ACADEMIC = "academic"
    CASUAL = "casual"


class AssessmentStyle(str, Enum):
    RUBRIC_BASED = "rubric_based"
    POINT_BASED = "point_based"
    PORTFOLIO = "portfolio"
    STANDARDS_BASED = "standards_based"
    COMPETENCY_BASED = "competency_based"
    MASTERY_BASED = "mastery_based"
    PARTICIPATION_BASED = "participation_based"


class TeacherPersona(BaseModel):
    """Extracted teacher persona from curriculum materials."""

    name: str = "My Teaching Persona"
    teaching_style: TeachingStyle = TeachingStyle.DIRECT_INSTRUCTION

    @field_validator("teaching_style", mode="before")
    @classmethod
    def _coerce_teaching_style(cls, v):
        """Map unrecognized LLM-generated styles to the closest enum value."""
        if isinstance(v, TeachingStyle):
            return v
        if isinstance(v, str):
            # Try exact match first
            try:
                return TeachingStyle(v)
            except ValueError:
                pass
            # Fuzzy map common LLM outputs to valid enum values
            aliases = {
                "lecture": "lecture_discussion",
                "discussion": "lecture_discussion",
                "lecture_based": "lecture_discussion",
                "collaborative": "cooperative",
                "experiential": "inquiry_based",
                "constructivist": "inquiry_based",
                "problem_based": "project_based",
                "student_centered": "inquiry_based",
                "teacher_centered": "direct_instruction",
                "traditional": "direct_instruction",
                "hybrid": "blended",
                "mixed": "blended",
            }
            normalized = v.lower().strip().replace("-", "_").replace(" ", "_")
            if normalized in aliases:
                return TeachingStyle(aliases[normalized])
            # Last resort: default to blended
            return TeachingStyle.BLENDED
        return v

    vocabulary_level: VocabularyLevel = VocabularyLevel.GRADE_APPROPRIATE

    @field_validator("vocabulary_level", mode="before")
    @classmethod
    def _coerce_vocabulary_level(cls, v):
        """Map unrecognized vocabulary levels to the closest enum value."""
        if isinstance(v, VocabularyLevel):
            return v
        if isinstance(v, str):
            try:
                return VocabularyLevel(v)
            except ValueError:
                pass
            normalized = v.lower().strip().replace("-", "_").replace(" ", "_")
            # Try with normalization
            for member in VocabularyLevel:
                if member.value == normalized:
                    return member
            return VocabularyLevel.GRADE_APPROPRIATE
        return v

    tone: str = "warm and encouraging"
    structural_preferences: list[str] = Field(default_factory=lambda: ["warm-ups", "exit tickets"])
    assessment_style: AssessmentStyle = AssessmentStyle.RUBRIC_BASED

    @field_validator("assessment_style", mode="before")
    @classmethod
    def _coerce_assessment_style(cls, v):
        """Map unrecognized assessment styles to the closest enum value."""
        if isinstance(v, AssessmentStyle):
            return v
        if isinstance(v, str):
            try:
                return AssessmentStyle(v)
            except ValueError:
                pass
            aliases = {
                "points_based": "point_based",
                "points": "point_based",
                "rubric": "rubric_based",
                "rubrics": "rubric_based",
                "standards": "standards_based",
                "standard_based": "standards_based",
                "competency": "competency_based",
                "mastery": "mastery_based",
                "participation": "participation_based",
                "performance_based": "rubric_based",
                "grade_based": "point_based",
                "grading": "point_based",
            }
            normalized = v.lower().strip().replace("-", "_").replace(" ", "_")
            if normalized in aliases:
                return AssessmentStyle(aliases[normalized])
            return AssessmentStyle.RUBRIC_BASED
        return v

    preferred_lesson_format: str = "I Do / We Do / You Do"
    favorite_strategies: list[str] = Field(default_factory=list)
    subject_area: str = ""
    grade_levels: list[str] = Field(default_factory=list)
    voice_sample: str = ""
    voice_examples: list[str] = Field(default_factory=list)

    @field_validator("tone", mode="before")
    @classmethod
    def _truncate_tone(cls, v):
        if isinstance(v, str) and len(v) > 500:
            return v[:500]
        return v

    @field_validator("preferred_lesson_format", mode="before")
    @classmethod
    def _truncate_preferred_lesson_format(cls, v):
        if isinstance(v, str) and len(v) > 500:
            return v[:500]
        return v

    @field_validator("subject_area", mode="before")
    @classmethod
    def _truncate_subject_area(cls, v):
        if isinstance(v, str) and len(v) > 200:
            return v[:200]
        return v

    @field_validator("voice_sample", mode="before")
    @classmethod
    def _truncate_voice_sample(cls, v):
        if isinstance(v, str) and len(v) > 2000:
            return v[:2000]
        return v

    # ── Pedagogical fingerprint (v2.0) ────────────────────────────────
    # These fields capture HOW a teacher teaches, not just how they sound.
    source_types: list[str] = Field(default_factory=list)
    """Types of primary sources this teacher uses (e.g. 'political speeches',
    'historical maps', 'data tables', 'poetry excerpts', 'court documents')."""

    activity_patterns: list[str] = Field(default_factory=list)
    """Detailed descriptions of recurring activity structures, e.g.
    'Uses jigsaw with 4-person expert groups rotating every 10 minutes',
    'Do Nows are always analogy-based scenarios, never recall questions'."""

    scaffolding_moves: list[str] = Field(default_factory=list)
    """How this teacher scaffolds for access, e.g. 'Always provides writing
    frames with sentence starters', 'Uses T-charts before open-ended analysis',
    'Pre-teaches 3 vocabulary words with visual icons'."""

    grouping_preferences: str = ""
    """How students are typically grouped (e.g. 'pairs for turn-and-talk,
    table groups of 4 for document analysis, whole class for Socratic seminar')."""

    do_now_style: str = ""
    """Pattern for warm-ups/do-nows (e.g. 'analogy or scenario that previews the
    lesson concept without naming it — never a content recall question')."""

    exit_ticket_style: str = ""
    """Pattern for exit tickets (e.g. 'always 3 questions progressing
    recall → application → analysis, written on half-sheets')."""

    signature_moves: list[str] = Field(default_factory=list)
    """Distinctive teaching moves unique to this teacher, e.g.
    'Reads primary sources aloud with dramatic emphasis before analysis',
    'Always ends DI with "here is where it gets interesting"',
    'Uses physical movement — students walk to corners for opinion spectrums'."""

    handout_style: str = ""
    """Description of the teacher's handout/worksheet style, e.g.
    'Dense text packets with primary source excerpts and marginal annotations'
    or 'Graphic organizer-heavy with minimal text, always includes an image hook'."""

    assessment_question_types: list[str] = []
    """Assessment question formats this teacher uses, e.g.
    'CRQ with stimulus, context, analysis, application', 'DBQ with 5-7 docs',
    'stimulus-based multiple choice'. Extracted from ingested files."""

    writing_framework: str = ""
    """Student writing/response framework, e.g. 'TEA (Thesis-Evidence-Analysis)',
    'RACE (Restate-Answer-Cite-Explain)', 'CER (Claim-Evidence-Reasoning)'.
    Critical — all generated content must use the same framework."""

    def to_prompt_context(self) -> str:
        """Serialize persona into a string for LLM prompt injection."""
        lines = [
            "Teacher Persona:",
            f"- Name: {self.name}",
            f"- Teaching Style: {self.teaching_style.value.replace('_', ' ').title()}",
            f"- Vocabulary Level: {self.vocabulary_level.value.replace('_', ' ').title()}",
            f"- Tone: {self.tone}",
            f"- Structural Preferences: {', '.join(self.structural_preferences)}",
            f"- Assessment Style: {self.assessment_style.value.replace('_', ' ').title()}",
            f"- Preferred Lesson Format: {self.preferred_lesson_format}",
            f"- Favorite Strategies: {', '.join(self.favorite_strategies) or 'None specified'}",
            f"- Subject Area: {self.subject_area or 'General'}",
            f"- Grade Levels: {', '.join(self.grade_levels) or 'Not specified'}",
            f"- Voice Sample: {self.voice_sample[:2000] if self.voice_sample else 'None'}",
        ]

        # Pedagogical fingerprint — how this teacher actually teaches
        if self.source_types:
            lines.append("\n=== Source Types This Teacher Uses ===")
            for src in self.source_types:
                lines.append(f"- {src}")
            lines.append("Use these TYPES of sources in generated lessons.")

        if self.activity_patterns:
            lines.append("\n=== Activity Patterns (replicate these structures) ===")
            for pat in self.activity_patterns:
                lines.append(f"- {pat}")

        if self.scaffolding_moves:
            lines.append("\n=== Scaffolding Moves ===")
            for move in self.scaffolding_moves:
                lines.append(f"- {move}")

        if self.do_now_style:
            lines.append(f"\n=== Do Now Style ===\n{self.do_now_style}")
            lines.append("Generate Do Nows that follow this pattern.")

        if self.exit_ticket_style:
            lines.append(f"\n=== Exit Ticket Style ===\n{self.exit_ticket_style}")

        if self.grouping_preferences:
            lines.append(f"\n=== Grouping ===\n{self.grouping_preferences}")

        if self.signature_moves:
            lines.append("\n=== Signature Teaching Moves (MUST include) ===")
            for move in self.signature_moves:
                lines.append(f"- {move}")

        if self.handout_style:
            lines.append(f"\n=== Handout Style ===\n{self.handout_style}")
            lines.append("Student packets must match this format.")

        if self.assessment_question_types:
            lines.append("\n=== Assessment Question Types (use these formats) ===")
            for qt in self.assessment_question_types:
                lines.append(f"- {qt}")

        if self.writing_framework:
            lines.append("\n=== Writing Framework (CRITICAL — students use this) ===")
            lines.append(self.writing_framework)
            lines.append("ALL generated writing prompts and responses must use this framework.")

        if self.voice_examples:
            lines.append("")
            lines.append("=== Voice Examples (write EXACTLY like this) ===")
            for i, example in enumerate(self.voice_examples[:5], 1):
                lines.append(f'Example {i}: "{example}"')

        # Strong voice enforcement block
        lines.append("")
        lines.append("=== VOICE ENFORCEMENT (CRITICAL) ===")
        lines.append("Your writing MUST match this teacher's actual voice. This means:")
        lines.append("- Use their EXACT phrases and transitions from the voice examples above")
        lines.append("- Match their tone — if they're warm and witty, be warm and witty. If they're direct, be direct.")
        lines.append(
            "- Use their scaffolding patterns — if they use fill-in-"
            "the-blank guided notes, you MUST use fill-in-the-blank "
            "guided notes"
        )
        lines.append(
            "- Use their activity structures — if they use jigsaw groups of 3, you MUST use jigsaw groups of 3"
        )
        lines.append(
            "- DO NOT write like a textbook. DO NOT use generic AI "
            "language. DO NOT be dry or formal unless the teacher is "
            "dry and formal."
        )
        lines.append("- A colleague reading this lesson should think the teacher wrote it themselves.")
        return "\n".join(lines) + "\n"


class LessonBrief(BaseModel):
    """Brief description of a lesson within a unit plan."""

    lesson_number: int
    topic: str
    description: str
    lesson_type: str = "instruction"


class AssessmentPlan(BaseModel):
    """Assessment plan within a unit."""

    formative: list[str] = Field(default_factory=list)
    summative: list[str] = Field(default_factory=list)


class ProjectPhase(BaseModel):
    """One phase/day of a multi-day project arc."""

    day_number: int
    title: str  # "Day 1: The Spark (Selection)"
    objective: str
    activities: list[str] = Field(default_factory=list)
    student_deliverable: str = ""  # What students produce this day
    checkpoint: str = ""  # How teacher checks progress


class CulminatingPerformance(BaseModel):
    """The final performance task of a project arc."""

    title: str = ""  # "The Reformers' Summit"
    format: str = ""  # gallery_walk, debate, presentation, symposium
    duration_minutes: int = 40
    setup_instructions: str = ""  # How to arrange the room
    student_prep: str = ""  # What students need ready
    evaluation_criteria: list[str] = Field(default_factory=list)
    debrief_protocol: str = ""  # How to close


class ProjectArc(BaseModel):
    """A multi-day project arc with phases, rubric, and culminating performance."""

    title: str
    essential_question: str = ""  # Driving question for the whole project
    duration_days: int = 5
    phases: list[ProjectPhase] = Field(default_factory=list)
    movement_options: list[str] = Field(default_factory=list)  # Topics students can choose
    format_options: list[str] = Field(default_factory=list)  # Project formats
    resource_library: list[dict] = Field(default_factory=list)  # curated research databases
    rubric_text: str = ""  # Full 4-point rubric as formatted text
    culminating_performance: CulminatingPerformance = Field(default_factory=CulminatingPerformance)
    debate_prep_template: str = ""  # Formatted debate/argument prep sheet
    graphic_organizer: str = ""  # Research note-taking template


class UnitPlan(BaseModel):
    """A complete unit plan."""

    title: str
    subject: str
    grade_level: str
    topic: str
    duration_weeks: int
    overview: str
    essential_questions: list[str] = Field(default_factory=list)
    enduring_understandings: list[str] = Field(default_factory=list)
    standards: list[str] = Field(default_factory=list)
    daily_lessons: list[LessonBrief] = Field(default_factory=list)
    assessment_plan: AssessmentPlan = Field(default_factory=AssessmentPlan)
    required_materials: list[str] = Field(default_factory=list)
    project: Optional[ProjectArc] = None  # Multi-day project arc (for units > 1 week)


class ExitTicketQuestion(BaseModel):
    """A single exit ticket question."""

    question: str
    expected_response: str = ""


class DifferentiationNotes(BaseModel):
    """Differentiation accommodations."""

    struggling: list[str] = Field(default_factory=list)
    advanced: list[str] = Field(default_factory=list)
    ell: list[str] = Field(default_factory=list)


class IEPProfile(BaseModel):
    """A student's IEP (Individualized Education Program) profile.

    Contains disability information, required accommodations, modifications,
    and annual goals — everything a teacher needs to differentiate a lesson
    for this student.
    """

    student_name: str
    disability_type: str = ""
    accommodations: list[str] = Field(default_factory=list)
    modifications: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)


# ── Structured lesson components (v2.3) ────────────────────────────────


class VocabularyTerm(BaseModel):
    """A key vocabulary term with definition."""

    term: str
    definition: str


class PrimarySourceDocument(BaseModel):
    """A primary source for station-based or jigsaw activities."""

    document_label: str = ""
    title: str = ""
    author: str = ""
    date: str = ""
    context: str = ""
    full_text: str = ""
    analysis_questions: list[str] = Field(default_factory=list)


class GuidedNotesBlank(BaseModel):
    """A fill-in-the-blank item within guided notes."""

    sentence_with_blank: str = ""
    answer: str = ""


class GraphicOrganizerSpec(BaseModel):
    """Schema for a table-based graphic organizer."""

    title: str = ""
    instructions: str = ""
    columns: list[str] = Field(default_factory=list)
    num_rows: int = 4


class ImageSpec(BaseModel):
    """Specification for an image to include in materials."""

    description: str = ""
    search_query: str = ""
    placement: str = ""
    size: str = "large"


class LessonSectionDetail(BaseModel):
    """Per-section detail for the administrator lesson plan."""

    section_name: str = ""
    timing_minutes: int = 0
    teacher_actions: str = ""
    student_actions: str = ""
    observer_look_fors: str = ""
    differentiation: str = ""


class AnticipatedResponse(BaseModel):
    """Expected student response or misconception."""

    response_or_misconception: str = ""
    is_misconception: bool = False
    teacher_correction: str = ""


class DailyLesson(BaseModel):
    """A complete daily lesson plan."""

    title: str
    lesson_number: int
    objective: str
    standards: list[str] = Field(default_factory=list)
    do_now: str = ""
    direct_instruction: str = ""
    guided_practice: str = ""
    independent_work: str = ""
    exit_ticket: list[ExitTicketQuestion] = Field(default_factory=list)
    homework: Optional[str] = None
    differentiation: DifferentiationNotes = Field(default_factory=DifferentiationNotes)
    materials_needed: list[str] = Field(default_factory=list)
    time_estimates: dict[str, int] = Field(
        default_factory=lambda: {
            "do_now": 5,
            "direct_instruction": 20,
            "guided_practice": 15,
            "independent_work": 10,
        }
    )

    # Structured fields (v2.3) — all optional for backward compatibility
    vocabulary: list[VocabularyTerm] = Field(default_factory=list)
    primary_sources: list[PrimarySourceDocument] = Field(default_factory=list)
    graphic_organizer: Optional[GraphicOrganizerSpec] = None
    teacher_content_knowledge: str = ""
    image_specs: list[ImageSpec] = Field(default_factory=list)


class StudentPacket(BaseModel):
    """LLM-generated student packet — the primary student-facing deliverable.

    This is the document students actually work through in class: fill-in-the-blank
    guided notes, station sections with primary source text and analysis questions,
    graphic organizer tables, and exit ticket with sentence starters.
    """

    title: str = ""
    aim: str = ""
    do_now_prompt: str = ""
    do_now_response_lines: int = 4
    vocabulary: list[VocabularyTerm] = Field(default_factory=list)
    guided_notes: list[GuidedNotesBlank] = Field(default_factory=list)
    stations: list[PrimarySourceDocument] = Field(default_factory=list)
    graphic_organizer: Optional[GraphicOrganizerSpec] = None
    exit_ticket_questions: list[str] = Field(default_factory=list)
    sentence_starters: list[str] = Field(default_factory=list)
    image_specs: list[ImageSpec] = Field(default_factory=list)


class AdminLessonPlan(BaseModel):
    """Enriched lesson plan for administrator observation.

    Structured as a multi-column table with per-section teacher actions,
    student actions, observer look-fors, and differentiation. Includes
    anticipated student responses and teacher content knowledge.
    """

    teacher_name: str = ""
    course: str = ""
    date: str = ""
    unit_title: str = ""
    topic: str = ""
    grade_level: str = ""
    duration_minutes: int = 40
    aim: str = ""
    standards: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    sections: list[LessonSectionDetail] = Field(default_factory=list)
    anticipated_responses: list[AnticipatedResponse] = Field(default_factory=list)
    teacher_content_knowledge: str = ""


class WorksheetItem(BaseModel):
    """A single item on a worksheet."""

    item_number: int
    item_type: str = "short_answer"
    prompt: str
    answer_key: str = ""
    point_value: int = 1

    @field_validator("point_value", mode="before")
    @classmethod
    def _coerce_point_value(cls, v):
        if isinstance(v, str):
            import re

            match = re.match(r"(\d+)", v.strip())
            return int(match.group(1)) if match else 1
        return v


class AssessmentQuestion(BaseModel):
    """A single assessment question."""

    question_number: int
    question_type: str = "multiple_choice"
    question: str
    choices: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    point_value: int = 1

    @field_validator("point_value", mode="before")
    @classmethod
    def _coerce_point_value(cls, v):
        if isinstance(v, str):
            import re

            match = re.match(r"(\d+)", v.strip())
            return int(match.group(1)) if match else 1
        return v


class RubricCriterion(BaseModel):
    """A single rubric criterion with levels."""

    criterion: str
    excellent: str = ""
    proficient: str = ""
    developing: str = ""
    beginning: str = ""


class SlideOutline(BaseModel):
    """Outline for a single slide."""

    slide_number: int
    title: str
    content_bullets: list[str] = Field(default_factory=list)
    speaker_notes: str = ""


class LessonMaterials(BaseModel):
    """All materials generated for a daily lesson."""

    lesson_title: str
    worksheet_items: list[WorksheetItem] = Field(default_factory=list)
    assessment_questions: list[AssessmentQuestion] = Field(default_factory=list)
    rubric: list[RubricCriterion] = Field(default_factory=list)
    slide_outline: list[SlideOutline] = Field(default_factory=list)
    iep_notes: list[str] = Field(default_factory=list)


class School(BaseModel):
    """A school deployment — groups teachers for curriculum sharing."""

    school_id: str = ""
    name: str = ""
    district: str = ""
    state: str = ""
    grade_levels: list[str] = Field(default_factory=list)


class SharedContentEntry(BaseModel):
    """A unit or lesson shared to a school's curriculum library."""

    id: str = ""
    school_id: str = ""
    teacher_id: str = ""
    teacher_name: str = ""
    content_type: str = "unit"  # "unit" or "lesson"
    content_id: str = ""
    title: str = ""
    subject: str = ""
    grade_level: str = ""
    department: str = ""
    rating: Optional[int] = None
    shared_at: str = ""


class ScheduleBlock(BaseModel):
    """A single time block in the daily schedule."""

    time: str
    period: str
    class_name: str
    notes: str = ""


class BehavioralNote(BaseModel):
    """Behavioral context for a class period."""

    period: str
    class_dynamics: str
    seating_chart: str = "See printed seating chart on teacher desk."
    accommodations: list[str] = Field(default_factory=list)
    key_students: list[str] = Field(default_factory=list)


class SubLessonInstructions(BaseModel):
    """Step-by-step lesson instructions written for a substitute."""

    period: str
    lesson_title: str
    objective: str
    step_by_step: list[str] = Field(default_factory=list)
    materials_needed: list[str] = Field(default_factory=list)
    backup_activity: str = ""
    answer_key_location: str = ""


class SubPacket(BaseModel):
    """A complete substitute teacher packet."""

    teacher_name: str
    date: str
    school: str = ""
    schedule: list[ScheduleBlock] = Field(default_factory=list)
    behavioral_notes: list[BehavioralNote] = Field(default_factory=list)
    lesson_instructions: list[SubLessonInstructions] = Field(default_factory=list)
    emergency_contacts: list[str] = Field(
        default_factory=lambda: [
            "Main Office: ext. 100",
            "Nurse: ext. 150",
            "Nearest Teacher (for emergencies): See posted list by door",
        ]
    )
    emergency_procedures: str = (
        "Fire drill: exit via nearest marked exit, proceed to designated area. "
        "Lockdown: lock door, lights off, students against interior wall away from windows."
    )
    general_notes: str = ""
    materials_checklist: list[str] = Field(default_factory=list)


class ProgressUpdate(BaseModel):
    """A parent communication progress update in the teacher's voice."""

    student_name: str
    greeting: str
    strengths: list[str] = Field(default_factory=list)
    areas_to_grow: list[str] = Field(default_factory=list)
    specific_examples: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    closing: str = ""


# ── Assessment intelligence models ─────────────────────────────────────


class QuestionType(str, Enum):
    """Types of assessment questions."""

    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    TRUE_FALSE = "true_false"
    ESSAY = "essay"
    DBQ = "dbq"
    FILL_IN_BLANK = "fill_in_the_blank"


class RubricLevel(BaseModel):
    """A single level within a rubric row (e.g. '4 — Exceeds')."""

    score: int
    label: str
    descriptors: list[str] = Field(default_factory=list)


class Rubric(BaseModel):
    """A complete rubric for any written task. 4-point scale."""

    task_description: str
    criteria: list[RubricCriterion] = Field(default_factory=list)
    total_points: int = 0


class FormativeAssessment(BaseModel):
    """Exit-ticket style formative assessment — checks ONE lesson's objective."""

    lesson_title: str
    objective: str
    questions: list[AssessmentQuestion] = Field(default_factory=list)
    answer_key: dict[int, str] = Field(default_factory=dict)
    time_minutes: int = 5


class SummativeQuestion(BaseModel):
    """A question in a summative assessment with Bloom's level tag."""

    question_number: int
    question_type: str = "multiple_choice"
    blooms_level: str = "remember"
    question: str
    choices: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    point_value: int = 1
    standard_aligned: str = ""

    @field_validator("point_value", mode="before")
    @classmethod
    def _coerce_point_value(cls, v):
        if isinstance(v, str):
            import re

            match = re.match(r"(\d+)", v.strip())
            return int(match.group(1)) if match else 1
        return v


class SummativeAssessment(BaseModel):
    """Unit test — mix of MC, short answer, DBQ/essay aligned to all unit objectives."""

    unit_title: str
    subject: str
    grade_level: str
    objectives: list[str] = Field(default_factory=list)
    questions: list[SummativeQuestion] = Field(default_factory=list)
    rubric: list[RubricCriterion] = Field(default_factory=list)
    total_points: int = 0
    time_minutes: int = 45


class DBQDocument(BaseModel):
    """A primary source document within a DBQ assessment."""

    document_number: int
    title: str
    source: str = ""
    date: str = ""
    content: str = ""
    scaffolding_questions: list[str] = Field(default_factory=list)


class DBQAssessment(BaseModel):
    """Document-Based Question — NYS Regents style.

    Includes background paragraph, primary source documents with scaffolding
    questions, extended response prompt, and a model answer.
    """

    topic: str
    grade_level: str
    background: str = ""
    documents: list[DBQDocument] = Field(default_factory=list)
    essay_prompt: str = ""
    model_answer: str = ""
    rubric: list[RubricCriterion] = Field(default_factory=list)
    time_minutes: int = 60


class Quiz(BaseModel):
    """Short quiz — teacher-specified format mix."""

    topic: str
    grade_level: str
    questions: list[AssessmentQuestion] = Field(default_factory=list)
    answer_key: dict[int, str] = Field(default_factory=dict)
    total_points: int = 0
    time_minutes: int = 15


# ── Year-level curriculum planning models ─────────────────────────────────


class YearMapUnit(BaseModel):
    """A single unit within the full-year curriculum map."""

    unit_number: int
    title: str
    duration_weeks: int
    essential_questions: list[str] = Field(default_factory=list)
    standards: list[str] = Field(default_factory=list)
    description: str = ""


class BigIdea(BaseModel):
    """A big idea that connects across multiple units in the year."""

    idea: str
    connected_units: list[int] = Field(default_factory=list)


class AssessmentCalendarEntry(BaseModel):
    """A planned assessment on the year calendar."""

    unit_number: int
    assessment_type: str = "summative"  # formative, summative, benchmark, diagnostic
    title: str
    week: int


class YearMap(BaseModel):
    """A full-year curriculum map — the top-level planning document."""

    subject: str
    grade_level: str
    school_year: str = ""
    total_weeks: int = 36
    units: list[YearMapUnit] = Field(default_factory=list)
    big_ideas: list[BigIdea] = Field(default_factory=list)
    assessment_calendar: list[AssessmentCalendarEntry] = Field(default_factory=list)


class SchoolCalendarEvent(BaseModel):
    """A school calendar event (holiday, break, PD day)."""

    date: str  # ISO date
    end_date: str = ""  # For multi-day events like breaks
    event: str
    type: str = "holiday"  # holiday, break, pd_day, half_day, testing


class PacingWeek(BaseModel):
    """A single week in the pacing guide."""

    week_number: int
    start_date: str  # ISO date
    end_date: str  # ISO date
    unit_title: str
    unit_number: int
    topics: list[str] = Field(default_factory=list)
    notes: str = ""  # holidays, testing windows, etc.


class PacingGuide(BaseModel):
    """A week-by-week pacing guide with actual calendar dates."""

    subject: str
    grade_level: str
    school_year: str = ""
    start_date: str  # ISO date of first instructional day
    weeks: list[PacingWeek] = Field(default_factory=list)


class CurriculumGap(BaseModel):
    """An identified gap in curriculum coverage vs. standards."""

    standard: str
    description: str
    severity: str = "medium"  # low, medium, high
    suggestion: str = ""


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    GOOGLE = "google"
    OPENROUTER = "openrouter"


VALID_SUBJECTS = {
    "math",
    "mathematics",
    "science",
    "biology",
    "chemistry",
    "physics",
    "social studies",
    "history",
    "civics",
    "government",
    "geography",
    "english",
    "ela",
    "language arts",
    "reading",
    "writing",
    "art",
    "music",
    "physical education",
    "health",
    "technology",
    "computer science",
    "foreign language",
    "spanish",
    "french",
    "special education",
    "general",
}


class TeacherProfile(BaseModel):
    """Teacher-specific configuration that auto-tailors all generation.

    This is the key to personalization — when a teacher sets their profile,
    every lesson plan, unit, worksheet, and assessment is automatically
    aligned to their state standards, subjects, and grade levels.
    """

    name: str = ""
    school: str = ""

    # What they teach
    subjects: list[str] = Field(default_factory=list)
    grade_levels: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if len(v) > 100:
                v = v[:100]
        return v

    @field_validator("subjects", mode="before")
    @classmethod
    def _validate_subjects(cls, v):
        if isinstance(v, list):
            validated = []
            for s in v:
                if not isinstance(s, str):
                    continue
                s_lower = s.strip().lower()
                if s_lower in VALID_SUBJECTS:
                    # Exact match — canonicalize to title case
                    validated.append(s.strip().title())
                else:
                    # Not an exact match — preserve the original value unchanged
                    # (fuzzy substitution risks corrupting legitimate subject names)
                    validated.append(s.strip())
            return validated if validated else v
        return v

    @field_validator("school", mode="before")
    @classmethod
    def _validate_school(cls, v):
        if isinstance(v, str) and len(v) > 200:
            v = v[:200]
        return v

    # Standards framework (determines which standards to reference)
    # Options: "CCSS", "NGSS", "C3", "NY_SS", "TX_TEKS", "CA_FRAMEWORKS", "custom"
    standards_framework: str = "CCSS"
    state: str = ""  # e.g., "NY", "CA", "TX" — used to select state-specific standards

    # Teaching context
    class_size: Optional[int] = None
    has_iep_students: bool = True
    has_ell_students: bool = True
    school_year: str = "2025-26"

    # Materials paths (where their curriculum lives)
    materials_paths: list[str] = Field(default_factory=list)  # Local paths
    drive_urls: list[str] = Field(default_factory=list)  # Google Drive URLs

    # API keys (stored here for portability, keyring preferred)
    tavily_api_key: Optional[str] = None

    def get_standards_prefix(self) -> str:
        """Get the standards code prefix for this teacher's framework."""
        mapping = {
            "CCSS": "CCSS",
            "NGSS": "NGSS",
            "C3": "C3",
            "NY_SS": "NYS-SS",
            "TX_TEKS": "TEKS",
        }
        return mapping.get(self.standards_framework, self.standards_framework)

    def describe(self) -> str:
        """Human-readable profile summary for LLM prompts."""
        parts = []
        if self.name:
            parts.append(f"Teacher: {self.name}")
        if self.school:
            parts.append(f"School: {self.school}")
        if self.subjects:
            parts.append(f"Subjects: {', '.join(self.subjects)}")
        if self.grade_levels:
            parts.append(f"Grades: {', '.join(self.grade_levels)}")
        if self.standards_framework:
            parts.append(f"Standards: {self.standards_framework}")
        if self.state:
            parts.append(f"State: {self.state}")
        if self.has_iep_students:
            parts.append("Has IEP students: Yes")
        if self.has_ell_students:
            parts.append("Has ELL students: Yes")
        return "\n".join(parts) if parts else "Profile not configured"

    def get_standards_context(self) -> str:
        """Generate standards context string for LLM prompt injection.

        Uses the teacher's state, subjects, and grade levels to produce
        a block of text describing applicable standards frameworks.
        """
        if not self.state:
            return ""
        from clawed.state_standards import get_standards_context_for_prompt

        return get_standards_context_for_prompt(self.state, self.subjects, self.grade_levels)


class AppConfig(BaseModel):
    """Application configuration."""

    provider: LLMProvider = LLMProvider.ANTHROPIC
    anthropic_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-4.1"
    ollama_model: str = "gemma4:31b-cloud"
    google_model: str = "gemini-2.5-flash"
    openrouter_model: str = "anthropic/claude-sonnet-4"
    ollama_base_url: str = "http://localhost:11434"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    output_dir: str = "~/clawed_output"
    include_homework: bool = True
    agent_gateway: bool = True
    export_format: str = "docx"
    drive_root_folder: str = ""
    drive_token_path: str = ""

    # Custom agent name — teacher picks during onboarding
    agent_name: str = "Claw-ED"

    # Ollama API key (for cloud Ollama)
    ollama_api_key: Optional[str] = None

    # Telegram bot token (persisted so teachers don't re-enter it every time)
    telegram_bot_token: Optional[str] = None

    # Per-task model overrides (e.g. {"bellringer": "qwen3.5:cloud"})
    task_models: Optional[dict[str, str]] = None

    # Tier model overrides (e.g. {"fast": "qwen3.5:cloud", "deep": "claude-opus-4-6"})
    tier_models: Optional[dict[str, str]] = None

    # Tier → provider routing (e.g. {"fast": "ollama", "deep": "anthropic"})
    # Allows different tiers to use different providers simultaneously
    tier_providers: Optional[dict[str, str]] = None

    # Max agent loop iterations (increase for complex curriculum planning)
    max_agent_iterations: int = 20

    # Web dashboard password (None = no auth, set to enable basic auth)
    dashboard_password: Optional[str] = None

    # Per-image network timeout for the image pipeline (seconds)
    image_fetch_timeout: int = 10

    # Zero-touch auto-chain: generate_lesson_bundle auto-produces everything
    auto_differentiate: bool = True  # Auto-generate IEP/ELL/gifted versions
    auto_game: bool = True  # Auto-generate review game with each lesson
    auto_standards: bool = True  # Auto-lookup and align to state standards
    quality_threshold: float = 3.5  # Warn if voice match score below this

    # Teacher profile — the key to auto-tailoring
    teacher_profile: TeacherProfile = Field(default_factory=TeacherProfile)

    @staticmethod
    def config_path() -> Path:
        import os

        env_dir = os.environ.get("EDUAGENT_DATA_DIR")
        if env_dir:
            return Path(env_dir) / "config.json"
        from clawed.paths import data_dir

        return data_dir() / "config.json"

    # Fields that contain secrets and must never be written to the JSON
    # config file.  They are stored via keyring (preferred) or env vars
    # only.  See clawed/config.py for the secure storage helpers.
    # Note: telegram_bot_token is intentionally NOT in _SECRET_FIELDS.
    # It must be readable by the entry router (stdlib-only, no keyring import)
    # for auto-daemon startup. It's also saved to keyring as a backup.
    _SECRET_FIELDS: tuple[str, ...] = (
        "ollama_api_key",
        "dashboard_password",
    )

    @classmethod
    def load(cls) -> "AppConfig":
        """Load config from disk, or return defaults.

        After loading the JSON config, hydrate secret fields from the
        secure store (keyring > env var).  This ensures API keys are
        never read from the plaintext JSON file.
        """
        path = cls.config_path()
        if path.exists():
            cfg = cls.model_validate_json(path.read_text(encoding="utf-8"))
        else:
            cfg = cls()

        # Honor OLLAMA_URL env var as an alias for ollama_base_url
        import os

        ollama_url_env = os.environ.get("OLLAMA_URL")
        if ollama_url_env:
            cfg.ollama_base_url = ollama_url_env

        # Auto-fix stale Ollama Cloud URLs from earlier versions
        from clawed.config import is_ollama_cloud

        if is_ollama_cloud(cfg.ollama_base_url) and cfg.ollama_base_url != "https://ollama.com":
            cfg.ollama_base_url = "https://ollama.com"
            cfg.save()

        # Hydrate secrets from secure storage
        from clawed.config import get_api_key

        if not cfg.ollama_api_key:
            cfg.ollama_api_key = get_api_key("ollama")
        if not cfg.telegram_bot_token:
            cfg.telegram_bot_token = get_api_key("telegram")
        # Teacher-profile tavily key
        if cfg.teacher_profile and not cfg.teacher_profile.tavily_api_key:
            cfg.teacher_profile.tavily_api_key = get_api_key("tavily")

        return cfg

    def save(self) -> None:
        """Persist config to disk.

        Secret fields (API keys, tokens) are stripped before writing so
        they never end up in the plaintext JSON config file.  Use
        clawed.config.set_api_key() to store secrets securely.
        """
        # Move secrets to the secure store before writing
        from clawed.config import set_api_key

        if self.ollama_api_key:
            set_api_key("ollama", self.ollama_api_key)
        if self.telegram_bot_token:
            set_api_key("telegram", self.telegram_bot_token)
        if self.teacher_profile and self.teacher_profile.tavily_api_key:
            set_api_key("tavily", self.teacher_profile.tavily_api_key)

        # Serialize, stripping secret fields so they are never on disk
        data = self.model_dump()
        for field in self._SECRET_FIELDS:
            data.pop(field, None)
        # Also strip tavily from the nested teacher profile
        tp = data.get("teacher_profile")
        if tp and isinstance(tp, dict):
            tp.pop("tavily_api_key", None)

        import json

        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


class StudentProgress(BaseModel):
    """Per-student progress tracking model."""

    student_name: str = ""
    student_id: str = ""
    class_code: str = ""
    topics_asked: dict[str, int] = Field(default_factory=dict)
    total_questions: int = 0
    last_active: str = ""  # ISO datetime string
    struggle_topics: list[str] = Field(default_factory=list)

    def record_question(self, topic: str) -> None:
        """Record a question about a topic, updating counts and struggle detection."""
        from datetime import datetime, timezone

        self.total_questions += 1
        self.last_active = datetime.now(timezone.utc).isoformat()
        topic_key = topic.strip().lower() if topic else "general"
        self.topics_asked[topic_key] = self.topics_asked.get(topic_key, 0) + 1
        # Mark as struggle topic if asked 3+ times
        if self.topics_asked[topic_key] >= 3 and topic_key not in self.struggle_topics:
            self.struggle_topics.append(topic_key)
