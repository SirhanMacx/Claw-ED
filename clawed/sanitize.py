"""Output sanitization — clean LLM artifacts before export.

Strips XML/HTML tags, markdown formatting, CJK character leakage,
and other artifacts from multilingual LLM output so exported documents
(DOCX, PPTX) contain only clean, print-ready prose.
"""
from __future__ import annotations

import re

# Pre-compiled patterns for performance (called on every text field)

# XML/HTML-like tags including MiniMax M2.7 artifacts
_RE_KNOWN_TAGS = re.compile(
    r'</?(?:'
    r'teacher[_ ]?(?:prompt|script|talk)'
    r'|transition|activity[_ ]?structure|task'
    r'|homework[_ ]?assignment|student[_ ]?task'
    r'|section|primary[_ ]?source[_ ]?\d*|warm[_\-.]?up'
    r'|do[_\-.]?now|check|guided|independent'
    r'|closing|intro|summary|script'
    r')[^>]*>',
    re.IGNORECASE,
)

# Any remaining angle-bracket tags (e.g. <foo>, </bar>, <baz/>)
_RE_GENERIC_TAGS = re.compile(r'</?[a-zA-Z_][a-zA-Z0-9_ ]{0,30}/?>')

# Markdown headers (## Heading → Heading)
_RE_MD_HEADERS = re.compile(r'^#{1,4}\s+', re.MULTILINE)

# Markdown bold (**text** → text)
_RE_MD_BOLD = re.compile(r'\*\*([^*]+)\*\*')

# Markdown italic (*text* → text) — must run after bold
_RE_MD_ITALIC = re.compile(r'\*([^*]+)\*')

# HTML entities
_RE_HTML_ENTITIES = re.compile(r'&(?:amp|lt|gt|nbsp|quot|apos|#\d{1,4}|#x[0-9a-fA-F]{1,4});')

# CJK character leakage between Latin text
_RE_CJK_LEAK = re.compile(
    r'(?<=[a-zA-Z0-9.,;:!?\s])'
    r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f'
    r'\u30a0-\u30ff\u3040-\u309f]+'
    r'(?=[\sa-zA-Z0-9.,;:!?])',
)

# Whitespace cleanup
_RE_TRIPLE_NEWLINES = re.compile(r'\n{3,}')
_RE_MULTI_SPACES = re.compile(r'  +')

# Map common HTML entities to their text equivalents
_ENTITY_MAP = {
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&nbsp;': ' ',
    '&quot;': '"',
    '&apos;': "'",
}


def sanitize_text(text: str) -> str:
    """Remove LLM formatting artifacts from text for clean document export.

    Strips:
    - XML-like tags (<teacher prompt>, </transition>, etc.)
    - Remaining generic angle-bracket tags
    - Markdown headers (## → plain text)
    - Markdown bold/italic (**text** / *text* → text)
    - HTML entities (&amp; → &)
    - CJK character leakage from multilingual models
    - Excessive whitespace
    """
    if not isinstance(text, str):
        text = str(text) if text is not None else ""  # type: ignore[unreachable]
    if not text:
        return text

    # Strip known XML/HTML-like tags (MiniMax artifacts)
    text = _RE_KNOWN_TAGS.sub('', text)

    # Strip any remaining angle-bracket tags
    text = _RE_GENERIC_TAGS.sub('', text)

    # Strip markdown headers (## Header → Header)
    text = _RE_MD_HEADERS.sub('', text)

    # Strip markdown bold/italic
    text = _RE_MD_BOLD.sub(r'\1', text)
    text = _RE_MD_ITALIC.sub(r'\1', text)

    # Decode HTML entities
    for entity, replacement in _ENTITY_MAP.items():
        text = text.replace(entity, replacement)
    # Strip any remaining numeric/hex entities
    text = _RE_HTML_ENTITIES.sub('', text)

    # Strip CJK character leakage
    text = _RE_CJK_LEAK.sub('', text)

    # Clean up whitespace
    text = _RE_TRIPLE_NEWLINES.sub('\n\n', text)
    text = _RE_MULTI_SPACES.sub(' ', text)

    # Strip leading/trailing whitespace per line
    lines = text.split('\n')
    text = '\n'.join(line.strip() for line in lines)

    return text.strip()
