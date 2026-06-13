"""Asset registry — file-level awareness of teacher's materials.

Sits alongside the curriculum KB (same SQLite database). While the KB stores
text chunks for semantic search, the asset registry stores one row per *file*
with rich metadata: material type, embedded images, YouTube links, slide counts.

This powers the "I found your Reconstruction PPT from 2020" experience.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def _resolve_default_db() -> Path:
    import os as _os
    base = Path(_os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
    return base / "memory" / "curriculum_kb.db"

_DEFAULT_DB = _resolve_default_db()

# ── YouTube URL normalization ────────────────────────────────────────

_YT_PATTERNS = [
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})'),
    re.compile(r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})'),
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})'),
    re.compile(r'(?:https?://)?m\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})'),
]

_URL_PATTERN = re.compile(r'https?://[^\s<>"\')\]]+')


def extract_youtube_ids(text: str) -> list[str]:
    """Extract unique YouTube video IDs from text."""
    ids: list[str] = []
    for pat in _YT_PATTERNS:
        for m in pat.finditer(text):
            vid = m.group(1)
            if vid not in ids:
                ids.append(vid)
    return ids


def extract_urls(text: str) -> list[str]:
    """Extract all URLs from text."""
    return _URL_PATTERN.findall(text)


def classify_url(url: str) -> str:
    """Classify a URL type."""
    lower = url.lower()
    if 'youtube.com' in lower or 'youtu.be' in lower:
        return 'youtube'
    if 'docs.google.com' in lower or 'drive.google.com' in lower:
        return 'google_doc'
    return 'website'


# ── Material type classification ─────────────────────────────────────

_ASSESSMENT_KEYWORDS = {'test', 'quiz', 'exam', 'assessment', 'midterm', 'final', 'regents'}
_HANDOUT_KEYWORDS = {'handout', 'worksheet', 'graphic organizer', 'organizer', 'guided notes'}
_UNIT_PLAN_KEYWORDS = {'unit plan', 'essential questions', 'enduring understandings', 'pacing'}
_LESSON_PLAN_KEYWORDS = {'lesson plan', 'objective', 'do now', 'exit ticket', 'swbat'}


def classify_material_type(
    doc_type: str, text: str, filename: str, slide_count: int | None = None,
) -> str:
    """Classify a document into a material type using heuristics."""
    lower_fn = filename.lower()
    lower_text = text[:2000].lower()

    if doc_type == 'pptx':
        if slide_count and slide_count >= 8:
            return 'slideshow'
        if slide_count and slide_count <= 3:
            return 'fragment'
        return 'slideshow'

    combined = lower_fn + " " + lower_text

    if any(kw in combined for kw in _ASSESSMENT_KEYWORDS):
        return 'assessment'
    if any(kw in combined for kw in _HANDOUT_KEYWORDS):
        return 'handout'
    if any(kw in combined for kw in _UNIT_PLAN_KEYWORDS):
        return 'unit_plan'
    if any(kw in combined for kw in _LESSON_PLAN_KEYWORDS):
        return 'lesson_plan'
    if doc_type == 'docx':
        return 'notes'
    return 'unknown'


# ── Extracted metadata dataclasses ───────────────────────────────────

@dataclass
class ExtractedImage:
    """An image extracted from a teaching document."""
    image_bytes: bytes
    format: str  # 'png', 'jpeg', 'gif'
    width: int | None = None
    height: int | None = None
    alt_text: str = ''
    context_text: str = ''
    slide_number: int | None = None


@dataclass
class ExtractedURL:
    """A URL found in a teaching document."""
    url: str
    link_type: str  # 'youtube', 'website', 'google_doc'
    context_text: str = ''
    title_hint: str = ''


@dataclass
class ExtractionResult:
    """Rich extraction result from a document."""
    text: str
    page_count: int | None = None
    slide_count: int | None = None
    images: list[ExtractedImage] = field(default_factory=list)
    urls: list[ExtractedURL] = field(default_factory=list)
    word_count: int = 0


# ── Topic tag extraction ─────────────────────────────────────────────

_STOP_WORDS = frozenset({
    'the', 'a', 'an', 'and', 'or', 'for', 'in', 'on', 'of', 'to', 'is',
    'it', 'by', 'at', 'be', 'as', 'do', 'if', 'so', 'no', 'up', 'but',
    'not', 'was', 'are', 'has', 'had', 'its', 'this', 'that', 'with',
    'from', 'will', 'can', 'all', 'may', 'new', 'one', 'two', 'use',
    'pdf', 'doc', 'docx', 'pptx', 'ppt', 'txt', 'copy', 'final', 'draft',
    # System path components that leak into directory-based tag extraction
    'users', 'home', 'documents', 'curricula', 'curriculum', 'desktop',
    'downloads', 'onedrive', 'google', 'drive', 'dropbox', 'icloud',
})


def _extract_topic_tags(filename: str, content: str, source_path: str = "") -> list[str]:
    """Extract topic tags from filename, directory path, and content.

    The curriculum directory structure carries strong topic signals:
    e.g., "7th us history 1/22-23/American_Revolution.pptx"
    → tags include "us history", "american", "revolution", "7th"
    """
    tags: set[str] = set()

    # From filename — split on common separators, filter stop words
    name = Path(filename).stem
    parts = re.split(r'[-_\s.()]+', name.lower())
    tags.update(p for p in parts if len(p) > 2 and p not in _STOP_WORDS)

    # From directory path — curriculum structure has subject/grade/topic folders
    if source_path:
        path_parts = Path(source_path).parts
        # Skip system prefix: everything up to and including "Documents"/"Curricula"
        # e.g., C:\Users\jonan\Documents\Curricula\7th us history 1\22-23\file.pptx
        # Skip: C:, Users, jonan, Documents, Curricula → start at "7th us history 1"
        skip_prefixes = {'/', 'c:', 'd:', 'users', 'home', 'documents', 'curricula',
                         'my documents', 'desktop', 'downloads', 'onedrive', 'dropbox'}
        start_idx = 0
        for i, part in enumerate(path_parts):
            if part.lower().rstrip('\\') in skip_prefixes:
                start_idx = i + 1

        for part in path_parts[start_idx:-1]:  # exclude filename itself
            dir_tokens = re.split(r'[-_\s.()]+', part.lower())
            for tok in dir_tokens:
                if len(tok) > 2 and tok not in _STOP_WORDS and not tok.isdigit():
                    tags.add(tok)
            # Also extract multi-word curriculum phrases from directory names
            # e.g., "7th us history 1" → "us history"
            multi_word = re.findall(r'[a-z]+(?:\s+[a-z]+)+', part.lower())
            for phrase in multi_word:
                cleaned = ' '.join(w for w in phrase.split() if w not in _STOP_WORDS and len(w) > 2)
                if cleaned and len(cleaned) > 4:
                    tags.add(cleaned)

    # From content — extract capitalised multi-word phrases (likely topics)
    for match in re.finditer(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', content[:1000]):
        tags.add(match.group().lower())

    # From content — extract standalone capitalised words that look like
    # subject keywords (longer than 4 chars to avoid noise)
    for match in re.finditer(r'\b[A-Z][a-z]{4,}\b', content[:1000]):
        word = match.group().lower()
        if word not in _STOP_WORDS:
            tags.add(word)

    return sorted(tags)[:20]  # cap at 20 tags


# ── Asset Registry ───────────────────────────────────────────────────

class AssetRegistry:
    """File-level asset registry for teacher's materials.

    Tracks complete files (slideshows, handouts, assessments) with metadata
    about embedded images, YouTube links, material type, and completeness.
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teacher_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    material_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    topic_tags TEXT DEFAULT '[]',
                    grade_hint TEXT DEFAULT '',
                    slide_count INTEGER,
                    page_count INTEGER,
                    word_count INTEGER DEFAULT 0,
                    has_images INTEGER DEFAULT 0,
                    image_count INTEGER DEFAULT 0,
                    youtube_urls TEXT DEFAULT '[]',
                    external_urls TEXT DEFAULT '[]',
                    completeness TEXT DEFAULT 'unknown',
                    file_size_bytes INTEGER,
                    content_hash TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    UNIQUE(teacher_id, content_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_assets_teacher
                    ON assets(teacher_id);
                CREATE INDEX IF NOT EXISTS idx_assets_material_type
                    ON assets(teacher_id, material_type);

                CREATE TABLE IF NOT EXISTS asset_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL REFERENCES assets(id),
                    image_index INTEGER NOT NULL,
                    image_path TEXT NOT NULL,
                    image_format TEXT DEFAULT '',
                    width_px INTEGER,
                    height_px INTEGER,
                    alt_text TEXT DEFAULT '',
                    context_text TEXT DEFAULT '',
                    slide_number INTEGER,
                    UNIQUE(asset_id, image_index)
                );

                CREATE TABLE IF NOT EXISTS asset_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL REFERENCES assets(id),
                    url TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    context_text TEXT DEFAULT '',
                    title_hint TEXT DEFAULT '',
                    UNIQUE(asset_id, url)
                );
            """)

    def register_asset(
        self,
        teacher_id: str,
        source_path: str,
        title: str,
        doc_type: str,
        text: str,
        extraction: ExtractionResult | None = None,
    ) -> int | None:
        """Register a file as an asset. Returns asset ID or None if duplicate."""
        content_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:32]
        filename = Path(source_path).name

        material_type = classify_material_type(
            doc_type, text, filename,
            slide_count=extraction.slide_count if extraction else None,
        )

        word_count = len(text.split()) if text else 0
        slide_count = extraction.slide_count if extraction else None
        page_count = extraction.page_count if extraction else None

        # Extract URLs from text
        yt_ids = extract_youtube_ids(text)
        youtube_urls = [f"https://youtube.com/watch?v={vid}" for vid in yt_ids]
        all_urls = extract_urls(text)
        external_urls = [u for u in all_urls if 'youtube' not in u.lower() and 'youtu.be' not in u.lower()]

        # Add URLs from extraction result
        if extraction:
            for eu in extraction.urls:
                if eu.link_type == 'youtube' and eu.url not in youtube_urls:
                    youtube_urls.append(eu.url)
                elif eu.url not in external_urls:
                    external_urls.append(eu.url)

        image_count = len(extraction.images) if extraction else 0
        has_images = 1 if image_count > 0 else 0

        try:
            file_size = Path(source_path).stat().st_size if Path(source_path).exists() else 0
        except (FileNotFoundError, OSError):
            file_size = 0

        completeness = 'complete' if material_type in ('slideshow', 'assessment', 'handout') else 'unknown'

        topic_tags = _extract_topic_tags(filename, text, source_path=source_path)

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO assets "
                    "(teacher_id, source_path, filename, doc_type, material_type, title, "
                    "topic_tags, word_count, slide_count, page_count, has_images, image_count, "
                    "youtube_urls, external_urls, completeness, file_size_bytes, "
                    "content_hash, indexed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        teacher_id, source_path, filename, doc_type, material_type, title,
                        json.dumps(topic_tags),
                        word_count, slide_count, page_count, has_images, image_count,
                        json.dumps(youtube_urls), json.dumps(external_urls),
                        completeness, file_size, content_hash,
                        datetime.now().isoformat(),
                    ),
                )
                if cursor.rowcount == 0:
                    return None  # duplicate
                asset_id = cursor.lastrowid

                # Store image references
                if extraction and extraction.images:
                    cache_dir = self._db_path.parent.parent / "cache" / "extracted" / content_hash
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    for idx, img in enumerate(extraction.images):
                        ext = img.format.lower().replace('jpeg', 'jpg')
                        img_path = cache_dir / f"{idx}.{ext}"
                        try:
                            img_path.write_bytes(img.image_bytes)
                            conn.execute(
                                "INSERT OR IGNORE INTO asset_images "
                                "(asset_id, image_index, image_path, image_format, "
                                "width_px, height_px, alt_text, context_text, slide_number) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    asset_id, idx, str(img_path), img.format,
                                    img.width, img.height, img.alt_text,
                                    img.context_text, img.slide_number,
                                ),
                            )
                        except Exception as e:
                            logger.debug("Failed to save image %d: %s", idx, e)

                # Store link references
                for yt_url in youtube_urls:
                    conn.execute(
                        "INSERT OR IGNORE INTO asset_links "
                        "(asset_id, url, link_type, context_text) VALUES (?, ?, ?, ?)",
                        (asset_id, yt_url, 'youtube', ''),
                    )
                for ext_url in external_urls[:20]:  # cap at 20 external URLs
                    conn.execute(
                        "INSERT OR IGNORE INTO asset_links "
                        "(asset_id, url, link_type, context_text) VALUES (?, ?, ?, ?)",
                        (asset_id, ext_url, classify_url(ext_url), ''),
                    )

                return asset_id
        except Exception as e:
            logger.debug("Asset registration failed: %s", e)
            return None

    def search_assets(
        self, teacher_id: str, query: str, top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search assets by keyword matching on title, filename, topic_tags, and material type.

        If teacher_id is empty, searches across all teachers (used as a
        fallback when the caller's transport teacher_id doesn't match the
        ingestion teacher_id).
        """
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        if not keywords:
            return []

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if teacher_id:
                rows = conn.execute(
                    "SELECT * FROM assets WHERE teacher_id = ?", (teacher_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM assets").fetchall()

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            title_lower = row["title"].lower()
            fn_lower = row["filename"].lower()
            tags_lower = (row["topic_tags"] or "").lower()
            combined = title_lower + " " + fn_lower + " " + tags_lower
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                asset = dict(row)
                asset["youtube_urls"] = json.loads(asset["youtube_urls"])
                asset["external_urls"] = json.loads(asset["external_urls"])
                scored.append((score, asset))

        scored.sort(key=lambda x: (-x[0], x[1].get("material_type", "")))
        return [item[1] for item in scored[:top_k]]

    def get_youtube_links(self, teacher_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search for YouTube links related to a topic.

        If teacher_id is empty, searches across all teachers.
        """
        assets = self.search_assets(teacher_id, query, top_k=50)
        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        for asset in assets:
            for yt_url in asset.get("youtube_urls", []):
                if yt_url not in seen:
                    seen.add(yt_url)
                    links.append({
                        "url": yt_url,
                        "from_file": asset["title"],
                        "material_type": asset["material_type"],
                    })
                    if len(links) >= top_k:
                        return links
        return links

    def format_asset_summary(
        self,
        assets: list[dict[str, Any]],
        youtube_links: list[dict[str, Any]] | None = None,
    ) -> str:
        """Format a human-readable summary of found assets."""
        if not assets and not youtube_links:
            return ""

        lines: list[str] = []
        if assets:
            lines.append("Teacher's Existing Materials on This Topic:")
            for a in assets:
                type_label = a["material_type"].replace("_", " ").title()
                extras: list[str] = []
                if a.get("slide_count"):
                    extras.append(f"{a['slide_count']} slides")
                if a.get("image_count"):
                    extras.append(f"{a['image_count']} images")
                yt_count = len(a.get("youtube_urls", []))
                if yt_count:
                    extras.append(f"{yt_count} YouTube links")
                extra_str = f" ({', '.join(extras)})" if extras else ""
                lines.append(f"  - [{type_label}] \"{a['title']}\"{extra_str}")
                lines.append(f"    File: {a['filename']}")

        if youtube_links:
            lines.append("\nYouTube Links Found in Your Files:")
            for link in youtube_links:
                lines.append(f"  - {link['url']} (from \"{link['from_file']}\")")

        lines.append(
            "\nReference and build on these existing materials. "
            "If the teacher has taught this topic before, extend their work."
        )
        return "\n".join(lines)

    def stats(self, teacher_id: str) -> dict[str, int]:
        """Return asset counts."""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE teacher_id = ?", (teacher_id,),
            ).fetchone()[0]
            images = conn.execute(
                "SELECT COUNT(*) FROM asset_images ai "
                "JOIN assets a ON ai.asset_id = a.id WHERE a.teacher_id = ?",
                (teacher_id,),
            ).fetchone()[0]
            links = conn.execute(
                "SELECT COUNT(*) FROM asset_links al "
                "JOIN assets a ON al.asset_id = a.id WHERE a.teacher_id = ?",
                (teacher_id,),
            ).fetchone()[0]
        return {"asset_count": total, "image_count": images, "link_count": links}

    def get_extracted_images(
        self,
        asset_id: int | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve extracted images from the asset registry.

        Args:
            asset_id: Filter by specific asset ID.
            query: Search image context/filename for keyword matches.
            limit: Max results to return.

        Returns:
            List of dicts with: path, source, content_type, context, asset_id,
            image_format, width, height, slide_number.
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if asset_id is not None:
                rows = conn.execute(
                    "SELECT ai.*, a.filename, a.title, a.source_path "
                    "FROM asset_images ai "
                    "JOIN assets a ON ai.asset_id = a.id "
                    "WHERE ai.asset_id = ? "
                    "ORDER BY ai.image_index "
                    "LIMIT ?",
                    (asset_id, limit),
                ).fetchall()
            elif query:
                keywords = [f"%{w.lower()}%" for w in query.split() if len(w) > 2]
                if not keywords:
                    return []
                # Match against context_text, alt_text, or parent asset filename/title
                conditions = " OR ".join(
                    ["LOWER(ai.context_text) LIKE ?"
                     " OR LOWER(ai.alt_text) LIKE ?"
                     " OR LOWER(a.filename) LIKE ?"
                     " OR LOWER(a.title) LIKE ?"] * len(keywords)
                )
                params: list[Any] = []
                for kw in keywords:
                    params.extend([kw, kw, kw, kw])
                params.append(limit)
                rows = conn.execute(
                    f"SELECT ai.*, a.filename, a.title, a.source_path "
                    f"FROM asset_images ai "
                    f"JOIN assets a ON ai.asset_id = a.id "
                    f"WHERE {conditions} "
                    f"ORDER BY ai.id DESC "
                    f"LIMIT ?",
                    params,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT ai.*, a.filename, a.title, a.source_path "
                    "FROM asset_images ai "
                    "JOIN assets a ON ai.asset_id = a.id "
                    "ORDER BY ai.id DESC "
                    "LIMIT ?",
                    (limit,),
                ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            fmt = row["image_format"] or "png"
            results.append({
                "path": row["image_path"],
                "source": row["filename"],
                "content_type": f"image/{fmt}",
                "context": row["context_text"] or "",
                "asset_id": row["asset_id"],
                "image_format": fmt,
                "width": row["width_px"],
                "height": row["height_px"],
                "slide_number": row["slide_number"],
                "alt_text": row["alt_text"] or "",
            })
        return results

    def search_images_for_topic(
        self,
        teacher_id: str,
        topic: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find teacher's own images relevant to a topic.

        Two-phase search:
        1. Fast keyword matching on context_text, alt_text, title, topic_tags
        2. If keyword match returns 0, fall back to ONNX embedding similarity

        Returns images sorted by relevance with valid local paths.
        """
        if not topic or len(topic.strip()) < 2:
            return []

        keywords = [w.lower() for w in topic.split() if len(w) > 2]
        if not keywords:
            return []

        rows = self._get_teacher_image_rows(teacher_id)

        # Phase 1: keyword scoring (fast)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            path = row["image_path"]
            if not path or not Path(path).exists():
                continue

            score = 0.0
            context = (row["context_text"] or "").lower()
            alt = (row["alt_text"] or "").lower()
            title = (row["title"] or "").lower()
            tags_str = (row["topic_tags"] or "[]").lower()

            for kw in keywords:
                if kw in tags_str:
                    score += 3.0  # Topic tag match (highest)
                if kw in title:
                    score += 2.0  # Title match
                if kw in alt:
                    score += 1.5  # Alt text match
                if kw in context:
                    score += 1.0  # Context match

            if score > 0:
                fmt = row["image_format"] or "png"
                scored.append((score, {
                    "path": path,
                    "source": row["filename"],
                    "context": row["context_text"] or "",
                    "score": score,
                    "image_format": fmt,
                    "width": row["width_px"],
                    "height": row["height_px"],
                }))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scored[:limit]]

        # Phase 2: embedding similarity fallback (slower, but catches semantic matches)
        return self._embedding_search_images(rows, topic, limit)

    def _get_teacher_image_rows(self, teacher_id: str) -> list[Any]:
        """Load all image rows for a teacher from the database."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT ai.*, a.filename, a.title, a.source_path, a.topic_tags "
                "FROM asset_images ai "
                "JOIN assets a ON ai.asset_id = a.id "
                "WHERE a.teacher_id = ? OR a.teacher_id = 'default'",
                (teacher_id,),
            ).fetchall()

    def _embedding_search_images(
        self,
        rows: list[Any],
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Semantic search fallback using ONNX MiniLM embeddings.

        When keyword matching finds nothing, this computes cosine similarity
        between the query and each image's context text. Slower but catches
        cases where the LLM's image_spec uses different vocabulary than the
        PPTX slide text.
        """
        try:
            import numpy as np

            from clawed.agent_core.memory.embeddings import ONNXMiniLMEmbedder
        except ImportError:
            logger.debug("ONNX embeddings not available for image fallback search")
            return []

        # Build candidate list with valid paths and non-empty context
        candidates: list[tuple[dict[str, Any], str]] = []
        for row in rows:
            path = row["image_path"]
            if not path or not Path(path).exists():
                continue
            context = (row["context_text"] or "") + " " + (row["alt_text"] or "") + " " + (row["title"] or "")
            context = context.strip()
            if len(context) < 5:
                continue
            fmt = row["image_format"] or "png"
            candidates.append(({
                "path": path,
                "source": row["filename"],
                "context": row["context_text"] or "",
                "image_format": fmt,
                "width": row["width_px"],
                "height": row["height_px"],
            }, context))

        if not candidates:
            return []

        try:
            embedder = ONNXMiniLMEmbedder()
            query_emb = np.array(embedder.embed(query), dtype=np.float32)

            # Batch embed all candidate contexts
            contexts = [c[1][:200] for c in candidates]  # truncate for speed
            ctx_embs = np.array([embedder.embed(t) for t in contexts], dtype=np.float32)

            # Cosine similarity via matrix multiply (embeddings are L2-normed)
            query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)
            ctx_norms = ctx_embs / (np.linalg.norm(ctx_embs, axis=1, keepdims=True) + 1e-8)
            similarities = ctx_norms @ query_norm

            # Rank by similarity, threshold at 0.3
            ranked = sorted(
                zip(similarities, candidates, strict=False),
                key=lambda x: x[0],
                reverse=True,
            )

            results = []
            for sim, (info, _ctx) in ranked[:limit]:
                if sim < 0.3:
                    break
                info["score"] = float(sim)
                results.append(info)

            if results:
                logger.info(
                    "Embedding fallback found %d images (best score: %.2f)",
                    len(results), results[0]["score"],
                )
            return results

        except Exception as e:
            logger.debug("Embedding fallback search failed: %s", e)
            return []
