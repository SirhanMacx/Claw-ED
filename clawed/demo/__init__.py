"""Demo mode — canned lesson outputs for trying Claw-ED without an API key."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEMO_DIR = Path(__file__).parent


def list_demo_files() -> list[Path]:
    """Return all demo JSON files."""
    return sorted(_DEMO_DIR.glob("demo_*.json"))


def load_demo(name: str) -> dict[str, Any]:
    """Load a demo JSON by short name (e.g. 'lesson_social_studies_g8')."""
    path = _DEMO_DIR / f"demo_{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Demo file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_demos() -> dict[str, dict[str, Any]]:
    """Load all demo JSONs keyed by short name."""
    demos: dict[str, dict[str, Any]] = {}
    for p in list_demo_files():
        key = p.stem.removeprefix("demo_")
        demos[key] = json.loads(p.read_text(encoding="utf-8"))
    return demos


def is_demo_mode(config: Any = None) -> bool:
    """Check whether the app should run in demo mode (no API key configured).

    Can be forced with CLAWED_DEMO=1 environment variable, which overrides
    stored keys. This is useful for demo presentations and development.
    """
    import os

    if os.environ.get("CLAWED_DEMO", "").strip() in ("1", "true", "yes"):
        return True
    from clawed.config import resolve_credentials

    provider, key = resolve_credentials(config)
    return provider is None
