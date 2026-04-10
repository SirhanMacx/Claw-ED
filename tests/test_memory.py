"""Tests for the cognitive memory system."""

from clawed.agent_core.memory.identity import load_identity, load_identity_from_db


class TestIdentityLayer:
    def test_load_identity_no_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawed.agent_core.memory.identity.IDENTITY_PATH", tmp_path / "nonexistent" / "identity.md")
        result = load_identity()
        assert isinstance(result, dict)
        assert result.get("name", "") == ""

    def test_load_identity_with_file(self, tmp_path, monkeypatch):
        ws = tmp_path / "workspace"
        ws.mkdir(parents=True)
        identity_file = ws / "identity.md"
        identity_file.write_text("# Ms. Smith\nSubject: Science\nGrade: 8\nStyle: inquiry-based\n")
        monkeypatch.setattr("clawed.agent_core.memory.identity.IDENTITY_PATH", identity_file)
        result = load_identity()
        assert result["name"] == "Ms. Smith"
        assert "inquiry-based" in result["raw"]

    def test_load_identity_from_db_no_teacher(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        result = load_identity_from_db("nonexistent-teacher")
        assert isinstance(result, dict)
        assert result.get("name", "") == ""


class TestCurriculumStateLayer:
    def test_load_curriculum_state_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.memory.curriculum import load_curriculum_state

        state = load_curriculum_state("nonexistent-teacher")
        assert isinstance(state, dict)
        assert state["units_generated"] == 0
        assert state["lessons_generated"] == 0
        assert state["recent_topics"] == []

    def test_summarize_curriculum_state(self):
        from clawed.agent_core.memory.curriculum import summarize_curriculum_state

        state = {
            "units_generated": 3,
            "lessons_generated": 15,
            "recent_topics": ["photosynthesis", "cell division"],
            "standards_covered": ["NGSS MS-LS1-5", "NGSS MS-LS1-6"],
            "avg_rating": 4.2,
            "recent_feedback": [],
        }
        summary = summarize_curriculum_state(state)
        assert "3 units" in summary
        assert "photosynthesis" in summary

    def test_summarize_empty_state(self):
        from clawed.agent_core.memory.curriculum import summarize_curriculum_state

        state = {
            "units_generated": 0,
            "lessons_generated": 0,
            "recent_topics": [],
            "standards_covered": [],
            "avg_rating": 0.0,
            "recent_feedback": [],
        }
        summary = summarize_curriculum_state(state)
        assert summary == ""


class TestEmbeddingProvider:
    def test_tfidf_embed(self):
        from clawed.agent_core.memory.embeddings import get_embedder

        embedder = get_embedder()
        vec = embedder.embed("photosynthesis is the process of converting light to energy")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(x, float) for x in vec)

    def test_tfidf_similarity(self):
        from clawed.agent_core.memory.embeddings import get_embedder

        embedder = get_embedder()
        v1 = embedder.embed("photosynthesis in plants")
        v2 = embedder.embed("plant energy from sunlight")
        v3 = embedder.embed("the american revolution war")
        sim_related = embedder.cosine_similarity(v1, v2)
        sim_unrelated = embedder.cosine_similarity(v1, v3)
        assert sim_related > sim_unrelated

    def test_embed_batch(self):
        from clawed.agent_core.memory.embeddings import get_embedder

        embedder = get_embedder()
        vecs = embedder.embed_batch(["hello world", "foo bar"])
        assert len(vecs) == 2
        assert all(isinstance(v, list) for v in vecs)


class TestEpisodicMemory:
    def test_store_and_recall(self, tmp_path):
        from clawed.agent_core.memory.episodes import EpisodicMemory

        mem = EpisodicMemory(db_path=tmp_path / "episodes.db")
        mem.store("t1", "I taught photosynthesis today and it went well")
        mem.store("t1", "Students struggled with the light reactions diagram")
        mem.store("t1", "The American Revolution unit is starting next week")

        results = mem.recall("t1", "photosynthesis", top_k=2)
        assert len(results) <= 2
        assert any("photosynthesis" in r["text"] for r in results)

    def test_recall_empty(self, tmp_path):
        from clawed.agent_core.memory.episodes import EpisodicMemory

        mem = EpisodicMemory(db_path=tmp_path / "episodes.db")
        results = mem.recall("t1", "anything", top_k=5)
        assert results == []

    def test_store_with_metadata(self, tmp_path):
        from clawed.agent_core.memory.episodes import EpisodicMemory

        mem = EpisodicMemory(db_path=tmp_path / "episodes.db")
        mem.store("t1", "Great lesson on fractions", metadata={"type": "feedback", "rating": 5})
        results = mem.recall("t1", "fractions")
        assert len(results) == 1
        assert results[0]["metadata"]["rating"] == 5

    def test_teacher_isolation(self, tmp_path):
        from clawed.agent_core.memory.episodes import EpisodicMemory

        mem = EpisodicMemory(db_path=tmp_path / "episodes.db")
        mem.store("t1", "Teacher 1 content about science")
        mem.store("t2", "Teacher 2 content about math")
        results = mem.recall("t1", "content")
        assert len(results) == 1
        assert "Teacher 1" in results[0]["text"]


class TestMemoryLoader:
    def test_load_full_context(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.memory.loader import load_memory_context

        ctx = load_memory_context("test-teacher", "What should I teach tomorrow?")
        assert isinstance(ctx, dict)
        assert "identity_summary" in ctx
        assert "curriculum_summary" in ctx
        assert "relevant_episodes" in ctx
        assert "improvement_context" in ctx

    def test_load_memory_context_graceful_on_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.memory.loader import load_memory_context

        ctx = load_memory_context("nonexistent", "hello")
        assert isinstance(ctx["identity_summary"], str)
        assert isinstance(ctx["curriculum_summary"], str)


class TestPreferenceLearning:
    def test_extract_preferences_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.memory.preferences import extract_preferences

        prefs = extract_preferences("nonexistent")
        assert isinstance(prefs, dict)
        assert "positive_patterns" in prefs
        assert "negative_patterns" in prefs

    def test_summarize_preferences(self):
        from clawed.agent_core.memory.preferences import summarize_preferences

        prefs = {
            "positive_patterns": ["Inquiry-based activities work well"],
            "negative_patterns": ["Avoid long lectures"],
            "structural_prefs": ["Teacher edits Do Now section"],
        }
        summary = summarize_preferences(prefs)
        assert "Inquiry-based" in summary
        assert "Do Now" in summary

    def test_summarize_empty(self):
        from clawed.agent_core.memory.preferences import summarize_preferences

        assert summarize_preferences({"positive_patterns": [], "negative_patterns": [], "structural_prefs": []}) == ""
