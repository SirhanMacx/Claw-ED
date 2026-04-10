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


def _is_garbage(name: str) -> bool:
    """Detect garbage entity names from OCR/formatting artifacts."""
    if not name or not name.strip():
        return True

    clean = name.strip()

    # Too short (single chars, punctuation)
    if len(clean) < 3:
        return True

    # Contains newlines or tabs (OCR artifact)
    if "\n" in clean or "\t" in clean:
        return True

    # Mostly underscores (fill-in-the-blank formatting)
    if clean.count("_") > len(clean) * 0.3:
        return True

    # Starts/ends with punctuation (formatting artifact)
    if clean[0] in ",:;.!?|/\\" or clean[-1] in ",:;":
        return True

    # Contains only numbers and punctuation
    if re.match(r"^[\d\s.,:;/\-]+$", clean):
        return True

    # Very long (likely OCR dump, not a real entity name)
    if len(clean) > 100:
        return True

    # Looks like a filename or path
    if any(ext in clean.lower() for ext in [".pptx", ".docx", ".pdf", ".jpg", ".png"]):
        return True

    # Contains HTML/XML fragments
    if "<" in clean and ">" in clean:
        return True

    # Multiple words jammed together (e.g., "AztecsRenaissanceHumanism")
    # Heuristic: 3+ capital letters in sequence without spaces
    capitals_no_space = re.findall(r"[A-Z][a-z]+[A-Z]", clean)
    if len(capitals_no_space) > 2:
        return True

    # Common formatting artifacts
    garbage_patterns = [
        r"^name\b",  # "name:______"
        r"^date\b",  # "date:______"
        r"^period\b",  # "period:____"
        r"^page\s*\d",  # "page 1"
        r"^directions?\b",  # "directions:"
        r"^answer\b",  # "answer key"
        r"^\d+\s*\.\s*$",  # "1. " (numbered list artifact)
        r"^key\s*(words?|terms?|vocabulary)\b",  # "key words", "key terms"
        r"^(true|false)\b",  # "true/false"
        r"^(yes|no)\b",  # "yes/no"
        r"^none\b",  # "none"
        r"^n/?a\b",  # "n/a"
    ]
    for pattern in garbage_patterns:
        if re.match(pattern, clean, re.IGNORECASE):
            return True

    return False


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    cleanup_kg(dry_run=dry_run)
