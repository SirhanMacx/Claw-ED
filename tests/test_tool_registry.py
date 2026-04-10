"""Tests for the tool protocol, registry, individual tools, and auto-discovery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import ToolRegistry
from clawed.models import AppConfig


def _ctx(**overrides) -> AgentContext:
    """Build a minimal AgentContext for testing."""
    defaults = dict(
        teacher_id="t1",
        config=AppConfig(),
        teacher_profile={},
        persona=None,
        session_history=[],
        improvement_context="",
    )
    defaults.update(overrides)
    return AgentContext(**defaults)


class _DummyTool:
    """A minimal tool for testing the registry."""

    risk_level = "read_only"  # Test tools bypass approval policy

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "dummy",
                "description": "A test tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }

    async def execute(self, params: dict, context: AgentContext) -> ToolResult:
        return ToolResult(text="dummy result")


# ── Registry basics ──────────────────────────────────────────────────────


class TestToolRegistry:
    def test_register_and_list(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())
        names = reg.tool_names()
        assert "dummy" in names

    def test_get_tool(self):
        reg = ToolRegistry()
        tool = _DummyTool()
        reg.register(tool)
        assert reg.get("dummy") is tool

    def test_get_unknown_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_schemas(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())
        schemas = reg.schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "dummy"

    @pytest.mark.asyncio
    async def test_execute(self):
        reg = ToolRegistry()
        reg.register(_DummyTool())
        result = await reg.execute("dummy", {}, _ctx())
        assert result.text == "dummy result"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        result = await reg.execute("nonexistent", {}, _ctx())
        assert "Unknown tool" in result.text


# ── generate_lesson (from Task 7) ────────────────────────────────────────


class TestGenerateLessonTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.generate_lesson import GenerateLessonTool

        tool = GenerateLessonTool()
        s = tool.schema()
        assert s["function"]["name"] == "generate_lesson"
        assert "topic" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.generate_lesson import GenerateLessonTool

        tool = GenerateLessonTool()
        mock_lesson = type(
            "Lesson",
            (),
            {"model_dump": lambda self: {"title": "Fractions", "sections": []}},
        )()
        with patch("clawed.lesson.generate_lesson", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_lesson
            result = await tool.execute({"topic": "fractions"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "Fractions" in result.text or "fractions" in result.text.lower()


# ── generate_unit ─────────────────────────────────────────────────────────


class TestGenerateUnitTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.generate_unit import GenerateUnitTool

        tool = GenerateUnitTool()
        s = tool.schema()
        assert s["function"]["name"] == "generate_unit"
        assert "topic" in s["function"]["parameters"]["properties"]
        assert "weeks" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.generate_unit import GenerateUnitTool

        tool = GenerateUnitTool()
        mock_unit = type(
            "Unit",
            (),
            {
                "model_dump": lambda self: {"title": "Photosynthesis Unit"},
                "daily_lessons": [1, 2, 3],
            },
        )()
        with patch("clawed.planner.plan_unit", new_callable=AsyncMock) as mock_plan:
            mock_plan.return_value = mock_unit
            result = await tool.execute({"topic": "photosynthesis"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "Photosynthesis" in result.text


# ── generate_materials ────────────────────────────────────────────────────


class TestGenerateMaterialsTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.generate_materials import GenerateMaterialsTool

        tool = GenerateMaterialsTool()
        s = tool.schema()
        assert s["function"]["name"] == "generate_materials"
        assert "topic" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.generate_materials import GenerateMaterialsTool

        tool = GenerateMaterialsTool()
        mock_item = type("Item", (), {"model_dump": lambda self: {"q": "What?"}})()
        with patch("clawed.materials.generate_worksheet", new_callable=AsyncMock) as mock_ws:
            mock_ws.return_value = [mock_item, mock_item]
            result = await tool.execute({"topic": "fractions"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "2" in result.text  # 2 items


# ── generate_assessment ───────────────────────────────────────────────────


class TestGenerateAssessmentTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.generate_assessment import GenerateAssessmentTool

        tool = GenerateAssessmentTool()
        s = tool.schema()
        assert s["function"]["name"] == "generate_assessment"
        assert "topic" in s["function"]["parameters"]["properties"]
        assert "num_questions" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.generate_assessment import GenerateAssessmentTool

        tool = GenerateAssessmentTool()
        mock_quiz = type(
            "Quiz",
            (),
            {
                "model_dump": lambda self: {"topic": "Fractions"},
                "topic": "Fractions",
                "total_points": 50,
                "questions": [1, 2, 3],
            },
        )()
        with patch(
            "clawed.assessment.AssessmentGenerator.generate_quiz",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = mock_quiz
            result = await tool.execute({"topic": "fractions"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "Fractions" in result.text


# ── search_standards ──────────────────────────────────────────────────────


class TestSearchStandardsTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.search_standards import SearchStandardsTool

        tool = SearchStandardsTool()
        s = tool.schema()
        assert s["function"]["name"] == "search_standards"
        assert "subject" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.search_standards import SearchStandardsTool

        tool = SearchStandardsTool()
        with patch("clawed.standards.get_standards") as mock_gs:
            mock_gs.return_value = [("CCSS.MATH.8.EE.1", "Integer exponents", "8")]
            result = await tool.execute({"subject": "math", "grade": "8"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "CCSS" in result.text

    @pytest.mark.asyncio
    async def test_execute_no_results(self):
        from clawed.agent_core.tools.search_standards import SearchStandardsTool

        tool = SearchStandardsTool()
        with patch("clawed.standards.get_standards") as mock_gs:
            mock_gs.return_value = []
            result = await tool.execute({"subject": "underwater_basket"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "No standards" in result.text


# ── ingest_materials ──────────────────────────────────────────────────────


class TestIngestMaterialsTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.ingest_materials import IngestMaterialsTool

        tool = IngestMaterialsTool()
        s = tool.schema()
        assert s["function"]["name"] == "ingest_materials"
        assert "path" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_path_not_found(self):
        from pathlib import Path

        from clawed.agent_core.tools.ingest_materials import IngestMaterialsTool

        tool = IngestMaterialsTool()
        fake = str(Path.home() / "nonexistent_clawed_test_path")
        result = await tool.execute({"path": fake}, _ctx())
        assert isinstance(result, ToolResult)
        assert "not found" in result.text.lower()

    @pytest.mark.asyncio
    async def test_execute_path_outside_home(self):
        from clawed.agent_core.tools.ingest_materials import IngestMaterialsTool

        tool = IngestMaterialsTool()
        result = await tool.execute({"path": "/nonexistent/path"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "access denied" in result.text.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self, tmp_path):
        from pathlib import Path

        from clawed.agent_core.tools.ingest_materials import IngestMaterialsTool

        tool = IngestMaterialsTool()
        mock_doc = MagicMock()
        # Patch home check to allow tmp_path
        with (
            patch("clawed.agent_core.tools.ingest_materials.Path") as mock_path,
            patch("clawed.ingestor.ingest_path") as mock_ip,
        ):
            mock_path.home.return_value.resolve.return_value = tmp_path.parent
            mock_path.side_effect = lambda p: Path(p)
            mock_ip.return_value = [mock_doc, mock_doc]
            result = await tool.execute({"path": str(tmp_path)}, _ctx())
        assert isinstance(result, ToolResult)
        assert "2" in result.text


# ── export_document ───────────────────────────────────────────────────────


class TestExportDocumentTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.export_document import ExportDocumentTool

        tool = ExportDocumentTool()
        s = tool.schema()
        assert s["function"]["name"] == "export_document"
        assert "topic" in s["function"]["parameters"]["properties"]
        assert "format" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self, tmp_path):
        from clawed.agent_core.tools.export_document import ExportDocumentTool

        tool = ExportDocumentTool()
        # The tool generates a lesson first, then exports.
        # We mock the full chain — just verify it doesn't crash.
        mock_lesson = MagicMock()
        mock_lesson.lesson_number = 1
        mock_lesson.title = "Test Lesson"
        mock_lesson.objective = "Learn stuff"
        out_file = tmp_path / "lesson_01.pdf"
        out_file.touch()
        with (
            patch("clawed.lesson.generate_lesson", new_callable=AsyncMock) as mock_gen,
            patch("clawed.export_pdf.export_lesson_pdf") as mock_pdf,
        ):
            mock_gen.return_value = mock_lesson
            mock_pdf.return_value = out_file
            result = await tool.execute(
                {"topic": "fractions", "format": "pdf", "output_dir": str(tmp_path)},
                _ctx(),
            )
        assert isinstance(result, ToolResult)


# ── configure_profile ─────────────────────────────────────────────────────


class TestConfigureProfileTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.configure_profile import ConfigureProfileTool

        tool = ConfigureProfileTool()
        s = tool.schema()
        assert s["function"]["name"] == "configure_profile"
        assert "teacher_name" in s["function"]["parameters"]["properties"]
        assert "subject" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.configure_profile import ConfigureProfileTool

        tool = ConfigureProfileTool()
        # Mock the config.save(), TeacherSession, init_workspace
        with (
            patch("clawed.models.AppConfig.save"),
            patch("clawed.state.TeacherSession.load") as mock_load,
        ):
            mock_session = MagicMock()
            mock_load.return_value = mock_session
            result = await tool.execute({"teacher_name": "Ms. Smith", "subject": "Math"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "Ms. Smith" in result.text


# ── request_approval ──────────────────────────────────────────────────────


class TestRequestApprovalTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.request_approval import RequestApprovalTool

        tool = RequestApprovalTool()
        s = tool.schema()
        assert s["function"]["name"] == "request_approval"
        assert "action_description" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self, tmp_path):
        from clawed.agent_core.tools.request_approval import RequestApprovalTool

        tool = RequestApprovalTool()
        with patch(
            "clawed.agent_core.approvals.ApprovalManager.__init__",
            lambda self, **kw: setattr(self, "_dir", tmp_path) or None,
        ):
            result = await tool.execute(
                {
                    "action_description": "Send grade report",
                    "action_payload": {"grades": [90, 85]},
                },
                _ctx(),
            )
        assert isinstance(result, ToolResult)
        assert "Approval requested" in result.text


# ── search_lessons ────────────────────────────────────────────────────────


class TestSearchLessonsTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.search_lessons import SearchLessonsTool

        tool = SearchLessonsTool()
        s = tool.schema()
        assert s["function"]["name"] == "search_lessons"
        assert "unit_id" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_no_results(self):
        from clawed.agent_core.tools.search_lessons import SearchLessonsTool

        tool = SearchLessonsTool()
        with (
            patch("clawed.database.Database.__init__", return_value=None),
            patch("clawed.database.Database.list_lessons", return_value=[]),
        ):
            result = await tool.execute({"unit_id": "unit-xyz"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "No lessons" in result.text


# ── curriculum_map ────────────────────────────────────────────────────────


class TestCurriculumMapTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.curriculum_map import CurriculumMapTool

        tool = CurriculumMapTool()
        s = tool.schema()
        assert s["function"]["name"] == "curriculum_map"
        assert "subject" in s["function"]["parameters"]["properties"]
        assert "grade" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.curriculum_map import CurriculumMapTool

        tool = CurriculumMapTool()
        mock_map = MagicMock()
        mock_map.model_dump.return_value = {"title": "Math 8 Map", "units": []}
        mock_map.units = []
        with patch(
            "clawed.curriculum_map.CurriculumMapper.generate_year_map",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = mock_map
            result = await tool.execute({"subject": "Math", "grade": "8"}, _ctx())
        assert isinstance(result, ToolResult)
        assert "curriculum map" in result.text.lower() or "Math" in result.text


# ── gap_analysis ──────────────────────────────────────────────────────────


class TestGapAnalysisTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.gap_analysis import GapAnalysisTool

        tool = GapAnalysisTool()
        s = tool.schema()
        assert s["function"]["name"] == "gap_analysis"
        assert "existing_materials" in s["function"]["parameters"]["properties"]
        assert "standards" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_no_gaps(self):
        from clawed.agent_core.tools.gap_analysis import GapAnalysisTool

        tool = GapAnalysisTool()
        with patch(
            "clawed.curriculum_map.CurriculumMapper.identify_curriculum_gaps",
            new_callable=AsyncMock,
        ) as mock_gaps:
            mock_gaps.return_value = []
            result = await tool.execute(
                {
                    "existing_materials": ["Lesson on fractions"],
                    "standards": ["CCSS.MATH.8.EE.1"],
                },
                _ctx(),
            )
        assert isinstance(result, ToolResult)
        assert "No curriculum gaps" in result.text


# ── sub_packet ────────────────────────────────────────────────────────────


class TestSubPacketTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.sub_packet import SubPacketTool

        tool = SubPacketTool()
        s = tool.schema()
        assert s["function"]["name"] == "sub_packet"
        assert "teacher_name" in s["function"]["parameters"]["properties"]
        assert "school" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.sub_packet import SubPacketTool

        tool = SubPacketTool()
        mock_packet = MagicMock()
        mock_packet.model_dump.return_value = {
            "teacher_name": "Ms. Smith",
            "overview": "Continue chapter 5",
        }
        with (
            patch("clawed.sub_packet.generate_sub_packet", new_callable=AsyncMock) as mock_gen,
            patch("clawed.sub_packet.sub_packet_to_markdown", return_value="# Sub Packet"),
        ):
            mock_gen.return_value = mock_packet
            result = await tool.execute(
                {
                    "teacher_name": "Ms. Smith",
                    "school": "Lincoln MS",
                    "class_name": "Period 3 Math",
                    "grade": "8",
                    "subject": "Math",
                    "date": "2025-03-15",
                    "period_or_time": "9:00-10:00",
                },
                _ctx(),
            )
        assert isinstance(result, ToolResult)


# ── parent_comm ───────────────────────────────────────────────────────────


class TestParentCommTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.parent_comm import ParentCommTool

        tool = ParentCommTool()
        s = tool.schema()
        assert s["function"]["name"] == "parent_comm"
        assert "comm_type" in s["function"]["parameters"]["properties"]
        assert "student_description" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        from clawed.agent_core.tools.parent_comm import ParentCommTool

        tool = ParentCommTool()
        mock_comm = MagicMock()
        mock_comm.subject_line = "Progress Update"
        mock_comm.email_body = "Dear Parent..."
        mock_comm.follow_up_suggestions = ["Schedule a conference"]
        with (
            patch("clawed.parent_comm.generate_parent_comm", new_callable=AsyncMock) as mock_gen,
            patch(
                "clawed.parent_comm.parent_comm_to_text",
                return_value="Subject: Progress Update\n\nDear Parent...",
            ),
        ):
            mock_gen.return_value = mock_comm
            result = await tool.execute(
                {
                    "comm_type": "progress_update",
                    "student_description": "Struggling with fractions",
                    "class_context": "8th grade math, period 3",
                },
                _ctx(),
            )
        assert isinstance(result, ToolResult)
        assert "parent email" in result.text.lower() or "Progress" in result.text


# ── Auto-discovery ────────────────────────────────────────────────────────


class TestAutoDiscovery:
    def test_discover_finds_all_tools(self):
        """discover() should find all 17 tool classes in the tools package."""
        reg = ToolRegistry()
        tools_dir = Path(__file__).resolve().parent.parent / "clawed" / "agent_core" / "tools"
        reg.discover(tools_dir)
        names = sorted(reg.tool_names())
        expected = sorted(
            [
                "generate_lesson",
                "generate_unit",
                "generate_materials",
                "generate_assessment",
                "search_standards",
                "ingest_materials",
                "export_document",
                "configure_profile",
                "request_approval",
                "search_lessons",
                "curriculum_map",
                "gap_analysis",
                "sub_packet",
                "parent_comm",
                "drive_upload",
                "drive_list",
                "drive_organize",
            ]
        )
        # Verify all expected tools are present (may have more from new features)
        for name in expected:
            assert name in names, f"Missing expected tool: {name}"
        assert len(names) >= 17

    def test_discover_skips_broken_modules(self, tmp_path):
        """discover() should skip modules that fail to import."""
        # Write a broken module
        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "bad_tool.py").write_text("raise RuntimeError('broken')\n")
        (tmp_path / "good_tool.py").write_text(
            "from clawed.agent_core.context import AgentContext, ToolResult\n"
            "class GoodTool:\n"
            "    def schema(self):\n"
            "        return {'type':'function','function':{'name':'good',"
            "'description':'g','parameters':{'type':'object','properties':{}}}}\n"
            "    async def execute(self, params, context):\n"
            "        return ToolResult(text='ok')\n"
        )
        import sys

        # Insert tmp_path parent so import works
        sys.path.insert(0, str(tmp_path.parent))
        try:
            reg = ToolRegistry()
            reg.discover(tmp_path)
            # broken module skipped, good one found
            assert "good" in reg.tool_names()
        finally:
            sys.path.pop(0)
            # Clean up imported module from sys.modules
            mod_name = tmp_path.name
            for key in list(sys.modules):
                if key.startswith(mod_name):
                    del sys.modules[key]
