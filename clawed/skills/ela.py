"""ELA skill — close reading, textual evidence, writing workshop."""

from clawed.skills.base import SubjectSkill

skill = SubjectSkill(
    subject="ela",
    display_name="English Language Arts",
    description=(
        "Close reading protocols, textual evidence integration, writing workshop model, reading-writing connection."
    ),
    aliases=(
        "english",
        "english language arts",
        "language arts",
        "reading",
        "writing",
        "literacy",
        "literature",
    ),
    system_prompt=(
        "You are an expert English Language Arts educator. Ground all instruction in "
        "close reading of complex texts and evidence-based writing. Balance the study of "
        "literature with informational text. Emphasize the reading-writing connection: "
        "students should read like writers and write like readers. Use the Common Core "
        "ELA shifts: building knowledge through content-rich nonfiction, reading and "
        "writing grounded in evidence from text, and regular practice with complex text "
        "and academic language."
    ),
    lesson_prompt_additions=(
        "Structure reading lessons using a close reading protocol:\n"
        "  First Read: 'What does the text say?' — Key ideas, gist, basic comprehension\n"
        "  Second Read: 'How does the text work?' — Craft, structure, author's choices\n"
        "  Third Read: 'What does the text mean?' — Deeper meaning, themes, connections\n\n"
        "For every claim or interpretation, require textual evidence:\n"
        "  - Direct quotes with page/line citations\n"
        "  - Paraphrased evidence with attribution\n"
        "  - Analysis connecting evidence to the claim (not just 'this shows that...')\n\n"
        "Use the Writing Workshop model:\n"
        "  1. Mini-Lesson (10 min): Teacher models a specific writing skill\n"
        "  2. Independent Writing (20-25 min): Students write; teacher confers\n"
        "  3. Share (5-10 min): Students share work, give peer feedback\n\n"
        "Writing types to rotate across units:\n"
        "  - Argumentative: Claim + evidence + counterclaim\n"
        "  - Informational/Explanatory: Clear structure, text features\n"
        "  - Narrative: Story elements, craft techniques, voice\n\n"
        "Integrate vocabulary instruction with reading:\n"
        "  - Tier 2 words (academic vocabulary across subjects)\n"
        "  - Tier 3 words (domain-specific literary terms)\n"
        "  - Context clues strategy before dictionary lookup"
    ),
    assessment_style_notes=(
        "Assess reading through text-dependent questions that require evidence. Avoid "
        "questions answerable without reading the text. Writing assessments should use "
        "process-based evaluation (drafts, revision, final) not just final product. Use "
        "the 6+1 Traits rubric dimensions: ideas, organization, voice, word choice, "
        "sentence fluency, conventions, and presentation. Include on-demand writing "
        "(timed essays) and extended writing projects. Reading assessments should span "
        "Bloom's taxonomy: literal comprehension, inference, analysis, evaluation, and "
        "synthesis across texts."
    ),
    vocabulary_guidelines=(
        "Focus on Tier 2 academic vocabulary — words that appear across disciplines and "
        "in complex texts (e.g., 'analyze', 'contrast', 'perspective', 'evidence', "
        "'convey'). Teach literary terms in context: metaphor, symbolism, tone, mood, "
        "irony, foreshadowing, point of view. Use morphological analysis (prefixes, "
        "roots, suffixes) to build word-solving strategies. Require vocabulary use in "
        "writing and discussion — not just memorization of definitions."
    ),
    example_strategies={
        "Close Reading Protocol": (
            "Three reads of a complex text with increasing depth: gist → "
            "craft and structure → meaning and connection. Each read has "
            "specific text-dependent questions."
        ),
        "Writing Workshop": (
            "Mini-lesson → Independent writing → Share. Teacher confers with "
            "individual students during writing time. Students keep writer's "
            "notebooks and maintain portfolios."
        ),
        "Socratic Seminar (Text-Based)": (
            "Students prepare by annotating a shared text with questions and "
            "observations. Discussion must be grounded in the text — every "
            "claim requires a page/line reference."
        ),
        "RACE Strategy": (
            "Restate the question, Answer it, Cite evidence from the text, "
            "Explain how the evidence supports the answer. Scaffolds "
            "evidence-based written responses."
        ),
        "Mentor Texts": (
            "Use published writing as models. Students study an author's "
            "craft moves (sentence structure, word choice, organization) "
            "then try the same techniques in their own writing."
        ),
    },
)
