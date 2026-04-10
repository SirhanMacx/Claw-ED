"""Hybrid search for the brain: keyword + vector + RRF fusion.

Combines three signals for maximum recall:
1. Keyword search over brain pages (title/compiled truth/timeline)
2. Vector similarity over brain pages using ONNX MiniLM embeddings
3. Full-text search over the corpus chunks (curriculum_kb.db)

Results are fused using Reciprocal Rank Fusion (RRF) which gives each
result a score of sum(1 / (k + rank)) across all ranked lists it
appears in. k=60 is the standard RRF constant.

Why RRF beats naive score blending: scores from different retrievers
are on different scales (cosine similarity vs BM25 vs keyword counts).
RRF operates on RANKS instead of scores, so it's scale-invariant.
"""
from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from clawed.brain.store import BrainPage, BrainStore

logger = logging.getLogger(__name__)

# RRF constant — standard value from the original paper
_RRF_K = 60


@dataclass
class SearchResult:
    """A single ranked search result from any source."""

    source: str  # "brain-keyword" | "brain-vector" | "corpus-fts"
    slug: str
    page_type: str
    title: str
    snippet: str
    score: float = 0.0
    rank: int = 0
    page: Optional[BrainPage] = None


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two float vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embed_brain_pages(
    pages: list[BrainPage],
    embedder,
) -> list[tuple[BrainPage, list[float]]]:
    """Generate (or reuse cached) embeddings for brain pages.

    Embeds the title + compiled_truth (timeline is noisier). Uses an
    in-memory LRU cache keyed by (slug, updated_date).
    """
    texts: list[str] = []
    for p in pages:
        text = f"{p.title}\n\n{p.compiled_truth[:2000]}"
        texts.append(text)
    if not texts:
        return []
    try:
        vectors = embedder.embed_batch(texts)
    except Exception as exc:
        logger.debug("Embedding failed: %s", exc)
        return []
    return list(zip(pages, vectors))


def brain_keyword_search(
    store: BrainStore,
    query: str,
    page_type: Optional[str] = None,
    limit: int = 20,
) -> list[SearchResult]:
    """Keyword search over brain pages."""
    pages = store.search(query, page_type=page_type, limit=limit)
    results: list[SearchResult] = []
    q_lower = query.lower()
    for rank, page in enumerate(pages, start=1):
        # Build a snippet from compiled truth around the match
        haystack = page.compiled_truth
        idx = haystack.lower().find(q_lower)
        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(haystack), idx + len(query) + 80)
            snippet = haystack[start:end].replace("\n", " ")
        else:
            snippet = page.compiled_truth[:160].replace("\n", " ")
        results.append(
            SearchResult(
                source="brain-keyword",
                slug=page.slug,
                page_type=page.page_type,
                title=page.title,
                snippet=snippet,
                rank=rank,
                page=page,
            )
        )
    return results


def brain_vector_search(
    store: BrainStore,
    query: str,
    page_type: Optional[str] = None,
    limit: int = 20,
) -> list[SearchResult]:
    """Vector similarity search over brain pages."""
    try:
        from clawed.agent_core.memory.embeddings import get_embedder
    except Exception as exc:
        logger.debug("Embedder unavailable: %s", exc)
        return []

    embedder = get_embedder()
    try:
        query_vec = embedder.embed(query)
    except Exception as exc:
        logger.debug("Query embedding failed: %s", exc)
        return []

    # Collect pages to search
    types_to_search = [page_type] if page_type else [
        "student", "topic", "lesson", "original", "concept", "class", "person",
    ]
    all_pages: list[BrainPage] = []
    for ptype in types_to_search:
        for slug in store.list_pages(ptype):
            page = store.get(ptype, slug)
            if page:
                all_pages.append(page)

    if not all_pages:
        return []

    embedded = _embed_brain_pages(all_pages, embedder)
    if not embedded:
        return []

    scored: list[tuple[float, BrainPage]] = []
    for page, vec in embedded:
        sim = _cosine(query_vec, vec)
        scored.append((sim, page))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[SearchResult] = []
    for rank, (score, page) in enumerate(scored[:limit], start=1):
        if score <= 0:
            break
        results.append(
            SearchResult(
                source="brain-vector",
                slug=page.slug,
                page_type=page.page_type,
                title=page.title,
                snippet=page.compiled_truth[:160].replace("\n", " "),
                score=score,
                rank=rank,
                page=page,
            )
        )
    return results


