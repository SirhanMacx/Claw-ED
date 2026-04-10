"""Social Studies skill — DBQs, primary sources, MAIN acronym, Socratic questioning."""

from clawed.skills.base import SubjectSkill

skill = SubjectSkill(
    subject="social_studies",
    display_name="Social Studies",
    description=(
        "DBQ analysis, primary source interpretation, MAIN acronym for causation, Socratic questioning techniques."
    ),
    aliases=("social studies", "civics", "government", "geography", "economics"),
    system_prompt=(
        "You are an expert social studies educator. Ground all instruction in primary and "
        "secondary source analysis. Emphasize disciplinary literacy: students should read, "
        "write, and think like social scientists. Use the C3 Framework (College, Career, and "
        "Civic Life) to structure inquiry. Every lesson should connect content to civic "
        "engagement and real-world decision-making."
    ),
    lesson_prompt_additions=(
        "Structure lessons around compelling and supporting questions (C3 Inquiry Arc). "
        "Include at least one primary source or document excerpt per lesson. Use the "
        "Document-Based Question (DBQ) format for extended analysis tasks:\n"
        "  1. Contextualize the source (author, audience, purpose, historical context)\n"
        "  2. Close-read for claims, evidence, and perspective\n"
        "  3. Corroborate across multiple sources\n"
        "  4. Construct an evidence-based argument\n\n"
        "Use the MAIN acronym (Militarism, Alliances, Imperialism, Nationalism) as a "
        "model for multi-causal analysis frameworks. Adapt similar acronym-based scaffolds "
        "for other topics (e.g., PERSIA for civilizations: Political, Economic, Religious, "
        "Social, Intellectual, Artistic).\n\n"
        "Embed Socratic questioning throughout:\n"
        "  - Clarifying: 'What do you mean by...?'\n"
        "  - Probing assumptions: 'What are we assuming here?'\n"
        "  - Evidence: 'What evidence supports that?'\n"
        "  - Perspective: 'How might someone else see this?'\n"
        "  - Consequence: 'What would happen if...?'\n"
        "  - Meta: 'Why is this question important?'"
    ),
    assessment_style_notes=(
        "Favor document-based assessments over recall-heavy tests. Assessments should "
        "require students to analyze sources, construct arguments with evidence, and "
        "evaluate multiple perspectives. Use structured academic controversy (SAC) and "
        "Socratic seminars as formative assessments. Summative assessments should include "
        "a DBQ essay or civic action project. Rubrics should evaluate: thesis quality, "
        "use of evidence, sourcing skills, and argumentation logic."
    ),
    vocabulary_guidelines=(
        "Explicitly teach disciplinary vocabulary: primary source, secondary source, bias, "
        "perspective, corroboration, contextualization, causation, continuity, change over "
        "time, turning point, civic engagement. Use word walls and vocabulary notebooks. "
        "Front-load key terms before source analysis. Provide glossaries for primary "
        "source documents with archaic or domain-specific language."
    ),
    example_strategies={
        "DBQ Analysis": (
            "Present 3-5 documents on a topic. Students HIPP each source "
            "(Historical context, Intended audience, Purpose, Point of view), "
            "then write an evidence-based essay with a clear thesis."
        ),
        "Socratic Seminar": (
            "Students prepare by annotating a text, then engage in structured "
            "dialogue. Inner circle discusses; outer circle takes notes and "
            "evaluates the quality of evidence and reasoning."
        ),
        "MAIN Acronym Framework": (
            "For multi-causal analysis, students categorize causes using an "
            "acronym scaffold (MAIN, PERSIA, SPRITE, etc.) to ensure they "
            "consider multiple dimensions of causation."
        ),
        "Structured Academic Controversy": (
            "Pairs research both sides of a historical debate, present "
            "arguments, switch sides, then reach consensus — builds "
            "perspective-taking and evidence evaluation skills."
        ),
        "Gallery Walk": (
            "Station-based activity where students rotate through primary "
            "source stations, analyzing documents and recording observations "
            "on graphic organizers."
        ),
    },
)
