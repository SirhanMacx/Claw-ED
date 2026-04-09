"""Low-level PPTX helpers — text splitting, shape fills, font styling.

These functions are stateless utilities used by all slide builders.
Extracted from the monolithic export_pptx.py for maintainability.
"""

from __future__ import annotations

from clawed.export_theme import _hex_to_rgb


def add_shape_fill(shape, hex_color: str) -> None:
    """Fill a shape with a solid color."""
    fill = shape.fill
    fill.solid()
    fill.fore_color.rgb = _hex_to_rgb(hex_color)


def set_text_props(
    run,
    font_size_pt: int,
    hex_color: str,
    bold: bool = False,
    font_name: str = "Calibri",
) -> None:
    """Set font properties on a text run."""
    from pptx.util import Pt

    run.font.size = Pt(font_size_pt)
    run.font.color.rgb = _hex_to_rgb(hex_color)
    run.font.bold = bold
    run.font.name = font_name


def split_text(text: str, max_len: int = 550) -> list[str]:
    """Split long text into chunks at sentence boundaries."""
    sentences = text.replace("\n", " ").split(". ")
    chunks: list[str] = []
    current = ""
    for s in sentences:
        candidate = f"{current}. {s}" if current else s
        if len(candidate) > max_len and current:
            chunks.append(current.strip())
            current = s
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]
