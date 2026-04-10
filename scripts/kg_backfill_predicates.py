"""Backfill prerequisite_for / builds_on relationships in the existing KG.

The original ingestion only created `related_to` relationships. This script
scans the existing kg_entities table for entities whose names match lesson
ordering patterns ("Lesson 1", "Day 2", "Part 3", etc.) and inserts
prerequisite_for + builds_on triples between consecutive lessons in the
same unit.

Usage: python -X utf8 scripts/kg_backfill_predicates.py [--dry-run]
"""
import hashlib
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_SEQUENCE_PAT = re.compile(
    r"(?:lesson|day|class|session|part)\s*(\d+)",
    re.IGNORECASE,
)


def _normalize_id(name: str) -> str:
    """Match knowledge_graph._normalize_id."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s[:120]


def _triple_hash(teacher_id: str, subj_id: str, predicate: str, obj_id: str) -> str:
    raw = f"{teacher_id}|{subj_id}|{predicate}|{obj_id}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def backfill_predicates(dry_run: bool = False) -> dict:
    """Add prerequisite_for and builds_on triples to the KG."""
    db_path = Path.home() / ".eduagent" / "memory" / "curriculum_kb.db"
    if not db_path.exists():
        print(f"KG database not found: {db_path}")
        return {}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Pull all topic entities (these are the lesson titles)
    rows = conn.execute(
        "SELECT id, teacher_id, name FROM kg_entities WHERE entity_type IN ('topic', 'unit')"
    ).fetchall()

    print(f"Scanning {len(rows)} topic/unit entities...")

    # Group by unit_key (entity name with sequence stripped)
    buckets: dict[tuple[str, str], list[tuple[int, str, str]]] = {}
    for row in rows:
        eid = row["id"]
        teacher_id = row["teacher_id"]
        name = row["name"]
        m = _SEQUENCE_PAT.search(name)
        if not m:
            continue
        seq = int(m.group(1))
        # Unit key = name with sequence stripped
        unit_key = _SEQUENCE_PAT.sub("", name).strip().lower()
        unit_key = re.sub(r"\s+", " ", unit_key)
        if not unit_key:
            continue
        key = (teacher_id, unit_key)
        buckets.setdefault(key, []).append((seq, eid, name))

    # Build the triples to insert
    new_triples = []
    for (teacher_id, unit_key), items in buckets.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: x[0])
        for i in range(len(items) - 1):
            current_seq, current_id, current_name = items[i]
            next_seq, next_id, next_name = items[i + 1]
            # Skip if not actually sequential
            if next_seq != current_seq + 1:
                continue

            # builds_on: next_lesson builds_on current_lesson
            new_triples.append({
                "id": _triple_hash(teacher_id, next_id, "builds_on", current_id),
                "teacher_id": teacher_id,
                "subject": next_id,
                "predicate": "builds_on",
                "object": current_id,
                "confidence": 0.85,
            })
            # prerequisite_for: current_lesson is prerequisite_for next_lesson
            new_triples.append({
                "id": _triple_hash(teacher_id, current_id, "prerequisite_for", next_id),
                "teacher_id": teacher_id,
                "subject": current_id,
                "predicate": "prerequisite_for",
                "object": next_id,
                "confidence": 0.85,
            })

    print(f"Found {len(buckets)} unit buckets with sequential lessons")
    print(f"Would insert {len(new_triples)} new triples")

    if dry_run:
        print("\nSample triples to insert:")
        for t in new_triples[:10]:
            sub_name = conn.execute(
                "SELECT name FROM kg_entities WHERE id = ?", (t["subject"],)
            ).fetchone()
            obj_name = conn.execute(
                "SELECT name FROM kg_entities WHERE id = ?", (t["object"],)
            ).fetchone()
            print(f"  {sub_name['name'] if sub_name else t['subject'][:30]} "
                  f"--{t['predicate']}--> "
                  f"{obj_name['name'] if obj_name else t['object'][:30]}")
        conn.close()
        return {"would_insert": len(new_triples), "dry_run": True}

    # Insert triples (INSERT OR IGNORE to skip duplicates)
    now = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    for t in new_triples:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO kg_triples "
                "(id, teacher_id, subject, predicate, object, valid_from, "
                "valid_to, confidence, source, source_path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)",
                (
                    t["id"],
                    t["teacher_id"],
                    t["subject"],
                    t["predicate"],
                    t["object"],
                    now,
                    t["confidence"],
                    "lesson_ordering_inference",
                    "",
                    now,
                ),
            )
            if conn.total_changes > 0:
                inserted += 1
        except Exception as e:
            print(f"  Insert failed: {e}")

    conn.commit()

    # Verify counts
    counts_by_predicate = conn.execute(
        "SELECT predicate, COUNT(*) FROM kg_triples GROUP BY predicate "
        "ORDER BY COUNT(*) DESC"
    ).fetchall()

    print(f"\nInserted {inserted} new triples")
    print("\nKG predicate distribution after backfill:")
    for row in counts_by_predicate:
        print(f"  {row[0]}: {row[1]}")

    conn.close()
    return {"inserted": inserted}


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    backfill_predicates(dry_run=dry_run)
