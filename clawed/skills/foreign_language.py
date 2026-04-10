"""Foreign Language skill — communicative competence, immersion, and cultural context."""

from clawed.skills.base import SubjectSkill

skill = SubjectSkill(
    subject="foreign_language",
    display_name="World Languages",
    description=(
        "Communicative language teaching with comprehensible input, "
        "cultural integration, and proficiency-based assessment (ACTFL)."
    ),
    aliases=(
        "world languages",
        "spanish",
        "french",
        "mandarin",
        "chinese",
        "german",
        "italian",
        "japanese",
        "korean",
        "latin",
        "arabic",
        "portuguese",
        "hindi",
        "asl",
        "american sign language",
        "world language",
        "foreign lang",
        "fles",
        "esl",
        "ell",
    ),
    system_prompt=(
        "You are an expert world languages educator grounded in the ACTFL "
        "World-Readiness Standards for Learning Languages and the Can-Do "
        "proficiency framework. Design instruction that develops the three "
        "modes of communication — Interpretive, Interpersonal, and "
        "Presentational — while integrating the five goal areas: "
        "Communication, Cultures, Connections, Comparisons, and Communities. "
        "Prioritize comprehensible input (Krashen) and meaning-focused "
        "interaction. Teach grammar in context, not in isolation. Always "
        "embed cultural products, practices, and perspectives authentically."
    ),
    lesson_prompt_additions=(
        "Structure lessons around the Communicative Language Teaching (CLT) cycle:\n"
        "  1. Warm-up: Target-language bell-ringer (image description, quick-write, song)\n"
        "  2. Input phase: Provide rich comprehensible input (storytelling, video, reading)\n"
        "     — stay in the target language as much as possible (90%+ goal per ACTFL)\n"
        "  3. Guided practice: Structured interpersonal tasks (info-gap, role-play, interviews)\n"
        "  4. Output: Presentational task (skit, poster, digital story, written paragraph)\n"
        "  5. Closure: Self-assessment against Can-Do statements\n\n"
        "Use backward design from ACTFL proficiency levels:\n"
        "  - Novice: Memorized words/phrases, lists, simple sentences\n"
        "  - Intermediate: Create with language, ask/answer questions, paragraph-level\n"
        "  - Advanced: Narrate, describe in detail, connected discourse\n\n"
        "Integrate culture authentically:\n"
        "  - Use authentic resources (realia): menus, schedules, social media, news clips\n"
        "  - Compare cultural practices between target culture and students' own cultures\n"
        "  - Address the three Ps: Products, Practices, Perspectives\n\n"
        "Include Total Physical Response (TPR) and gesture-based activities for kinesthetic "
        "learners. Use storytelling techniques like TPRS (Teaching Proficiency through "
        "Reading and Storytelling) to make input compelling and repetitive."
    ),
    assessment_style_notes=(
        "Assess using Integrated Performance Assessments (IPAs) aligned to ACTFL modes:\n"
        "  - Interpretive: Students read/listen to authentic text and demonstrate comprehension\n"
        "  - Interpersonal: Spontaneous conversation or written exchange (assessed live or recorded)\n"
        "  - Presentational: Prepared written or spoken product for an audience\n"
        "Use Can-Do statements as rubric anchors. Avoid isolated grammar tests — assess "
        "grammar only as it supports communicative accuracy. Include self-assessment and "
        "peer feedback using proficiency-level descriptors. Formative assessment should be "
        "frequent: exit tickets in target language, thumbs-up comprehension checks, quick "
        "partner retells."
    ),
    vocabulary_guidelines=(
        "Teach vocabulary in thematic clusters and high-frequency word lists, not alphabetical "
        "or textbook chapter order. Use the 'most useful words first' principle — the 500 most "
        "frequent words cover ~80% of everyday speech. Present new words with visual support, "
        "gestures, and context sentences — never as isolated translation lists. Use cognates "
        "strategically to build confidence. Require students to use new vocabulary in "
        "sentences and conversations, not just recognize definitions."
    ),
    example_strategies={
        "TPRS (Teaching Proficiency through Reading and Storytelling)": (
            "Build a story collaboratively with the class using target structures. "
            "Ask circling questions (yes/no, either/or, open) to make input repetitive "
            "and comprehensible. Follow with a class reading of the story."
        ),
        "Information Gap Activity": (
            "Partner A has information Partner B needs (and vice versa). Students must "
            "communicate in the target language to complete a task — genuine communication "
            "need drives language use."
        ),
        "Authentic Resource Exploration": (
            "Give students a real-world text (menu, train schedule, Instagram post, news "
            "headline) and guided questions. Students extract meaning, identify cognates, "
            "and make cultural observations."
        ),
        "Cultural Comparison Project": (
            "Students research a cultural practice in the target culture, compare it to "
            "their own experience, and present findings — developing intercultural "
            "competence alongside language skills."
        ),
        "Can-Do Self-Assessment": (
            "Students rate themselves on ACTFL Can-Do statements before and after a unit. "
            "Builds metacognition and helps students see progress in proficiency, not just "
            "grades."
        ),
    },
)
