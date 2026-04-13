"""Teacher workspace — persistent identity, memory, daily notes, and student profiles.

Mirrors the Hermes Agent workspace pattern, adapted for teachers:
    ~/.eduagent/workspace/
    ├── identity.md      # Auto-generated from TeacherPersona
    ├── soul.md          # Teaching philosophy, pedagogical approach
    ├── memory.md        # Long-term curated memories
    ├── notes/           # Daily teaching notes
    │   └── YYYY-MM-DD.md
    ├── heartbeat.md     # What to check on each scheduled run
    └── students/        # Per-student profiles
        └── student_name.md
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path

from clawed.models import AppConfig, TeacherPersona

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────

_BASE_DIR = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
WORKSPACE_DIR = _BASE_DIR / "workspace"
IDENTITY_PATH = WORKSPACE_DIR / "identity.md"
SOUL_PATH = WORKSPACE_DIR / "soul.md"
MEMORY_PATH = WORKSPACE_DIR / "memory.md"
MEMORY_SUMMARY_PATH = WORKSPACE_DIR / "memory_summary.md"
HEARTBEAT_PATH = WORKSPACE_DIR / "heartbeat.md"
NOTES_DIR = WORKSPACE_DIR / "notes"
STUDENTS_DIR = WORKSPACE_DIR / "students"


def _today() -> str:
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _sanitize_filename(name: str) -> str:
    """Turn an arbitrary name into a safe filename (lowercase, underscored)."""
    safe = re.sub(r"[^\w\s-]", "", name.lower().strip())
    safe = re.sub(r"[\s-]+", "_", safe)
    return safe or "unknown"


# ── Identity generation ────────────────────────────────────────────────


def generate_identity(persona: TeacherPersona, config: AppConfig | None = None) -> str:
    """Create identity.md content from a TeacherPersona and optional AppConfig."""
    cfg = config or AppConfig()
    profile = cfg.teacher_profile

    name = persona.name or profile.name or "Teacher"
    subject = persona.subject_area or (", ".join(profile.subjects) if profile.subjects else "General")
    grade_levels = persona.grade_levels or profile.grade_levels or []
    school = profile.school or ""
    style_summary = (
        f"{persona.teaching_style.value.replace('_', ' ').title()} approach, "
        f"{persona.tone} tone, "
        f"{persona.vocabulary_level.value.replace('_', ' ')} vocabulary"
    )

    lines = [
        f"# {name}",
        "",
        f"**Subject:** {subject}",
        f"**Grade Levels:** {', '.join(grade_levels) if grade_levels else 'Not specified'}",
    ]
    if school:
        lines.append(f"**School:** {school}")
    lines += [
        f"**Teaching Style:** {style_summary}",
        f"**Preferred Lesson Format:** {persona.preferred_lesson_format}",
        f"**Assessment Style:** {persona.assessment_style.value.replace('_', ' ').title()}",
        "",
        "---",
        f"*Generated {_now_iso()}*",
    ]
    return "\n".join(lines)


# ── Soul generation ───────────────────────────────────────────────────


def generate_soul(persona: TeacherPersona, config: AppConfig | None = None) -> str:
    """Create soul.md with teaching philosophy extracted from persona and config."""
    cfg = config or AppConfig()
    profile = cfg.teacher_profile

    style_label = persona.teaching_style.value.replace("_", " ").title()
    strategies = ", ".join(persona.favorite_strategies) if persona.favorite_strategies else "Not specified"
    structural = ", ".join(persona.structural_preferences) if persona.structural_preferences else "None"

    lines = [
        "# Teaching Soul",
        "",
        "## Pedagogical Philosophy",
        f"My approach is rooted in **{style_label}** instruction.",
        f"I maintain a **{persona.tone}** presence in the classroom.",
        f"I use **{persona.vocabulary_level.value.replace('_', ' ')}** vocabulary with students.",
        "",
        "## Preferred Lesson Structures",
        f"- **Format:** {persona.preferred_lesson_format}",
        f"- **Structural elements:** {structural}",
        "",
        "## Assessment Philosophy",
        f"- **Style:** {persona.assessment_style.value.replace('_', ' ').title()}",
    ]

    if profile.has_iep_students or profile.has_ell_students:
        lines += [
            "",
            "## Differentiation Approach",
        ]
        if profile.has_iep_students:
            lines.append("- I have IEP students and build accommodations into every lesson.")
        if profile.has_ell_students:
            lines.append("- I have ELL students and provide language scaffolding.")

    lines += [
        "",
        "## Favorite Strategies",
        f"{strategies}",
        "",
        "## Classroom Management Style",
        f"My tone is {persona.tone}. I use {structural} to structure each class period.",
    ]

    if persona.voice_sample:
        lines += [
            "",
            "## Voice Sample",
            persona.voice_sample[:500],
        ]

    lines += [
        "",
        "---",
        f"*Generated {_now_iso()}*",
    ]
    return "\n".join(lines)


# ── Memory ─────────────────────────────────────────────────────────────

_DEFAULT_MEMORY = """\
# Teaching Memory

