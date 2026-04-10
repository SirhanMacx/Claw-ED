"""Clean garbage entities from the Knowledge Graph.

Removes OCR artifacts, formatting junk, and low-quality entities that
pollute KG query results. Run after ingestion to improve connection quality.

Usage: python -X utf8 scripts/kg_cleanup.py [--dry-run]
"""
import re
import sqlite3
import sys


def cleanup_kg(dry_run: bool = False) -> dict:
    """Remove garbage entities and their associated triples.

    Returns stats on what was removed.
    """
    from clawed.config import _BASE_DIR

    db_path = _BASE_DIR / "memory" / "curriculum_kb.db"
    if not db_path.exists():
        print(f"KG database not found: {db_path}")
        return {}

    conn = sqlite3.connect(str(db_path))

    # Count before
    ent_before = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
    tri_before = conn.execute("SELECT COUNT(*) FROM kg_triples").fetchone()[0]

    # Rules for garbage entities
    garbage_ids: set[str] = set()

    rows = conn.execute("SELECT id, name FROM kg_entities").fetchall()
    for eid, name in rows:
        if _is_garbage(name):
            garbage_ids.add(eid)

    print(f"Entities before: {ent_before}")
    print(f"Garbage entities found: {len(garbage_ids)}")

    if dry_run:
        # Show samples
        samples = list(garbage_ids)[:20]
        sample_names = conn.execute(
            f"SELECT id, name FROM kg_entities WHERE id IN "
            f"({','.join('?' for _ in samples)})",
            samples,
        ).fetchall()
        print("Sample garbage entries:")
        for eid, name in sample_names:
            print(f"  [{eid}] {repr(name)[:80]}")
        print("\nDry run — no changes made. Run without --dry-run to clean.")
        conn.close()
        return {"garbage_found": len(garbage_ids), "dry_run": True}

    # Delete garbage entities and their triples
    if garbage_ids:
        # Delete in batches to avoid SQLite limits
        batch_size = 500
        garbage_list = list(garbage_ids)
        for i in range(0, len(garbage_list), batch_size):
            batch = garbage_list[i:i + batch_size]
            placeholders = ",".join("?" for _ in batch)

            # Delete triples where garbage is subject or object
            conn.execute(
                f"DELETE FROM kg_triples WHERE subject IN ({placeholders})",
                batch,
            )
            conn.execute(
                f"DELETE FROM kg_triples WHERE object IN ({placeholders})",
                batch,
            )
            # Delete the entities
            conn.execute(
                f"DELETE FROM kg_entities WHERE id IN ({placeholders})",
                batch,
            )

        conn.commit()

    # Count after
    ent_after = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
    tri_after = conn.execute("SELECT COUNT(*) FROM kg_triples").fetchone()[0]

    conn.close()

    stats = {
        "entities_before": ent_before,
        "entities_after": ent_after,
        "entities_removed": ent_before - ent_after,
        "triples_before": tri_before,
        "triples_after": tri_after,
        "triples_removed": tri_before - tri_after,
    }

    print(f"\nEntities: {ent_before} -> {ent_after} (removed {stats['entities_removed']})")
    print(f"Triples: {tri_before} -> {tri_after} (removed {stats['triples_removed']})")
    return stats


_GENERIC_STOPWORDS = {
    # Single common words that aren't curriculum entities
    "things", "stuff", "people", "person", "place", "time", "way", "day",
    "year", "thing", "way", "world", "life", "work", "ways", "years", "days",
    "first", "second", "third", "next", "last", "new", "old", "big", "small",
    "many", "few", "some", "any", "all", "every", "each", "other", "another",
    "what", "when", "where", "why", "how", "who", "which",
    "this", "that", "these", "those",
    "good", "bad", "right", "wrong", "true", "false",
    # Generic education terms (not curriculum-specific)
    "lesson", "lessons", "class", "classes", "students", "student",
    "teacher", "teachers", "school", "schools", "homework", "test", "quiz",
    "worksheet", "handout", "notes", "note", "page", "pages",
    "chapter", "section", "unit", "units", "review", "reviews",
    "today", "tomorrow", "yesterday", "week", "weeks", "month",
    # Verbs that aren't entities
    "read", "write", "complete", "answer", "answers", "explain", "describe",
    "list", "identify", "discuss", "compare", "contrast", "analyze",
    # Phrases without entities
    "key terms", "key words", "key vocabulary", "key concepts",
    "all societies", "modern world", "present day",
    "important", "main idea", "main ideas",
}


