"""History skill — historical thinking skills, causation, continuity and change."""

from clawed.skills.base import SubjectSkill

skill = SubjectSkill(
    subject="history",
    display_name="History",
    description=(
        "Historical thinking skills (sourcing, contextualization, corroboration), "
        "causation/continuity/change analysis, periodization."
    ),
    aliases=(
        "us history",
        "world history",
        "american history",
        "european history",
        "ap history",
        "ap us history",
        "apush",
    ),
    system_prompt=(
        "You are an expert history educator. Teach students to think historically, not "
        "just memorize facts. Emphasize the discipline's core skills: sourcing, "
        "contextualization, corroboration, and close reading of primary sources. History "
        "instruction should develop students' ability to construct evidence-based "
        "historical arguments and understand that history is an ongoing, interpretive "
        "conversation — not a fixed set of facts."
    ),
    lesson_prompt_additions=(
        "Anchor every lesson in historical thinking skills:\n\n"
        "1. Sourcing: Before reading a document, ask:\n"
        "   - Who wrote this? When? Why?\n"
        "   - What is their perspective or bias?\n"
        "   - Is this a reliable source for this question?\n\n"
        "2. Contextualization: Place events/sources in historical context:\n"
        "   - What else was happening at this time and place?\n"
        "   - How does the broader context shape this event/source?\n\n"
        "3. Corroboration: Compare multiple sources:\n"
        "   - Do these sources agree or disagree?\n"
        "   - Where do accounts conflict, and why?\n"
        "   - What might be missing from the historical record?\n\n"
        "4. Close Reading: Read for subtext and argument:\n"
        "   - What is the author's central argument?\n"
        "   - What language choices reveal the author's perspective?\n\n"
        "Use the Causation-Continuity-Change framework for analysis:\n"
        "   - Causation: What caused this event? (short-term triggers vs. long-term factors)\n"
        "   - Continuity: What stayed the same across this period?\n"
        "   - Change: What transformed, and for whom?\n"
        "   - Periodization: Why do historians mark this as a turning point?\n\n"
        "Structure debates and discussions around historical questions, not statements. "
        "Use 'To what extent...?' and 'How significant was...?' question stems."
    ),
    assessment_style_notes=(
        "Assessments should require historical thinking, not just recall. Use document-based "
        "questions (DBQs) with 4-7 primary sources. Long essay questions should ask students "
        "to develop a thesis, use specific historical evidence, and demonstrate causation or "
        "continuity/change analysis. Short answer questions should require source analysis "
        "(sourcing, purpose, audience, context). Use historical role-play debates and "
        "mock trials as formative/performance assessments. Rubrics should evaluate: thesis "
        "strength, evidence specificity, historical reasoning (causation, comparison, "
        "continuity/change), and sophistication of argument."
    ),
    vocabulary_guidelines=(
        "Teach historical thinking vocabulary explicitly: primary source, secondary source, "
        "bias, perspective, causation, correlation, continuity, change over time, turning "
        "point, periodization, historiography, thesis, evidence. Also teach era-specific "
        "vocabulary in context (e.g., 'mercantilism', 'suffrage', 'imperialism'). "
        "Distinguish between historical and modern meanings of words (e.g., 'liberal', "
        "'conservative', 'republic'). Use timeline vocabulary: antebellum, postwar, "
        "interwar, contemporary."
    ),
    example_strategies={
        "Historical Thinking Skills (Stanford History Education Group)": (
            "Sourcing → Contextualization → Close Reading → Corroboration. "
            "Students practice each skill with structured graphic organizers "
            "before combining them in full document analysis."
        ),
        "Causation-Continuity-Change Analysis": (
            "For any historical event or period, students identify and categorize "
            "causes (short/long-term), elements of continuity (what persisted), "
            "and changes (what transformed). Builds analytical thinking."
        ),
        "Document-Based Question (DBQ)": (
            "Students analyze 4-7 primary sources, develop a thesis, and write "
            "an evidence-based essay. Teaches synthesis across sources, argument "
            "construction, and historical reasoning."
        ),
        "Historical Role-Play / Mock Trial": (
            "Students research and argue from the perspective of historical "
            "figures or factions. Builds empathy, perspective-taking, and deep "
            "content knowledge through embodied learning."
        ),
        "Timeline / Periodization Activity": (
            "Students create annotated timelines and debate where to draw period "
            "boundaries. Develops chronological thinking and the understanding "
            "that periodization is an interpretive choice."
        ),
    },
)
