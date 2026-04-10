"""Professional document themes for Claw-ED exports.

Defines font, color, and spacing constants used by DOCX and PPTX
exporters. v0.9.20 ships a single PROFESSIONAL theme; v0.10 will
add teacher-selectable themes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocxTheme:
    title_font: str = "Calibri"
    title_size: int = 20
    heading_font: str = "Calibri"
    heading_size: int = 14
    body_font: str = "Calibri"
    body_size: int = 11
    accent_color: str = "2B579A"
    light_accent: str = "D6E4F0"
    header_bg: str = "2B579A"
    footer_text: str = "Created with Claw-ED"
    iep_bg_color: str = "FFF3CD"
    ell_bg_color: str = "D1ECF1"


@dataclass(frozen=True)
class PptxTheme:
    title_font: str = "Calibri"
    title_size: int = 36
    subtitle_size: int = 18
    body_font: str = "Calibri"
    body_size: int = 20
    accent_color: str = "2B579A"
    bg_color: str = "FFFFFF"
    divider_height: float = 0.12


PROFESSIONAL_DOCX = DocxTheme()
PROFESSIONAL_PPTX = PptxTheme()
