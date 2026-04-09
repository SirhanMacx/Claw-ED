"""Shared color themes, font constants, and helpers for document export.

Used by export_pptx, export_docx, and export_pdf.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.models import DailyLesson

# ── Enhanced color theme definitions ──────────────────────────────────

_COLOR_THEMES: dict[str, dict[str, str]] = {
    "history": {
        "primary": "8B6914",       # Warm brown (Jon's palette)
        "secondary": "DAA520",     # Goldenrod
        "accent": "F5E6C8",        # Warm cream (Jon's palette)
        "bg_dark": "2C1810",       # Dark brown (Jon's palette)
        "bg_light": "FFF8F0",      # Warm cream
        "text_dark": "2C1810",     # Body text matches dark brown
        "text_light": "FFFFFF",
    },
    "social studies": {
        "primary": "8B6914",       # Warm brown (Jon's palette)
        "secondary": "DAA520",     # Goldenrod
        "accent": "F5E6C8",        # Warm cream (Jon's palette)
        "bg_dark": "2C1810",       # Dark brown (Jon's palette)
        "bg_light": "FFF8F0",      # Warm cream
        "text_dark": "2C1810",     # Body text matches dark brown
        "text_light": "FFFFFF",
    },
    "science": {
        "primary": "1B5E20",       # Dark green
        "secondary": "43A047",     # Medium green
        "accent": "E8F5E9",        # Mint
        "bg_dark": "0D3311",       # Deep green
        "bg_light": "F0F8F5",      # Light mint
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "biology": {
        "primary": "1B5E20",
        "secondary": "43A047",
        "accent": "E8F5E9",
        "bg_dark": "0D3311",
        "bg_light": "F0F8F5",
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "chemistry": {
        "primary": "1B5E20",
        "secondary": "43A047",
        "accent": "E8F5E9",
        "bg_dark": "0D3311",
        "bg_light": "F0F8F5",
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "physics": {
        "primary": "1B5E20",
        "secondary": "43A047",
        "accent": "E8F5E9",
        "bg_dark": "0D3311",
        "bg_light": "F0F8F5",
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "math": {
        "primary": "1565C0",       # Blue
        "secondary": "42A5F5",     # Light blue
        "accent": "E3F2FD",        # Ice blue
        "bg_dark": "0D2137",       # Navy
        "bg_light": "F0F4FA",      # Soft blue
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "mathematics": {
        "primary": "1565C0",
        "secondary": "42A5F5",
        "accent": "E3F2FD",
        "bg_dark": "0D2137",
        "bg_light": "F0F4FA",
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "algebra": {
        "primary": "1565C0",
        "secondary": "42A5F5",
        "accent": "E3F2FD",
        "bg_dark": "0D2137",
        "bg_light": "F0F4FA",
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "ela": {
        "primary": "6A1B9A",       # Purple
        "secondary": "AB47BC",     # Light purple
        "accent": "F3E5F5",        # Lavender
        "bg_dark": "2A0845",       # Deep purple
        "bg_light": "F5F0FA",      # Light lavender
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "english": {
        "primary": "6A1B9A",
        "secondary": "AB47BC",
        "accent": "F3E5F5",
        "bg_dark": "2A0845",
        "bg_light": "F5F0FA",
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
    "language arts": {
        "primary": "6A1B9A",
        "secondary": "AB47BC",
        "accent": "F3E5F5",
        "bg_dark": "2A0845",
        "bg_light": "F5F0FA",
        "text_dark": "1A1A1A",
        "text_light": "FFFFFF",
    },
}

_DEFAULT_THEME: dict[str, str] = {
    "primary": "1A365D",       # Professional navy
    "secondary": "3182CE",     # Blue
    "accent": "EBF8FF",        # Light blue
    "bg_dark": "0A1628",       # Dark navy
    "bg_light": "F0F4FA",      # Soft blue-white
    "text_dark": "1A1A1A",
    "text_light": "FFFFFF",
}


def get_color_theme(subject: str) -> dict[str, str]:
    """Return the color theme dict for a subject, or the default."""
    return _COLOR_THEMES.get(subject.strip().lower(), _DEFAULT_THEME)


def _hex_to_rgb(hex_str: str):
    """Convert a hex color string to an RGBColor (pptx)."""
    from pptx.dml.color import RGBColor

    return RGBColor(int(hex_str[:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def _resolve_output(output_dir: Path | None, lesson: "DailyLesson", ext: str) -> Path:
    """Build the output file path using the lesson title."""
    if output_dir is None:
        output_dir = Path("clawed_output").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    # Use lesson title for filename, fallback to number
    title = getattr(lesson, 'title', '') or f"lesson_{getattr(lesson, 'lesson_number', 0):02d}"
    safe = "".join(c for c in title[:50] if c.isalnum() or c in " _-").strip().replace(" ", "_") or "lesson"
    return output_dir / f"{safe}{ext}"
