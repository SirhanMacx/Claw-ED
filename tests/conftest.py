"""Shared test fixtures — isolate state to prevent cascade failures.

Architecture: EDUAGENT_DATA_DIR env var is the single source of truth for
all data paths. Most modules read it at import time via os.environ.get().
Setting it BEFORE imports (line 20) handles the majority of cases.

The monkeypatch.setattr calls below cover modules that compute paths at
import time from the env var — they need patching because the env var
was set AFTER the module was first imported by another test.

See clawed/paths.py for the centralized path definitions.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_state_db(tmp_path, monkeypatch):
    """Redirect ALL filesystem paths to a temp dir for every test."""

    # ── Single source of truth ────────────────────────────────────────
    monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    # Enable auto-approve in tests so tool execution tests pass the policy layer
    monkeypatch.setenv("CLAWED_AUTO_APPROVE", "1")

    # ── Module-level constants that were evaluated at first import ─────
    # These need patching because Python evaluates them once.
    # Modules that call os.environ.get() in functions don't need patching.

    # clawed.state
    monkeypatch.setattr(
        "clawed.state.DEFAULT_DATA_DIR", tmp_path, raising=False,
    )

    # clawed.workspace (9 cascading paths from _BASE_DIR)
    monkeypatch.setattr("clawed.workspace._BASE_DIR", tmp_path, raising=False)
    monkeypatch.setattr("clawed.workspace.WORKSPACE_DIR", tmp_path / "workspace", raising=False)
    monkeypatch.setattr("clawed.workspace.IDENTITY_PATH", tmp_path / "workspace" / "identity.md", raising=False)
    monkeypatch.setattr("clawed.workspace.SOUL_PATH", tmp_path / "workspace" / "soul.md", raising=False)
    monkeypatch.setattr("clawed.workspace.MEMORY_PATH", tmp_path / "workspace" / "memory.md", raising=False)
    monkeypatch.setattr(
        "clawed.workspace.MEMORY_SUMMARY_PATH",
        tmp_path / "workspace" / "memory_summary.md", raising=False,
    )
    monkeypatch.setattr("clawed.workspace.HEARTBEAT_PATH", tmp_path / "workspace" / "heartbeat.md", raising=False)
    monkeypatch.setattr("clawed.workspace.NOTES_DIR", tmp_path / "workspace" / "notes", raising=False)
    monkeypatch.setattr("clawed.workspace.STUDENTS_DIR", tmp_path / "workspace" / "students", raising=False)

    # clawed.config
    monkeypatch.setattr("clawed.config._BASE_DIR", tmp_path, raising=False)
    monkeypatch.setattr("clawed.config._SECRETS_DIR", tmp_path, raising=False)
    monkeypatch.setattr("clawed.config._SECRETS_FILE", tmp_path / "secrets.json", raising=False)

    # clawed.scheduler
    monkeypatch.setattr("clawed.scheduler.SCHEDULE_CONFIG_PATH", tmp_path / "schedule.json", raising=False)

    # clawed.bot_state
    monkeypatch.setattr("clawed.bot_state._BASE_DIR", tmp_path, raising=False)

    # clawed.corpus
    monkeypatch.setattr("clawed.corpus._BASE_DIR", tmp_path, raising=False)
    monkeypatch.setattr("clawed.corpus.CORPUS_DIR", tmp_path / "corpus", raising=False)
    monkeypatch.setattr("clawed.corpus.CORPUS_DB", tmp_path / "corpus" / "corpus.db", raising=False)

    # clawed.slide_images
    monkeypatch.setattr("clawed.slide_images._CACHE_DIR", tmp_path / "cache" / "images", raising=False)

    # clawed.transports.telegram
    monkeypatch.setattr("clawed.transports.telegram._BOT_LOCK", tmp_path / "bot.lock", raising=False)
    monkeypatch.setattr("clawed.transports.telegram._ERROR_LOG", tmp_path / "errors.log", raising=False)

    # ── Module state flags (reset per test) ───────────────────────────
    monkeypatch.setattr("clawed.agent_core.memory.sessions._initialized", False, raising=False)
    monkeypatch.setattr("clawed.agent_core.quality._initialized", False, raising=False)
