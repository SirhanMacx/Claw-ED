"""Tests for v0.9.20 export improvements."""

from __future__ import annotations

import pytest

from clawed.export_templates import PROFESSIONAL_DOCX, PROFESSIONAL_PPTX


class TestExportTemplates:
    def test_docx_theme_defaults(self):
        theme = PROFESSIONAL_DOCX
        assert theme.title_font == "Calibri"
        assert theme.accent_color == "2B579A"
        assert theme.iep_bg_color == "FFF3CD"

    def test_pptx_theme_defaults(self):
        theme = PROFESSIONAL_PPTX
        assert theme.title_size == 36
        assert theme.accent_color == "2B579A"

    def test_themes_are_frozen(self):
        with pytest.raises(AttributeError):
            PROFESSIONAL_DOCX.title_font = "Arial"