## What Works (from 5-star lessons)
*(Patterns from your highest-rated lessons appear here automatically.)*

## What to Avoid (from 1-2-star lessons)
*(Patterns from your lowest-rated lessons appear here automatically.)*

## Structural Preferences
*(How you prefer lessons structured -- learned from your edits.)*

## Topic-Specific Notes
*(What works for specific subjects/topics.)*

## Common Student Questions
*(Patterns will appear here as students interact.)*

## Generation Statistics
- Total lessons rated: 0
- Average rating: --
- Rating trend: --
"""


def _load_memory() -> str:
    """Read memory.md, returning default if missing."""
    if MEMORY_PATH.exists():
        return MEMORY_PATH.read_text(encoding="utf-8")
    return _DEFAULT_MEMORY


def update_memory(key: str, value: str) -> None:
    """Update or append to a section in memory.md.

    The *key* should match a ## heading (e.g. "Lessons That Got 5-Star Ratings").
    The *value* is appended as a bullet point under that heading.
    """
    content = _load_memory()

    heading = f"## {key}"
    if heading in content:
        # Find the heading and insert after the placeholder or last line
        placeholder = "*(Nothing yet"
        lines = content.split("\n")
        new_lines: list[str] = []
        found_heading = False
        inserted = False
        for line in lines:
            if line.strip().startswith(heading):
                found_heading = True
                new_lines.append(line)
                continue
            if found_heading and not inserted:
                # Remove placeholder if present
                stripped = line.strip()
                if (
                    stripped.startswith(placeholder)
                    or stripped.startswith("*(Patterns will")
                    or stripped.startswith("*(Patterns from")
                    or stripped.startswith("*(Notes about")
                    or stripped.startswith("*(Captured from")
                    or stripped.startswith("*(How you prefer")
                    or stripped.startswith("*(What works for")
                ):
                    new_lines.append(f"- {value}")
                    inserted = True
                    continue
                elif line.startswith("## ") or line.startswith("# "):
                    # Next section -- insert before it
                    new_lines.append(f"- {value}")
                    inserted = True
                    new_lines.append(line)
                    continue
                else:
                    new_lines.append(line)
                    # If we're still in the section, keep going
                    continue
            new_lines.append(line)

        # If heading was last section and we haven't inserted yet
        if found_heading and not inserted:
            new_lines.append(f"- {value}")

        content = "\n".join(new_lines)
    else:
        # Append a new section
        content = content.rstrip() + f"\n\n{heading}\n- {value}\n"

    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(content, encoding="utf-8")


# ── Daily notes ────────────────────────────────────────────────────────


def _notes_path(day: str | None = None) -> Path:
    """Path to today's (or specified day's) notes file."""
    return NOTES_DIR / f"{day or _today()}.md"


def append_daily_note(text: str, category: str = "general") -> None:
    """Append a timestamped note to today's daily notes file."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    path = _notes_path()

    if not path.exists():
        path.write_text(f"# Teaching Notes — {_today()}\n\n", encoding="utf-8")

    timestamp = datetime.now(UTC).strftime("%H:%M UTC")
    entry = f"- **[{timestamp}]** [{category}] {text}\n"
    with open(path, "a") as f:
        f.write(entry)


def get_daily_notes(day: str | None = None) -> str:
    """Read a day's notes. Returns empty string if no notes exist."""
    path = _notes_path(day)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# ── Student profiles ──────────────────────────────────────────────────


def get_student_profile(name: str) -> str:
    """Read (or create) a student profile markdown file."""
    STUDENTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name)
    path = STUDENTS_DIR / f"{filename}.md"

    if path.exists():
        return path.read_text(encoding="utf-8")

    # Create a new profile
    initial = (
        f"# Student Profile — {name}\n\n"
        f"*Created {_now_iso()}*\n\n"
        f"## Interactions\n"
        f"*(No interactions yet.)*\n"
    )
    path.write_text(initial, encoding="utf-8")
    return initial


