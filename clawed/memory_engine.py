"""Teaching Memory Engine -- learns from teacher feedback to improve generation.

The feedback loop:
1. Teacher rates a lesson (1-5 stars) + optional notes
2. Memory engine extracts what worked (5*) or what failed (1-2*)
3. Patterns stored in memory.md as structured sections
4. Next generation reads memory.md and injects it as context
5. Output quality improves over time

This is prompt-level RLHF: no model fine-tuning required, transparent
(teacher can read and edit memory.md), and compounds over time.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clawed.models import AppConfig

if TYPE_CHECKING:
    from clawed.models import DailyLesson

logger = logging.getLogger(__name__)

# ── Sections in memory.md ────────────────────────────────────────────

SECTION_WHAT_WORKS = "What Works (from 5-star lessons)"
SECTION_WHAT_TO_AVOID = "What to Avoid (from 1-2-star lessons)"
SECTION_STRUCTURAL_PREFS = "Structural Preferences"
SECTION_TOPIC_NOTES = "Topic-Specific Notes"
SECTION_GENERATION_STATS = "Generation Statistics"

# Placeholders used in memory.md sections
_SECTION_PLACEHOLDERS: dict[str, str] = {
    SECTION_WHAT_WORKS: "*(Patterns from your highest-rated lessons appear here automatically.)*",
    SECTION_WHAT_TO_AVOID: "*(Patterns from your lowest-rated lessons appear here automatically.)*",
    SECTION_STRUCTURAL_PREFS: "*(How you prefer lessons structured -- learned from your edits.)*",
    SECTION_TOPIC_NOTES: "*(What works for specific subjects/topics.)*",
}


# ── Default memory template ──────────────────────────────────────────

DEFAULT_MEMORY_TEMPLATE = """\
# Teaching Memory

## What Works (from 5-star lessons)
*(Patterns from your highest-rated lessons appear here automatically.)*

## What to Avoid (from 1-2-star lessons)
*(Patterns from your lowest-rated lessons appear here automatically.)*

## Structural Preferences
*(How you prefer lessons structured -- learned from your edits.)*

## Topic-Specific Notes
*(What works for specific subjects/topics.)*

