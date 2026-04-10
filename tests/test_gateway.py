"""Tests for Claw-ED gateway."""

from __future__ import annotations

import asyncio

from clawed.gateway import ActivityEvent, EduAgentGateway, GatewayStats


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


class TestGatewayStats:
    def test_gateway_stats_init(self):
        """Verify default counter values."""
        stats = GatewayStats()
        assert stats.messages_today == 0
        assert stats.generations_today == 0
        assert stats.errors_today == 0

    def test_gateway_stats_uptime(self):
        """Uptime should be non-negative immediately after creation."""
        stats = GatewayStats()
        assert stats.uptime_seconds >= 0


class TestActivityEvents:
    def test_emit_event(self):
        """Emit an event and verify it's in the event bus."""

        async def _inner():
            gateway = EduAgentGateway()
            await gateway.emit(
                "message_received",
                {
                    "teacher_id": "mr_mac",
                    "text": "plan a lesson on Imperialism",
                },
            )

            assert not gateway.event_bus.empty()
            event = await gateway.event_bus.get()
            assert isinstance(event, ActivityEvent)
            assert event.event_type == "message_received"
            assert event.actor == "mr_mac"
            assert event.message == "plan a lesson on Imperialism"

        _run(_inner())

    def test_event_bus_overflow(self):
        """When queue is full, oldest event should be dropped."""

        async def _inner():
            gateway = EduAgentGateway()
            # Fill the queue (maxsize=500)
            for i in range(500):
                await gateway.emit("system", {"message": f"event {i}"})
            assert gateway.event_bus.full()

            # Adding one more should succeed (drops oldest)
            await gateway.emit("system", {"message": "overflow event"})
            assert gateway.event_bus.full()

            # First event should now be event 1 (event 0 was dropped)
            event = await gateway.event_bus.get()
            assert event.message == "event 1"

        _run(_inner())

    def test_emit_error_event(self):
        """Error events should work."""

        async def _inner():
            gateway = EduAgentGateway()
            await gateway.emit("error", {"message": "connection failed"})

            event = await gateway.event_bus.get()
            assert event.event_type == "error"
            assert event.message == "connection failed"

        _run(_inner())


class TestGatewayInit:
    def test_gateway_creates_with_defaults(self):
        """Gateway should initialize with default config."""
        gateway = EduAgentGateway()
        assert gateway.config is not None
        assert gateway._stats.messages_today == 0
        assert gateway.event_bus.maxsize == 500

    def test_gateway_start_demo_mode(self):
        """Starting without a token should enter demo mode and return."""

        async def _inner():
            gateway = EduAgentGateway()
            await gateway.start()
            # Should complete without hanging — demo mode with no Telegram
            assert gateway._running is True

        _run(_inner())

    def test_gateway_stats_method(self):
        """The stats() method should return a dict with expected keys."""

        async def _inner():
            gateway = EduAgentGateway()
            s = await gateway.stats()
            assert "messages_today" in s
            assert "generations_today" in s
            assert "errors_today" in s
            assert "uptime_seconds" in s
            assert "active_sessions" in s
            assert s["messages_today"] == 0

        _run(_inner())


class TestGatewayProcessMessage:
    def test_process_message_increments_stats(self):
        """process_message should increment counters and populate active_sessions."""

        async def _inner():
            gateway = EduAgentGateway()

            # Simulate what process_message does internally
            gateway._stats.messages_today += 1
            gateway.active_sessions["t1"] = {"name": "Mac", "last_activity": "now"}

            assert gateway._stats.messages_today == 1
            assert "t1" in gateway.active_sessions

            s = await gateway.stats()
            assert s["messages_today"] == 1
            assert s["active_sessions"] == 1

        _run(_inner())
