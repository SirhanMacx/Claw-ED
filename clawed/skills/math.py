"""Math skill — worked examples, scaffolded problems, multiple representations."""

from clawed.skills.base import SubjectSkill

skill = SubjectSkill(
    subject="math",
    display_name="Mathematics",
    description=(
        "Worked examples with faded scaffolding, multiple representations "
        "(concrete-representational-abstract), problem-based learning."
    ),
    aliases=(
        "mathematics",
        "algebra",
        "geometry",
        "calculus",
        "statistics",
        "pre-algebra",
        "pre-calculus",
        "trigonometry",
    ),
    system_prompt=(
        "You are an expert mathematics educator. Prioritize conceptual understanding "
        "alongside procedural fluency. Use the Concrete-Representational-Abstract (CRA) "
        "progression to build understanding. Emphasize the Standards for Mathematical "
        "Practice (SMP): make sense of problems, reason abstractly, construct arguments, "
        "model with mathematics, use tools strategically, attend to precision, look for "
        "structure, and express regularity in repeated reasoning."
    ),
    lesson_prompt_additions=(
        "Structure lessons using the Launch-Explore-Summarize format:\n"
        "  1. Launch: Pose a rich problem or real-world context (low floor, high ceiling)\n"
        "  2. Explore: Students work on the problem, teacher circulates and asks probing questions\n"
        "  3. Summarize: Select and sequence student strategies for class discussion\n\n"
        "Use worked examples with faded scaffolding:\n"
        "  - Step 1: Full worked example with annotations explaining each step\n"
        "  - Step 2: Partially completed example (student fills in key steps)\n"
        "  - Step 3: Student solves independently with structure cues\n"
        "  - Step 4: Open practice with no scaffolding\n\n"
        "Present every concept through multiple representations:\n"
        "  - Concrete: Manipulatives, physical models, real objects\n"
        "  - Visual: Number lines, area models, graphs, tables, diagrams\n"
        "  - Symbolic: Equations, expressions, formal notation\n"
        "  - Verbal: Written and spoken explanations in student language\n"
        "  - Contextual: Real-world applications and word problems\n\n"
        "Include 'number talks' or 'math talks' as warm-ups to build number sense "
        "and mental math fluency."
    ),
    assessment_style_notes=(
        "Assessments should balance procedural items with conceptual and application "
        "problems. Include 'explain your reasoning' prompts — correct answers without "
        "reasoning are incomplete. Use error analysis tasks where students identify and "
        "fix mistakes in sample work. Include multiple-representation problems (e.g., "
        "'draw a model AND write an equation'). Rubrics should evaluate: mathematical "
        "accuracy, strategy selection, representation use, and clarity of explanation."
    ),
    vocabulary_guidelines=(
        "Teach math vocabulary explicitly — do not assume students know terms like "
        "'coefficient', 'variable', 'expression' vs 'equation'. Use the Frayer Model "
        "(definition, characteristics, examples, non-examples) for key terms. Distinguish "
        "between everyday and mathematical meanings (e.g., 'difference', 'product', "
        "'table', 'volume'). Require students to use precise mathematical language in "
        "explanations and discussions."
    ),
    example_strategies={
        "Worked Example with Faded Scaffolding": (
            "Present a fully solved problem with annotations, then give "
            "progressively less-complete versions for students to finish. "
            "Reduces cognitive load while building independence."
        ),
        "Number Talks": (
            "Display a computation (no paper/pencil). Students solve mentally, "
            "share strategies. Teacher records strategies visually. Builds "
            "number sense, flexibility, and mathematical discourse."
        ),
        "Three-Act Math Tasks": (
            "Act 1: Show an image/video that provokes a question. "
            "Act 2: Students identify what info they need, estimate, then solve. "
            "Act 3: Reveal the answer and discuss."
        ),
        "Concrete-Representational-Abstract (CRA)": (
            "Introduce concepts with hands-on manipulatives (base-10 blocks, "
            "algebra tiles), then move to visual representations, then to "
            "symbolic/abstract notation."
        ),
        "Error Analysis": (
            "Present a worked problem with a deliberate error. Students must "
            "find the mistake, explain why it's wrong, and correct it — builds "
            "deeper procedural and conceptual understanding."
        ),
    },
)
