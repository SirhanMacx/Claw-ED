"""Tests for gateway handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from clawed.gateway_response import GatewayResponse
from clawed.handlers.onboard import OnboardHandler, OnboardState


class TestOnboardHandler:
    def setup_method(self):
        self.handler = OnboardHandler()

    @pytest.mark.asyncio
    async def test_start_onboarding_asks_subject(self):
        r = await self.handler.step("teacher_1", "hi")
        assert isinstance(r, GatewayResponse)
        assert "subject" in r.text.lower() or "teach" in r.text.lower()

    @pytest.mark.asyncio
    async def test_subject_then_asks_grade(self):
        await self.handler.step("t1", "hi")  # → ask_subject
        r = await self.handler.step("t1", "math")  # → ask_grade
        assert "grade" in r.text.lower()

    @pytest.mark.asyncio
    async def test_grade_then_asks_name(self):
        await self.handler.step("t1", "hi")
        await self.handler.step("t1", "science")
        r = await self.handler.step("t1", "8th grade")
        assert "name" in r.text.lower()

    @pytest.mark.asyncio
    async def test_full_onboarding_flow(self):
        await self.handler.step("t1", "hi")
        await self.handler.step("t1", "history")
        await self.handler.step("t1", "10")
        r = await self.handler.step("t1", "Ms. Rivera")
        assert r.has_content

    @pytest.mark.asyncio
    async def test_is_onboarding(self):
        assert not self.handler.is_onboarding("t1")
        await self.handler.step("t1", "hi")
        assert self.handler.is_onboarding("t1")

    @pytest.mark.asyncio
    async def test_combined_subject_and_grade(self):
        """User says '8th grade math' in one message — should skip grade step."""
        await self.handler.step("t1", "hi")
        r = await self.handler.step("t1", "8th grade math")
        assert "name" in r.text.lower()

    @pytest.mark.asyncio
    async def test_onboarding_state_cleared_after_complete(self):
        await self.handler.step("t1", "hi")
        await self.handler.step("t1", "math")
        await self.handler.step("t1", "6")
        await self.handler.step("t1", "Mr. Smith")
        await self.handler.step("t1", "NY")
        assert not self.handler.is_onboarding("t1")

    def test_onboard_state_enum(self):
        assert OnboardState.ASK_SUBJECT.value == "ask_subject"
        assert OnboardState.DONE.value == "done"


from clawed.handlers.generate import GenerateHandler  # noqa: E402


class TestGenerateHandler:
    def setup_method(self):
        self.handler = GenerateHandler()

    @pytest.mark.asyncio
    async def test_generate_lesson_returns_response(self):
        with patch("clawed.generation.generate_lesson", new_callable=AsyncMock) as mock_gl:
            mock_gl.return_value = "Here is your lesson on photosynthesis..."
            r = await self.handler.lesson("photosynthesis", "teacher_1")
            assert isinstance(r, GatewayResponse)
            assert "photosynthesis" in r.text.lower()
            mock_gl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_unit_returns_response(self):
        with patch("clawed.generation.generate_unit", new_callable=AsyncMock) as mock_gu:
            mock_gu.return_value = "Unit plan for WWI..."
            r = await self.handler.unit("World War I", "teacher_1")
            assert isinstance(r, GatewayResponse)
            assert r.has_content

    @pytest.mark.asyncio
    async def test_generate_with_post_gen_buttons(self):
        with patch("clawed.generation.generate_lesson", new_callable=AsyncMock) as mock_gl:
            mock_gl.return_value = "Lesson content..."
            with patch("clawed.handlers.generate.get_last_lesson_id", return_value="lesson_abc"):
                r = await self.handler.lesson("fractions", "teacher_1")
                assert len(r.button_rows) > 0 or len(r.buttons) > 0

    @pytest.mark.asyncio
    async def test_generate_error_returns_friendly_message(self):
        with patch("clawed.generation.generate_lesson", new_callable=AsyncMock) as mock_gl:
            mock_gl.side_effect = RuntimeError("LLM timeout")
            r = await self.handler.lesson("topic", "teacher_1")
            assert "issue" in r.text.lower() or "error" in r.text.lower() or "try again" in r.text.lower()


from pathlib import Path  # noqa: E402

from clawed.handlers.export import ExportHandler  # noqa: E402


class TestExportHandler:
    def setup_method(self):
        self.handler = ExportHandler()

    @pytest.mark.asyncio
    async def test_export_unknown_format(self):
        r = await self.handler.export("lesson_123", "teacher_1", "unknown_format")
        assert "not supported" in r.text.lower() or "format" in r.text.lower()

    @pytest.mark.asyncio
    async def test_export_no_lesson_found(self):
        r = await self.handler.export("nonexistent_id", "teacher_1", "slides")
        assert "couldn't find" in r.text.lower() or "no lesson" in r.text.lower()

    @pytest.mark.asyncio
    async def test_export_slides_calls_pptx(self):
        from clawed.models import DailyLesson

        lesson = DailyLesson(
            title="Test Lesson",
            lesson_number=1,
            objective="Test",
            do_now="Test",
            direct_instruction="Test",
            guided_practice="Test",
            independent_work="Test",
        )
        with patch("clawed.handlers.export._load_lesson", return_value=lesson):
            with patch("clawed.handlers.export._load_persona", return_value=None):
                with patch.object(self.handler, "_do_export", new_callable=AsyncMock) as mock_export:
                    mock_export.return_value = Path("/tmp/test.pptx")
                    r = await self.handler.export("lesson_123", "teacher_1", "slides")
                    assert len(r.files) == 1
                    mock_export.assert_called_once()

    def test_supported_formats(self):
        assert "slides" in ExportHandler.SUPPORTED_FORMATS
        assert "handout" in ExportHandler.SUPPORTED_FORMATS
        assert "doc" in ExportHandler.SUPPORTED_FORMATS


from clawed.handlers.feedback import FeedbackHandler  # noqa: E402


class TestFeedbackHandler:
    def setup_method(self):
        self.handler = FeedbackHandler()

    @pytest.mark.asyncio
    async def test_rate_lesson_valid(self):
        with patch("clawed.handlers.feedback.rate_lesson") as mock_rate:
            with patch("clawed.handlers.feedback.memory_process"):
                r = await self.handler.rate("lesson_abc", "teacher_1", 5)
                assert r.has_content
                assert "5" in r.text or "star" in r.text.lower() or "thank" in r.text.lower()
                mock_rate.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_lesson_skip(self):
        r = await self.handler.rate("lesson_abc", "teacher_1", 0)
        assert "skip" in r.text.lower() or r.text == ""

    @pytest.mark.asyncio
    async def test_rate_prompt_returns_buttons(self):
        r = self.handler.rating_prompt("lesson_abc")
        assert len(r.buttons) > 0 or len(r.button_rows) > 0

    @pytest.mark.asyncio
    async def test_feedback_summary(self):
        with patch(
            "clawed.handlers.feedback.get_teacher_stats",
            return_value={
                "overall_avg_rating": 4.2,
                "rated_lessons": 10,
                "streak": 3,
                "total_lessons": 15,
                "total_units": 3,
                "total_feedback": 8,
                "rating_distribution": {1: 0, 2: 1, 3: 2, 4: 4, 5: 3},
            },
        ):
            r = await self.handler.summary("teacher_1")
            assert "4.2" in r.text or "rating" in r.text.lower()


from clawed.handlers.gaps import GapsHandler  # noqa: E402
from clawed.handlers.ingest import IngestHandler  # noqa: E402
from clawed.handlers.schedule import ScheduleHandler  # noqa: E402
from clawed.handlers.standards import StandardsHandler  # noqa: E402


class TestScheduleHandler:
    def setup_method(self):
        self.handler = ScheduleHandler()

    @pytest.mark.asyncio
    async def test_show_schedule(self):
        with patch(
            "clawed.handlers.schedule.load_schedule_config",
            return_value={"tasks": {"morning-prep": {"enabled": True, "cron": {"hour": "6", "minute": "0"}}}},
        ):
            r = await self.handler.show("teacher_1")
            assert r.has_content
            assert "morning" in r.text.lower()

    @pytest.mark.asyncio
    async def test_disable_task(self):
        with patch("clawed.handlers.schedule.disable_task") as mock_dis:
            r = await self.handler.disable("teacher_1", "morning-prep")
            assert r.has_content
            mock_dis.assert_called_once()


class TestGapsHandler:
    def setup_method(self):
        self.handler = GapsHandler()

    @pytest.mark.asyncio
    async def test_gaps_returns_response(self):
        with patch("clawed.generation.generate_freeform", new_callable=AsyncMock) as mock_gf:
            mock_gf.return_value = "You're missing: fractions, decimals"
            r = await self.handler.analyze("teacher_1")
            assert r.has_content


class TestStandardsHandler:
    def setup_method(self):
        self.handler = StandardsHandler()

    @pytest.mark.asyncio
    async def test_lookup_standards(self):
        with patch(
            "clawed.handlers.standards.get_standards", return_value=[("CCSS.MATH.6.NS.1", "Divide fractions", "6-8")]
        ):
            r = await self.handler.lookup("math", "6")
            assert r.has_content
            assert "CCSS" in r.text or "standard" in r.text.lower()

    @pytest.mark.asyncio
    async def test_no_standards_found(self):
        with patch("clawed.handlers.standards.get_standards", return_value=[]):
            r = await self.handler.lookup("underwater basket weaving", "99")
            assert "no standards" in r.text.lower() or "couldn't find" in r.text.lower()


class TestIngestHandler:
    def setup_method(self):
        self.handler = IngestHandler()

    @pytest.mark.asyncio
    async def test_ingest_returns_instructions_when_no_files(self):
        r = await self.handler.handle(teacher_id="teacher_1", files=[])
        assert "upload" in r.text.lower() or "send" in r.text.lower()

    @pytest.mark.asyncio
    async def test_ingest_with_path(self):
        with patch("clawed.handlers.ingest.ingest_path") as mock_ingest:
            mock_ingest.return_value = [{"title": "doc1", "content": "stuff"}]
            with patch("clawed.handlers.ingest.extract_persona", new_callable=AsyncMock):
                r = await self.handler.handle(teacher_id="teacher_1", files=[], path="/tmp/test_lessons")
                assert r.has_content


from clawed.handlers.misc import DemoHandler, PersonaHandler, ProgressHandler, SettingsHandler  # noqa: E402


class TestMiscHandlers:
    @pytest.mark.asyncio
    async def test_demo_handler(self):
        with patch("clawed.generation.generate_lesson", new_callable=AsyncMock) as mock_gl:
            mock_gl.return_value = "Here's a sample lesson..."
            handler = DemoHandler()
            r = await handler.run("teacher_1")
            assert r.has_content

    @pytest.mark.asyncio
    async def test_persona_handler_no_persona(self):
        handler = PersonaHandler()
        with patch("clawed.handlers.misc.TeacherSession", create=True) as mock_session_cls:
            mock_session = mock_session_cls.load.return_value
            mock_session.persona = None
            # PersonaHandler does a lazy import of TeacherSession inside show(),
            # so we patch at the state module level
            with patch.dict("sys.modules", {"clawed.state": type("mod", (), {"TeacherSession": mock_session_cls})}):
                r = await handler.show("teacher_1")
                assert r.has_content

    @pytest.mark.asyncio
    async def test_settings_handler(self):
        handler = SettingsHandler()
        # SettingsHandler tries to load AppConfig which may fail in tests — that's OK,
        # the handler catches exceptions and returns a response.
        r = await handler.show("teacher_1")
        assert r.has_content

    @pytest.mark.asyncio
    async def test_progress_handler(self):
        handler = ProgressHandler()
        # ProgressHandler tries to load analytics — catches exceptions.
        r = await handler.show("teacher_1")
        assert r.has_content
