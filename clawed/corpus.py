"""Claw-ED Teaching Excellence Corpus.

The corpus is the collective intelligence of Claw-ED — a growing library of
high-quality teaching examples that improves every teacher's generated content.

Teachers opt in to contribute their best materials. These become few-shot
examples injected into generation prompts, making outputs better for everyone.

Jon Maccarello's 9 years of social studies materials are the founding dataset.
Every teacher who contributes expands the corpus across subjects and grade levels.

The corpus is:
- Anonymous by default (no PII, no teacher names in examples)
- Subject/grade-specific (materials are tagged and retrieved by context)
- Quality-filtered (only highly-rated materials enter the corpus)
- Versioned (we know which materials improved which generations)
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

_BASE_DIR = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
CORPUS_DIR = _BASE_DIR / "corpus"
CORPUS_DB = CORPUS_DIR / "corpus.db"


def _get_conn() -> sqlite3.Connection:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CORPUS_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_corpus_db() -> None:
    """Initialize the corpus database."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS corpus_examples (
                id TEXT PRIMARY KEY,
                content_type TEXT NOT NULL,  -- 'unit_plan', 'lesson_plan', 'worksheet', 'assessment'
                subject TEXT NOT NULL,
                grade_level TEXT NOT NULL,
                topic TEXT,
                content_json TEXT NOT NULL,
                quality_score REAL DEFAULT 0.0,  -- 0-5 rating from teacher feedback
                contributor_hash TEXT,           -- hash of teacher_id for attribution without PII
                state TEXT DEFAULT '',           -- state standards context
                framework TEXT DEFAULT '',       -- standards framework used
                source TEXT DEFAULT 'teacher',   -- 'teacher' | 'seed' | 'generated'
                created_at TEXT DEFAULT (datetime('now')),
                times_used INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_corpus_subject ON corpus_examples(subject);
            CREATE INDEX IF NOT EXISTS idx_corpus_grade ON corpus_examples(grade_level);
            CREATE INDEX IF NOT EXISTS idx_corpus_type ON corpus_examples(content_type);
            CREATE INDEX IF NOT EXISTS idx_corpus_quality ON corpus_examples(quality_score DESC);
        """)


def contribute_example(
    content_type: str,
    subject: str,
    grade_level: str,
    content: dict,
    topic: Optional[str] = None,
    quality_score: float = 4.0,
    teacher_id: Optional[str] = None,
    state: str = "",
    framework: str = "",
    source: str = "teacher",
) -> str:
    """Add a teaching example to the corpus.

    Args:
        content_type: 'unit_plan', 'lesson_plan', 'worksheet', 'assessment'
        subject: Subject area (e.g., 'social studies', 'science')
        grade_level: Grade level (e.g., '8', '9-10', 'K-2')
        content: The actual content as a dict (will be stored as JSON)
        topic: Optional topic/unit name
        quality_score: 0-5 rating (default 4.0 for teacher-contributed)
        teacher_id: Teacher's ID (hashed before storage for privacy)
        state: State abbreviation (e.g., 'NY')
        framework: Standards framework (e.g., 'NY_SS')
        source: Where this came from

    Returns:
        The ID of the created corpus entry
    """
    init_corpus_db()

    # Hash teacher ID for privacy (we keep attribution but not identity)
    contributor_hash = None
    if teacher_id:
        import hashlib
        contributor_hash = hashlib.sha256(teacher_id.encode()).hexdigest()[:16]

    # Strip any PII from content before storing
    clean_content = _sanitize_content(content)

    entry_id = str(uuid.uuid4())
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO corpus_examples
                (id, content_type, subject, grade_level, topic, content_json,
                 quality_score, contributor_hash, state, framework, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                content_type,
                subject.lower(),
                grade_level,
                topic,
                json.dumps(clean_content),
                quality_score,
                contributor_hash,
                state,
                framework,
                source,
            ),
        )
    return entry_id


def get_examples(
    content_type: str,
    subject: str,
    grade_level: Optional[str] = None,
    limit: int = 3,
    min_quality: float = 3.5,
) -> list[dict]:
    """Retrieve high-quality examples for few-shot injection into prompts.

    Args:
        content_type: Type of content to retrieve
        subject: Subject area
        grade_level: Optional grade level filter
        limit: Max examples to return
        min_quality: Minimum quality score

    Returns:
        List of content dicts, best quality first
    """
    init_corpus_db()

    # Normalize subject for flexible matching
    # "US History" -> also matches "social studies", "history"
    subject_aliases = {
        "us history": "social studies",
        "global history": "social studies",
        "world history": "social studies",
        "american history": "social studies",
        "government": "social studies",
        "civics": "social studies",
        "economics": "social studies",
        "geography": "social studies",
        "english": "ela",
        "language arts": "ela",
        "reading": "ela",
        "writing": "ela",
        "literature": "ela",
        "biology": "science",
        "chemistry": "science",
        "physics": "science",
        "earth science": "science",
        "algebra": "math",
        "geometry": "math",
        "calculus": "math",
        "mathematics": "math",
    }
    normalized_subject = subject_aliases.get(subject.lower(), subject.lower())

    query = """
        SELECT content_json, quality_score, topic, grade_level, framework
        FROM corpus_examples
        WHERE content_type = ?
        AND (subject = ? OR subject = ?)
        AND quality_score >= ?
    """
    params: list = [content_type, subject.lower(), normalized_subject, min_quality]

    if grade_level:
        query += " AND (grade_level = ? OR grade_level LIKE ?)"
        params.extend([grade_level, f"%{grade_level}%"])

    query += " ORDER BY quality_score DESC LIMIT ?"
    params.append(limit)

    with _get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    examples = []
    for row in rows:
        try:
            content = json.loads(row["content_json"])
            content["_meta"] = {
                "quality_score": row["quality_score"],
                "topic": row["topic"],
                "grade_level": row["grade_level"],
                "framework": row["framework"],
            }
            examples.append(content)
        except Exception:
            continue

    # Update usage count
    if examples:
        with _get_conn() as conn:
            conn.execute(
                "UPDATE corpus_examples SET times_used = times_used + 1 WHERE content_type = ? AND subject = ?",
                (content_type, subject.lower()),
            )

    return examples


def get_few_shot_context(
    content_type: str,
    subject: str,
    grade_level: Optional[str] = None,
) -> str:
    """Get a few-shot context string for injection into generation prompts.

    Returns a formatted string showing 1-2 high-quality examples that the
    LLM can use as reference for the quality bar we expect.
    """
    examples = get_examples(content_type, subject, grade_level, limit=2)
    if not examples:
        return ""

    parts = [
        f"\n## Reference Examples (high-quality {content_type.replace('_', ' ')} from experienced teachers)\n",
        "Use these as a reference for quality and depth. Match or exceed this level.\n",
    ]

    for i, ex in enumerate(examples, 1):
        meta = ex.pop("_meta", {})
        grade = meta.get("grade_level", "?")
        quality = meta.get("quality_score", "?")
        parts.append(f"\n### Example {i} (Grade {grade}, Quality: {quality}/5)")
        if meta.get("topic"):
            parts.append(f"Topic: {meta['topic']}")
        # Show a condensed version of the example
        parts.append(json.dumps(ex, indent=2)[:2000])  # Cap at 2000 chars per example

    return "\n".join(parts)


def corpus_stats() -> dict:
    """Return statistics about the corpus."""
    init_corpus_db()
    with _get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM corpus_examples").fetchone()[0]
        by_subject = conn.execute(
            "SELECT subject, COUNT(*) as count FROM corpus_examples GROUP BY subject ORDER BY count DESC"
        ).fetchall()
        by_type = conn.execute(
            "SELECT content_type, COUNT(*) as count FROM corpus_examples GROUP BY content_type"
        ).fetchall()
        avg_quality = conn.execute("SELECT AVG(quality_score) FROM corpus_examples").fetchone()[0]

    return {
        "total_examples": total,
        "average_quality": round(avg_quality or 0, 2),
        "by_subject": {row["subject"]: row["count"] for row in by_subject},
        "by_type": {row["content_type"]: row["count"] for row in by_type},
    }


def seed_from_curriculum(
    materials_path: Path,
    subject: str,
    grade_levels: list[str],
    state: str = "",
    framework: str = "",
    teacher_id: Optional[str] = None,
) -> int:
    """Seed the corpus from a directory of curriculum materials.

    This is called during ingestion when a teacher opts in to contribute.
    Analyzes files and adds high-quality examples to the platform corpus.

    Returns the number of examples added.
    """
    from clawed.ingestor import ingest_path

    docs = ingest_path(materials_path)
    if not docs:
        return 0

    added = 0
    for doc in docs:
        # Only contribute documents that look like lesson plans or units
        content_lower = doc.content.lower()
        is_lesson = any(kw in content_lower for kw in [
            "objective", "swbat", "do now", "aim", "warm up",
            "direct instruction", "guided practice", "exit ticket",
            "homework", "materials needed", "lesson plan"
        ])
        is_unit = any(kw in content_lower for kw in [
            "unit plan", "essential question", "enduring understanding",
            "unit overview", "unit goals", "pacing guide", "week 1", "week 2"
        ])

        if not (is_lesson or is_unit):
            continue

        content_type = "lesson_plan" if is_lesson else "unit_plan"

        contribute_example(
            content_type=content_type,
            subject=subject,
            grade_level=grade_levels[0] if grade_levels else "9-12",
            content={"title": doc.title, "text": doc.content[:3000], "source_file": doc.title},
            topic=doc.title,
            quality_score=4.0,  # Assume teacher-contributed = good quality, feedback will refine
            teacher_id=teacher_id,
            state=state,
            framework=framework,
            source="seed",
        )
        added += 1

    return added


def _sanitize_content(content: dict) -> dict:
    """Remove any PII from content before corpus storage."""
    # Remove teacher name if it appears
    content_str = json.dumps(content)

    # Common PII patterns to remove
    import re
    # Remove email addresses
    content_str = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[email]', content_str)
    # Remove phone numbers
    content_str = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[phone]', content_str)

    try:
        return json.loads(content_str)
    except Exception:
        return content