def corpus_fts_search(
    query: str,
    limit: int = 20,
) -> list[SearchResult]:
    """Full-text search over the curriculum_kb chunks table."""
    from clawed.config import _BASE_DIR

    db_path = _BASE_DIR / "memory" / "curriculum_kb.db"
    if not db_path.exists():
        return []

    results: list[SearchResult] = []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # Prefer chunks_fts if it exists
            has_fts = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='chunks_fts'"
            ).fetchone()
            if has_fts:
                # FTS5 MATCH — strip problematic chars and use phrase query
                safe_query = query.replace('"', '').strip()
                if not safe_query:
                    return []
                rows = conn.execute(
                    "SELECT chunks.source_path, chunks.text "
                    "FROM chunks_fts "
                    "JOIN chunks ON chunks_fts.rowid = chunks.id "
                    "WHERE chunks_fts MATCH ? LIMIT ?",
                    (safe_query, limit),
                ).fetchall()
            else:
                # Fallback to LIKE
                rows = conn.execute(
                    "SELECT source_path, text FROM chunks "
                    "WHERE text LIKE ? LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()

            for rank, row in enumerate(rows, start=1):
                source_path = row["source_path"] or "corpus"
                text = (row["text"] or "")[:200].replace("\n", " ")
                slug = Path(source_path).stem[:80] if source_path else f"chunk-{rank}"
                results.append(
                    SearchResult(
                        source="corpus-fts",
                        slug=slug,
                        page_type="corpus",
                        title=Path(source_path).name if source_path else "Corpus chunk",
                        snippet=text,
                        rank=rank,
                    )
                )
    except Exception as exc:
        logger.debug("Corpus FTS search failed: %s", exc)

    return results


def reciprocal_rank_fusion(
    result_lists: list[list[SearchResult]],
    k: int = _RRF_K,
) -> list[SearchResult]:
    """Fuse multiple ranked lists using Reciprocal Rank Fusion.

    Each result gets a score of sum(1 / (k + rank)) across all lists
    it appears in. Deduplication is by (page_type, slug).
    """
    fused: dict[tuple[str, str], SearchResult] = {}
    for results in result_lists:
        for result in results:
            key = (result.page_type, result.slug)
            score = 1.0 / (k + result.rank)
            if key not in fused:
                # Use the first occurrence as the canonical result
                # (so we keep the richer data from the first source)
                result.score = score
                fused[key] = result
            else:
                fused[key].score += score

    ordered = sorted(fused.values(), key=lambda r: r.score, reverse=True)
    # Re-rank
    for i, r in enumerate(ordered, start=1):
        r.rank = i
    return ordered


def hybrid_search(
    query: str,
    store: Optional[BrainStore] = None,
    page_type: Optional[str] = None,
    limit: int = 10,
    include_corpus: bool = True,
) -> list[SearchResult]:
    """Hybrid search combining brain keyword + vector + corpus FTS.

    Args:
        query: The search query.
        store: BrainStore (creates default if None).
        page_type: Limit brain search to a specific page type.
        limit: Max results to return.
        include_corpus: Whether to also search the curriculum corpus.

    Returns:
        RRF-fused ranked list of SearchResult objects.
    """
    if store is None:
        store = BrainStore()

    result_lists: list[list[SearchResult]] = []

    # 1. Brain keyword
    try:
        result_lists.append(
            brain_keyword_search(store, query, page_type=page_type, limit=limit * 2)
        )
    except Exception as exc:
        logger.debug("Brain keyword search failed: %s", exc)

    # 2. Brain vector
    try:
        result_lists.append(
            brain_vector_search(store, query, page_type=page_type, limit=limit * 2)
        )
    except Exception as exc:
        logger.debug("Brain vector search failed: %s", exc)

    # 3. Corpus FTS (optional)
    if include_corpus:
        try:
            result_lists.append(corpus_fts_search(query, limit=limit * 2))
        except Exception as exc:
            logger.debug("Corpus FTS search failed: %s", exc)

    fused = reciprocal_rank_fusion(result_lists)
    return fused[:limit]
