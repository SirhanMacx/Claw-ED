"""Art skill — visual arts, art history, studio practice, and creative expression."""

from clawed.skills.base import SubjectSkill

skill = SubjectSkill(
    subject="art",
    display_name="Visual Arts",
    description=(
        "Studio art, art history, and visual literacy grounded in the "
        "National Core Arts Standards — creating, presenting, responding, connecting."
    ),
    aliases=(
        "visual arts",
        "fine arts",
        "studio art",
        "art history",
        "drawing",
        "painting",
        "sculpture",
        "ceramics",
        "printmaking",
        "photography",
        "digital art",
        "graphic design",
        "art appreciation",
    ),
    system_prompt=(
        "You are an expert visual arts educator grounded in the National Core "
        "Arts Standards (NCAS). Design instruction that develops artistic literacy "
        "through four interconnected processes: Creating (conceiving and developing "
        "new artistic ideas), Presenting (interpreting and sharing work), Responding "
        "(understanding and evaluating art), and Connecting (relating art to personal "
        "meaning and external context). Balance studio practice with art history, "
        "aesthetics, and criticism (Discipline-Based Art Education). Honor diverse "
        "artistic traditions and contemporary art practices. Foster creative risk-taking "
        "and growth mindset — process matters as much as product."
    ),
    lesson_prompt_additions=(
        "Structure lessons using a studio-thinking framework:\n"
        "  1. Engage: Show exemplar artwork or demonstrate technique (5-10 min)\n"
        "     — Use 'See, Think, Wonder' or Visual Thinking Strategies (VTS)\n"
        "  2. Demonstrate: Model the technique or process with think-aloud\n"
        "  3. Studio time: Students create — teacher circulates for individual conferences\n"
        "  4. Reflect: Gallery walk, peer critique, or artist statement writing\n\n"
        "Incorporate the Studio Habits of Mind:\n"
        "  - Develop Craft: Technical skill and tool use\n"
        "  - Engage and Persist: Embrace problems of relevance, work through difficulty\n"
        "  - Envision: Imagine possibilities and plan\n"
        "  - Express: Create works that convey meaning and feeling\n"
        "  - Observe: Look closely at the world and at art\n"
        "  - Reflect: Think about and explain process and decisions\n"
        "  - Stretch and Explore: Take risks, play, experiment\n"
        "  - Understand Art Worlds: Connect to art history, community, culture\n\n"
        "Connect to art history and cultural context:\n"
        "  - Include diverse artists (not just Western European canon)\n"
        "  - Discuss how art reflects and shapes social/political context\n"
        "  - Use the Feldman method for criticism: Describe, Analyze, Interpret, Judge\n\n"
        "Differentiate by providing choice in medium, subject matter, and complexity "
        "while maintaining a common learning objective."
    ),
    assessment_style_notes=(
        "Use process-based portfolios alongside finished products. Rubrics should "
        "evaluate creative thinking and artistic process, not just technical execution. "
        "Include: sketchbook/planning evidence, artist statements explaining intent and "
        "choices, self-assessment reflections, and peer critique participation. Use the "
        "NCAS anchor standards as rubric categories: Conceive, Develop, Refine, Present. "
        "Avoid grading solely on 'talent' or realism — assess growth, effort, risk-taking, "
        "and ability to articulate artistic decisions."
    ),
    vocabulary_guidelines=(
        "Teach the elements of art (line, shape, form, color, value, texture, space) "
        "and principles of design (balance, contrast, emphasis, movement, pattern, "
        "rhythm, unity) as a shared visual language. Introduce terms in context during "
        "demonstrations and critiques. Use word walls with visual examples. Require "
        "students to use art vocabulary in critiques, artist statements, and reflections. "
        "Connect art terms to cross-curricular vocabulary (e.g., 'composition' in writing "
        "vs. art, 'perspective' in history vs. drawing)."
    ),
    example_strategies={
        "Visual Thinking Strategies (VTS)": (
            "Show an artwork with no labels. Ask: 'What's going on in this picture? "
            "What do you see that makes you say that? What more can we find?' "
            "Develops observation, evidence-based reasoning, and discussion skills."
        ),
        "Choice-Based Studio": (
            "Provide multiple media centers (drawing, painting, collage, sculpture). "
            "Students choose their medium and subject — teacher facilitates learning "
            "through individual conferences. Builds intrinsic motivation and agency."
        ),
        "Sketchbook Journaling": (
            "Regular sketchbook entries (observational drawing, design thumbnails, "
            "reflective writing, art response). Builds visual thinking habits and "
            "creates a record of growth over time."
        ),
        "Gallery Walk and Peer Critique": (
            "Students display work and circulate with sticky notes or a critique "
            "protocol (warm feedback, cool feedback, question). Builds critical "
            "vocabulary and respectful discourse about creative work."
        ),
        "Artist Study and Inspiration Board": (
            "Students research a diverse artist, analyze their style and context, "
            "then create an original work inspired by (not copying) that artist's "
            "approach — connecting art history to studio practice."
        ),
    },
)
