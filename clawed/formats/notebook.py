"""Extractor for SMART Notebook (.notebook) files.

SMART Notebook files are ZIP archives containing XML files.
The lesson content lives in XML pages inside the archive.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree


def extract_notebook(path: Path) -> tuple[str, int | None]:
    """Extract text from a SMART Notebook (.notebook) file.

    These are ZIP archives containing XML page files. We walk all XML
    files inside and extract any text content we find.
    """
    texts: list[str] = []
    page_count = 0

    try:
        with zipfile.ZipFile(str(path), "r") as zf:
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
    except (zipfile.BadZipFile, OSError):
        return "", None

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
