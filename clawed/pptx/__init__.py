"""PPTX subpackage — slide generation broken into focused modules.

The monolithic export_pptx.py (1600+ lines) is being incrementally refactored
into this subpackage.  During the migration, the legacy export_pptx.py remains
the primary entry point.  This package re-exports the public API for callers
that want to import from ``clawed.pptx``.

Submodules:
    helpers  — text splitting, shape fills, font styling
    images   — image fetching and placement
    themes   — topic-based visual theming (keyword → palette)
"""

from clawed.export_pptx import cleanup_temp_images, export_lesson_pptx

__all__ = ["export_lesson_pptx", "cleanup_temp_images"]
