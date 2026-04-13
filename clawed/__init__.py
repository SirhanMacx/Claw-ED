"""Claw-ED — Personal AI teaching agent. Learns your voice, works while you sleep."""

import contextlib
import os
import sys

# Ensure UTF-8 encoding on all platforms. Windows defaults to cp1252,
# which crashes on emoji/non-Latin characters from LLM output.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

__version__ = "4.13.2026.1"
__author__ = "Jon Maccarello & Claw-ED contributors"
__description__ = "Your AI co-teacher. Generate lessons, games, slides, and assessments from your terminal."

# Central I/O — re-exported for convenience
from clawed.io import output_dir as output_dir
from clawed.io import read_text as read_text
from clawed.io import safe_filename as safe_filename
from clawed.io import save_output as save_output
from clawed.io import write_text as write_text


def _safe_filename(title: str) -> str:
    """.. deprecated:: 0.2.0 Use :func:`clawed.io.safe_filename` instead."""
    return safe_filename(title, max_len=50)
