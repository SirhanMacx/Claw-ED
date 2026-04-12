"""Parent communication generator — professional parent emails and notes.

Covers two use cases:
  1. Generic parent emails by comm type (progress, behavior, positive note, etc.)
     via ParentCommRequest / ParentComm / generate_parent_comm.
  2. Voice-matched progress updates using the teacher's persona
     via generate_progress_update / save_progress_update /
     format_progress_update_text.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from clawed.llm import LLMClient
from clawed.models import AppConfig, ProgressUpdate, TeacherPersona

PROMPT_PATH = Path(__file__).parent / "prompts" / "parent_note.txt"


# ── Comm-type enum & labels ───────────────────────────────────────────


class CommType(str, Enum):
    """Types of parent communications."""

    PROGRESS_UPDATE = "progress_update"
    BEHAVIOR_CONCERN = "behavior_concern"
    POSITIVE_NOTE = "positive_note"
    UPCOMING_UNIT = "upcoming_unit"
    PERMISSION_REQUEST = "permission_request"
    GENERAL_UPDATE = "general_update"


_COMM_TYPE_LABELS: dict[CommType, str] = {
    CommType.PROGRESS_UPDATE: "Progress Update",
    CommType.BEHAVIOR_CONCERN: "Behavior Concern",
    CommType.POSITIVE_NOTE: "Positive Note",
    CommType.UPCOMING_UNIT: "Upcoming Unit Announcement",
    CommType.PERMISSION_REQUEST: "Permission Request",
    CommType.GENERAL_UPDATE: "General Update",
}


# ── Pydantic models ───────────────────────────────────────────────────


class ParentCommRequest(BaseModel):
    """Everything the generator needs to create a parent communication."""

    comm_type: CommType
    student_description: str
    class_context: str
    tone: str = "professional and warm"
    additional_notes: str = ""


class ParentComm(BaseModel):
    """A complete parent communication ready to send."""

    comm_type: CommType
    subject_line: str
    email_body: str
    follow_up_suggestions: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)


# ── Generic email generator ───────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are an experienced teacher writing a professional email to a parent or "
    "guardian. Write in a tone that is {tone}. Be clear, specific, and actionable. "
    "Never use the student's real name — use 'your child' or 'your student' instead."
)

_USER_PROMPT_TEMPLATE = """\
Generate a parent communication email as JSON.

Communication type: {comm_type_label}
Student description: {student_description}
Class context: {class_context}
Tone: {tone}
{additional_line}
Return a JSON object with these exact keys:
- "subject_line": A concise, professional email subject line.
- "email_body": The full email text. Include a greeting, body paragraphs, and \
a professional closing with the teacher's name placeholder "[Teacher Name]". \
Do NOT use any real student names — say "your child" or "your student".
- "follow_up_suggestions": A list of 2-4 suggested follow-up actions the \
teacher could take (e.g. "Schedule a parent-teacher conference", \
"Send a follow-up in two weeks").

Return ONLY the JSON object, no markdown fences."""


async def generate_parent_comm(
    request: ParentCommRequest,
    llm: LLMClient,
) -> ParentComm:
    """Generate a complete parent communication email via LLM."""
    comm_type_label = _COMM_TYPE_LABELS.get(
        request.comm_type, request.comm_type.value.replace("_", " ").title()
    )
    additional_line = (
        f"Additional notes: {request.additional_notes}\n"
        if request.additional_notes
        else ""
    )

    prompt = _USER_PROMPT_TEMPLATE.format(
        comm_type_label=comm_type_label,
        student_description=request.student_description,
        class_context=request.class_context,
        tone=request.tone,
        additional_line=additional_line,
    )

    system = _SYSTEM_PROMPT.format(tone=request.tone)

    data = await llm.generate_json(
        prompt=prompt,
        system=system,
        temperature=0.6,
        max_tokens=4096,
    )

    return ParentComm(
        comm_type=request.comm_type,
        subject_line=data.get("subject_line", ""),
        email_body=data.get("email_body", ""),
        follow_up_suggestions=data.get("follow_up_suggestions", []),
    )


def parent_comm_to_text(comm: ParentComm) -> str:
    """Format a ParentComm for output (email-ready text)."""
    lines: list[str] = []
    lines.append(f"Subject: {comm.subject_line}")
    lines.append("")
    lines.append(comm.email_body)
    lines.append("")

    if comm.follow_up_suggestions:
        lines.append("---")
        lines.append("Suggested follow-ups:")
        for suggestion in comm.follow_up_suggestions:
            lines.append(f"  - {suggestion}")

    return "\n".join(lines)


# ── Voice-matched progress-update generator ───────────────────────────


async def generate_progress_update(
    student_name: str,
    strengths: list[str],
    areas_to_grow: list[str],
    teacher_persona: TeacherPersona | None = None,
    topic: str = "general progress",
    config: AppConfig | None = None,
) -> ProgressUpdate:
    """Generate a parent progress update in the teacher's voice.

    Args:
        student_name: The student's name.
        strengths: List of observed strengths to highlight.
        areas_to_grow: List of growth areas to address constructively.
        teacher_persona: The teacher's persona for voice matching.
        topic: Context for the update (e.g., "midterm", "quarterly", "behavior").
        config: Optional app config override.

    Returns:
        A ProgressUpdate with greeting, strengths, growth areas, examples,
        action items, and closing — all in the teacher's voice.
    """
    config = config or AppConfig.load()
    persona = teacher_persona or TeacherPersona()
    persona_context = persona.to_prompt_context()

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{persona}", persona_context)
        .replace("{student_name}", student_name)
        .replace("{topic}", topic)
        .replace("{strengths}", ", ".join(strengths) if strengths else "general positive observations")
        .replace("{areas_to_grow}", ", ".join(areas_to_grow) if areas_to_grow else "general growth areas")
    )

    client = LLMClient(config)
    data = await client.generate_json(
        prompt=prompt,
        system=(
            "You are helping a teacher write a progress update to a student's parent/guardian. "
            "Write in the teacher's authentic voice. Be warm, specific, and actionable. "
            "Return valid JSON only."
        ),
        temperature=0.6,
        max_tokens=4096,
    )

    return ProgressUpdate.model_validate(data)


def save_progress_update(update: ProgressUpdate, output_dir: Path) -> Path:
    """Save a progress update as JSON and return the path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    from clawed import _safe_filename

    safe_name = _safe_filename(update.student_name)
    filename = f"progress_update_{safe_name}.json"
    path = output_dir / filename
    path.write_text(update.model_dump_json(indent=2), encoding="utf-8")
    return path


def format_progress_update_text(update: ProgressUpdate) -> str:
    """Format a ProgressUpdate as a ready-to-send email/note."""
    lines = []

    lines.append(update.greeting)
    lines.append("")

    if update.strengths:
        for s in update.strengths:
            lines.append(s)
        lines.append("")

    if update.specific_examples:
        for ex in update.specific_examples:
            lines.append(ex)
        lines.append("")

    if update.areas_to_grow:
        for a in update.areas_to_grow:
            lines.append(a)
        lines.append("")

    if update.action_items:
        lines.append("Here's how we can work together:")
        for item in update.action_items:
            lines.append(f"  - {item}")
        lines.append("")

    if update.closing:
        lines.append(update.closing)

    return "\n".join(lines)
