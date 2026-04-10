"""Tests for sub packet generator — request creation, generation, markdown rendering."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawed.sub_packet import (
    SubPacket,
    SubPacketRequest,
    generate_sub_packet,
    sub_packet_to_markdown,
)

# ── Request model tests ──────────────────────────────────────────────


class TestSubPacketRequest:
    def test_create_request_all_fields(self):
        req = SubPacketRequest(
            teacher_name="Ms. Rivera",
            school="Lincoln Middle School",
            class_name="Period 3 Global Studies",
            grade="8",
            subject="Social Studies",
            date="March 25, 2026",
            period_or_time="Period 3 (10:00-10:45)",
            lesson_topic="WWI Document Analysis",
            lesson_context="Unit 4: World War I",
        )
        assert req.teacher_name == "Ms. Rivera"
        assert req.school == "Lincoln Middle School"
        assert req.class_name == "Period 3 Global Studies"
        assert req.grade == "8"
        assert req.subject == "Social Studies"
        assert req.date == "March 25, 2026"
        assert req.period_or_time == "Period 3 (10:00-10:45)"
        assert req.lesson_topic == "WWI Document Analysis"
        assert req.lesson_context == "Unit 4: World War I"

    def test_create_request_required_only(self):
        req = SubPacketRequest(
            teacher_name="Mr. Chen",
            school="Westbrook High",
            class_name="AP Biology",
            grade="11",
            subject="Biology",
            date="2026-04-01",
            period_or_time="Block A",
        )
        assert req.lesson_topic == ""
        assert req.lesson_context == ""

    def test_request_serialization_roundtrip(self):
        req = SubPacketRequest(
            teacher_name="Ms. Patel",
            school="Oak Elementary",
            class_name="3rd Grade Math",
            grade="3",
            subject="Math",
            date="2026-05-10",
            period_or_time="Morning",
        )
        data = req.model_dump()
        restored = SubPacketRequest.model_validate(data)
        assert restored == req


# ── Packet model tests ───────────────────────────────────────────────


class TestSubPacketModel:
    def test_create_packet_all_fields(self):
        packet = SubPacket(
            teacher_name="Ms. Rivera",
            class_name="Period 3 Global Studies",
            grade="8",
            subject="Social Studies",
            date="March 25, 2026",
            period_or_time="Period 3",
            overview="This is a well-behaved 8th grade class.",
            daily_schedule=["0:00-5:00 Attendance", "5:00-35:00 Document analysis"],
            lesson_instructions=["Hand out the document packet", "Read the intro aloud"],
            student_notes="Front row finishes early. Back table needs redirection.",
            materials_needed=["Document packet", "Colored pencils"],
            emergency_info="Office: ext 100, Nurse: ext 150",
            closing_notes="Thank you for being here!",
        )
        assert packet.teacher_name == "Ms. Rivera"
        assert len(packet.daily_schedule) == 2
        assert len(packet.lesson_instructions) == 2
        assert len(packet.materials_needed) == 2
        assert isinstance(packet.generated_at, datetime)

    def test_packet_has_generated_at_default(self):
        packet = SubPacket(
            teacher_name="T",
            class_name="C",
            grade="5",
            subject="Math",
            date="2026-01-01",
            period_or_time="P1",
            overview="Overview",
        )
        assert packet.generated_at is not None
        assert isinstance(packet.generated_at, datetime)

    def test_packet_empty_lists_default(self):
        packet = SubPacket(
            teacher_name="T",
            class_name="C",
            grade="5",
            subject="Math",
            date="2026-01-01",
            period_or_time="P1",
            overview="Overview",
        )
        assert packet.daily_schedule == []
        assert packet.lesson_instructions == []
        assert packet.materials_needed == []


# ── Generation tests (mocked LLM) ────────────────────────────────────


class TestGenerateSubPacket:
    @pytest.mark.asyncio
    async def test_generate_returns_sub_packet(self):
        mock_llm = MagicMock()
        mock_llm.generate_json = AsyncMock(
            return_value={
                "overview": "A great 8th grade class studying WWI.",
                "daily_schedule": [
                    "0:00-5:00 — Attendance and warm-up",
                    "5:00-35:00 — Document analysis activity",
                    "35:00-45:00 — Exit ticket",
                ],
                "lesson_instructions": [
                    "1. Take attendance using the seating chart on the desk.",
                    "2. Have students read Document A silently.",
                    "3. Lead a brief discussion using the guiding questions.",
                ],
                "student_notes": "Generally well-behaved. Table 3 may need redirection.",
                "materials_needed": ["Document packet (on desk)", "Pencils"],
                "emergency_info": "Main Office: ext 100. Nurse: ext 150.",
                "closing_notes": "Thank you so much for covering my class!",
            }
        )

        req = SubPacketRequest(
            teacher_name="Ms. Rivera",
            school="Lincoln MS",
            class_name="Period 3 Global Studies",
            grade="8",
            subject="Social Studies",
            date="March 25, 2026",
            period_or_time="Period 3",
            lesson_topic="WWI Document Analysis",
            lesson_context="Unit 4: World War I",
        )

        packet = await generate_sub_packet(req, mock_llm)

        assert isinstance(packet, SubPacket)
        assert packet.teacher_name == "Ms. Rivera"
        assert packet.class_name == "Period 3 Global Studies"
        assert packet.grade == "8"
        assert packet.subject == "Social Studies"
        assert packet.date == "March 25, 2026"
        assert len(packet.daily_schedule) == 3
        assert len(packet.lesson_instructions) == 3
        assert "Document packet" in packet.materials_needed[0]
        assert "ext 100" in packet.emergency_info

    @pytest.mark.asyncio
    async def test_generate_without_optional_fields(self):
        mock_llm = MagicMock()
        mock_llm.generate_json = AsyncMock(
            return_value={
                "overview": "A standard math class.",
                "daily_schedule": ["Full period: Review worksheet"],
                "lesson_instructions": ["Hand out worksheet"],
                "student_notes": "",
                "materials_needed": [],
                "emergency_info": "Office: 100",
                "closing_notes": "Thanks!",
            }
        )

        req = SubPacketRequest(
            teacher_name="Mr. Kim",
            school="Central High",
            class_name="Algebra I",
            grade="9",
            subject="Math",
            date="2026-04-01",
            period_or_time="Period 5",
        )

        packet = await generate_sub_packet(req, mock_llm)
        assert packet.teacher_name == "Mr. Kim"
        assert packet.overview == "A standard math class."
        assert len(packet.lesson_instructions) == 1

    @pytest.mark.asyncio
    async def test_generate_calls_llm_with_system_prompt(self):
        mock_llm = MagicMock()
        mock_llm.generate_json = AsyncMock(
            return_value={
                "overview": "O",
                "daily_schedule": [],
                "lesson_instructions": [],
                "student_notes": "",
                "materials_needed": [],
                "emergency_info": "",
                "closing_notes": "",
            }
        )

        req = SubPacketRequest(
            teacher_name="T",
            school="S",
            class_name="C",
            grade="7",
            subject="ELA",
            date="2026-01-01",
            period_or_time="P1",
        )

        await generate_sub_packet(req, mock_llm)

        mock_llm.generate_json.assert_called_once()
        call_kwargs = mock_llm.generate_json.call_args
        assert "substitute" in call_kwargs.kwargs["system"].lower()


# ── Markdown rendering tests ─────────────────────────────────────────


class TestSubPacketMarkdown:
    def _make_packet(self) -> SubPacket:
        return SubPacket(
            teacher_name="Ms. Rivera",
            class_name="Period 3 Global Studies",
            grade="8",
            subject="Social Studies",
            date="March 25, 2026",
            period_or_time="Period 3",
            overview="A great class studying WWI.",
            daily_schedule=["0-5 min: Attendance", "5-35 min: Activity"],
            lesson_instructions=["Take attendance", "Hand out documents"],
            student_notes="Table 3 may need redirection.",
            materials_needed=["Document packet", "Pencils"],
            emergency_info="Office: ext 100",
            closing_notes="Thank you!",
        )

    def test_markdown_contains_header(self):
        md = sub_packet_to_markdown(self._make_packet())
        assert "# Substitute Teacher Packet" in md

    def test_markdown_contains_teacher_info(self):
        md = sub_packet_to_markdown(self._make_packet())
        assert "Ms. Rivera" in md
        assert "March 25, 2026" in md
        assert "Social Studies" in md
        assert "Grade" in md

    def test_markdown_contains_all_sections(self):
        md = sub_packet_to_markdown(self._make_packet())
        assert "## Overview" in md
        assert "## Daily Schedule" in md
        assert "## Lesson Instructions" in md
        assert "## Student & Classroom Notes" in md
        assert "## Materials Needed" in md
        assert "## Emergency Information" in md
        assert "## Notes from the Teacher" in md

    def test_markdown_lesson_instructions_numbered(self):
        md = sub_packet_to_markdown(self._make_packet())
        assert "1. " in md
        assert "2. " in md

    def test_markdown_materials_are_checklist(self):
        md = sub_packet_to_markdown(self._make_packet())
        assert "- [ ] Document packet" in md
        assert "- [ ] Pencils" in md

    def test_markdown_has_generated_footer(self):
        md = sub_packet_to_markdown(self._make_packet())
        assert "Generated by Claw-ED" in md


# ── CLI command registration test ────────────────────────────────────


class TestSubCLI:
    def test_sub_command_registered(self):
        from typer.testing import CliRunner

        from clawed.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["sub", "--help"])
        assert result.exit_code == 0
        assert (
            "substitute" in result.output.lower() or "sub packet" in result.output.lower() or "--class" in result.output
        )

    def test_parent_comm_command_registered(self):
        from typer.testing import CliRunner

        from clawed.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["parent-comm", "--help"])
        assert result.exit_code == 0
        assert "parent" in result.output.lower() or "--type" in result.output