## Generation Statistics
- Total lessons rated: 0
- Average rating: --
- Rating trend: --
"""


# ── Pattern extraction (rule-based, no LLM needed) ──────────────────


def extract_lesson_patterns(
    lesson: DailyLesson,
    rating: int,
    notes: str = "",
    edited_sections: list[str] | None = None,
    subject: str = "",
) -> list[dict[str, str]]:
    """Extract patterns from a rated lesson using rule-based heuristics.

    Returns a list of pattern dicts: {"type": ..., "pattern": ..., "section": ...}
    Each pattern is a short sentence describing what worked or what to avoid.

    Args:
        subject: The subject area (e.g. "Science", "History"). Used to tag
            patterns so they can be filtered during prompt injection, preventing
            cross-subject contamination.
    """
    patterns: list[dict[str, str]] = []
    edited = edited_sections or []
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d")

    # Tag patterns with subject for cross-subject filtering
    subject_tag = f" [{subject}]" if subject else ""

    if rating == 5:
        # Extract what made it excellent
        patterns.append({
            "type": "positive",
            "pattern": f"Lesson '{lesson.title}' rated 5-star{subject_tag} ({timestamp})",
            "section": SECTION_WHAT_WORKS,
        })

        # Structural patterns from the lesson itself
        if lesson.do_now and len(lesson.do_now) > 50:
            _extract_do_now_pattern(lesson.do_now, patterns)
        if lesson.exit_ticket and len(lesson.exit_ticket) >= 3:
            patterns.append({
                "type": "positive",
                "pattern": "Exit tickets with 3+ questions work well",
                "section": SECTION_STRUCTURAL_PREFS,
            })
        if notes:
            patterns.append({
                "type": "positive",
                "pattern": f"Teacher note on 5-star lesson{subject_tag}: {notes[:200]}",
                "section": SECTION_WHAT_WORKS,
            })

    elif rating <= 2:
        # Extract what went wrong
        patterns.append({
            "type": "negative",
            "pattern": f"Lesson '{lesson.title}' rated {rating}-star{subject_tag} ({timestamp})",
            "section": SECTION_WHAT_TO_AVOID,
        })

        if notes:
            patterns.append({
                "type": "negative",
                "pattern": f"Teacher complaint{subject_tag}: {notes[:200]}",
                "section": SECTION_WHAT_TO_AVOID,
            })

        # Track which sections were edited (they needed fixing)
        for section_name in edited:
            patterns.append({
                "type": "structural",
                "pattern": f"Teacher edited '{section_name}' section{subject_tag} -- needs improvement",
                "section": SECTION_STRUCTURAL_PREFS,
            })

    elif rating == 4:
        # Good but not perfect -- note minor tweaks if notes provided
        if notes:
            patterns.append({
                "type": "positive",
                "pattern": f"4-star lesson '{lesson.title}': {notes[:150]}",
                "section": SECTION_TOPIC_NOTES,
            })
        if edited:
            for section_name in edited:
                patterns.append({
                    "type": "structural",
                    "pattern": f"Minor edit needed in '{section_name}' on 4-star lesson",
                    "section": SECTION_STRUCTURAL_PREFS,
                })

    # Rating 3 = neutral, don't learn from mediocre

    return patterns


def _extract_do_now_pattern(do_now_text: str, patterns: list[dict[str, str]]) -> None:
    """Identify structural patterns in a successful Do-Now section."""
    text_lower = do_now_text.lower()

    if "?" in do_now_text:
        q_count = do_now_text.count("?")
        if q_count >= 2:
            patterns.append({
                "type": "positive",
                "pattern": f"Do-Now with {q_count} questions works well",
                "section": SECTION_STRUCTURAL_PREFS,
            })
    if any(kw in text_lower for kw in ("predict", "prediction", "what do you think")):
        patterns.append({
            "type": "positive",
            "pattern": "Do-Now with prediction/anticipation questions gets high ratings",
            "section": SECTION_STRUCTURAL_PREFS,
        })
    if any(kw in text_lower for kw in ("reflect", "reflection", "yesterday", "last class")):
        patterns.append({
            "type": "positive",
            "pattern": "Do-Now with reflection on prior learning gets high ratings",
            "section": SECTION_STRUCTURAL_PREFS,
        })


# ── Memory.md read/write ─────────────────────────────────────────────


def _get_memory_path():
    """Get the memory.md path, respecting EDUAGENT_DATA_DIR."""
    from clawed.workspace import MEMORY_PATH
    return MEMORY_PATH


def _read_memory() -> str:
    """Read memory.md, returning the default template if it doesn't exist."""
    path = _get_memory_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return DEFAULT_MEMORY_TEMPLATE


def _write_memory(content: str) -> None:
    """Write content to memory.md, creating parent dirs if needed."""
    path = _get_memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _append_to_section(content: str, section_name: str, entry: str) -> str:
    """Append a bullet point to a section in memory.md content.

    If the section exists, inserts after the heading (replacing placeholder if present).
    If the section doesn't exist, appends it at the end.
    """
    heading = f"## {section_name}"

    if heading not in content:
        # Append new section before Generation Statistics (if present) or at end
        stats_heading = f"## {SECTION_GENERATION_STATS}"
        if stats_heading in content:
            content = content.replace(
                stats_heading,
                f"{heading}\n- {entry}\n\n{stats_heading}",
            )
        else:
            content = content.rstrip() + f"\n\n{heading}\n- {entry}\n"
        return content

    lines = content.split("\n")
    new_lines: list[str] = []
    found_heading = False
    inserted = False

    for line in lines:
        if line.strip() == heading or line.strip().startswith(heading):
            found_heading = True
            new_lines.append(line)
            continue

        if found_heading and not inserted:
            stripped = line.strip()
            # Check if this line is a placeholder
            if stripped.startswith("*(") and stripped.endswith(")*"):
                new_lines.append(f"- {entry}")
                inserted = True
                continue
            # Check if we've hit the next section
            elif stripped.startswith("## ") or stripped.startswith("# "):
                new_lines.append(f"- {entry}")
                new_lines.append("")
                inserted = True
                new_lines.append(line)
                continue
            else:
                new_lines.append(line)
                continue
        else:
            new_lines.append(line)

    if found_heading and not inserted:
        new_lines.append(f"- {entry}")

    return "\n".join(new_lines)


