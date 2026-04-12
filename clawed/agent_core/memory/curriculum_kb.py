"""Curriculum Knowledge Base — semantic search over teacher's uploaded materials.

This is the core differentiator: teacher files aren't analyzed once and
forgotten. They become a living database the agent searches every time
it generates content.

Embeddings are stored as compact binary (BLOB) for ~10x smaller DB
compared to JSON text. Search uses numpy vectorized cosine similarity
for fast retrieval even with large collections.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import sqlite3
import struct
from datetime import datetime
from pathlib import Path
from typing import Any

from clawed.agent_core.memory.embeddings import get_embedder

logger = logging.getLogger(__name__)

def _get_default_db() -> Path:
    """Resolve DB path respecting EDUAGENT_DATA_DIR."""
    import os
    base = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
    return base / "memory" / "curriculum_kb.db"


_DEFAULT_DB = None  # Lazy — see _get_default_db()
_CHUNK_SIZE = 500  # ~500 words per chunk
_CHUNK_OVERLAP = 50


def _embed_to_blob(vec: list[float]) -> bytes:
    """Pack embedding vector as compact binary BLOB."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _blob_to_embed(blob: bytes) -> list[float]:
    """Unpack embedding BLOB back to list of floats."""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


class CurriculumKB:
    """Semantic search over a teacher's uploaded curriculum files.

    Documents are chunked, embedded, and stored in SQLite. The agent
    searches this KB before generating to ground output in the teacher's
    own materials.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _get_default_db()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._embedder = get_embedder()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            # WAL mode allows concurrent reads during writes (ingest + search)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teacher_id TEXT NOT NULL,
                    doc_title TEXT NOT NULL,
                    source_path TEXT,
                    chunk_text TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_teacher "
                "ON chunks(teacher_id)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_dedup "
                "ON chunks(teacher_id, chunk_hash)"
            )
            # FTS5 full-text index for fast keyword pre-filtering
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_text, doc_title,
                    content='chunks', content_rowid='id'
                )
            """
            )

    @staticmethod
    def _sanitize_for_indexing(text: str) -> str:
        """Strip non-educational noise from document text before chunking.

        Aggressively removes binary data, XML internals, URL-encoded strings,
        OLE/OOXML artifacts, and other parser garbage. Only keeps lines that
        contain real human-readable educational content.
        """
        import re

        if not text:
            return ""

        # Strip base64 blobs (images/OLE embedded as text)
        text = re.sub(r'[A-Za-z0-9+/]{80,}={0,2}', ' ', text)

        # Strip XML/HTML tags and internal XML content
        text = re.sub(r'<[^>]{1,500}>', ' ', text)
        text = re.sub(r'<\?xml[^?]*\?>', ' ', text)

        # Strip URL-encoded sequences (%3D, %26, etc.)
        text = re.sub(r'(?:%[0-9A-Fa-f]{2}){3,}', ' ', text)

        # Strip binary/encoding artifacts
        text = re.sub(r'\\x[0-9a-fA-F]{2}', ' ', text)
        text = re.sub(r'&#x?[0-9a-fA-F]+;', ' ', text)

        # Strip OLE/OOXML internal paths and markers
        text = re.sub(r'\b\w+/\w+\.xml\b', ' ', text)
        text = re.sub(r'\bbjbj\w*\b', ' ', text)
        text = re.sub(r'\bPK\x03\x04.*', ' ', text)

        # Strip runs of non-ASCII (binary data parsed as text)
        # Keep only lines where >60% of non-space chars are printable ASCII
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip very short lines (noise)
            if len(stripped) < 4:
                continue
            # Skip OOXML internal paths (PPTX/DOCX zip structure)
            if '[Content_Types]' in stripped or '.xmlPK' in stripped or '_rels/' in stripped:
                continue
            # Skip image format headers (embedded binary images)
            if re.search(r'\bJFIF\b|\bPNG\b|\bIDAT\b|\bIEND\b', stripped):
                continue
            # Skip lines with 3+ consecutive '?' (decoded binary garbage)
            if '???' in stripped:
                continue
            # Count actual letters (the stuff that matters in education)
            letters = sum(1 for c in stripped if c.isalpha())
            total = len(stripped)
            # Line must be >50% letters to be real text (not binary/encoded)
            if total > 0 and letters / total > 0.5:
                # Must contain at least three real words (3+ letters each)
                if len(re.findall(r'[A-Za-z]{3,}', stripped)) >= 3:
                    clean_lines.append(stripped)

        text = '\n'.join(clean_lines)

        # Final whitespace cleanup
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        """Split text into chunks, respecting slide boundaries when present.

        If the text contains [Slide N] markers (from PPTX extraction),
        chunks by slide — each slide is one chunk. Otherwise uses the
        standard overlapping word-window approach.
        """
        import re

        if not text.strip():
            return []

        # PPTX slide-aware chunking: [Slide N] markers from ingestor
        if '[Slide ' in text:
            slide_chunks = re.split(r'(?=\[Slide \d+\])', text)
            slides = [s.strip() for s in slide_chunks if s.strip()]
            if slides:
                return slides

        # Standard overlapping word-window chunking
        words = text.split()
        if not words:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(words):
            end = start + _CHUNK_SIZE
            chunk = " ".join(words[start:end])
            if chunk.strip():
                chunks.append(chunk.strip())
            start += _CHUNK_SIZE - _CHUNK_OVERLAP
        return chunks or ([text.strip()] if text.strip() else [])

    # Batch size for commits during indexing — prevents OOM on large documents
    _INDEX_BATCH = 50

    def index(
        self,
        teacher_id: str,
        doc_title: str,
        source_path: str,
        full_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Chunk, embed, and store a document. Returns new chunks added.

        Processes chunks in batches of _INDEX_BATCH to keep memory bounded.
        Sanitizes text to remove non-educational content (base64, XML, etc.)
        before chunking.
        """
        import gc

        full_text = self._sanitize_for_indexing(full_text)
        chunks = self._chunk_text(full_text)
        if not chunks:
            return 0

        added = 0
        meta_json = json.dumps(metadata or {})
        now = datetime.now().isoformat()

        # Process in batches to keep memory bounded on large docs
        for batch_start in range(0, len(chunks), self._INDEX_BATCH):
            batch = chunks[batch_start: batch_start + self._INDEX_BATCH]

            with sqlite3.connect(self._db_path) as conn:
                for chunk in batch:
                    chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()[:32]
                    existing = conn.execute(
                        "SELECT 1 FROM chunks "
                        "WHERE teacher_id=? AND chunk_hash=?",
                        (teacher_id, chunk_hash),
                    ).fetchone()
                    if existing:
                        continue

                    embedding = self._embedder.embed(chunk)
                    blob = _embed_to_blob(embedding)

                    cursor = conn.execute(
                        "INSERT INTO chunks "
                        "(teacher_id, doc_title, source_path, chunk_text, "
                        "chunk_hash, embedding, metadata, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            teacher_id, doc_title, source_path,
                            chunk, chunk_hash, blob, meta_json, now,
                        ),
                    )
                    # Populate FTS index
                    try:
                        conn.execute(
                            "INSERT INTO chunks_fts(rowid, chunk_text, doc_title) "
                            "VALUES (?, ?, ?)",
                            (cursor.lastrowid, chunk, doc_title),
                        )
                    except Exception:
                        pass  # FTS table may not exist on old DBs
                    added += 1

            # Free embedding memory between batches
            if len(chunks) > self._INDEX_BATCH:
                gc.collect()

        if len(chunks) > 100:
            logger.info(
                "Large doc '%s': %d chunks, %d new (batched)",
                doc_title[:50], len(chunks), added,
            )
        else:
            logger.debug(
                "Indexed %d new chunks from '%s' for teacher %s",
                added, doc_title, teacher_id,
            )
        return added

    @staticmethod
    def _apply_quality_boost(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Post-process search results with quality-based score boosts.

        Favors longer, lesson-plan-style chunks over short noise:
        - Chunks >200 words get 1.2x boost (more context = more useful)
        - Lesson plan markers (Do Now, Exit Ticket, etc.) get 1.3x boost
        - Vocabulary/key terms chunks get 1.1x boost
        - Very short chunks (<50 words) get 0.7x penalty
        """
        import re

        lesson_plan_re = re.compile(
            r'\b(Do\s+Now|Exit\s+Ticket|Objective|Aim)\b', re.IGNORECASE,
        )
        vocab_re = re.compile(
            r'\b(vocabulary|key\s+terms)\b', re.IGNORECASE,
        )

        for result in results:
            text = result.get("chunk_text", "")
            word_count = len(text.split())
            boost = 1.0

            # Penalize very short chunks
            if word_count < 50:
                boost *= 0.7
            # Boost long, content-rich chunks
            elif word_count > 200:
                boost *= 1.2

            # Boost lesson plan chunks (most actionable for generation)
            if lesson_plan_re.search(text):
                boost *= 1.3

            # Boost vocabulary-rich chunks
            if vocab_re.search(text):
                boost *= 1.1

            result["similarity"] = result.get("similarity", 0) * boost

        # Re-sort by boosted similarity and return
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results

    def search(
        self,
        teacher_id: str,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search the teacher's curriculum files by semantic similarity."""
        return self._search_impl(
            query, top_k,
            where="teacher_id = ?", params=(teacher_id,),
        )

    def search_all_teachers(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Fallback search across ALL teachers."""
        return self._search_impl(query, top_k, where="1=1", params=())

    def _search_impl(
        self,
        query: str,
        top_k: int,
        where: str,
        params: tuple,
    ) -> list[dict[str, Any]]:
        """Two-stage search: FTS5 keyword filter → embedding re-rank.

        Stage 1: FTS5 full-text search finds candidate chunks by keywords.
        Stage 2: Cosine similarity re-ranks candidates by semantic meaning.
        Falls back to brute-force scan if FTS table doesn't exist.
        """
        query_embedding = self._embedder.embed(query)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Stage 1: Try FTS5 keyword pre-filter (fast, searches ALL chunks)
            rows = None
            try:
                # FTS5 match query — extract keywords
                fts_query = " OR ".join(
                    w for w in query.split() if len(w) > 2
                )
                if fts_query:
                    rows = conn.execute(
                        "SELECT c.doc_title, c.source_path, c.chunk_text, "
                        "c.embedding, c.metadata, c.created_at "
                        "FROM chunks c "
                        "JOIN chunks_fts f ON c.id = f.rowid "
                        f"WHERE {where} AND chunks_fts MATCH ? "
                        "LIMIT 500",
                        (*params, fts_query),
                    ).fetchall()
            except Exception:
                pass  # FTS table may not exist

            # Stage 2: Fall back to brute-force if FTS found nothing
            if not rows:
                rows = conn.execute(
                    "SELECT doc_title, source_path, chunk_text, "
                    "embedding, metadata, created_at "
                    f"FROM chunks WHERE {where} "
                    "ORDER BY RANDOM() LIMIT 5000",
                    params,
                ).fetchall()

        if not rows:
            return []

        # Try numpy vectorized similarity (100x faster)
        results = None
        with contextlib.suppress(ImportError):
            results = self._search_numpy(query_embedding, rows, top_k)

        if results is None:
            # Fallback: Python loop
            scored = []
            for row in rows:
                stored = _parse_embedding(row["embedding"])
                sim = self._embedder.cosine_similarity(query_embedding, stored)
                if sim > 0.05:
                    scored.append({
                        "doc_title": row["doc_title"],
                        "source_path": row["source_path"],
                        "chunk_text": row["chunk_text"],
                        "metadata": json.loads(row["metadata"]),
                        "created_at": row["created_at"],
                        "similarity": sim,
                    })

            scored.sort(key=lambda x: x["similarity"], reverse=True)
            results = scored[:top_k]

        # Post-processing: boost quality signals to surface best materials
        return self._apply_quality_boost(results)

    @staticmethod
    def _search_numpy(
        query_vec: list[float],
        rows: list,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Vectorized search using numpy — handles thousands of chunks fast."""
        import numpy as np

        q = np.array(query_vec, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        q = q / q_norm

        # Build matrix of all stored embeddings
        embeddings = []
        for row in rows:
            vec = _parse_embedding(row["embedding"])
            embeddings.append(vec)

        # Pad to same dimension if needed (mixed embedder compatibility)
        max_dim = max(len(e) for e in embeddings)
        if len(q) < max_dim:
            q = np.pad(q, (0, max_dim - len(q)))
        matrix = np.zeros((len(embeddings), max_dim), dtype=np.float32)
        for i, e in enumerate(embeddings):
            matrix[i, :len(e)] = e

        # L2 normalize rows
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        matrix = matrix / norms

        # Batch cosine similarity
        similarities = matrix @ q

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k * 2]

        results = []
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim <= 0.05:
                break
            row = rows[idx]
            results.append({
                "doc_title": row["doc_title"],
                "source_path": row["source_path"],
                "chunk_text": row["chunk_text"],
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"],
                "similarity": sim,
            })
            if len(results) >= top_k:
                break

        return results

    def stats(self, teacher_id: str) -> dict[str, Any]:
        """Return stats about the teacher's curriculum knowledge base."""
        with sqlite3.connect(self._db_path) as conn:
            doc_count = conn.execute(
                "SELECT COUNT(DISTINCT doc_title) FROM chunks "
                "WHERE teacher_id=?",
                (teacher_id,),
            ).fetchone()[0]
            chunk_count = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE teacher_id=?",
                (teacher_id,),
            ).fetchone()[0]
        return {
            "doc_count": doc_count,
            "chunk_count": chunk_count,
        }


def _parse_embedding(raw: Any) -> list[float]:
    """Parse embedding from BLOB or legacy JSON text."""
    if isinstance(raw, bytes):
        return _blob_to_embed(raw)
    if isinstance(raw, str):
        return json.loads(raw)
    return list(raw)
