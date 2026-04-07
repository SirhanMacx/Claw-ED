"""Curriculum Knowledge Graph — temporal triples over educational concepts.

Maps relationships between topics, standards, skills, figures, and vocabulary
so Ed can inject curriculum context (prerequisites, related concepts, standard
alignments) into lesson generation prompts.

Inspired by MemPalace's knowledge_graph.py, adapted for education. Stored in
curriculum_kb.db alongside chunks and assets. Entities are auto-created on
triple insertion for fast ingestion. Temporal windows track when topics were
taught and when alignments are valid.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".eduagent" / "memory" / "curriculum_kb.db"

VALID_ENTITY_TYPES = frozenset({
    "topic", "standard", "skill", "figure", "term", "unit",
})

VALID_PREDICATES = frozenset({
    "prerequisite_for", "builds_on", "covers_standard", "related_to",
    "contrasts_with", "taught_in", "assessed_by", "includes_vocab",
    "aligned_to", "part_of",
})


def _normalize_id(name: str) -> str:
    """Normalize entity name to a stable ID.

    'American Revolution' -> 'american_revolution'
    """
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s[:120]


def _embed_to_blob(vec: list[float]) -> bytes:
    import struct
    return struct.pack(f"<{len(vec)}f", *vec)


def _blob_to_embed(blob: bytes) -> list[float]:
    import struct
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


class CurriculumKG:
    """Curriculum knowledge graph with temporal triples."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kg_entities (
                    id TEXT PRIMARY KEY,
                    teacher_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    entity_type TEXT DEFAULT 'topic',
                    properties TEXT DEFAULT '{}',
                    embedding BLOB,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_kg_ent_teacher
                    ON kg_entities(teacher_id);

                CREATE INDEX IF NOT EXISTS idx_kg_ent_type
                    ON kg_entities(teacher_id, entity_type);

                CREATE TABLE IF NOT EXISTS kg_triples (
                    id TEXT PRIMARY KEY,
                    teacher_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    valid_from TEXT,
                    valid_to TEXT,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'auto',
                    source_path TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (subject) REFERENCES kg_entities(id),
                    FOREIGN KEY (object) REFERENCES kg_entities(id)
                );

                CREATE INDEX IF NOT EXISTS idx_kg_triple_subj
                    ON kg_triples(teacher_id, subject);
                CREATE INDEX IF NOT EXISTS idx_kg_triple_obj
                    ON kg_triples(teacher_id, object);
                CREATE INDEX IF NOT EXISTS idx_kg_triple_pred
                    ON kg_triples(teacher_id, predicate);
                CREATE INDEX IF NOT EXISTS idx_kg_triple_valid
                    ON kg_triples(valid_from, valid_to);
            """)

    # ── Entity operations ────────────────────────────────────────────

    def add_entity(
        self,
        teacher_id: str,
        name: str,
        entity_type: str = "topic",
        properties: dict[str, Any] | None = None,
        embed: bool = True,
    ) -> str:
        """Add or update an entity. Returns the normalized entity ID."""
        eid = _normalize_id(name)
        if not eid:
            return ""

        now = datetime.utcnow().isoformat()
        embedding_blob = None
        if embed:
            try:
                from clawed.agent_core.memory.embeddings import get_embedder
                vec = get_embedder().embed(name)
                embedding_blob = _embed_to_blob(vec)
            except Exception:
                pass

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO kg_entities "
                "(id, teacher_id, name, entity_type, properties, embedding, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "updated_at=excluded.updated_at, "
                "embedding=COALESCE(excluded.embedding, kg_entities.embedding)",
                (
                    eid, teacher_id, name, entity_type,
                    json.dumps(properties or {}),
                    embedding_blob, now, now,
                ),
            )
        return eid

    def add_triple(
        self,
        teacher_id: str,
        subject: str,
        predicate: str,
        object_: str,
        valid_from: str | None = None,
        valid_to: str | None = None,
        confidence: float = 1.0,
        source: str = "auto",
        source_path: str = "",
    ) -> str:
        """Add a relationship triple. Auto-creates entities if needed."""
        subj_id = _normalize_id(subject)
        obj_id = _normalize_id(object_)
        pred = predicate.lower().replace(" ", "_").replace("-", "_")

        if not subj_id or not obj_id or not pred:
            return ""

        # Auto-create entities (no embedding during bulk ingest — use batch_embed later)
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO kg_entities "
                "(id, teacher_id, name, entity_type, properties, created_at, updated_at) "
                "VALUES (?, ?, ?, 'topic', '{}', ?, ?)",
                (subj_id, teacher_id, subject, now, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO kg_entities "
                "(id, teacher_id, name, entity_type, properties, created_at, updated_at) "
                "VALUES (?, ?, ?, 'topic', '{}', ?, ?)",
                (obj_id, teacher_id, object_, now, now),
            )

            # Triple ID: deterministic hash for dedup
            raw = f"{subj_id}_{pred}_{obj_id}"
            h = hashlib.md5(raw.encode()).hexdigest()[:8]
            triple_id = f"t_{subj_id[:30]}_{pred[:20]}_{obj_id[:30]}_{h}"

            conn.execute(
                "INSERT OR IGNORE INTO kg_triples "
                "(id, teacher_id, subject, predicate, object, "
                "valid_from, valid_to, confidence, source, source_path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    triple_id, teacher_id, subj_id, pred, obj_id,
                    valid_from, valid_to, confidence, source, source_path, now,
                ),
            )
        return triple_id

    def invalidate(self, teacher_id: str, triple_id: str) -> bool:
        """Mark a triple as expired by setting valid_to=now."""
        now = datetime.utcnow().isoformat()[:10]
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "UPDATE kg_triples SET valid_to = ? "
                "WHERE id = ? AND teacher_id = ? AND valid_to IS NULL",
                (now, triple_id, teacher_id),
            )
            return cur.rowcount > 0

    # ── Query operations ─────────────────────────────────────────────

    def query_entity(
        self,
        teacher_id: str,
        name: str,
    ) -> dict[str, Any] | None:
        """Get an entity by name with relationship counts."""
        eid = _normalize_id(name)
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM kg_entities WHERE id = ? AND teacher_id = ?",
                (eid, teacher_id),
            ).fetchone()
            if not row:
                return None
            out_count = conn.execute(
                "SELECT COUNT(*) FROM kg_triples "
                "WHERE teacher_id = ? AND subject = ? AND valid_to IS NULL",
                (teacher_id, eid),
            ).fetchone()[0]
            in_count = conn.execute(
                "SELECT COUNT(*) FROM kg_triples "
                "WHERE teacher_id = ? AND object = ? AND valid_to IS NULL",
                (teacher_id, eid),
            ).fetchone()[0]
            return {
                "id": row["id"],
                "name": row["name"],
                "entity_type": row["entity_type"],
                "properties": json.loads(row["properties"] or "{}"),
                "outgoing_count": out_count,
                "incoming_count": in_count,
            }

    def query_related(
        self,
        teacher_id: str,
        entity_name: str,
        predicate: str | None = None,
        direction: str = "both",
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        """Find entities related to the given one."""
        eid = _normalize_id(entity_name)
        results: list[dict[str, Any]] = []

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            valid_clause = "" if include_expired else " AND t.valid_to IS NULL"

            if direction in ("outgoing", "both"):
                pred_clause = " AND t.predicate = ?" if predicate else ""
                params: list[Any] = [teacher_id, eid]
                if predicate:
                    params.append(predicate)
                rows = conn.execute(
                    f"SELECT t.*, e.name AS target_name, e.entity_type AS target_type "
                    f"FROM kg_triples t "
                    f"JOIN kg_entities e ON t.object = e.id "
                    f"WHERE t.teacher_id = ? AND t.subject = ?"
                    f"{pred_clause}{valid_clause} "
                    f"ORDER BY t.confidence DESC",
                    params,
                ).fetchall()
                for r in rows:
                    results.append({
                        "direction": "outgoing",
                        "predicate": r["predicate"],
                        "entity": r["target_name"],
                        "entity_type": r["target_type"],
                        "confidence": r["confidence"],
                        "valid_from": r["valid_from"],
                        "valid_to": r["valid_to"],
                        "triple_id": r["id"],
                    })

            if direction in ("incoming", "both"):
                pred_clause = " AND t.predicate = ?" if predicate else ""
                params = [teacher_id, eid]
                if predicate:
                    params.append(predicate)
                rows = conn.execute(
                    f"SELECT t.*, e.name AS source_name, e.entity_type AS source_type "
                    f"FROM kg_triples t "
                    f"JOIN kg_entities e ON t.subject = e.id "
                    f"WHERE t.teacher_id = ? AND t.object = ?"
                    f"{pred_clause}{valid_clause} "
                    f"ORDER BY t.confidence DESC",
                    params,
                ).fetchall()
                for r in rows:
                    results.append({
                        "direction": "incoming",
                        "predicate": r["predicate"],
                        "entity": r["source_name"],
                        "entity_type": r["source_type"],
                        "confidence": r["confidence"],
                        "valid_from": r["valid_from"],
                        "valid_to": r["valid_to"],
                        "triple_id": r["id"],
                    })

        return results

    def get_prerequisites(
        self,
        teacher_id: str,
        topic_name: str,
    ) -> list[dict[str, Any]]:
        """Get prerequisite topics for a given topic."""
        prereqs = self.query_related(
            teacher_id, topic_name,
            predicate="prerequisite_for", direction="incoming",
        )
        builds = self.query_related(
            teacher_id, topic_name,
            predicate="builds_on", direction="outgoing",
        )
        seen = set()
        result = []
        for r in prereqs + builds:
            name = r["entity"]
            if name not in seen:
                seen.add(name)
                result.append(r)
        return sorted(result, key=lambda x: x["confidence"], reverse=True)

    def get_topic_context(
        self,
        teacher_id: str,
        topic_name: str,
        max_relations: int = 15,
    ) -> str:
        """Render a formatted text block for prompt injection."""
        related = self.query_related(teacher_id, topic_name)
        if not related:
            # Try semantic entity search as fallback
            matches = self.search_entities(teacher_id, topic_name, top_k=1)
            if matches:
                related = self.query_related(teacher_id, matches[0]["name"])

        if not related:
            return ""

        prereqs = []
        standards = []
        vocab = []
        related_topics = []

        for r in related[:max_relations]:
            pred = r["predicate"]
            name = r["entity"]
            if pred in ("prerequisite_for", "builds_on"):
                prereqs.append(name)
            elif pred == "covers_standard":
                standards.append(name)
            elif pred == "includes_vocab":
                vocab.append(name)
            else:
                related_topics.append(name)

        parts = []
        if prereqs:
            parts.append(f"Prerequisites: {', '.join(prereqs)}")
        if standards:
            parts.append(f"Standards: {', '.join(standards)}")
        if vocab:
            parts.append(f"Key vocabulary: {', '.join(vocab[:10])}")
        if related_topics:
            parts.append(f"Related topics: {', '.join(related_topics[:8])}")

        if parts:
            return "**Curriculum knowledge graph:**\n" + "\n".join(parts)
        return ""

    # ── Semantic search ──────────────────────────────────────────────

    def search_entities(
        self,
        teacher_id: str,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search over entity embeddings."""
        try:
            import numpy as np

            from clawed.agent_core.memory.embeddings import get_embedder
        except ImportError:
            return []

        embedder = get_embedder()
        query_vec = np.array(embedder.embed(query), dtype=np.float32)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, name, entity_type, embedding FROM kg_entities "
                "WHERE teacher_id = ? AND embedding IS NOT NULL",
                (teacher_id,),
            ).fetchall()

        if not rows:
            return []

        names = []
        types = []
        ids = []
        vecs = []
        for r in rows:
            try:
                vec = _blob_to_embed(r["embedding"])
                vecs.append(vec)
                names.append(r["name"])
                types.append(r["entity_type"])
                ids.append(r["id"])
            except Exception:
                continue

        if not vecs:
            return []

        mat = np.array(vecs, dtype=np.float32)
        q_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        m_norms = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)
        sims = m_norms @ q_norm

        ranked = sorted(
            zip(sims, ids, names, types),
            key=lambda x: x[0],
            reverse=True,
        )
        return [
            {"id": eid, "name": n, "entity_type": t, "similarity": float(s)}
            for s, eid, n, t in ranked[:top_k]
            if s > 0.2
        ]

    def batch_embed_unembedded(self, teacher_id: str) -> int:
        """Embed all entities that don't have embeddings yet."""
        try:
            from clawed.agent_core.memory.embeddings import get_embedder
        except ImportError:
            return 0

        embedder = get_embedder()
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, name FROM kg_entities "
                "WHERE teacher_id = ? AND embedding IS NULL",
                (teacher_id,),
            ).fetchall()

        if not rows:
            return 0

        count = 0
        with sqlite3.connect(self._db_path) as conn:
            for r in rows:
                try:
                    vec = embedder.embed(r["name"])
                    blob = _embed_to_blob(vec)
                    conn.execute(
                        "UPDATE kg_entities SET embedding = ? WHERE id = ?",
                        (blob, r["id"]),
                    )
                    count += 1
                except Exception:
                    continue
        logger.info("Batch embedded %d/%d entities", count, len(rows))
        return count

    # ── Stats ────────────────────────────────────────────────────────

    def stats(self, teacher_id: str) -> dict[str, Any]:
        """Return knowledge graph statistics."""
        with sqlite3.connect(self._db_path) as conn:
            ent_count = conn.execute(
                "SELECT COUNT(*) FROM kg_entities WHERE teacher_id = ?",
                (teacher_id,),
            ).fetchone()[0]
            triple_count = conn.execute(
                "SELECT COUNT(*) FROM kg_triples WHERE teacher_id = ?",
                (teacher_id,),
            ).fetchone()[0]
            current_count = conn.execute(
                "SELECT COUNT(*) FROM kg_triples "
                "WHERE teacher_id = ? AND valid_to IS NULL",
                (teacher_id,),
            ).fetchone()[0]

            types = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT entity_type FROM kg_entities "
                    "WHERE teacher_id = ?",
                    (teacher_id,),
                ).fetchall()
            ]
            preds = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT predicate FROM kg_triples "
                    "WHERE teacher_id = ?",
                    (teacher_id,),
                ).fetchall()
            ]

        return {
            "entity_count": ent_count,
            "triple_count": triple_count,
            "current_facts": current_count,
            "expired_facts": triple_count - current_count,
            "entity_types": types,
            "predicates": preds,
        }