def _update_stats_section(content: str, total_rated: int, avg_rating: float, trend: str) -> str:
    """Update the Generation Statistics section in memory.md."""
    heading = f"## {SECTION_GENERATION_STATS}"
    avg_str = f"{avg_rating:.1f}" if avg_rating > 0 else "--"

    stats_block = (
        f"{heading}\n"
        f"- Total lessons rated: {total_rated}\n"
        f"- Average rating: {avg_str}\n"
        f"- Rating trend: {trend}\n"
    )

    if heading in content:
        # Replace entire stats section
        pattern = re.compile(
            r"## Generation Statistics\n(?:- .*\n)*",
            re.MULTILINE,
        )
        content = pattern.sub(stats_block, content)
    else:
        content = content.rstrip() + f"\n\n{stats_block}"

    return content


# ── Deduplication ────────────────────────────────────────────────────


def _is_duplicate_entry(content: str, entry: str) -> bool:
    """Check if an entry (or something very similar) already exists in memory.md."""
    # Exact match
    if f"- {entry}" in content:
        return True
    # Check if the core lesson title is already recorded
    # e.g. "Lesson 'Photosynthesis' rated 5-star" should not be added twice
    match = re.search(r"Lesson '([^']+)'", entry)
    if match:
        title = match.group(1)
        if title in content:
            return True
    return False


# ── Core API ─────────────────────────────────────────────────────────


def process_feedback(
    lesson: DailyLesson,
    rating: int,
    notes: str = "",
    edited_sections: list[str] | None = None,
    subject: str = "",
) -> list[dict[str, str]]:
    """Process teacher feedback and update memory.md with learned patterns.

    This is the primary entry point for the feedback loop. Call it after
    every rating to incrementally build the teacher's preference profile.

    Args:
        lesson: The rated lesson.
        rating: 1-5 star rating.
        notes: Optional free-text feedback from the teacher.
        edited_sections: Optional list of section names the teacher edited.
        subject: The subject area (for cross-subject filtering in prompts).

    Returns:
        List of patterns that were extracted and stored.
    """
    rating = max(1, min(5, rating))

    # Rating 3 = neutral, skip
    if rating == 3:
        logger.debug("Rating 3 (neutral) for '%s' -- skipping pattern extraction", lesson.title)
        return []

    # Resolve subject: from parameter, persona config, or empty
    if not subject:
        try:
            cfg = AppConfig.load()
            if cfg.teacher_profile and cfg.teacher_profile.subjects:
                subject = cfg.teacher_profile.subjects[0]
        except Exception:
            logger.debug("operation_failed", exc_info=True)

    # Extract patterns from the rated lesson
    patterns = extract_lesson_patterns(lesson, rating, notes, edited_sections, subject=subject)

    if not patterns:
        return []

    # Read current memory and apply patterns
    content = _read_memory()

    applied: list[dict[str, str]] = []
    for pattern in patterns:
        entry = pattern["pattern"]
        section = pattern["section"]

        # Skip duplicates
        if _is_duplicate_entry(content, entry):
            logger.debug("Skipping duplicate pattern: %s", entry[:80])
            continue

        content = _append_to_section(content, section, entry)
        applied.append(pattern)

    if applied:
        # Update stats
        stats = _compute_stats(content)
        content = _update_stats_section(
            content,
            total_rated=stats["total_rated"],
            avg_rating=stats["avg_rating"],
            trend=stats["trend"],
        )
        _write_memory(content)
        logger.info(
            "Memory updated: %d pattern(s) from %d-star rating of '%s'",
            len(applied), rating, lesson.title,
        )

    # Preference drift detection (runs on every rated lesson)
    try:
        detect_preference_drift(rating)
    except Exception as e:
        logger.debug("Drift detection failed: %s", e)

    # Check if persona evolution should trigger
    try:
        from clawed.persona_evolution import apply_confirmed_changes, get_confirmed_changes
        confirmed = get_confirmed_changes()
        if confirmed:
            from clawed.commands._helpers import persona_path
            from clawed.persona import load_persona
            pp = persona_path()
            if pp.exists():
                current_persona = load_persona(pp)
                updated, descriptions = apply_confirmed_changes(current_persona)
                if descriptions:
                    pp.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
                    # Log to SOUL.md
                    from clawed.workspace import SOUL_PATH
                    if SOUL_PATH.exists():
                        soul_content = SOUL_PATH.read_text(encoding="utf-8")
                        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
                        for desc in descriptions:
                            entry = f"\n\n*({stamp})* Fingerprint updated: {desc}\n"
                            marker = "## Agent Observations"
                            soul_content = soul_content.replace(
                                marker, marker + entry, 1
                            )
                        SOUL_PATH.write_text(soul_content, encoding="utf-8")
                    logger.info("Persona evolution applied: %s", "; ".join(descriptions))
    except Exception as e:
        logger.debug("Persona evolution check failed: %s", e)

    return applied


