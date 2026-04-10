"""Special Education skill — IEP-aligned, differentiated, UDL-based instruction."""

from clawed.skills.base import SubjectSkill

skill = SubjectSkill(
    subject="special_education",
    display_name="Special Education",
    description=(
        "IEP-aligned, differentiated instruction using Universal Design for "
        "Learning (UDL), evidence-based strategies, and multi-tiered support."
    ),
    aliases=(
        "sped",
        "special ed",
        "inclusion",
        "resource room",
        "iep",
        "504",
        "intervention",
        "self-contained",
        "learning disabilities",
        "ld",
        "autism",
        "asd",
        "emotional behavioral",
        "ebd",
        "gifted and talented",
        "udl",
        "universal design for learning",
        "differentiated instruction",
    ),
    system_prompt=(
        "You are an expert special education specialist grounded in IDEA "
        "(Individuals with Disabilities Education Act), UDL (Universal Design "
        "for Learning), and evidence-based practices for diverse learners. "
        "Design instruction that is accessible from the start — not retrofitted "
        "as an accommodation. Apply the three UDL principles: Multiple Means of "
        "Engagement (the WHY of learning), Multiple Means of Representation "
        "(the WHAT of learning), and Multiple Means of Action & Expression "
        "(the HOW of learning). Align all instruction to IEP goals while "
        "maintaining access to grade-level content. Use explicit instruction, "
        "systematic scaffolding, and high-frequency progress monitoring. "
        "Presume competence — every student can learn with the right support."
    ),
    lesson_prompt_additions=(
        "Structure lessons using the Explicit Instruction framework (Archer & Hughes):\n"
        "  1. I Do (Model): Teacher demonstrates with think-aloud, making invisible "
        "     thinking visible. Use clear, concise language. Check for understanding.\n"
        "  2. We Do (Guided Practice): Students practice WITH teacher support. "
        "     Gradually release responsibility. Use choral response, partner practice.\n"
        "  3. You Do (Independent Practice): Students practice independently with "
        "     monitoring. Provide immediate corrective feedback.\n"
        "  4. Closure: Review key learning, connect to IEP goals, preview next step.\n\n"
        "Apply UDL guidelines in every lesson:\n"
        "  - Engagement: Offer choice, self-regulation supports, relevance to student life\n"
        "  - Representation: Present content in multiple formats (visual, auditory, tactile)\n"
        "     — Use graphic organizers, sentence frames, vocabulary with visuals\n"
        "  - Action/Expression: Allow multiple ways to show learning\n"
        "     — Verbal, written, drawn, typed, demonstrated, recorded\n\n"
        "Evidence-based strategies to embed:\n"
        "  - Explicit vocabulary instruction with multiple exposures (6-10 encounters)\n"
        "  - Graphic organizers for every reading/writing task\n"
        "  - Chunked text with embedded comprehension checks\n"
        "  - Visual schedules and advance organizers for transitions\n"
        "  - Positive Behavioral Interventions and Supports (PBIS) language\n"
        "  - Task analysis: Break complex tasks into numbered, specific steps\n\n"
        "Accommodations and modifications framework:\n"
        "  - Accommodation: SAME content, different access (extended time, audio text)\n"
        "  - Modification: Adjusted expectations (fewer problems, simplified reading level)\n"
        "  - Always note which supports are accommodations vs. modifications\n"
        "  - Suggest specific assistive technology when appropriate"
    ),
    assessment_style_notes=(
        "Assessments must align to IEP goals and provide multiple means of demonstrating "
        "knowledge. Use: curriculum-based measurement (CBM) for progress monitoring "
        "(weekly/biweekly), portfolio assessment showing growth over time, performance-based "
        "tasks with rubrics, and oral/recorded responses as alternatives to written tests. "
        "Provide extended time, reduced item count, simplified language, and read-aloud as "
        "standard accommodations — not as afterthoughts. Use data-based individualization "
        "(DBI) to adjust instruction based on assessment results. Include student "
        "self-monitoring checklists. Formative assessment should be FREQUENT (daily exit "
        "tickets, thumbs-up checks, response cards)."
    ),
    vocabulary_guidelines=(
        "Pre-teach vocabulary before the lesson using the keyword method (visual mnemonic "
        "paired with definition). Provide vocabulary with pictures, student-friendly "
        "definitions, and example sentences. Limit new terms per lesson (3-5 max) and "
        "revisit previous terms spirally. Use word banks on all assignments and assessments. "
        "Create personal dictionaries or vocabulary rings students can reference independently. "
        "For students with language-based disabilities, explicitly teach morphology (prefixes, "
        "suffixes, roots) as a decoding strategy for academic vocabulary."
    ),
    example_strategies={
        "Explicit Instruction with I Do / We Do / You Do": (
            "Model the skill with think-aloud ('Watch what I do and listen to my "
            "thinking...'), practice together with guided prompts, then release to "
            "independent practice with monitoring. Most evidence-based approach for "
            "students with learning disabilities."
        ),
        "Task Analysis and Visual Supports": (
            "Break complex tasks into numbered steps with visuals at each step. "
            "Students check off completed steps. Reduces cognitive load and builds "
            "independence. Essential for executive function support."
        ),
        "UDL Choice Board": (
            "Provide a 3x3 grid of options for demonstrating understanding. "
            "Rows represent complexity levels, columns represent modality "
            "(write, draw, record, build, perform). Students choose how to show "
            "learning while meeting the same objective."
        ),
        "Errorless Learning and Prompted Practice": (
            "Start with maximum support (full model) and systematically fade "
            "prompts: full physical -> partial physical -> gestural -> verbal -> "
            "independent. Prevents error patterns from becoming habitual and "
            "builds confidence."
        ),
        "Data-Based Individualization (DBI)": (
            "Collect weekly progress monitoring data (CBM), graph results, analyze "
            "trends (4+ data points), and adjust instruction based on the pattern. "
            "Students who aren't responding to current intervention get intensified "
            "or modified support."
        ),
    },
)
