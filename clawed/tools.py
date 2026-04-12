"""Claw-ED tools -- functions the conversational agent can call.

These are the tools available during freeform chat. When a teacher
asks something that needs action (generate a lesson, look up standards,
read a file), the LLM can call these tools.

Reuses implementations from the MCP server and handlers where possible.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# -- Tool definitions (OpenAI function-calling format) ---------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "generate_lesson",
            "description": "Generate a complete daily lesson plan on a topic",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The lesson topic"},
                    "grade": {"type": "string", "description": "Grade level (e.g. '8', 'K')"},
                    "subject": {"type": "string", "description": "Subject area (e.g. 'Math', 'Science')"},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_unit",
            "description": "Generate a multi-week unit plan with daily lesson sequence",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The unit topic"},
                    "grade": {"type": "string", "description": "Grade level"},
                    "subject": {"type": "string", "description": "Subject area"},
                    "weeks": {"type": "integer", "description": "Duration in weeks (1-6)", "default": 2},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_quiz",
            "description": "Generate a quiz or assessment on a topic",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Quiz topic"},
                    "grade": {"type": "string", "description": "Grade level"},
                    "num_questions": {"type": "integer", "description": "Number of questions", "default": 10},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_standards",
            "description": "Look up curriculum standards for a subject and grade level",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject (e.g. 'math', 'science')"},
                    "grade": {"type": "string", "description": "Grade level"},
                },
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_persona",
            "description": "Read the current teacher's persona/teaching style profile",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List generated files (lessons, units, exports) in the teacher's output directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Which directory to list: 'output', 'workspace', or 'all'",
                        "default": "all",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read and return the contents of a generated file (lesson, unit, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search generated files by keyword in filenames and content",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "configure_profile",
            "description": "Save the teacher's profile (name, subject, grade, state, assistant name)",
            "parameters": {
                "type": "object",
                "properties": {
                    "teacher_name": {"type": "string"},
                    "subject": {"type": "string"},
                    "grade_levels": {
                        "type": "string",
                        "description": "Comma-separated: '7,8' or '8'",
                    },
                    "state": {
                        "type": "string",
                        "description": "US state abbreviation like NY, CA",
                    },
                    "assistant_name": {
                        "type": "string",
                        "description": "What the teacher wants to call the AI",
                        "default": "Claw-ED",
                    },
                },
                "required": ["teacher_name", "subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ingest_folder",
            "description": "Ingest lesson plans from a folder path to learn the teacher's style",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Folder path like ~/Documents/Lessons",
                    },
                },
                "required": ["path"],
            },
        },
    },
    # ── Google Drive tools ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "drive_list",
            "description": "List files and folders in the teacher's Google Drive",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_id": {"type": "string", "description": "Drive folder ID (empty for root)"},
                    "query": {"type": "string", "description": "Search query to filter files"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_read",
            "description": "Read the content of a file from Google Drive",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "Drive file ID to read"},
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_ingest",
            "description": "Ingest all curriculum files from a Google Drive folder into the knowledge base",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_url": {"type": "string", "description": "Google Drive folder URL or ID"},
                },
                "required": ["folder_url"],
            },
        },
    },
]


# -- Shared helpers -------------------------------------------------------


def _load_persona_for_tool(teacher_id: str = ""):
    """Load persona from session first, then file path fallback."""
    from clawed.models import TeacherPersona

    # Try session first (set by Telegram bot, web dashboard, etc.)
    if teacher_id:
        try:
            from clawed.state import TeacherSession
            session = TeacherSession.load(teacher_id)
            if session.persona:
                return session.persona
        except Exception:
            pass

    # Fallback to file on disk
    try:
        from clawed.paths import data_dir
        from clawed.persona import load_persona
        return load_persona(data_dir() / "persona.json")
    except Exception:
        return TeacherPersona()


# -- Tool implementations -------------------------------------------------


async def execute_tool(name: str, arguments: dict[str, Any], teacher_id: str = "") -> str:
    """Execute a tool by name and return the result as a string."""
    try:
        if name == "generate_lesson":
            return await _tool_generate_lesson(teacher_id=teacher_id, **arguments)
        elif name == "generate_unit":
            return await _tool_generate_unit(teacher_id=teacher_id, **arguments)
        elif name == "generate_quiz":
            return await _tool_generate_quiz(**arguments)
        elif name == "search_standards":
            return await _tool_search_standards(**arguments)
        elif name == "read_persona":
            return await _tool_read_persona(teacher_id)
        elif name == "list_files":
            return _tool_list_files(**arguments)
        elif name == "read_file":
            return _tool_read_file(**arguments)
        elif name == "search_files":
            return _tool_search_files(**arguments)
        elif name == "configure_profile":
            return await _tool_configure_profile(teacher_id=teacher_id, **arguments)
        elif name == "ingest_folder":
            return await _tool_ingest_folder(teacher_id=teacher_id, **arguments)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e)
        return json.dumps({"error": str(e)})


async def _tool_generate_lesson(
    topic: str, grade: str = "8", subject: str = "General", teacher_id: str = ""
) -> str:
    """Generate a lesson -- reuses existing lesson generation."""
    from clawed.lesson import generate_lesson
    from clawed.models import AppConfig, LessonBrief, UnitPlan

    config = AppConfig.load()
    persona = _load_persona_for_tool(teacher_id)

    unit = UnitPlan(
        title=f"{topic} Unit", subject=subject, grade_level=grade, topic=topic,
        duration_weeks=1, overview=f"A lesson on {topic}.",
        daily_lessons=[LessonBrief(lesson_number=1, topic=topic, description=f"Introduction to {topic}")],
    )
    lesson = await generate_lesson(lesson_number=1, unit=unit, persona=persona, config=config)
    # Return a readable summary, not raw JSON
    lines = [f"**{lesson.title}**", f"Objective: {lesson.objective}", ""]
    if lesson.do_now:
        lines.append(f"**Do Now:** {lesson.do_now[:300]}")
    if lesson.direct_instruction:
        lines.append(f"\n**Direct Instruction:** {lesson.direct_instruction[:500]}")
    if lesson.guided_practice:
        lines.append(f"\n**Guided Practice:** {lesson.guided_practice[:300]}")
    if lesson.exit_ticket:
        lines.append(f"\n**Exit Ticket:** {len(lesson.exit_ticket)} question(s)")
    return "\n".join(lines)


async def _tool_generate_unit(
    topic: str, grade: str = "8", subject: str = "General", weeks: int = 2, teacher_id: str = ""
) -> str:
    """Generate a unit plan."""
    from clawed.models import AppConfig
    from clawed.planner import plan_unit

    config = AppConfig.load()
    persona = _load_persona_for_tool(teacher_id)

    unit = await plan_unit(
        subject=subject, grade_level=grade, topic=topic,
        duration_weeks=weeks, persona=persona, config=config,
    )
    lines = [f"**{unit.title}** ({unit.duration_weeks} weeks, {len(unit.daily_lessons)} lessons)"]
    for q in unit.essential_questions[:3]:
        lines.append(f"  - {q}")
    for brief in unit.daily_lessons:
        lines.append(f"  Lesson {brief.lesson_number}: {brief.topic}")
    return "\n".join(lines)


async def _tool_generate_quiz(topic: str, grade: str = "8", num_questions: int = 10) -> str:
    """Generate a quiz."""
    from clawed.assessment import AssessmentGenerator
    from clawed.models import AppConfig

    config = AppConfig.load()
    gen = AssessmentGenerator(config)
    quiz = await gen.generate_quiz(topic=topic, question_count=num_questions, grade=grade)
    lines = [f"**Quiz: {quiz.topic}** ({quiz.total_points} points, {len(quiz.questions)} questions)"]
    for q in quiz.questions[:5]:
        lines.append(f"  {q.question_number}. {q.question[:100]}")
    if len(quiz.questions) > 5:
        lines.append(f"  ... and {len(quiz.questions) - 5} more")
    return "\n".join(lines)


async def _tool_search_standards(subject: str, grade: str = "") -> str:
    """Look up curriculum standards."""
    from clawed.standards import get_standards
    results = get_standards(subject, grade or None)
    if not results:
        return f"No standards found for {subject} grade {grade}."
    lines = [f"Standards for {subject.title()} Grade {grade}:"]
    for code, desc, _band in results[:10]:
        lines.append(f"  {code}: {desc}")
    if len(results) > 10:
        lines.append(f"  ... and {len(results) - 10} more")
    return "\n".join(lines)


async def _tool_read_persona(teacher_id: str = "") -> str:
    """Read the teacher's persona."""
    try:
        from clawed.state import TeacherSession
        session = TeacherSession.load(teacher_id or "local-teacher")
        if session.persona:
            return session.persona.to_prompt_context()
        return "No persona configured yet. Run 'clawed ingest <folder>' to learn your teaching style."
    except Exception:
        return "No persona available."