def build_improvement_context(
    subject: str = "",
    grade: str = "",
    topic: str = "",
) -> str:
    """Build a focused prompt injection from memory.md for the current generation.

    Reads memory.md and constructs a block of text that gets injected into
    the system prompt so the LLM knows the teacher's preferences.

    Args:
        subject: The subject being generated for (for topic-specific filtering).
        grade: The grade level.
        topic: The specific topic.

    Returns:
        A formatted string for prompt injection. Empty string if no useful
        content exists in memory.md.
    """
    content = _read_memory()

    # If memory only contains the default template with placeholders, return empty
    if _is_only_template(content):
        return ""

    parts: list[str] = []

    # Subject aliases for cross-matching (ELA ↔ English, History ↔ Social Studies)
    _subject_groups: list[set[str]] = [
        {"ela", "english", "language arts", "reading", "writing", "literature"},
        {"history", "social studies", "civics", "government", "geography"},
        {"science", "biology", "chemistry", "physics", "earth science"},
        {"math", "mathematics", "algebra", "geometry", "calculus", "statistics"},
        {"art", "visual arts", "studio art"},
        {"music", "band", "orchestra", "choir"},
        {"pe", "physical education", "health"},
        {"cs", "computer science", "programming", "coding"},
        {"foreign language", "spanish", "french", "mandarin", "latin", "german"},
    ]

    def _subjects_match(a: str, b: str) -> bool:
        """Check if two subject names refer to the same subject family."""
        a_lower, b_lower = a.lower(), b.lower()
        if a_lower == b_lower or a_lower in b_lower or b_lower in a_lower:
            return True
        for group in _subject_groups:
            if any(alias in a_lower or a_lower in alias for alias in group):
                if any(alias in b_lower or b_lower in alias for alias in group):
                    return True
        return False

    def _filter_by_subject(entries: list[str], subj: str) -> list[str]:
        """Filter entries to those relevant to the given subject.

        Entries tagged with [Subject] are only included if they match
        (using alias groups: ELA=English, History=Social Studies, etc.).
        Entries without a tag are always included (they're universal).
        """
        if not subj:
            return entries
        result = []
        for e in entries:
            tag_match = re.search(r"\[([^\]]+)\]", e)
            if tag_match:
                tag = tag_match.group(1)
                if _subjects_match(subj, tag):
                    result.append(e)
                # Skip entries tagged for other subjects
            else:
                # No tag — universal pattern, always include
                result.append(e)
        return result

    # Extract "What Works" entries, filtered by subject
    works = _extract_section_entries(content, SECTION_WHAT_WORKS)
    works = _filter_by_subject(works, subject)
    if works:
        parts.append("What works well for this teacher:")
        for entry in works[-10:]:
            parts.append(f"  - {entry}")

    # Extract "What to Avoid" entries, filtered by subject
    avoid = _extract_section_entries(content, SECTION_WHAT_TO_AVOID)
    avoid = _filter_by_subject(avoid, subject)
    if avoid:
        parts.append("")
        parts.append("What to avoid:")
        for entry in avoid[-10:]:
            parts.append(f"  - {entry}")

    # Extract structural preferences (these are universal, no subject filter)
    structural = _extract_section_entries(content, SECTION_STRUCTURAL_PREFS)
    if structural:
        parts.append("")
        parts.append("Structural preferences:")
        for entry in structural[-8:]:
            parts.append(f"  - {entry}")

    # Extract topic-specific notes (filter by subject/topic if provided)
    topic_notes = _extract_section_entries(content, SECTION_TOPIC_NOTES)
    if topic_notes:
        relevant = topic_notes
        if subject or topic:
            # Filter to entries mentioning the subject or topic
            search_terms = [t.lower() for t in [subject, topic] if t]
            filtered = [
                n for n in topic_notes
                if any(term in n.lower() for term in search_terms)
            ]
            relevant = filtered if filtered else topic_notes[-5:]
        parts.append("")
        parts.append("Topic-specific notes:")
        for entry in relevant[-5:]:
            parts.append(f"  - {entry}")

    # Inject rule-based quality insights (no LLM calls)
    insights = get_quality_insights()
    if insights:
        parts.append("")
        parts.append("Statistical patterns from your ratings:")
        for insight in insights[:5]:
            parts.append(f"  - {insight}")

    if not parts:
        return ""

    header = "=== Learning from Past Lessons ==="
    footer = "=== End Learning Context ==="
    return f"\n{header}\n" + "\n".join(parts) + f"\n{footer}\n"


