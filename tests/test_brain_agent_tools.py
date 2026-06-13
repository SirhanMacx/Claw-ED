from __future__ import annotations

from pathlib import Path

import pytest

from clawed.agent_core.context import AgentContext
from clawed.agent_core.tools.base import ToolRegistry
from clawed.brain.store import BrainPage, BrainStore
from clawed.models import AppConfig


def _ctx() -> AgentContext:
    return AgentContext(
        teacher_id="t1",
        config=AppConfig(),
        teacher_profile={},
        persona=None,
        session_history=[],
        improvement_context="",
        transport="test",
    )


@pytest.fixture
def seeded_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BrainStore:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path / ".eduagent"))
    store = BrainStore()
    store.save(
        BrainPage(
            slug="industrial-revolution",
            page_type="topic",
            title="Industrial Revolution",
            compiled_truth="Stations work better than jigsaws for dense factory readings.",
        )
    )
    return store


def test_brain_tools_are_discovered() -> None:
    import clawed.agent_core.tools as tools_pkg

    registry = ToolRegistry()
    registry.discover(Path(tools_pkg.__file__).parent)
    names = set(registry.tool_names())

    assert "brain_stats" in names
    assert "brain_search" in names
    assert "brain_read" in names
    assert "brain_capture" in names
    assert "brain_dream" in names
    assert "curriculum_index" in names
    assert "portfolio_build" in names


@pytest.mark.asyncio
async def test_brain_search_tool_reads_default_store(seeded_home: BrainStore) -> None:
    from clawed.agent_core.tools.brain import BrainSearchTool

    result = await BrainSearchTool().execute(
        {"query": "factory readings", "include_corpus": False},
        _ctx(),
    )

    assert "industrial-revolution" in result.text
    assert result.data["results"]


@pytest.mark.asyncio
async def test_brain_capture_tool_persists_insight(seeded_home: BrainStore) -> None:
    from clawed.agent_core.tools.brain import BrainCaptureTool

    result = await BrainCaptureTool().execute(
        {
            "message": (
                "I think students write better CRQs when the cognitive verb is "
                "defined before they see the question."
            )
        },
        _ctx(),
    )

    assert "Captured insight" in result.text
    assert seeded_home.get("original", result.data["slug"]) is not None


@pytest.mark.asyncio
async def test_brain_dream_tool_supports_dry_run(seeded_home: BrainStore) -> None:
    from clawed.agent_core.tools.brain import BrainDreamTool

    result = await BrainDreamTool().execute(
        {"dry_run": True, "consolidate": False},
        _ctx(),
    )

    assert "Dream Cycle Report" in result.text
    assert result.data["pages_scanned"] >= 1


@pytest.mark.asyncio
async def test_portfolio_build_tool_writes_sample_artifacts(
    seeded_home: BrainStore,
) -> None:
    from clawed.agent_core.tools.portfolio import PortfolioBuildTool

    result = await PortfolioBuildTool().execute(
        {"topic": "Industrial Revolution", "source_status": "synthetic"},
        _ctx(),
    )

    assert "Built sample portfolio" in result.text
    assert len(result.files) >= 6
    assert any(path.name == "manifest.json" for path in result.files)
