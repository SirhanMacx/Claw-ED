"""Extractor for SMART Board (.xbk) files.

XBK files are XML-based SMART Board lesson files. They may be plain XML
or ZIP-compressed XML archives, depending on version.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree


def extract_xbk(path: Path) -> tuple[str, int | None]:
    """Extract text from a SMART Board (.xbk) file.

    Tries ZIP-based extraction first, then falls back to plain XML.
    """
    # Try as ZIP archive first (newer XBK versions)
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            return _extract_from_zip(zf)
    except zipfile.BadZipFile:
        pass

    # Fall back to plain XML
    try:
        data = path.read_bytes()
        root = ElementTree.fromstring(data)
        texts = _extract_text_from_element(root)
        if texts:
            return "\n".join(texts), None
    except (ElementTree.ParseError, OSError):
        pass

    return "", None


def _extract_from_zip(zf: zipfile.ZipFile) -> tuple[str, int | None]:
    """Extract text from XML files within a ZIP-based XBK."""
    texts: list[str] = []
    page_count = 0

    for name in sorted(zf.namelist()):
        if not name.endswith(".xml"):
            continue
        try:
            data = zf.read(name)
            root = ElementTree.fromstring(data)
            page_texts = _extract_text_from_element(root)
            if page_texts:
                page_count += 1
                texts.append(f"[Page {page_count}]\n" + "\n".join(page_texts))
        except (ElementTree.ParseError, KeyError):
            continue

    return "\n\n".join(texts), page_count if page_count else None


def _extract_text_from_element(element: ElementTree.Element) -> list[str]:
    """Recursively extract all text content from an XML element tree."""
    results: list[str] = []
    if element.text and element.text.strip():
        results.append(element.text.strip())
    if element.tail and element.tail.strip():
        results.append(element.tail.strip())
    for child in element:
        results.extend(_extract_text_from_element(child))
    return results