def get_improvement_stats() -> dict[str, Any]:
    """Return statistics about the improvement loop.

    Returns:
        Dict with total_rated, avg_rating, trend, patterns_count,
        what_works_count, what_to_avoid_count.
    """
    content = _read_memory()
    stats = _compute_stats(content)

    works = _extract_section_entries(content, SECTION_WHAT_WORKS)
    avoid = _extract_section_entries(content, SECTION_WHAT_TO_AVOID)
    structural = _extract_section_entries(content, SECTION_STRUCTURAL_PREFS)
    topics = _extract_section_entries(content, SECTION_TOPIC_NOTES)

    stats["what_works_count"] = len(works)
    stats["what_to_avoid_count"] = len(avoid)
    stats["structural_count"] = len(structural)
    stats["topic_notes_count"] = len(topics)
    stats["total_patterns"] = len(works) + len(avoid) + len(structural) + len(topics)
    stats["what_works"] = works[-5:]
    stats["what_to_avoid"] = avoid[-5:]

    return stats


def reset_memory(confirm: bool = False) -> bool:
    """Reset memory.md to the default template. Requires confirm=True.

    Returns True if reset was performed.
    """
    if not confirm:
        return False
    _write_memory(DEFAULT_MEMORY_TEMPLATE)
    logger.info("Memory reset to default template.")
    return True


# ── Rule-based lesson metadata tracking (no LLM calls) ──────────────


def _base_dir() -> Path:
    """Get the base data directory for stats files."""
    from clawed.paths import data_dir
    return data_dir()


