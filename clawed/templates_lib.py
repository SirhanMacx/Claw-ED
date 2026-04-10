"""Lesson Template System — structured lesson formats beyond 'I Do / We Do / You Do'."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LessonTemplate(BaseModel):
    """A lesson structure template with timing and section definitions."""

    name: str
    slug: str
    description: str
    sections: list[TemplateSection] = Field(default_factory=list)
    student_activities: list[str] = Field(default_factory=list)
    best_for: str = ""


class TemplateSection(BaseModel):
    """A single section within a lesson template."""

    name: str
    duration_minutes: int
    description: str
    teacher_role: str = ""
    student_role: str = ""


# Fix forward reference
LessonTemplate.model_rebuild()

# ── Built-in templates ───────────────────────────────────────────────────

TEMPLATES: dict[str, LessonTemplate] = {}


def _register(t: LessonTemplate) -> None:
    TEMPLATES[t.slug] = t


_register(
    LessonTemplate(
        name="I Do / We Do / You Do",
        slug="i-do-we-do-you-do",
        description=(
            "Traditional gradual release of responsibility model. Teacher models, "
            "class practices together, students work independently."
        ),
        sections=[
            TemplateSection(
                name="Do-Now",
                duration_minutes=5,
                description="Warm-up activity connecting to prior knowledge",
                teacher_role="Monitor",
                student_role="Individual work",
            ),
            TemplateSection(
                name="I Do (Direct Instruction)",
                duration_minutes=15,
                description="Teacher models the skill or concept explicitly",
                teacher_role="Model and explain",
                student_role="Active listening, note-taking",
            ),
            TemplateSection(
                name="We Do (Guided Practice)",
                duration_minutes=15,
                description="Teacher and students work through examples together",
                teacher_role="Guide and check",
                student_role="Participate with support",
            ),
            TemplateSection(
                name="You Do (Independent Practice)",
                duration_minutes=10,
                description="Students practice the skill independently",
                teacher_role="Circulate and support",
                student_role="Independent work",
            ),
            TemplateSection(
                name="Exit Ticket",
                duration_minutes=5,
                description="Quick assessment of understanding",
                teacher_role="Collect and review",
                student_role="Demonstrate learning",
            ),
        ],
        student_activities=["Note-taking", "Guided examples", "Independent practice", "Self-assessment"],
        best_for="Introducing new skills or procedures, math algorithms, writing mechanics",
    )
)

_register(
    LessonTemplate(
        name="Socratic Seminar",
        slug="socratic-seminar",
        description="Student-led discussion driven by open-ended questions. Teacher facilitates rather than lectures.",
        sections=[
            TemplateSection(
                name="Preparation",
                duration_minutes=5,
                description="Review text/material and prepare discussion notes",
                teacher_role="Set expectations",
                student_role="Review and annotate",
            ),
            TemplateSection(
                name="Opening Question",
                duration_minutes=5,
                description="Teacher poses the essential question to spark discussion",
                teacher_role="Pose question, then step back",
                student_role="Initial response",
            ),
            TemplateSection(
                name="Inner Circle Discussion",
                duration_minutes=20,
                description="Students discuss while teacher facilitates minimally",
                teacher_role="Facilitate, redirect, probe",
                student_role="Discuss, cite evidence, build on peers",
            ),
            TemplateSection(
                name="Outer Circle Observation",
                duration_minutes=0,
                description="Optional: outer circle takes notes on discussion quality",
                teacher_role="Monitor outer circle",
                student_role="Observe and note key points",
            ),
            TemplateSection(
                name="Debrief",
                duration_minutes=10,
                description="Reflect on the discussion and key takeaways",
                teacher_role="Guide reflection",
                student_role="Share insights, self-assess",
            ),
            TemplateSection(
                name="Exit Ticket",
                duration_minutes=5,
                description="Written response to the essential question",
                teacher_role="Collect",
                student_role="Write reflective response",
            ),
        ],
        student_activities=[
            "Close reading",
            "Discussion",
            "Active listening",
            "Evidence-based argumentation",
            "Self-reflection",
        ],
        best_for="Analyzing texts, exploring complex questions, developing critical thinking and communication skills",
    )
)

_register(
    LessonTemplate(
        name="Jigsaw",
        slug="jigsaw",
        description="Cooperative learning where students become experts on subtopics, then teach their peers.",
        sections=[
            TemplateSection(
                name="Introduction",
                duration_minutes=5,
                description="Explain the jigsaw process and assign expert groups",
                teacher_role="Organize groups",
                student_role="Understand roles",
            ),
            TemplateSection(
                name="Expert Groups",
                duration_minutes=15,
                description="Students in expert groups study their assigned subtopic in depth",
                teacher_role="Circulate, provide resources",
                student_role="Read, discuss, become expert",
            ),
            TemplateSection(
                name="Jigsaw Groups",
                duration_minutes=15,
                description="Experts return to mixed groups and teach their subtopic",
                teacher_role="Monitor teaching quality",
                student_role="Teach peers, take notes",
            ),
            TemplateSection(
                name="Whole-Class Synthesis",
                duration_minutes=5,
                description="Class comes together to connect all subtopics",
                teacher_role="Facilitate connections",
                student_role="Share key takeaways",
            ),
            TemplateSection(
                name="Exit Ticket",
                duration_minutes=5,
                description="Individual assessment covering all subtopics",
                teacher_role="Assess understanding",
                student_role="Demonstrate learning from all groups",
            ),
        ],
        student_activities=["Expert reading", "Group discussion", "Peer teaching", "Note-taking", "Synthesis"],
        best_for="Content-heavy topics with natural subtopics, building collaboration and communication skills",
    )
)

_register(
    LessonTemplate(
        name="Think-Pair-Share",
        slug="think-pair-share",
        description=(
            "Students think individually, discuss with a partner, then share with the class. Builds confidence before"
            "whole-group discussion."
        ),
        sections=[
            TemplateSection(
                name="Do-Now / Hook",
                duration_minutes=5,
                description="Engaging question or scenario to activate thinking",
                teacher_role="Present the prompt",
                student_role="Engage with prompt",
            ),
            TemplateSection(
                name="Mini-Lesson",
                duration_minutes=10,
                description="Brief direct instruction on the key concept",
                teacher_role="Teach core concept",
                student_role="Active listening",
            ),
            TemplateSection(
                name="Think",
                duration_minutes=5,
                description="Students think independently about the question",
                teacher_role="Pose question, wait",
                student_role="Silent individual thinking, jot notes",
            ),
            TemplateSection(
                name="Pair",
                duration_minutes=8,
                description="Students discuss their thinking with a partner",
                teacher_role="Circulate, listen",
                student_role="Share ideas, compare thinking",
            ),
            TemplateSection(
                name="Share",
                duration_minutes=12,
                description="Pairs share key ideas with the whole class",
                teacher_role="Facilitate, record ideas",
                student_role="Present, listen, respond",
            ),
            TemplateSection(
                name="Exit Ticket",
                duration_minutes=5,
                description="Individual written response",
                teacher_role="Collect",
                student_role="Write response",
            ),
        ],
        student_activities=["Individual reflection", "Partner discussion", "Whole-class sharing", "Written response"],
        best_for="Engaging quieter students, building discussion skills, formative assessment of understanding",
    )
)

_register(
    LessonTemplate(
        name="Project-Based Learning",
        slug="project-based",
        description=(
            "Students work on an extended project that addresses a real-world problem."
            " Single-day session focuses on one phase."
        ),
        sections=[
            TemplateSection(
                name="Project Check-In",
                duration_minutes=5,
                description="Review progress, goals for today, address blockers",
                teacher_role="Facilitate check-in",
                student_role="Report status",
            ),
            TemplateSection(
                name="Mini-Lesson / Skill Build",
                duration_minutes=10,
                description="Targeted instruction on a skill needed for the project",
                teacher_role="Direct instruction",
                student_role="Learn applicable skill",
            ),
            TemplateSection(
                name="Work Time",
                duration_minutes=25,
                description="Students work on their projects individually or in teams",
                teacher_role="Consult, coach, redirect",
                student_role="Create, research, build",
            ),
            TemplateSection(
                name="Gallery Walk / Share-Out",
                duration_minutes=5,
                description="Brief sharing of progress or discoveries",
                teacher_role="Facilitate sharing",
                student_role="Present work, give feedback",
            ),
            TemplateSection(
                name="Reflection",
                duration_minutes=5,
                description="Students reflect on progress and next steps",
                teacher_role="Guide reflection",
                student_role="Write reflection, plan next steps",
            ),
        ],
        student_activities=["Research", "Creation", "Collaboration", "Presentation", "Self-reflection"],
        best_for="Interdisciplinary topics, real-world applications, student agency and deeper learning",
    )
)

_register(
    LessonTemplate(
        name="Flipped Classroom",
        slug="flipped-classroom",
        description=(
            "Students watch/read instructional content at home; class time is for active practice and application."
        ),
        sections=[
            TemplateSection(
                name="Quick Review / Q&A",
                duration_minutes=8,
                description="Address questions from the pre-class content",
                teacher_role="Clarify misconceptions",
                student_role="Ask questions, discuss",
            ),
            TemplateSection(
                name="Application Activity",
                duration_minutes=20,
                description="Hands-on practice applying the pre-learned concepts",
                teacher_role="Facilitate, differentiate",
                student_role="Apply concepts actively",
            ),
            TemplateSection(
                name="Problem Solving / Lab",
                duration_minutes=12,
                description="Deeper challenge problems or experiment",
                teacher_role="Coach and extend",
                student_role="Solve, experiment, collaborate",
            ),
            TemplateSection(
                name="Wrap-Up & Preview",
                duration_minutes=5,
                description="Summarize learning and preview next pre-class assignment",
                teacher_role="Assign and preview",
                student_role="Reflect, note next steps",
            ),
        ],
        student_activities=[
            "Pre-class video/reading",
            "Application exercises",
            "Problem solving",
            "Peer collaboration",
        ],
        best_for="Maximizing practice time, differentiated pacing, when strong pre-class content exists",
    )
)

_register(
    LessonTemplate(
        name="Station Rotation",
        slug="station-rotation",
        description=(
            "Students rotate through stations with different activities."
            " Each station addresses the objective differently."
        ),
        sections=[
            TemplateSection(
                name="Introduction & Directions",
                duration_minutes=5,
                description="Explain stations, expectations, rotation schedule",
                teacher_role="Set up and explain",
                student_role="Understand expectations",
            ),
            TemplateSection(
                name="Station 1: Teacher-Led",
                duration_minutes=10,
                description="Small group instruction with the teacher",
                teacher_role="Direct small-group instruction",
                student_role="Focused learning with teacher",
            ),
            TemplateSection(
                name="Station 2: Collaborative",
                duration_minutes=10,
                description="Group activity or discussion task",
                teacher_role="Monitor from distance",
                student_role="Work with peers",
            ),
            TemplateSection(
                name="Station 3: Independent",
                duration_minutes=10,
                description="Individual practice or technology-based task",
                teacher_role="Available for support",
                student_role="Self-paced work",
            ),
            TemplateSection(
                name="Station 4: Hands-On / Creative",
                duration_minutes=10,
                description="Manipulatives, art, or experiential activity",
                teacher_role="Prepare materials",
                student_role="Create, explore, experiment",
            ),
            TemplateSection(
                name="Debrief",
                duration_minutes=5,
                description="Whole-class reflection on learning from all stations",
                teacher_role="Lead discussion",
                student_role="Share takeaways",
            ),
        ],
        student_activities=[
            "Small group instruction",
            "Peer collaboration",
            "Independent practice",
            "Hands-on creation",
        ],
        best_for="Differentiated instruction, varied learning styles, maintaining engagement, mixed-ability classrooms",
    )
)


def list_templates() -> list[LessonTemplate]:
    """Return all registered lesson templates."""
    return list(TEMPLATES.values())


def get_template(slug: str) -> LessonTemplate | None:
    """Get a template by its slug."""
    return TEMPLATES.get(slug)


def template_to_prompt_constraint(template: LessonTemplate) -> str:
    """Convert a template into a constraint string for the lesson generation prompt."""
    lines = [
        f"Use the '{template.name}' lesson structure with these sections:",
        "",
    ]
    for section in template.sections:
        lines.append(f"- {section.name} ({section.duration_minutes} min): {section.description}")
        if section.teacher_role:
            lines.append(f"  Teacher role: {section.teacher_role}")
        if section.student_role:
            lines.append(f"  Student role: {section.student_role}")
    lines.append("")
    lines.append(f"Expected student activities: {', '.join(template.student_activities)}")
    return "\n".join(lines)