def update_student_profile(name: str, interaction: str) -> None:
    """Append an interaction record to a student's profile."""
    STUDENTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name)
    path = STUDENTS_DIR / f"{filename}.md"

    if not path.exists():
        # Create the profile first
        get_student_profile(name)

    content = path.read_text(encoding="utf-8")

    # Remove placeholder if present
    placeholder = "*(No interactions yet.)*"
    if placeholder in content:
        content = content.replace(placeholder, "")

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"- **[{timestamp}]** {interaction}\n"
    content = content.rstrip() + "\n" + entry

    path.write_text(content, encoding="utf-8")


def list_student_profiles() -> list[str]:
    """Return a list of student profile names (from filenames)."""
    if not STUDENTS_DIR.exists():
        return []
    return sorted(
        p.stem.replace("_", " ").title()
        for p in STUDENTS_DIR.glob("*.md")
    )


# ── Heartbeat ──────────────────────────────────────────────────────────

_DEFAULT_HEARTBEAT = """\
# Heartbeat — What to Check Each Run

This file tells the scheduler what to check during the morning-prep task.
Edit it to customize your autonomous assistant's behavior.

## Morning Prep Checks
- Are there lessons scheduled for today that haven't been generated?
- Are there any unrated lessons from yesterday?
- Is there new student activity to review?

## Weekly Checks
- Review and compress daily notes into memory highlights.
- Summarize student bot interactions for the week.
- Draft next week's lesson plans based on unit pacing.
"""


# ── Soul deduplication & consolidation ────────────────────────────────

_DATE_PREFIX_RE = re.compile(r"\(\d{4}-\d{2}-\d{2}\)\s*")

# Minimum SOUL.md size (chars) before consolidation is triggered.
_CONSOLIDATION_THRESHOLD = 3000


def _deduplicate_entry(content: str, new_entry: str, section_header: str) -> bool:
    """Check if a substantially similar entry already exists in a section.

    Returns True if a duplicate is found (entry should NOT be appended).
    """
    # Locate the section in the content
    idx = content.find(section_header)
    if idx == -1:
        return False

    # Extract text from the section header to the next section or end
    section_start = idx + len(section_header)
    next_section = re.search(r"\n## ", content[section_start:])
    if next_section:
        section_text = content[section_start: section_start + next_section.start()]
    else:
        section_text = content[section_start:]

    # Strip date prefixes for comparison
    clean_new = _DATE_PREFIX_RE.sub("", new_entry).strip()
    clean_section = _DATE_PREFIX_RE.sub("", section_text)

    # 1. Exact substring match (ignoring dates)
    if clean_new and clean_new in clean_section:
        return True

    # 2. >70% word overlap with any existing line
    new_words = set(clean_new.lower().split())
    if not new_words:
        return False

    for line in clean_section.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        line_words = set(line_stripped.lower().split())
        if not line_words:
            continue
        overlap = new_words & line_words
        # Check overlap relative to new entry
        if len(overlap) / len(new_words) > 0.70:
            return True

    return False


async def _llm_consolidate_soul(content: str) -> str:
    """Ask the LLM to consolidate a bloated SOUL.md into a concise version."""
    from clawed.llm import LLMClient

    cfg = AppConfig.load()
    client = LLMClient(cfg)
    result = await client.generate(
        prompt=content,
        system=(
            "This is a teaching identity document (SOUL.md) for an AI teaching assistant. "
            "Consolidate it: merge duplicates, remove contradictions (keep the most recent), "
            "produce a clean concise version. Preserve section structure."
        ),
        temperature=0.2,
        max_tokens=2000,
    )
    return result


async def consolidate_soul() -> bool:
    """Consolidate SOUL.md by merging duplicates via LLM.

    Returns True if consolidation was performed.
    """
    if not SOUL_PATH.exists():
        return False

    content = SOUL_PATH.read_text(encoding="utf-8")
    if len(content) <= _CONSOLIDATION_THRESHOLD:
        return False

    # Save backup before overwriting
    backup_path = SOUL_PATH.with_suffix(".md.bak")
    backup_path.write_text(content, encoding="utf-8")
    logger.info("Saved SOUL.md backup to %s", backup_path)

    try:
        consolidated = await _llm_consolidate_soul(content)
        if not consolidated or not consolidated.strip():
            raise ValueError("LLM returned empty consolidation result")
        SOUL_PATH.write_text(consolidated, encoding="utf-8")
        logger.info(
            "Consolidated SOUL.md: %d chars -> %d chars",
            len(content),
            len(consolidated),
        )
        return True
    except Exception:
        logger.exception("SOUL.md consolidation failed — restoring from backup")
        SOUL_PATH.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
        return False