def _load_stats(stats_path: Path) -> dict[str, Any]:
    """Load lesson stats from disk."""
    if stats_path.exists():
        try:
            return json.loads(stats_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_stats(stats_path: Path, stats: dict[str, Any]) -> None:
    """Persist lesson stats to disk."""
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def track_lesson_metadata(lesson: DailyLesson, rating: int) -> None:
    """Track which lesson characteristics correlate with high ratings.

    Pure rule-based -- no LLM calls. Builds a statistical profile
    over time that the prompt injection can reference.
    """
    metadata = {
        "has_do_now": bool(lesson.do_now and len(lesson.do_now) > 20),
        "has_exit_ticket": bool(lesson.exit_ticket and len(lesson.exit_ticket) >= 1),
        "exit_ticket_count": len(lesson.exit_ticket) if lesson.exit_ticket else 0,
        "has_homework": bool(lesson.homework),
        "has_differentiation": bool(
            lesson.differentiation
            and (
                lesson.differentiation.struggling
                or lesson.differentiation.advanced
                or lesson.differentiation.ell
            )
        ),
        "instruction_length": len(lesson.direct_instruction or ""),
        "practice_length": len(lesson.guided_practice or ""),
        "has_materials_list": bool(lesson.materials_needed),
    }

    stats_path = _base_dir() / "lesson_stats.json"
    stats = _load_stats(stats_path)

    # Classify rating into buckets
    if rating >= 4:
        bucket = "high"
    elif rating <= 2:
        bucket = "low"
    else:
        bucket = "mid"

    for key, value in metadata.items():
        if isinstance(value, bool):
            value = 1 if value else 0
        stats.setdefault(key, {}).setdefault(bucket, []).append(value)

    _save_stats(stats_path, stats)


def get_quality_insights() -> list[str]:
    """Derive insights from lesson metadata statistics.

    Returns plain-English insights like:
    - "Lessons with exit tickets average higher ratings"
    - "Including a materials list correlates with higher ratings"

    Pure rule-based -- no LLM calls.
    """
    stats_path = _base_dir() / "lesson_stats.json"
    stats = _load_stats(stats_path)

    if not stats:
        return []

    insights: list[str] = []

    for key in stats:
        high = stats[key].get("high", [])
        low = stats[key].get("low", [])

        if not high and not low:
            continue

        high_avg = sum(high) / len(high) if high else 0
        low_avg = sum(low) / len(low) if low else 0

        # Only report if we have enough data and the difference is meaningful
        if len(high) + len(low) < 3:
            continue

        label = key.replace("_", " ").replace("has ", "")

        if key.startswith("has_"):
            # Boolean feature: compare rates
            if high_avg > 0.7 and low_avg < 0.4:
                insights.append(
                    f"Including {label} correlates with higher ratings "
                    f"({high_avg:.0%} of top lessons vs {low_avg:.0%} of low-rated)"
                )
            elif low_avg > 0.7 and high_avg < 0.4:
                insights.append(
                    f"Lessons without {label} tend to rate higher"
                )
        elif key == "exit_ticket_count":
            if high_avg > low_avg + 0.5:
                insights.append(
                    f"Top-rated lessons average {high_avg:.1f} exit ticket questions "
                    f"vs {low_avg:.1f} for lower-rated"
                )
        elif key in ("instruction_length", "practice_length"):
            if high_avg > low_avg * 1.3 and len(high) >= 2:
                insights.append(
                    f"Higher-rated lessons have longer {label} sections "
                    f"(avg {high_avg:.0f} chars vs {low_avg:.0f})"
                )
            elif low_avg > high_avg * 1.3 and len(low) >= 2:
                insights.append(
                    f"Shorter {label} sections correlate with higher ratings "
                    f"(avg {high_avg:.0f} chars vs {low_avg:.0f})"
                )

    return insights


# ── Internal helpers ─────────────────────────────────────────────────


def _extract_section_entries(content: str, section_name: str) -> list[str]:
    """Extract bullet-point entries from a section in memory.md.

    Returns a list of entry strings (without the leading '- ').
    """
    heading = f"## {section_name}"
    if heading not in content:
        return []

    entries: list[str] = []
    in_section = False

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == heading or stripped.startswith(heading):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## ") or stripped.startswith("# "):
                break  # Next section
            if stripped.startswith("- "):
                entry = stripped[2:].strip()
                # Skip placeholders
                if entry.startswith("*(") and entry.endswith(")*"):
                    continue
                entries.append(entry)

    return entries


def _is_only_template(content: str) -> bool:
    """Check if memory.md only contains the default template with no real entries."""
    for section in [SECTION_WHAT_WORKS, SECTION_WHAT_TO_AVOID, SECTION_STRUCTURAL_PREFS, SECTION_TOPIC_NOTES]:
        entries = _extract_section_entries(content, section)
        if entries:
            return False
    return True


def _compute_stats(content: str) -> dict[str, Any]:
    """Compute stats from the memory.md content.

    Counts rated entries and computes average from the star mentions.
    """
    # Count rated lessons by counting star-rating mentions
    five_star = len(re.findall(r"rated 5-star", content))
    four_star = content.count("4-star lesson")
    one_two_star = len(re.findall(r"rated [12]-star", content))

    total_rated = five_star + four_star + one_two_star

    if total_rated == 0:
        return {"total_rated": 0, "avg_rating": 0.0, "trend": "--"}

    # Count 1-star and 2-star separately for accurate average
    one_star = len(re.findall(r"rated 1-star", content))
    two_star = len(re.findall(r"rated 2-star", content))
    # If we can't distinguish (old format), split evenly
    if one_star + two_star == 0 and one_two_star > 0:
        one_star = one_two_star // 2
        two_star = one_two_star - one_star

    total_score = (five_star * 5) + (four_star * 4) + (two_star * 2) + (one_star * 1)
    avg_rating = total_score / total_rated if total_rated else 0.0

    # Simple trend: if more 5-star than low, trending up
    if five_star > one_two_star:
        trend = "improving"
    elif one_two_star > five_star:
        trend = "needs attention"
    else:
        trend = "stable"

    return {
        "total_rated": total_rated,
        "avg_rating": round(avg_rating, 2),
        "trend": trend,
    }


# ── Long-term memory compression ─────────────────────────────────────

COMPRESSION_THRESHOLD = 20  # Compress after every N episodes
EPISODES_TO_KEEP_VERBATIM = 10  # Keep this many recent episodes uncompressed


def _get_memory_summary_path() -> Path:
    """Get the memory_summary.md path, respecting EDUAGENT_DATA_DIR."""
    from clawed.workspace import MEMORY_SUMMARY_PATH
    return MEMORY_SUMMARY_PATH


def compress_old_episodes(teacher_id: str) -> str:
    """Summarize older episodes into compressed highlights.

    Keeps the last ``EPISODES_TO_KEEP_VERBATIM`` episodes verbatim and
    compresses everything older into a bullet-point summary stored in
    ``memory_summary.md``.  This prevents episodic memory from growing
    unbounded and degrading context quality.

    Returns the summary text (empty string if nothing to compress).
    """
    from clawed.agent_core.memory.episodes import EpisodicMemory

    mem = EpisodicMemory()
    total = mem.count_episodes(teacher_id)

    if total <= EPISODES_TO_KEEP_VERBATIM:
        return ""

    # Fetch all episodes oldest-first
    all_eps = mem.get_all_episodes(teacher_id, limit=total)

    # Split: compress older, keep recent verbatim
    cutoff = len(all_eps) - EPISODES_TO_KEEP_VERBATIM
    old_episodes = all_eps[:cutoff]

    if not old_episodes:
        return ""

    # Build compressed highlights (rule-based, no LLM)
    highlights: list[str] = []
    for ep in old_episodes:
        text = ep["text"]
        date_str = ep["created_at"][:10] if ep.get("created_at") else "unknown"
        # Extract the first meaningful line (usually "Teacher: <message>")
        first_line = text.split("\n")[0].strip()
        if len(first_line) > 120:
            first_line = first_line[:117] + "..."
        highlights.append(f"- [{date_str}] {first_line}")

    summary_header = (
        "# Memory Summary — Compressed Episode Highlights\n\n"
        f"*{len(old_episodes)} older episodes compressed. "
        f"Last {min(EPISODES_TO_KEEP_VERBATIM, total)} episodes kept verbatim in episodic memory.*\n\n"
    )
    summary_body = "\n".join(highlights) + "\n"
    summary_text = summary_header + summary_body

    # Write summary to disk
    summary_path = _get_memory_summary_path()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary_text, encoding="utf-8")

    logger.info(
        "Compressed %d old episodes into memory_summary.md for teacher %s",
        len(old_episodes), teacher_id,
    )
    return summary_text


