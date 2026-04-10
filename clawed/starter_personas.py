"""Built-in starter personas for teachers who haven't ingested materials yet.

Teachers can use these to generate lessons immediately, then refine
their persona later with clawed ingest.
"""

from __future__ import annotations

from clawed.models import (
    AssessmentStyle,
    TeacherPersona,
    TeachingStyle,
    VocabularyLevel,
)

STARTER_PERSONAS: dict[str, TeacherPersona] = {
    "social_studies": TeacherPersona(
        name="Teacher",
        teaching_style=TeachingStyle.INQUIRY_BASED,
        vocabulary_level=VocabularyLevel.GRADE_APPROPRIATE,
        tone="warm and encouraging",
        assessment_style=AssessmentStyle.RUBRIC_BASED,
        structural_preferences=[
            "Do Now",
            "direct instruction",
            "guided practice",
            "exit ticket",
        ],
        preferred_lesson_format="I Do / We Do / You Do",
        favorite_strategies=[
            "primary source analysis",
            "Socratic questioning",
            "think-pair-share",
        ],
        subject_area="Social Studies",
        grade_levels=["8"],
        source_types=["primary documents", "maps", "political cartoons"],
        activity_patterns=[
            "document analysis",
            "DBQ practice",
            "timeline construction",
        ],
        scaffolding_moves=[
            "sentence starters",
            "graphic organizers",
            "word banks",
        ],
        do_now_style="stimulus-based warm up",
        exit_ticket_style="short written response",
        signature_moves=["connecting past to present"],
    ),
    "science": TeacherPersona(
        name="Teacher",
        teaching_style=TeachingStyle.INQUIRY_BASED,
        vocabulary_level=VocabularyLevel.ACADEMIC,
        tone="curious and supportive",
        assessment_style=AssessmentStyle.RUBRIC_BASED,
        structural_preferences=[
            "bell ringer",
            "guided inquiry",
            "lab activity",
            "reflection",
        ],
        preferred_lesson_format="5E Model (Engage, Explore, Explain, Elaborate, Evaluate)",
        favorite_strategies=[
            "hands-on experiments",
            "claim-evidence-reasoning",
            "modeling",
        ],
        subject_area="Science",
        grade_levels=["8"],
        source_types=["data tables", "diagrams", "lab procedures"],
        activity_patterns=[
            "lab investigations",
            "data analysis",
            "scientific argumentation",
        ],
        scaffolding_moves=[
            "vocabulary cards",
            "CER framework",
            "visual models",
        ],
        do_now_style="phenomenon observation",
        exit_ticket_style="CER paragraph",
        signature_moves=["real-world connections"],
    ),
    "math": TeacherPersona(
        name="Teacher",
        teaching_style=TeachingStyle.DIRECT_INSTRUCTION,
        vocabulary_level=VocabularyLevel.GRADE_APPROPRIATE,
        tone="patient and methodical",
        assessment_style=AssessmentStyle.POINT_BASED,
        structural_preferences=[
            "warm up problem",
            "mini lesson",
            "guided practice",
            "independent work",
        ],
        preferred_lesson_format="Gradual Release",
        favorite_strategies=[
            "number talks",
            "worked examples",
            "error analysis",
        ],
        subject_area="Math",
        grade_levels=["8"],
        source_types=["word problems", "graphs", "equations"],
        activity_patterns=[
            "problem sets",
            "collaborative problem solving",
            "math journaling",
        ],
        scaffolding_moves=[
            "step-by-step guides",
            "manipulatives",
            "anchor charts",
        ],
        do_now_style="review problem from yesterday",
        exit_ticket_style="3 quick problems",
        signature_moves=["multiple solution methods"],
    ),
    "ela": TeacherPersona(
        name="Teacher",
        teaching_style=TeachingStyle.BLENDED,
        vocabulary_level=VocabularyLevel.GRADE_APPROPRIATE,
        tone="enthusiastic and literary",
        assessment_style=AssessmentStyle.RUBRIC_BASED,
        structural_preferences=[
            "journal writing",
            "close reading",
            "discussion",
            "writing workshop",
        ],
        preferred_lesson_format="Workshop Model",
        favorite_strategies=[
            "close reading",
            "annotation",
            "peer editing",
            "Socratic seminar",
        ],
        subject_area="ELA",
        grade_levels=["8"],
        source_types=["novels", "poetry", "nonfiction articles"],
        activity_patterns=[
            "annotated reading",
            "literary analysis",
            "creative writing",
        ],
        scaffolding_moves=[
            "sentence frames",
            "graphic organizers",
            "mentor texts",
        ],
        do_now_style="quick write prompt",
        exit_ticket_style="reflection on today's reading",
        signature_moves=["connecting texts to student lives"],
    ),
}


_SUBJECT_ALIASES: dict[str, str] = {
    # ELA
    "english": "ela",
    "language arts": "ela",
    "english language arts": "ela",
    "reading": "ela",
    "writing": "ela",
    "literature": "ela",
    # Science
    "biology": "science",
    "chemistry": "science",
    "physics": "science",
    "earth science": "science",
    "environmental science": "science",
    "life science": "science",
    "physical science": "science",
    # Social Studies
    "history": "social_studies",
    "geography": "social_studies",
    "civics": "social_studies",
    "government": "social_studies",
    "economics": "social_studies",
    "global studies": "social_studies",
    "world history": "social_studies",
    "us history": "social_studies",
    "american history": "social_studies",
    # Math
    "algebra": "math",
    "geometry": "math",
    "calculus": "math",
    "statistics": "math",
    "pre-algebra": "math",
    "mathematics": "math",
}


def get_starter_persona(subject: str) -> TeacherPersona | None:
    """Get a starter persona for a subject, or None if not available."""
    subject_lower = subject.strip().lower()

    # Direct key match
    if subject_lower in STARTER_PERSONAS:
        return STARTER_PERSONAS[subject_lower]

    # Alias match
    if subject_lower in _SUBJECT_ALIASES:
        return STARTER_PERSONAS[_SUBJECT_ALIASES[subject_lower]]

    # Substring match against keys and subject_area
    for key, persona in STARTER_PERSONAS.items():
        if key in subject_lower or subject_lower in key:
            return persona
        if persona.subject_area.lower() in subject_lower or subject_lower in persona.subject_area.lower():
            return persona

    # Default fallback
    return STARTER_PERSONAS.get("social_studies")


def list_starter_subjects() -> list[str]:
    """List available starter persona subjects."""
    return [p.subject_area for p in STARTER_PERSONAS.values()]
