"""Tests for the Karpathy wiki compilation layer.

Tests pure functions in clawed.wiki without LLM calls.
Covers: hashing, grouping, indexing, linting, and state persistence.
"""

from __future__ import annotations

import sqlite3

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def wiki_env(tmp_path, monkeypatch):
    """Set up an isolated wiki environment with a populated chunks table."""
    monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))

    # Patch wiki module paths
    import clawed.wiki as wiki_mod

    monkeypatch.setattr(wiki_mod, "_BASE_DIR", tmp_path)
    monkeypatch.setattr(wiki_mod, "WIKI_DIR", tmp_path / "wiki")
    monkeypatch.setattr(wiki_mod, "ARTICLES_DIR", tmp_path / "wiki" / "articles")
    monkeypatch.setattr(wiki_mod, "INDEX_PATH", tmp_path / "wiki" / "_index.md")
    monkeypatch.setattr(wiki_mod, "COMPILE_STATE_PATH", tmp_path / "wiki" / "_compile_state.json")
    monkeypatch.setattr(wiki_mod, "KB_DB_PATH", tmp_path / "memory" / "curriculum_kb.db")

    # Create the chunks table
    db_path = tmp_path / "memory" / "curriculum_kb.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                doc_title TEXT NOT NULL,
                source_path TEXT,
                chunk_text TEXT NOT NULL,
                chunk_hash TEXT NOT NULL,
                embedding TEXT,
                metadata TEXT,
                created_at TEXT
            )
        """)
        # Insert test chunks
        sql = "INSERT INTO chunks (teacher_id, doc_title, source_path, chunk_text, chunk_hash) VALUES (?, ?, ?, ?, ?)"
        conn.executemany(
            sql,
            [
                (
                    "default",
                    "Photosynthesis Lecture",
                    "/docs/photo.pptx",
                    "Plants convert sunlight into glucose.",
                    "h1",
                ),
                ("default", "Photosynthesis Lecture", "/docs/photo.pptx", "Chloroplasts contain chlorophyll.", "h2"),
                (
                    "default",
                    "Photosynthesis Lecture",
                    "/docs/photo.pptx",
                    "The Calvin cycle fixes carbon dioxide.",
                    "h3",
                ),
                ("default", "Civil War Unit", "/docs/cw.docx", "The Civil War began in 1861.", "h4"),
                ("default", "Civil War Unit", "/docs/cw.docx", "Fort Sumter was the first battle.", "h5"),
                ("other_teacher", "Algebra Basics", "/docs/algebra.pdf", "Solve for x.", "h6"),
            ],
        )

    return tmp_path


# ── Hash tests ───────────────────────────────────────────────────────


class TestComputeDocHash:
    def test_deterministic(self):
        from clawed.wiki import _compute_doc_hash

        chunks = [{"chunk_text": "hello"}, {"chunk_text": "world"}]
        h1 = _compute_doc_hash(chunks)
        h2 = _compute_doc_hash(chunks)
        assert h1 == h2

    def test_different_content_different_hash(self):
        from clawed.wiki import _compute_doc_hash

        h1 = _compute_doc_hash([{"chunk_text": "hello"}])
        h2 = _compute_doc_hash([{"chunk_text": "world"}])
        assert h1 != h2

    def test_order_independent(self):
        from clawed.wiki import _compute_doc_hash

        h1 = _compute_doc_hash([{"chunk_text": "a"}, {"chunk_text": "b"}])
        h2 = _compute_doc_hash([{"chunk_text": "b"}, {"chunk_text": "a"}])
        assert h1 == h2  # Sorted internally


# ── Doc groups tests ─────────────────────────────────────────────────


class TestGetDocGroups:
    def test_groups_by_title(self, wiki_env):
        from clawed.wiki import _get_doc_groups

        groups = _get_doc_groups("default")
        assert "Photosynthesis Lecture" in groups
        assert "Civil War Unit" in groups
        assert len(groups["Photosynthesis Lecture"]) == 3
        assert len(groups["Civil War Unit"]) == 2

    def test_teacher_isolation(self, wiki_env):
        from clawed.wiki import _get_doc_groups

        groups = _get_doc_groups("default")
        assert "Algebra Basics" not in groups

        other_groups = _get_doc_groups("other_teacher")
        assert "Algebra Basics" in other_groups
        assert "Photosynthesis Lecture" not in other_groups

    def test_empty_db(self, wiki_env):
        from clawed.wiki import _get_doc_groups

        groups = _get_doc_groups("nonexistent_teacher")
        assert groups == {}

    def test_no_db_file(self, tmp_path, monkeypatch):
        import clawed.wiki as wiki_mod

        monkeypatch.setattr(wiki_mod, "KB_DB_PATH", tmp_path / "nonexistent.db")
        groups = wiki_mod._get_doc_groups()
        assert groups == {}


# ── Index tests ──────────────────────────────────────────────────────


class TestBuildIndex:
    def test_builds_from_articles(self, wiki_env):
        from clawed.wiki import ARTICLES_DIR, _build_index

        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
        (ARTICLES_DIR / "photosynthesis.md").write_text(
            "# Photosynthesis\n\nPlants convert light energy into chemical energy.\n",
            encoding="utf-8",
        )
        (ARTICLES_DIR / "civil_war.md").write_text(
            "# The Civil War\n\nThe American Civil War lasted from 1861 to 1865.\n",
            encoding="utf-8",
        )

        index = _build_index()
        assert "2 articles compiled" in index
        assert "Photosynthesis" in index
        assert "The Civil War" in index
        assert "photosynthesis.md" in index

    def test_empty_directory(self, wiki_env):
        from clawed.wiki import ARTICLES_DIR, _build_index

        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
        index = _build_index()
        assert "0 articles" in index or "No articles" in index

    def test_no_directory(self, wiki_env, monkeypatch):
        import clawed.wiki as wiki_mod

        monkeypatch.setattr(wiki_mod, "ARTICLES_DIR", wiki_env / "nonexistent")
        index = wiki_mod._build_index()
        assert "No articles" in index


# ── Compile state tests ──────────────────────────────────────────────


class TestCompileState:
    def test_roundtrip(self, wiki_env):
        from clawed.wiki import _load_compile_state, _save_compile_state

        state = {
            "Photosynthesis Lecture": {
                "hash": "abc123",
                "compiled_at": "2026-04-03T12:00:00",
                "article_file": "photosynthesis_lecture.md",
            }
        }
        _save_compile_state(state)
        loaded = _load_compile_state()
        assert loaded == state

    def test_missing_file_returns_empty(self, wiki_env):
        from clawed.wiki import _load_compile_state

        assert _load_compile_state() == {}


# ── Lint tests ───────────────────────────────────────────────────────


class TestLintWiki:
    def test_finds_uncovered_docs(self, wiki_env):
        """Documents in chunks but not compiled should be uncovered."""
        from clawed.wiki import lint_wiki

        # No compile state → all docs are uncovered
        result = lint_wiki("default")
        assert len(result.uncovered) == 2  # Photosynthesis + Civil War
        assert result.healthy is False

    def test_finds_stale_articles(self, wiki_env):
        from clawed.wiki import _save_compile_state, lint_wiki

        # Save state with wrong hash
        _save_compile_state(
            {
                "Photosynthesis Lecture": {
                    "hash": "wrong_hash",
                    "compiled_at": "2026-01-01",
                    "article_file": "photosynthesis.md",
                },
                "Civil War Unit": {
                    "hash": "also_wrong",
                    "compiled_at": "2026-01-01",
                    "article_file": "civil_war.md",
                },
            }
        )
        result = lint_wiki("default")
        assert len(result.stale) == 2
        assert result.healthy is False

    def test_finds_orphaned_articles(self, wiki_env):
        from clawed.wiki import _save_compile_state, lint_wiki

        # State references a document that doesn't exist in chunks
        _save_compile_state(
            {
                "Deleted Document": {
                    "hash": "xyz",
                    "compiled_at": "2026-01-01",
                    "article_file": "deleted.md",
                },
            }
        )
        result = lint_wiki("default")
        assert len(result.orphaned) == 1
        assert result.orphaned[0]["doc_title"] == "Deleted Document"

    def test_healthy_wiki(self, wiki_env):
        from clawed.wiki import _compute_doc_hash, _get_doc_groups, _save_compile_state, lint_wiki

        # Compile state matches current chunks exactly
        groups = _get_doc_groups("default")
        state = {}
        for title, chunks in groups.items():
            state[title] = {
                "hash": _compute_doc_hash(chunks),
                "compiled_at": "2026-04-03",
                "article_file": f"{title.lower().replace(' ', '_')}.md",
            }
        _save_compile_state(state)

        result = lint_wiki("default")
        assert result.healthy is True
        assert result.stale == []
        assert result.uncovered == []
        assert result.orphaned == []


# ── Prompt loading ───────────────────────────────────────────────────


class TestPromptLoading:
    def test_wiki_compile_prompt_exists(self):
        from clawed.wiki import _load_prompt

        prompt = _load_prompt("wiki_compile")
        assert "wiki article" in prompt.lower()
        assert len(prompt) > 50

    def test_wiki_query_prompt_exists(self):
        from clawed.wiki import _load_prompt

        prompt = _load_prompt("wiki_query")
        assert "question" in prompt.lower()
        assert len(prompt) > 50

    def test_missing_prompt_returns_empty(self):
        from clawed.wiki import _load_prompt

        prompt = _load_prompt("nonexistent_prompt_xyz")
        assert prompt == ""


# ── CLI commands exist ───────────────────────────────────────────────


class TestKBCommands:
    def test_compile_command_exists(self):
        from clawed.commands.kb import kb_app

        names = [cmd.name for cmd in kb_app.registered_commands]
        assert "compile" in names

    def test_query_command_exists(self):
        from clawed.commands.kb import kb_app

        names = [cmd.name for cmd in kb_app.registered_commands]
        assert "query" in names

    def test_lint_command_exists(self):
        from clawed.commands.kb import kb_app

        names = [cmd.name for cmd in kb_app.registered_commands]
        assert "lint" in names

    def test_existing_commands_unchanged(self):
        from clawed.commands.kb import kb_app

        names = [cmd.name for cmd in kb_app.registered_commands]
        assert "stats" in names
        assert "topics" in names
        assert "search" in names
        assert "browse" in names