def maybe_compress_episodes(teacher_id: str) -> str:
    """Trigger compression if the episode count crosses a threshold.

    Should be called after storing a new episode.  Compression runs
    every ``COMPRESSION_THRESHOLD`` episodes.

    Returns the summary text if compression ran, empty string otherwise.
    """
    from clawed.agent_core.memory.episodes import EpisodicMemory

    mem = EpisodicMemory()
    total = mem.count_episodes(teacher_id)

    if total > 0 and total % COMPRESSION_THRESHOLD == 0:
        return compress_old_episodes(teacher_id)
    return ""


# ── Preference drift detection ────────────────────────────────────────

DRIFT_WINDOW_SIZE = 10  # Rolling window of ratings to compare
DRIFT_THRESHOLD = 0.5   # Minimum average change to trigger an alert


def _get_rating_history_path() -> Path:
    """Get the rating_history.json path."""
    return _base_dir() / "rating_history.json"


def _load_rating_history() -> list[int]:
    """Load the chronological list of ratings from disk."""
    path = _get_rating_history_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_rating_history(ratings: list[int]) -> None:
    """Persist the rating history to disk."""
    path = _get_rating_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ratings), encoding="utf-8")


def detect_preference_drift(rating: int) -> str | None:
    """Track ratings and detect quality drift across a rolling window.

    Appends ``rating`` to the history.  When at least two full windows
    exist (``2 * DRIFT_WINDOW_SIZE`` ratings), compares the current
    window average to the prior window.

    Returns a drift message if detected (also logged to memory.md),
    or ``None`` if no meaningful drift.
    """
    ratings = _load_rating_history()
    ratings.append(rating)
    _save_rating_history(ratings)

    needed = 2 * DRIFT_WINDOW_SIZE
    if len(ratings) < needed:
        return None

    current_window = ratings[-DRIFT_WINDOW_SIZE:]
    prior_window = ratings[-needed:-DRIFT_WINDOW_SIZE]

    current_avg = sum(current_window) / len(current_window)
    prior_avg = sum(prior_window) / len(prior_window)
    diff = current_avg - prior_avg

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
    message: str | None = None

    if diff < -DRIFT_THRESHOLD:
        message = (
            f"[{timestamp}] Your recent lessons are rating lower "
            f"(avg {current_avg:.1f} vs prior {prior_avg:.1f}) "
            "— consider reviewing what changed."
        )
    elif diff > DRIFT_THRESHOLD:
        message = (
            f"[{timestamp}] Ratings are improving! "
            f"(avg {current_avg:.1f} vs prior {prior_avg:.1f}) "
            "— keep up the great work."
        )

    if message:
        _log_drift_to_memory(message)

    return message


def _log_drift_to_memory(message: str) -> None:
    """Append a drift alert to the Drift Alerts section of memory.md."""
    content = _read_memory()
    content = _append_to_section(content, "Drift Alerts", message)
    _write_memory(content)
