"""Format-specific extractors for curriculum file ingestion.

Each extractor is a plugin that handles a specific file format used by teachers.
"""

from clawed.formats.flipchart import extract_flipchart
from clawed.formats.notebook import extract_notebook
from clawed.formats.xbk import extract_xbk

__all__ = ["extract_flipchart", "extract_notebook", "extract_xbk"]
