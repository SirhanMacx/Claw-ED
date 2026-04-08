"""Centralized path configuration for all Claw-ED data directories.

Every module that needs a file path should call functions from here
instead of computing paths from module-level constants. This:
  - Respects EDUAGENT_DATA_DIR consistently everywhere
  - Makes test isolation trivial (one env var, not 20 monkeypatches)
  - Fixes modules that previously ignored EDUAGENT_DATA_DIR

Usage:
    from clawed.paths import data_dir, workspace_dir, soul_path
    # All return Path objects resolved against EDUAGENT_DATA_DIR
"""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Root data directory (~/.eduagent or EDUAGENT_DATA_DIR)."""
    return Path(
        os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
    )


# ── Workspace ────────────────────────────────────────────────────────

def workspace_dir() -> Path:
    return data_dir() / "workspace"


def soul_path() -> Path:
    return workspace_dir() / "soul.md"


def memory_path() -> Path:
    return workspace_dir() / "memory.md"


def memory_summary_path() -> Path:
    return workspace_dir() / "memory_summary.md"


def heartbeat_path() -> Path:
    return workspace_dir() / "heartbeat.md"


def identity_path() -> Path:
    return workspace_dir() / "identity.md"


def notes_dir() -> Path:
    return workspace_dir() / "notes"


def students_dir() -> Path:
    return workspace_dir() / "students"


# ── Config ───────────────────────────────────────────────────────────

def config_path() -> Path:
    return data_dir() / "config.json"


def secrets_dir() -> Path:
    return data_dir()


def secrets_file() -> Path:
    return data_dir() / "secrets.json"


# ── Database ─────────────────────────────────────────────────────────

def state_db_path() -> Path:
    return data_dir() / "state.db"


def curriculum_kb_path() -> Path:
    return data_dir() / "memory" / "curriculum_kb.db"


def episodes_db_path() -> Path:
    return data_dir() / "memory" / "episodes.db"


def sessions_db_path() -> Path:
    return data_dir() / "memory" / "sessions.db"


def quality_db_path() -> Path:
    return data_dir() / "memory" / "quality.db"


# ── Corpus ───────────────────────────────────────────────────────────

def corpus_dir() -> Path:
    return data_dir() / "corpus"


def corpus_db_path() -> Path:
    return corpus_dir() / "corpus.db"


# ── Cache ────────────────────────────────────────────────────────────

def image_cache_dir() -> Path:
    return data_dir() / "cache" / "images"


def drive_cache_dir() -> Path:
    return data_dir() / "drive_cache"


# ── Bot ──────────────────────────────────────────────────────────────

def bot_lock_path() -> Path:
    return data_dir() / "bot.lock"


def bot_error_log_path() -> Path:
    return data_dir() / "errors.log"


def student_error_log_path() -> Path:
    return data_dir() / "student_errors.log"


# ── Skills ───────────────────────────────────────────────────────────

def custom_skills_dir() -> Path:
    return data_dir() / "skills"


# ── Scheduler ────────────────────────────────────────────────────────

def schedule_config_path() -> Path:
    return data_dir() / "schedule.json"


# ── Wiki ─────────────────────────────────────────────────────────────

def wiki_dir() -> Path:
    return data_dir() / "wiki"


# ── Models ───────────────────────────────────────────────────────────

def models_dir() -> Path:
    return data_dir() / "models"


# ── API ──────────────────────────────────────────────────────────────

def api_token_path() -> Path:
    return data_dir() / "api_token"


# ── Databases (all SQLite files) ────────────────────────────────────

def curriculum_kb_db() -> Path:
    return data_dir() / "memory" / "curriculum_kb.db"


def sessions_db() -> Path:
    return data_dir() / "memory" / "sessions.db"


def episodes_db() -> Path:
    return data_dir() / "memory" / "episodes.db"


def quality_db() -> Path:
    return data_dir() / "memory" / "quality.db"


def bot_state_db() -> Path:
    return data_dir() / "bot_state.db"


def approvals_db() -> Path:
    return data_dir() / "approvals.db"


def task_queue_db() -> Path:
    return data_dir() / "memory" / "task_queue.db"


# ── Cache ───────────────────────────────────────────────────────────

def animation_dir() -> Path:
    return data_dir() / "animations"
