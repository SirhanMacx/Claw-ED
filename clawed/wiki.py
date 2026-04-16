"""Karpathy wiki — compile curriculum chunks into an organized markdown wiki.

Transforms raw ingested chunks (stored in curriculum_kb.db) into
LLM-synthesized wiki articles, enables structured Q&A with citations,
and provides health checks for wiki integrity.

Architecture:
    raw files → ingest → chunks table → compile_wiki() → markdown articles
    question → query_wiki() → index lookup → article reading → cited answer
    lint_wiki() → stale / uncovered / orphaned detection
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawed.io import safe_filename

logger = logging.getLogger(__name__)

# ── Paths (respect EDUAGENT_DATA_DIR) ────────────────────────────────

_BASE_DIR = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
WIKI_DIR = _BASE_DIR / "wiki"
ARTICLES_DIR = WIKI_DIR / "articles"
INDEX_PATH = WIKI_DIR / "_index.md"
COMPILE_STATE_PATH = WIKI_DIR / "_compile_state.json"
KB_DB_PATH = _BASE_DIR / "memory" / "curriculum_kb.db"

_PROMPT_DIR = Path(__file__).parent / "prompts"
_MAX_WORDS_PER_CALL = 15_000  # Cap chunk text to stay within context limits


# ── Result types ─────────────────────────────────────────────────────

@dataclass
class CompileResult:
    compiled: int = 0
    skipped: int = 0
    total: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class QueryResult:
    answer: str = ""
    sources: list[str] = field(default_factory=list)
    articles_read: int = 0


@dataclass
class LintResult:
    stale: list[dict[str, Any]] = field(default_factory=list)
    uncovered: list[dict[str, Any]] = field(default_factory=list)
    orphaned: list[dict[str, Any]] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.stale and not self.uncovered and not self.orphaned


# ── Internal helpers ─────────────────────────────────────────────────

def _load_compile_state() -> dict[str, Any]:
    """Read _compile_state.json, return empty dict if missing."""
    if COMPILE_STATE_PATH.exists():
        try:
            loaded: dict[str, Any] = json.loads(COMPILE_STATE_PATH.read_text(encoding="utf-8"))
            return loaded
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_compile_state(state: dict[str, Any]) -> None:
    """Persist compile state to disk."""
    COMPILE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPILE_STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def _get_doc_groups(teacher_id: str = "default") -> dict[str, list[dict[str, str]]]:
    """Query chunks table grouped by doc_title.

    Returns {doc_title: [{chunk_text, source_path}, ...]}.
    """
    if not KB_DB_PATH.exists():
        return {}

    groups: dict[str, list[dict[str, str]]] = {}
    try:
        with sqlite3.connect(str(KB_DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT doc_title, chunk_text, source_path "
                "FROM chunks WHERE teacher_id = ? "
                "ORDER BY doc_title, id",
                (teacher_id,),
            ).fetchall()
            for row in rows:
                title = row["doc_title"]
                if title not in groups:
                    groups[title] = []
                groups[title].append({
                    "chunk_text": row["chunk_text"],
                    "source_path": row["source_path"] or "",
                })
    except sqlite3.OperationalError as e:
        logger.warning("Could not read chunks table: %s", e)
    return groups


def _compute_doc_hash(chunks: list[dict[str, str]]) -> str:
    """Deterministic hash over chunk texts for change detection."""
    h = hashlib.sha256()
    for chunk in sorted(chunks, key=lambda c: c.get("chunk_text", "")):
        h.update(chunk.get("chunk_text", "").encode("utf-8"))
    return h.hexdigest()[:16]


def _load_prompt(name: str) -> str:
    """Load a prompt template from clawed/prompts/{name}.txt."""
    path = _PROMPT_DIR / f"{name}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _build_index() -> str:
    """Scan articles directory and build a markdown index."""
    if not ARTICLES_DIR.exists():
        return "# Curriculum Wiki\n\nNo articles compiled yet.\n"

    entries: list[str] = []
    for md_file in sorted(ARTICLES_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        lines = text.strip().splitlines()

        # Extract title (first # heading)
        title = md_file.stem.replace("_", " ").title()
        for line in lines:
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break

        # Extract summary (first non-empty, non-heading line)
        summary = ""
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 10:
                summary = stripped[:150]
                if len(stripped) > 150:
                    summary += "..."
                break

        entries.append(f"- **{title}** ({md_file.name}) — {summary}")

    header = f"# Curriculum Wiki\n\n{len(entries)} articles compiled.\n\n"
    return header + "\n".join(entries) + "\n"


# ── Core: compile ────────────────────────────────────────────────────

async def compile_article(
    doc_title: str,
    chunks: list[dict[str, str]],
    config: Any,
) -> str:
    """Synthesize chunks into a single wiki article via LLM."""
    from clawed.llm import LLMClient
    from clawed.model_router import route

    # Concatenate chunk texts
    full_text = "\n\n".join(c.get("chunk_text", "") for c in chunks)

    # Cap at _MAX_WORDS_PER_CALL to avoid context overflow
    words = full_text.split()
    if len(words) > _MAX_WORDS_PER_CALL:
        full_text = " ".join(words[:_MAX_WORDS_PER_CALL])
        full_text += f"\n\n[Truncated — {len(words)} words total, showing first {_MAX_WORDS_PER_CALL}]"

    system = _load_prompt("wiki_compile")
    prompt = (
        f"Document: {doc_title}\n"
        f"Source: {chunks[0].get('source_path', 'unknown') if chunks else 'unknown'}\n"
        f"Chunks: {len(chunks)}\n\n"
        f"--- Raw content ---\n\n{full_text}"
    )

    routed = route("wiki_compile", config)
    client = LLMClient(config=routed)
    article = await client.generate(
        prompt=prompt,
        system=system,
        temperature=0.3,
        max_tokens=4096,
    )
    return article.strip()


async def compile_wiki(
    teacher_id: str = "default",
    force: bool = False,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> CompileResult:
    """Compile all ingested documents into wiki articles.

    Incremental by default — only recompiles documents whose chunks
    have changed since last compilation. Use force=True to recompile all.
    """
    from clawed.models import AppConfig

    config = AppConfig.load()
    result = CompileResult()

    # Ensure directories exist
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    # Get all documents and their chunks
    doc_groups = _get_doc_groups(teacher_id)
    if not doc_groups:
        logger.info("No ingested documents found. Run `clawed ingest` first.")
        return result

    result.total = len(doc_groups)
    state = _load_compile_state()

    # Filter to only docs that need compilation
    to_compile: list[tuple[str, list[dict[str, Any]], str]] = []
    for doc_title, chunks in doc_groups.items():
        doc_hash = _compute_doc_hash(chunks)
        prev = state.get(doc_title, {})
        if not force and prev.get("hash") == doc_hash:
            result.skipped += 1
        else:
            to_compile.append((doc_title, chunks, doc_hash))

    if not to_compile:
        return result

    # Compile articles in parallel batches (5 concurrent LLM calls)
    import asyncio
    from datetime import datetime as _dt

    concurrency = 5
    sem = asyncio.Semaphore(concurrency)
    compiled_count = 0

    async def _compile_one(
        title: str, chunks: list[dict[str, Any]], doc_hash: str,
    ) -> tuple[str, str | None, str]:
        """Compile one article under semaphore."""
        async with sem:
            try:
                md = await compile_article(title, chunks, config)
                return title, md, doc_hash
            except Exception as e:
                logger.error("Failed to compile %s: %s", title, e)
                return title, None, str(e)

    # Process in batches to save state periodically
    batch_size = 50
    for batch_start in range(0, len(to_compile), batch_size):
        batch = to_compile[batch_start: batch_start + batch_size]
        tasks = [
            _compile_one(title, chunks, doc_hash)
            for title, chunks, doc_hash in batch
        ]
        results_batch = await asyncio.gather(*tasks)

        for title, article_md, doc_hash_or_err in results_batch:
            if article_md and len(article_md) >= 20:
                filename = safe_filename(title, max_len=60) + ".md"
                article_path = ARTICLES_DIR / filename
                article_path.write_text(article_md, encoding="utf-8")
                state[title] = {
                    "hash": doc_hash_or_err,
                    "compiled_at": _dt.now().isoformat(),
                    "article_file": filename,
                    "source_path": "",
                    "chunk_count": 0,
                }
                result.compiled += 1
            elif article_md is None:
                result.errors.append(f"{title}: {doc_hash_or_err}")
            else:
                result.errors.append(f"{title}: LLM returned empty/short article")

        compiled_count += len(batch)
        if on_progress:
            on_progress(f"Batch {batch_start // batch_size + 1}", compiled_count, len(to_compile))

        # Save state after each batch (crash recovery)
        _save_compile_state(state)

    # Rebuild index
    index_md = _build_index()
    INDEX_PATH.write_text(index_md, encoding="utf-8")

    return result


# ── Core: query ──────────────────────────────────────────────────────

async def query_wiki(question: str) -> QueryResult:
    """Ask a question against the compiled wiki.

    Two-step LLM pipeline:
    1. FAST: read index, pick relevant articles
    2. DEEP: read articles, generate cited answer
    """
    from clawed.llm import LLMClient
    from clawed.model_router import route
    from clawed.models import AppConfig

    if not INDEX_PATH.exists() or not ARTICLES_DIR.exists():
        raise FileNotFoundError(
            "No wiki found. Run `clawed kb compile` first to build your curriculum wiki."
        )

    config = AppConfig.load()
    index_text = INDEX_PATH.read_text(encoding="utf-8")

    # Step 1: Pick relevant articles (FAST tier)
    available_files = [f.name for f in ARTICLES_DIR.glob("*.md")]
    if not available_files:
        raise FileNotFoundError("Wiki has no articles. Run `clawed kb compile` first.")

    pick_prompt = (
        f"Here is the index of available wiki articles:\n\n{index_text}\n\n"
        f"Available files: {json.dumps(available_files)}\n\n"
        f"Question: {question}\n\n"
        f"Return a JSON array of the most relevant filenames (max 5) to answer "
        f"this question. Example: [\"file1.md\", \"file2.md\"]\n"
        f"If no articles seem relevant, return an empty array: []"
    )

    fast_config = route("wiki_query_select", config)
    fast_client = LLMClient(config=fast_config)
    pick_response = await fast_client.generate(
        prompt=pick_prompt,
        temperature=0.1,
        max_tokens=512,
    )

    # Parse the file list
    selected: list[str] = []
    try:
        # Try to extract JSON array from response
        pick_text = pick_response.strip()
        # Handle markdown code fences
        if "```" in pick_text:
            for line in pick_text.splitlines():
                line = line.strip()
                if line.startswith("["):
                    pick_text = line
                    break
        if pick_text.startswith("["):
            selected = list(json.loads(pick_text))
        else:
            # Fallback: try json_repair
            try:
                import json_repair
                selected = list(json_repair.loads(pick_text))  # type: ignore[arg-type]
            except ImportError:
                pass
    except (json.JSONDecodeError, TypeError):
        pass

    # Validate filenames and cap at 5
    selected = [f for f in selected if f in available_files][:5]

    # If LLM didn't pick any, fall back to all articles (capped)
    if not selected:
        selected = available_files[:5]

    # Step 2: Read selected articles and answer (DEEP tier)
    articles_content: list[str] = []
    source_titles: list[str] = []
    for fname in selected:
        path = ARTICLES_DIR / fname
        if path.exists():
            text = path.read_text(encoding="utf-8")
            articles_content.append(f"--- Article: {fname} ---\n{text}")
            # Extract title from first line
            for line in text.splitlines():
                if line.startswith("# "):
                    source_titles.append(line.lstrip("# ").strip())
                    break
            else:
                source_titles.append(fname.replace(".md", "").replace("_", " ").title())

    system = _load_prompt("wiki_query")
    answer_prompt = (
        f"Question: {question}\n\n"
        f"Articles:\n\n" + "\n\n".join(articles_content)
    )

    deep_config = route("wiki_query_answer", config)
    deep_client = LLMClient(config=deep_config)
    answer = await deep_client.generate(
        prompt=answer_prompt,
        system=system,
        temperature=0.3,
        max_tokens=2048,
    )

    return QueryResult(
        answer=answer.strip(),
        sources=source_titles,
        articles_read=len(selected),
    )


# ── Core: lint ───────────────────────────────────────────────────────

def lint_wiki(teacher_id: str = "default") -> LintResult:
    """Check wiki health — no LLM calls, purely structural.

    Detects:
    - Stale articles: source chunks changed since compilation
    - Uncovered documents: ingested but no wiki article
    - Orphaned articles: wiki article but source chunks deleted
    """
    result = LintResult()

    state = _load_compile_state()
    doc_groups = _get_doc_groups(teacher_id)

    # Stale: compiled article exists but chunk hash has changed
    for doc_title, entry in state.items():
        if doc_title in doc_groups:
            current_hash = _compute_doc_hash(doc_groups[doc_title])
            if current_hash != entry.get("hash"):
                result.stale.append({
                    "doc_title": doc_title,
                    "compiled_at": entry.get("compiled_at", "unknown"),
                    "article_file": entry.get("article_file", ""),
                })

    # Uncovered: in chunks but never compiled
    for doc_title, chunks in doc_groups.items():
        if doc_title not in state:
            result.uncovered.append({
                "doc_title": doc_title,
                "chunk_count": len(chunks),
                "source_path": chunks[0].get("source_path", "") if chunks else "",
            })

    # Orphaned: in compile state but no longer in chunks
    for doc_title, entry in state.items():
        if doc_title not in doc_groups:
            result.orphaned.append({
                "doc_title": doc_title,
                "article_file": entry.get("article_file", ""),
            })

    return result