def _tool_list_files(directory: str = "all") -> str:
    """List files in teacher's output/workspace directories."""
    dirs_to_check: list[tuple[str, Path]] = []
    from clawed.paths import data_dir
    base = data_dir()

    if directory in ("output", "all"):
        dirs_to_check.append(("Generated Output", Path("clawed_output").resolve()))
        dirs_to_check.append(("Generated Output (legacy)", Path("eduagent_output").resolve()))
    if directory in ("workspace", "all"):
        dirs_to_check.append(("Workspace", base / "workspace"))

    lines: list[str] = []
    for label, d in dirs_to_check:
        if not d.exists():
            continue
        files = sorted(d.rglob("*"))
        files = [f for f in files if f.is_file() and not f.name.startswith(".")]
        if files:
            lines.append(f"**{label}** ({d}):")
            for f in files[:20]:
                size = f.stat().st_size
                lines.append(f"  {f.relative_to(d)} ({size:,} bytes)")
            if len(files) > 20:
                lines.append(f"  ... and {len(files) - 20} more files")
    if not lines:
        return "No generated files found yet. Generate a lesson with 'lesson on [topic]'."
    return "\n".join(lines)


def _tool_read_file(path: str) -> str:
    """Read a file and return its contents (truncated if large)."""
    p = Path(path).expanduser().resolve()
    # Security: only allow reading from known directories (resolved path containment)
    from clawed.paths import data_dir
    allowed = [data_dir(), Path("clawed_output").resolve(), Path("eduagent_output").resolve()]
    if not any(str(p).startswith(str(a.resolve()) + os.sep) or p == a.resolve() for a in allowed):
        return "Cannot read files outside of Claw-ED directories."
    if not p.exists():
        return f"File not found: {path}"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        if len(content) > 3000:
            return content[:3000] + f"\n\n... (truncated, {len(content):,} chars total)"
        return content
    except Exception as e:
        return f"Could not read file: {e}"


