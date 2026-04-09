"""Claw-ED — Personal AI teaching agent. Learns your voice, works while you sleep."""

import os
import sys

# Ensure UTF-8 encoding on all platforms. Windows defaults to cp1252,
# which crashes on emoji/non-Latin characters from LLM output.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

__version__ = "4.9.2026.8"
__author__ = "Jon Maccarello & Claw-ED contributors"
__description__ = "Your AI co-teacher. Generate lessons, games, slides, and assessments from your terminal."

# Central I/O — re-exported for convenience
from clawed.io import output_dir as output_dir  # noqa: F401
from clawed.io import read_text as read_text  # noqa: F401
from clawed.io import safe_filename as safe_filename  # noqa: F401
from clawed.io import save_output as save_output  # noqa: F401
from clawed.io import write_text as write_text  # noqa: F401


def _safe_filename(title: str) -> str:
    """.. deprecated:: 0.2.0 Use :func:`clawed.io.safe_filename` instead."""
    return safe_filename(title, max_len=50)
