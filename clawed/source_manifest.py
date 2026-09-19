"""Evidence captured from retrieval, separate from model-authored citations."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field


class SourceEvidence(BaseModel):
    id: str
    document_id: str
    title: str
    origin: str
    locator: str = "Location not recorded by ingestion"
    excerpt: str
    excerpt_sha256: str


def capture_sources(rows: list[dict[str, Any]]) -> list[SourceEvidence]:
    sources = []
    for row in rows:
        excerpt = str(row.get("chunk_text", ""))
        if not excerpt.strip():
            continue
        origin = str(row.get("source_path") or row.get("doc_title", "Unknown"))
        digest = hashlib.sha256(excerpt.encode()).hexdigest()
        document_id = hashlib.sha256(origin.encode()).hexdigest()[:16]
        metadata = row.get("metadata") or {}
        locator = "; ".join(f"{key}: {metadata[key]}" for key in ("page", "slide", "chunk_index") if key in metadata)
        sources.append(SourceEvidence(
            id=f"{document_id}:{digest[:16]}", document_id=document_id,
            title=str(row.get("doc_title", "Untitled")), origin=origin,
            locator=locator or "Location not recorded by ingestion", excerpt=excerpt, excerpt_sha256=digest,
        ))
    return sources


def render_sources(sources: list[SourceEvidence]) -> str:
    return "\n\n".join(
        f"Evidence ID: {source.id}\nDocument: {source.title}\nLocation: {source.locator}\n"
        f"<source_excerpt>\n{source.excerpt}\n</source_excerpt>"
        for source in sources
    )


class EvidenceCheck(BaseModel):
    source_id: str
    status: str
    matched_evidence: list[str] = Field(default_factory=list)


def check_quotations(primary_sources: list[Any], evidence: list[SourceEvidence]) -> list[EvidenceCheck]:
    """A text match proves provenance only, never historical truth or answer quality."""
    def normalized(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().casefold()

    checks = []
    for source in primary_sources:
        quote = normalized(source.content_text)
        matches = [item.id for item in evidence if len(quote) >= 30 and quote in normalized(item.excerpt)]
        checks.append(EvidenceCheck(
            source_id=source.id, status="matched_excerpt" if matches else "needs_teacher_verification",
            matched_evidence=matches,
        ))
    return checks