def _tool_search_files(query: str) -> str:
    """Search filenames and content for a keyword."""
    query_lower = query.lower()
    matches: list[str] = []
    from clawed.paths import data_dir
    dirs = [data_dir(), Path("clawed_output").resolve(), Path("eduagent_output").resolve()]
    for d in dirs:
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if not f.is_file() or f.name.startswith("."):
                continue
            if query_lower in f.name.lower():
                matches.append(f"  {f} (filename match)")
                continue
            try:
                if f.suffix in (".json", ".txt", ".md") and f.stat().st_size < 100_000:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    if query_lower in content.lower():
                        matches.append(f"  {f} (content match)")
            except Exception:
                pass
            if len(matches) >= 15:
                break
    if not matches:
        return f"No files matching '{query}' found."
    return f"Files matching '{query}':\n" + "\n".join(matches)


async def _tool_configure_profile(
    teacher_name: str,
    subject: str,
    grade_levels: str = "",
    state: str = "",
    assistant_name: str = "Claw-ED",
    teacher_id: str = "",
) -> str:
    """Save the teacher's profile during onboarding."""
    from clawed.models import AppConfig, TeacherPersona, TeacherProfile
    from clawed.state import TeacherSession
    from clawed.workspace import init_workspace

    grades = [g.strip() for g in grade_levels.split(",") if g.strip()]

    config = AppConfig.load()
    config.teacher_profile = TeacherProfile(
        name=teacher_name,
        subjects=[subject],
        grade_levels=grades,
        state=state,
    )
    config.save()

    persona = TeacherPersona(name=teacher_name, subject_area=subject)
    session = TeacherSession.load(teacher_id or "local-teacher")
    session.persona = persona
    session.save()

    with contextlib.suppress(Exception):
        init_workspace(persona, config)

    return (
        f"Profile saved! {teacher_name} teaches {subject}"
        f"{' grade ' + grade_levels if grade_levels else ''}"
        f"{' in ' + state if state else ''}. "
        f"Assistant name: {assistant_name}."
    )


async def _tool_ingest_folder(path: str, teacher_id: str = "") -> str:
    """Ingest lesson plans from a folder to learn the teacher's style."""
    from clawed.ingestor import ingest_path

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return f"Folder not found: {path}. Check the path and try again."

    docs = ingest_path(str(resolved))
    if not docs:
        return (
            f"No supported files found in {path}. "
            "I can read PDF, DOCX, PPTX, TXT, and MD files."
        )

    # Extract persona from ingested documents
    try:
        from clawed.models import AppConfig
        from clawed.persona import extract_persona, save_persona

        persona = await extract_persona(docs, AppConfig.load())
        from clawed.paths import data_dir
        save_persona(persona, data_dir())
        style = persona.teaching_style.value.replace("_", " ").title()
        return f"Ingested {len(docs)} files! Teaching style: {style}, Tone: {persona.tone}."
    except Exception as e:
        return f"Ingested {len(docs)} files, but couldn't extract style patterns: {e}"
