"""Knowledge graph entity and relationship extraction from documents.

Heuristic-based (no LLM) — designed for speed during bulk ingestion.
Extracts topics, standards, figures, vocabulary terms, and infers
prerequisite/builds_on/related_to relationships from document structure.
"""
from __future__ import annotations

import re

from clawed.noise_words import ALL_NOISE as _STOP_WORDS

# Standard code patterns
_STANDARD_PATTERNS = [
    re.compile(r"\bCCSS\.[A-Z]+\.\w+\.\d+[\.\d]*\b"),   # CCSS.ELA.RL.8.1
    re.compile(r"\bNGSS\s*[-:]?\s*\w+-\w+[-\d]+\b"),     # NGSS HS-PS1-1
    re.compile(r"\bNY\s*\d+[A-Z]?\.\d+\b"),               # NY state standards
    re.compile(r"\bC3\s*D\d\.\d+\.\d+\b"),                # C3 framework
    re.compile(r"\b[A-Z]{2}\.\d+\.\d+\.\d+[a-z]?\b"),        # Generic: SS.8.1.1a (3+ dot segments)
]


def extract_entities_from_document(
    doc_title: str,
    content: str,
    tags: list[str] | None = None,
) -> list[dict]:
    """Extract curriculum entities from a parsed document.

    Returns list of {"name": ..., "entity_type": ..., "properties": {...}}
    """
    entities: list[dict] = []
    seen_names: set[str] = set()

    def _add(name: str, etype: str, props: dict | None = None) -> None:
        clean = name.strip()
        if len(clean) < 3 or clean.lower() in _STOP_WORDS:
            return
        # Filter out OCR/formatting garbage
        if "\n" in clean or "\t" in clean:
            return
        if clean.count("_") > len(clean) * 0.3:  # fill-in-the-blank
            return
        if len(clean) > 100:  # OCR dump, not a real entity
            return
        if clean[0] in ",:;.!?|/\\" or clean[-1] in ",:;":
            return
        if re.match(r"^[\d\s.,:;/\-]+$", clean):  # only numbers/punctuation
            return
        key = clean.lower()
        if key in seen_names:
            return
        seen_names.add(key)
        entities.append({
            "name": clean,
            "entity_type": etype,
            "properties": props or {},
        })

    # 1. Doc title → primary topic entity
    if doc_title:
        title_clean = re.sub(r"[-_\s.()]+", " ", doc_title).strip()
        if len(title_clean) > 3:
            _add(title_clean, "topic", {"source": "title"})

    # 2. Tags → topic entities
    for tag in (tags or []):
        if len(tag) > 3 and tag.lower() not in _STOP_WORDS:
            _add(tag, "topic", {"source": "tag"})

    # 3. Capitalized multi-word phrases from content → topics/figures
    for m in re.finditer(
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\b", content[:3000]
    ):
        phrase = m.group()
        # Skip if it looks like a sentence start (preceded by period)
        start = m.start()
        if start > 0 and content[start - 2: start] in (". ", "? ", "! "):
            continue
        # Heuristic: names of people (2 words, both capitalized) → figure
        words = phrase.split()
        if len(words) == 2 and all(w[0].isupper() for w in words):
            _add(phrase, "figure")
        elif len(phrase) > 5:
            _add(phrase, "topic")

    # 4. Standard codes → standard entities
    for pat in _STANDARD_PATTERNS:
        for m in pat.finditer(content[:5000]):
            _add(m.group(), "standard", {"source": "content"})

    # 5. Vocabulary sections → term entities
    vocab_patterns = [
        r"(?:key\s+)?(?:vocabulary|terms|words)\s*[:\-]\s*(.+?)(?:\n\n|\Z)",
        r"(?:define|definitions)\s*[:\-]\s*(.+?)(?:\n\n|\Z)",
    ]
    for pat in vocab_patterns:
        for m in re.finditer(pat, content[:5000], re.IGNORECASE | re.DOTALL):
            block = m.group(1)
            # Split on commas, semicolons, bullets, or newlines
            terms = re.split(r"[,;\n•\-\*]+", block)
            for term in terms[:15]:
                clean = term.strip().rstrip(".")
                # Take just the term (before any definition separator)
                for sep in [":", " - ", " – ", " — "]:
                    if sep in clean:
                        clean = clean.split(sep)[0].strip()
                if 2 < len(clean) < 50:
                    _add(clean, "term")

    return entities


def infer_relationships(
    entities: list[dict],
    doc_title: str,
    doc_sequence_hint: int | None = None,
) -> list[dict]:
    """Infer relationships between extracted entities.

    Returns list of {"subject": ..., "predicate": ..., "object": ..., "confidence": ...}
    """
    if not entities:
        return []

    relationships: list[dict] = []
    primary_topic = entities[0]["name"] if entities else doc_title

    for ent in entities[1:]:
        etype = ent["entity_type"]
        name = ent["name"]

        if etype == "term":
            # Vocabulary belongs to the primary topic
            relationships.append({
                "subject": primary_topic,
                "predicate": "includes_vocab",
                "object": name,
                "confidence": 0.8,
            })
        elif etype == "standard":
            # Topic covers this standard
            relationships.append({
                "subject": primary_topic,
                "predicate": "covers_standard",
                "object": name,
                "confidence": 0.7,
            })
        elif etype in ("topic", "figure"):
            # Related to the primary topic
            relationships.append({
                "subject": primary_topic,
                "predicate": "related_to",
                "object": name,
                "confidence": 0.5,
            })

    return relationships


def extract_standard_codes(text: str) -> list[str]:
    """Extract education standard codes from text."""
    codes: list[str] = []
    seen: set[str] = set()
    for pat in _STANDARD_PATTERNS:
        for m in pat.finditer(text[:10000]):
            code = m.group()
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes
