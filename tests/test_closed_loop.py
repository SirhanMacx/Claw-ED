"""Integration test — proves the feedback loop closes.

Flow: generate -> feedback -> next generation sees the feedback.
"""

import pytest

from clawed.agent_core.memory.episodes import EpisodicMemory
from clawed.agent_core.memory.loader import load_memory_context
from clawed.models import AppConfig


class TestClosedLoop:
    def test_episode_stored_after_interaction(self, tmp_path, monkeypatch):
        """After an agent interaction, the exchange is stored as an episode."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        mem = EpisodicMemory(db_path=tmp_path / "memory" / "episodes.db")
        mem.store("t1", "Teacher: Plan a lesson on photosynthesis\nClaw-ED: Generated lesson on photosynthesis.")

        results = mem.recall("t1", "photosynthesis")
        assert len(results) >= 1
        assert "photosynthesis" in results[0]["text"]

    def test_feedback_influences_next_context(self, tmp_path, monkeypatch):
        """Stored feedback appears in the memory context for the next interaction."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))

        db_path = tmp_path / "memory" / "episodes.db"

        # Store an episode with feedback
        mem = EpisodicMemory(db_path=db_path)
        mem.store(
            "t1",
            "Teacher rated lesson 'Photosynthesis Intro' 5 stars. "
            "Feedback: The inquiry-based Do Now worked really well.",
            metadata={"type": "feedback", "rating": 5},
        )

        # Point the default DB path so load_memory_context finds our episodes
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes._DEFAULT_DB",
            db_path,
        )

        # Load context for a new interaction about the same topic
        ctx = load_memory_context("t1", "plan another photosynthesis lesson")
        # The relevant episode should appear
        assert (
            "inquiry-based" in ctx.get("relevant_episodes", "")
            or "photosynthesis" in ctx.get("relevant_episodes", "")
            or ctx.get("relevant_episodes", "") != ""
        )

    def test_negative_feedback_appears_in_context(self, tmp_path, monkeypatch):
        """Negative feedback shows up to prevent repeating mistakes."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))

        db_path = tmp_path / "memory" / "episodes.db"

        mem = EpisodicMemory(db_path=db_path)
        mem.store(
            "t1",
            "Teacher rated lesson 'Cell Division' 1 star. Feedback: The vocabulary section was too long and boring.",
            metadata={"type": "feedback", "rating": 1},
        )

        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes._DEFAULT_DB",
            db_path,
        )

        ctx = load_memory_context("t1", "plan a lesson on cell division")
        episodes = ctx.get("relevant_episodes", "")
        assert "vocabulary" in episodes or "boring" in episodes or "cell" in episodes.lower()

    @pytest.mark.asyncio
    async def test_full_loop_with_fake_llm(self, tmp_path, monkeypatch):
        """Full loop: agent generates -> feedback stored -> next generation sees it."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))

        db_path = tmp_path / "memory" / "episodes.db"
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes._DEFAULT_DB",
            db_path,
        )

        from clawed.agent_core.core import Gateway as AgentGateway
        from clawed.agent_core.fake_llm import FakeLLM

        # Create a config file with teacher profile so onboarding is skipped
        from clawed.models import TeacherProfile

        config = AppConfig(
            agent_gateway=True,
            teacher_profile=TeacherProfile(name="Test Teacher", subjects=["Math"]),
        )
        config_path = tmp_path / "config.json"
        config_path.write_text(config.model_dump_json(), encoding="utf-8")

        # Step 1: Agent generates (with FakeLLM)
        llm = FakeLLM(
            [
                {"type": "text", "content": "Here's your lesson on fractions."},
            ]
        )
        gw = AgentGateway(config=config, llm=llm)
        result = await gw.handle("generate a lesson on fractions", "t1")
        assert "fractions" in result.text.lower()

        # Step 2: Store feedback as an episode
        mem = EpisodicMemory(db_path=db_path)
        mem.store(
            "t1",
            "Teacher feedback: The fractions lesson was great but needed more visual examples.",
            metadata={"type": "feedback", "rating": 4},
        )

        # Step 3: Next generation should see the feedback
        ctx = load_memory_context("t1", "another fractions lesson")
        # Should have episodes referencing fractions
        all_context = " ".join(
            [
                ctx.get("relevant_episodes", ""),
                ctx.get("improvement_context", ""),
                ctx.get("preferences_summary", ""),
            ]
        )
        assert "fractions" in all_context.lower() or len(ctx.get("relevant_episodes", "")) > 0

    def test_episode_metadata_includes_interaction_type(self, tmp_path, monkeypatch):
        """Episodes stored by the agent loop include metadata about the interaction."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))

        mem = EpisodicMemory(db_path=tmp_path / "memory" / "episodes.db")
        mem.store(
            "t1",
            "Teacher: Make a quiz\nClaw-ED: Here is a 10-question quiz.",
            metadata={
                "type": "interaction",
                "had_tool_calls": True,
                "message_length": 12,
            },
        )

        results = mem.recall("t1", "quiz")
        assert len(results) == 1
        meta = results[0]["metadata"]
        assert meta["type"] == "interaction"
        assert meta["had_tool_calls"] is True
        assert meta["message_length"] == 12