# ── Workspace init ─────────────────────────────────────────────────────


def _is_corrupted(path: Path) -> bool:
    """Detect corruption: returns True if a file has the same content repeated.

    Checks whether more than 50% of non-empty lines are duplicates, which
    indicates the file got its content appended repeatedly instead of overwritten.
    """
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return False
    lines = [ln for ln in content.split("\n") if ln.strip()]
    if len(lines) < 4:
        return False  # Too small to judge
    unique = set(lines)
    return len(unique) < len(lines) * 0.5


def init_workspace(
    persona: TeacherPersona | None = None,
    config: AppConfig | None = None,
) -> Path:
    """Create the workspace directory structure and generate initial files.

    Returns the workspace root path.
    """
    cfg = config or AppConfig.load()

    # Load persona from disk if not provided
    if persona is None:
        try:
            from clawed.commands._helpers import persona_path
            from clawed.persona import load_persona

            pp = persona_path()
            if pp.exists():
                persona = load_persona(pp)
        except (FileNotFoundError, OSError):
            pass

    if persona is None:
        persona = TeacherPersona()

    # Create directories
    for d in (WORKSPACE_DIR, NOTES_DIR, STUDENTS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # Detect corrupted files (same content repeated) and auto-fix
    for check_path, label in [(SOUL_PATH, "soul.md"), (IDENTITY_PATH, "identity.md")]:
        if _is_corrupted(check_path):
            logger.warning(
                "%s appears corrupted (duplicate content detected). "
                "Regenerating from persona...",
                label,
            )
            check_path.unlink()

    # All workspace docs are teacher-editable. Never overwrite existing files.
    # Teachers can freely edit identity.md, soul.md, memory.md, heartbeat.md.
    # Re-running init only creates missing files — it never clobbers edits.

    if not IDENTITY_PATH.exists():
        IDENTITY_PATH.write_text(generate_identity(persona, cfg), encoding="utf-8")

    if not SOUL_PATH.exists():
        SOUL_PATH.write_text(generate_soul(persona, cfg), encoding="utf-8")

    if not MEMORY_PATH.exists():
        MEMORY_PATH.write_text(_DEFAULT_MEMORY, encoding="utf-8")

    if not HEARTBEAT_PATH.exists():
        HEARTBEAT_PATH.write_text(_DEFAULT_HEARTBEAT, encoding="utf-8")

    notes_path = _notes_path()
    if not notes_path.exists():
        notes_path.write_text(f"# Teaching Notes — {_today()}\n\n", encoding="utf-8")

    return WORKSPACE_DIR


def _ensure_workspace() -> None:
    """Auto-initialize workspace on first use if it doesn't exist."""
    if not WORKSPACE_DIR.exists() or not IDENTITY_PATH.exists():
        init_workspace()


# ── Context loading ───────────────────────────────────────────────────


def load_context() -> str:
    """Load identity + soul + today's notes + memory for LLM context injection.

    Returns a single string suitable for inclusion in a system prompt.
    """
    _ensure_workspace()

    parts: list[str] = []

    if IDENTITY_PATH.exists():
        parts.append(IDENTITY_PATH.read_text(encoding="utf-8"))

    if SOUL_PATH.exists():
        parts.append(SOUL_PATH.read_text(encoding="utf-8"))

    today_notes = get_daily_notes()
    if today_notes:
        parts.append(today_notes)

    if MEMORY_PATH.exists():
        memory = MEMORY_PATH.read_text(encoding="utf-8")
        # Only include memory if it has actual content beyond the template
        if "Nothing yet" not in memory or len(memory.split("\n")) > 15:
            parts.append(memory)

    return "\n\n---\n\n".join(parts)


# ── LLM context injection helper ──────────────────────────────────────


def inject_workspace_context() -> str:
    """Return workspace context formatted for inclusion in an LLM system prompt.

    This is the method that prompt builders should call.
    """
    ctx = load_context()
    if not ctx:
        return ""
    return (
        "\n\n<!-- Teacher Workspace Context -->\n"
        f"{ctx}\n"
        "<!-- End Teacher Workspace Context -->\n"
    )
