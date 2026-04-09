"""Tests for the pptx/ subpackage extracted from export_pptx.py."""

from __future__ import annotations


class TestPptxHelpers:
    """Test low-level PPTX helper functions."""

    def test_split_text_short(self):
        from clawed.pptx.helpers import split_text

        result = split_text("Hello world.", max_len=100)
        assert result == ["Hello world."]

    def test_split_text_long(self):
        from clawed.pptx.helpers import split_text

        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = split_text(text, max_len=40)
        assert len(result) >= 2
        # All original content preserved
        assert "First sentence" in result[0]

    def test_split_text_empty(self):
        from clawed.pptx.helpers import split_text

        result = split_text("")
        assert result == [""]


class TestPptxThemes:
    """Test topic-based theme selection."""

    def test_renaissance_matches_warm_brown(self):
        from clawed.pptx.themes import get_topic_theme

        theme = get_topic_theme("Renaissance Art in Florence")
        assert theme["primary"] == "8B6914"  # Warm brown
        assert theme["accent"] == "F5E6C8"

    def test_reform_matches_warm_brown(self):
        from clawed.pptx.themes import get_topic_theme

        theme = get_topic_theme("Reform Movements in the US")
        assert theme["primary"] == "8B6914"

    def test_revolution_matches_red(self):
        from clawed.pptx.themes import get_topic_theme

        theme = get_topic_theme("French Revolution")
        assert theme["primary"] == "8b0000"  # Dark red

    def test_science_matches_teal(self):
        from clawed.pptx.themes import get_topic_theme

        theme = get_topic_theme("Cell Biology")
        assert theme["primary"] == "1a4a4a"

    def test_math_matches_purple(self):
        from clawed.pptx.themes import get_topic_theme

        theme = get_topic_theme("Algebra equations")
        assert theme["primary"] == "2a1a4a"

    def test_unknown_topic_gets_default(self):
        from clawed.pptx.themes import DEFAULT_TOPIC_THEME, get_topic_theme

        theme = get_topic_theme("Totally unrelated topic xyz")
        assert theme == DEFAULT_TOPIC_THEME

    def test_subject_matching(self):
        from clawed.pptx.themes import get_topic_theme

        theme = get_topic_theme("Introduction Lesson", subject="biology")
        assert theme["primary"] == "1a4a4a"  # Science teal


class TestPptxSubpackageImport:
    """Verify that clawed.pptx re-exports the public API."""

    def test_import_export_function(self):
        from clawed.pptx import export_lesson_pptx

        assert callable(export_lesson_pptx)

    def test_import_cleanup(self):
        from clawed.pptx import cleanup_temp_images

        assert callable(cleanup_temp_images)


class TestDocxTheming:
    """Verify DOCX compilers use subject-aware theme colors."""

    def test_history_theme_uses_warm_brown(self):
        from clawed.export_theme import get_color_theme

        theme = get_color_theme("history")
        assert theme["primary"] == "8B6914"
        assert theme["accent"] == "F5E6C8"
        assert theme["bg_dark"] == "2C1810"
        assert theme["text_dark"] == "2C1810"

    def test_social_studies_matches_history(self):
        from clawed.export_theme import get_color_theme

        assert get_color_theme("social studies") == get_color_theme("history")

    def test_science_theme_is_green(self):
        from clawed.export_theme import get_color_theme

        theme = get_color_theme("science")
        assert theme["primary"] == "1B5E20"

    def test_math_theme_is_blue(self):
        from clawed.export_theme import get_color_theme

        theme = get_color_theme("math")
        assert theme["primary"] == "1565C0"

    def test_ela_theme_is_purple(self):
        from clawed.export_theme import get_color_theme

        theme = get_color_theme("ela")
        assert theme["primary"] == "6A1B9A"

    def test_unknown_subject_gets_default(self):
        from clawed.export_theme import get_color_theme

        theme = get_color_theme("underwater basket weaving")
        # Should get the professional navy default
        assert theme["primary"] == "1A365D"
