"""Centralized file I/O — encoding, filenames, output paths.

Every module that writes files should use these functions instead of
raw Path.write_text() to guarantee:
- UTF-8 encoding on all platforms (no cp1252 crashes on Windows)
- Safe filenames (no colons, no NTFS ADS bugs)
- Consistent output directory (~/.eduagent/output/ or EDUAGENT_DATA_DIR)
"""

import os
import re
from pathlib import Path


def _base_dir() -> Path:
    return Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))


def output_dir() -> Path:
    """Return the configured output directory.

    Priority: AppConfig.output_dir > ~/clawed_output (default).
    Falls back to ~/.eduagent/output/ if config can't be loaded.
    """
    try:
        from clawed.models import AppConfig

        cfg = AppConfig.load()
        if cfg.output_dir:
            d = Path(cfg.output_dir).expanduser().resolve()
            d.mkdir(parents=True, exist_ok=True)
            return d
    except Exception:
        pass
    d = Path.home() / "clawed_output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_filename(name: str, max_len: int = 80) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    safe = safe.strip().replace(" ", "_")[:max_len]
    return safe or "untitled"


def write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save_output(content: str, name: str, ext: str = ".md", subdir: str = "") -> Path:
    base = output_dir()
    if subdir:
        base = base / subdir
        base.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(name) + ext
    return write_text(base / filename, content)
