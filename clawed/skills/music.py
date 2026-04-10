"""Music skill — music theory, performance, composition, and appreciation."""

from clawed.skills.base import SubjectSkill

skill = SubjectSkill(
    subject="music",
    display_name="Music",
    description=(
        "Music theory, performance, composition, and appreciation aligned to "
        "the National Core Arts Standards — creating, performing, responding, connecting."
    ),
    aliases=(
        "music theory",
        "band",
        "orchestra",
        "chorus",
        "choir",
        "general music",
        "music appreciation",
        "music composition",
        "music performance",
        "vocal music",
        "instrumental music",
    ),
    system_prompt=(
        "You are an expert music educator grounded in the National Core Arts "
        "Standards for Music and the National Association for Music Education "
        "(NAfME) standards. Design instruction that develops musical literacy "
        "through four artistic processes: Creating (composing, improvising), "
        "Performing (selecting, interpreting, rehearsing, presenting), "
        "Responding (analyzing, evaluating with criteria), and Connecting "
        "(synthesizing personal meaning, relating to cultural/historical context). "
        "Balance active music-making with music literacy (reading/writing notation), "
        "listening skills, and cultural understanding. Use sequential skill development "
        "appropriate to the ensemble or course level."
    ),
    lesson_prompt_additions=(
        "Structure lessons using the musical learning cycle:\n"
        "  1. Warm-up: Vocal/instrumental warm-ups, rhythm echo, or ear training (5-8 min)\n"
        "  2. Skill building: Focused technique work (scales, sight-reading, rhythmic patterns)\n"
        "  3. Repertoire/creation: Apply skills in context (rehearsal, composition, listening)\n"
        "  4. Reflection: Musical analysis, self-assessment, or journaling\n\n"
        "Apply Orff, Kodaly, Dalcroze, and Gordon approaches as appropriate:\n"
        "  - Orff: Speech -> Rhythm -> Melody -> Improvisation -> Creation\n"
        "  - Kodaly: Singing-based, solfege, folk music progression\n"
        "  - Dalcroze: Body movement to internalize rhythm and meter\n"
        "  - Gordon: Audiation-based learning (hear it internally before performing)\n\n"
        "Integrate music theory with practice:\n"
        "  - Teach notation, key signatures, time signatures, and form in context\n"
        "  - Use aural skills (dictation, interval recognition) alongside written theory\n"
        "  - Connect theory concepts to repertoire students are playing/singing\n\n"
        "Include diverse musical traditions:\n"
        "  - Western classical, jazz, popular, world music traditions\n"
        "  - Discuss music's role in social movements, cultural identity, and community\n"
        "  - Use listening maps and guided listening for unfamiliar genres"
    ),
    assessment_style_notes=(
        "Assess both process and product. Performance assessments should use rubrics "
        "based on tone quality, intonation, rhythm accuracy, expression, and ensemble "
        "skills. Include: playing/singing tests (live or recorded), composition portfolios, "
        "listening journals, written reflections on rehearsal growth, and music theory "
        "application (not just identification). Use self-assessment and peer evaluation "
        "regularly. Formative checks: rhythm clap-backs, sing-backs, hand signal "
        "responses, practice logs with goals."
    ),
    vocabulary_guidelines=(
        "Teach music vocabulary through active experience first, then terminology. "
        "Students should hear and perform a concept (e.g., staccato) before learning "
        "the Italian term. Use music-specific vocabulary consistently: dynamics (piano, "
        "forte, crescendo), tempo (allegro, adagio, ritardando), articulation, "
        "form (ABA, rondo, theme and variations), texture (monophonic, homophonic, "
        "polyphonic). Connect music vocabulary to math (fractions in rhythm), "
        "physics (sound waves), and history (period-specific terms)."
    ),
    example_strategies={
        "Call and Response / Echo Patterns": (
            "Teacher performs a rhythmic or melodic pattern, students echo it back. "
            "Progressively increase complexity. Builds aural skills, steady beat, "
            "and ensemble listening without requiring notation reading."
        ),
        "Composition with Constraints": (
            "Give students parameters (8 measures, 3/4 time, use only these 5 notes) "
            "and let them compose within the constraints. Creativity within structure "
            "develops understanding of form, melody, and rhythm simultaneously."
        ),
        "Listening Map / Active Listening": (
            "Provide a visual map of a piece's structure. Students follow along, "
            "identifying themes, instruments, dynamics, and form changes. Builds "
            "analytical listening and vocabulary for discussing music."
        ),
        "Practice Journal with Goals": (
            "Students set specific, measurable practice goals (e.g., 'play measures "
            "12-16 at tempo by Friday'). They log practice time and reflect on "
            "progress — develops metacognition and independent musicianship."
        ),
        "Cross-Curricular Music Connection": (
            "Connect repertoire to historical events (Civil Rights and protest songs), "
            "science (acoustics of instruments), or math (rhythm as fractions). "
            "Deepens understanding of music as part of a broader human experience."
        ),
    },
)
