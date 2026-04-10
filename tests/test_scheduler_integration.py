"""Tests for proactive scheduler integration."""

from __future__ import annotations

import pytest

from clawed.agent_core.scheduler import AgentScheduler


class TestAgentScheduler:
    def test_init(self):
        scheduler = AgentScheduler()
        assert scheduler is not None

    def test_get_tasks(self):
        scheduler = AgentScheduler()
        tasks = scheduler.get_tasks()
        assert isinstance(tasks, list)
        # Should have the 5 built-in tasks
        names = [t["name"] for t in tasks]
        assert "morning-prep" in names
        assert "weekly-plan" in names
        assert "feedback-digest" in names
        assert "memory-compress" in names
        assert "student-digest" in names

    def test_enable_disable_task(self):
        scheduler = AgentScheduler()
        scheduler.enable_task("morning-prep")
        tasks = scheduler.get_tasks()
        morning = next(t for t in tasks if t["name"] == "morning-prep")
        assert morning["enabled"] is True

        scheduler.disable_task("morning-prep")
        tasks = scheduler.get_tasks()
        morning = next(t for t in tasks if t["name"] == "morning-prep")
        assert morning["enabled"] is False

    def test_set_schedule(self):
        scheduler = AgentScheduler()
        scheduler.set_schedule("morning-prep", "7:30")
        tasks = scheduler.get_tasks()
        morning = next(t for t in tasks if t["name"] == "morning-prep")
        assert morning["schedule"]["hour"] == "7"
        assert morning["schedule"]["minute"] == "30"

    def test_tasks_have_required_fields(self):
        scheduler = AgentScheduler()
        for task in scheduler.get_tasks():
            assert "name" in task
            assert "enabled" in task
            assert "schedule" in task
            assert "description" in task


class TestHandleSystemEvent:
    @pytest.mark.asyncio
    async def test_system_event_emits(self):
        from clawed.agent_core.core import Gateway as AgentGateway
        from clawed.agent_core.fake_llm import FakeLLM
        from clawed.models import AppConfig

        llm = FakeLLM([{"type": "text", "content": "Handled system event"}])
        gw = AgentGateway(config=AppConfig(agent_gateway=True), llm=llm)
        result = await gw.handle_system_event(
            "scheduled_task",
            teacher_id="t1",
            payload={"task_name": "morning-prep"},
        )
        assert result is not None
        assert result.text  # should have some response

    @pytest.mark.asyncio
    async def test_system_event_uses_task_name_in_message(self):
        from clawed.agent_core.core import Gateway as AgentGateway
        from clawed.agent_core.fake_llm import FakeLLM
        from clawed.models import AppConfig

        llm = FakeLLM([{"type": "text", "content": "Morning prep complete"}])
        gw = AgentGateway(config=AppConfig(agent_gateway=True), llm=llm)
        result = await gw.handle_system_event(
            "scheduled_task",
            teacher_id="t1",
            payload={"task_name": "morning-prep"},
        )
        assert result.text == "Morning prep complete"

    @pytest.mark.asyncio
    async def test_system_event_default_teacher_id(self):
        from clawed.agent_core.core import Gateway as AgentGateway
        from clawed.agent_core.fake_llm import FakeLLM
        from clawed.models import AppConfig

        llm = FakeLLM([{"type": "text", "content": "Done"}])
        gw = AgentGateway(config=AppConfig(agent_gateway=True), llm=llm)
        # No teacher_id — should default to "local-teacher"
        result = await gw.handle_system_event(
            "scheduled_task",
            payload={"task_name": "feedback-digest"},
        )
        assert result is not None
        assert result.text == "Done"

    @pytest.mark.asyncio
    async def test_system_event_handles_error_gracefully(self):
        from clawed.agent_core.core import Gateway as AgentGateway
        from clawed.agent_core.fake_llm import FakeLLM
        from clawed.models import AppConfig

        # FakeLLM with no responses will raise on generate
        llm = FakeLLM([])
        gw = AgentGateway(config=AppConfig(agent_gateway=True), llm=llm)
        result = await gw.handle_system_event(
            "scheduled_task",
            payload={"task_name": "morning-prep"},
        )
        assert result is not None
        assert "could not be processed" in result.text


class TestScheduleTaskTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.schedule_task import ScheduleTaskTool

        tool = ScheduleTaskTool()
        s = tool.schema()
        assert s["function"]["name"] == "schedule_task"
        assert "action" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_list_tasks(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.context import AgentContext
        from clawed.agent_core.tools.schedule_task import ScheduleTaskTool
        from clawed.models import AppConfig

        tool = ScheduleTaskTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"action": "list"}, ctx)
        assert "morning-prep" in result.text