def _is_garbage(name: str) -> bool:
    """Detect garbage entity names from OCR/formatting artifacts.

    Aggressive: catches OCR junk, fill-in-the-blank artifacts, generic
    stopwords, single-word common nouns, and entities that don't represent
    real curriculum concepts.
    """
    if not name or not name.strip():
        return True

    clean = name.strip()
    clean_lower = clean.lower()

    # Too short (single chars, punctuation)
    if len(clean) < 4:
        return True

    # Generic stopword (single common word)
    if clean_lower in _GENERIC_STOPWORDS:
        return True

    # Contains newlines or tabs (OCR artifact)
    if "\n" in clean or "\t" in clean or "\r" in clean:
        return True

    # Mostly underscores (fill-in-the-blank formatting)
    if clean.count("_") > len(clean) * 0.25:
        return True

    # Starts/ends with punctuation (formatting artifact)
    if clean[0] in ",:;.!?|/\\#@$%^&*()[]{}" or clean[-1] in ",:;|/\\":
        return True

    # Contains only numbers and punctuation
    if re.match(r"^[\d\s.,:;/\-]+$", clean):
        return True

    # Very long (OCR dump)
    if len(clean) > 80:
        return True

    # Looks like a filename
    if any(
        ext in clean_lower for ext in [".pptx", ".docx", ".pdf", ".jpg", ".png", ".gif", ".mp4"]
    ):
        return True

    # Contains HTML/XML fragments
    if "<" in clean and ">" in clean:
        return True

    # URL-like
    if "://" in clean or clean_lower.startswith(("www.", "http")):
        return True

    # Multiple words jammed together (CamelCase OCR fail)
    capitals_no_space = re.findall(r"[A-Z][a-z]+[A-Z]", clean)
    if len(capitals_no_space) > 2:
        return True

    # Single word that's overly generic (e.g. "consequences", "things")
    if " " not in clean and len(clean) < 15:
        # Common single-word stopword family
        generic_singles = [
            "consequences", "results", "outcomes", "effects", "causes",
            "examples", "instances", "items", "options", "choices",
            "parts", "pieces", "sections", "groups", "teams",
            "ideas", "concepts", "topics", "subjects", "areas",
            "facts", "statements", "claims", "points",
            "questions", "problems", "issues", "matters",
            "details", "elements", "features", "aspects",
        ]
        if clean_lower in generic_singles:
            return True

    # Common formatting artifacts
    garbage_patterns = [
        r"^name\b",  # "name:______"
        r"^date\b",  # "date:______"
        r"^period\b",  # "period:____"
        r"^page\s*\d",  # "page 1"
        r"^directions?\b",  # "directions:"
        r"^answer\s*key",  # "answer key"
        r"^answer\b\s*$",  # just "answer"
        r"^\d+\s*\.\s*$",  # "1. " (numbered list artifact)
        r"^key\s*(words?|terms?|vocabulary|concepts?|points?|ideas?)\b",
        r"^(true|false)\b",
        r"^(yes|no)\b",
        r"^none\b",
        r"^n/?a\b",
        r"^all\s+",  # "all things", "all of them"
        r"^the\s+(thing|stuff|way|idea|main)\b",
        r"^[a-z]\s*$",  # single letter
        r"^\d+\s*$",  # just a number
        r"^q\d",  # "q1", "q2"
        r"^homework$|^class\s*work$|^classwork$",
        r"^chapter\s*\d",  # "chapter 1"
        r"^unit\s*\d",  # "unit 1"
        r"^lesson\s*\d",  # "lesson 1"
        r"^week\s*\d",
        r"^day\s*\d",
        r"^step\s*\d",
        r"^part\s*\d",
        r"^figure\s*\d",
        r"^table\s*\d",
        r"^item\s*\d",
        r"^section\s*\d",
        r"^\.\.\.+$",  # ellipsis
        r"^[ivx]+\s*$",  # roman numerals alone
    ]
    for pattern in garbage_patterns:
        if re.match(pattern, clean, re.IGNORECASE):
            return True

    return False


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    cleanup_kg(dry_run=dry_run)
