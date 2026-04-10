"""Tests for parent communication generator — all comm types, email structure, formatting."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawed.parent_comm import (
    CommType,
    ParentComm,
    ParentCommRequest,
    generate_parent_comm,
    parent_comm_to_text,
)

# ── CommType enum tests ──────────────────────────────────────────────


class TestCommType:
    def test_all_comm_types_exist(self):
        assert CommType.PROGRESS_UPDATE.value == "progress_update"
        assert CommType.BEHAVIOR_CONCERN.value == "behavior_concern"
        assert CommType.POSITIVE_NOTE.value == "positive_note"
        assert CommType.UPCOMING_UNIT.value == "upcoming_unit"
        assert CommType.PERMISSION_REQUEST.value == "permission_request"
        assert CommType.GENERAL_UPDATE.value == "general_update"

    def test_comm_type_count(self):
        assert len(CommType) == 6


# ── Request model tests ──────────────────────────────────────────────


class TestParentCommRequest:
    def test_create_request_all_fields(self):
        req = ParentCommRequest(
            comm_type=CommType.PROGRESS_UPDATE,
            student_description="a 7th grade student who struggles with document analysis",
            class_context="Unit 4 WWI — Social Studies",
            tone="professional and warm",
            additional_notes="Student has shown improvement recently.",
        )
        assert req.comm_type == CommType.PROGRESS_UPDATE
        assert "7th grade" in req.student_description
        assert req.tone == "professional and warm"
        assert "improvement" in req.additional_notes

    def test_create_request_defaults(self):
        req = ParentCommRequest(
            comm_type=CommType.POSITIVE_NOTE,
            student_description="a student excelling in math",
            class_context="Algebra I",
        )
        assert req.tone == "professional and warm"
        assert req.additional_notes == ""

    def test_request_serialization_roundtrip(self):
        req = ParentCommRequest(
            comm_type=CommType.BEHAVIOR_CONCERN,
            student_description="a student who has been disruptive",
            class_context="Period 3 English",
            tone="firm but caring",
        )
        data = req.model_dump()
        restored = ParentCommRequest.model_validate(data)
        assert restored.comm_type == req.comm_type
        assert restored.student_description == req.student_description


# ── ParentComm model tests ───────────────────────────────────────────


class TestParentCommModel:
    def test_create_comm(self):
        comm = ParentComm(
            comm_type=CommType.PROGRESS_UPDATE,
            subject_line="Progress Update: Social Studies",
            email_body="Dear Parent/Guardian,\n\nI'm writing to share...",
            follow_up_suggestions=["Schedule a conference", "Check homework nightly"],
        )
        assert comm.comm_type == CommType.PROGRESS_UPDATE
        assert "Progress Update" in comm.subject_line
        assert "Dear Parent" in comm.email_body
        assert len(comm.follow_up_suggestions) == 2
        assert isinstance(comm.generated_at, datetime)

    def test_comm_defaults(self):
        comm = ParentComm(
            comm_type=CommType.GENERAL_UPDATE,
            subject_line="Update",
            email_body="Hello",
        )
        assert comm.follow_up_suggestions == []
        assert comm.generated_at is not None


# ── Generation tests (mocked LLM) ────────────────────────────────────


class TestGenerateParentComm:
    @pytest.mark.asyncio
    async def test_generate_progress_update(self):
        mock_llm = MagicMock()
        mock_llm.generate_json = AsyncMock(
            return_value={
                "subject_line": "Progress Update: Unit 4 WWI",
                "email_body": "Dear Parent/Guardian,\n\nI wanted to reach out about your child's progress...",
                "follow_up_suggestions": [
                    "Schedule a parent-teacher conference",
                    "Review document analysis skills at home",
                ],
            }
        )

        req = ParentCommRequest(
            comm_type=CommType.PROGRESS_UPDATE,
            student_description="a student struggling with document analysis",
            class_context="Unit 4 WWI",
        )

        comm = await generate_parent_comm(req, mock_llm)

        assert isinstance(comm, ParentComm)
        assert comm.comm_type == CommType.PROGRESS_UPDATE
        assert "Progress Update" in comm.subject_line
        assert len(comm.email_body) > 0
        assert len(comm.follow_up_suggestions) == 2

    @pytest.mark.asyncio
    async def test_generate_behavior_concern(self):
        mock_llm = MagicMock()
        mock_llm.generate_json = AsyncMock(
            return_value={
                "subject_line": "Classroom Behavior Update",
                "email_body": "Dear Parent/Guardian,\n\nI'm reaching out because...",
                "follow_up_suggestions": ["Schedule a meeting"],
            }
        )

        req = ParentCommRequest(
            comm_type=CommType.BEHAVIOR_CONCERN,
            student_description="a student who has been talking during instruction",
            class_context="Period 5 Science",
            tone="firm but caring",
        )

        comm = await generate_parent_comm(req, mock_llm)
        assert comm.comm_type == CommType.BEHAVIOR_CONCERN

    @pytest.mark.asyncio
    async def test_generate_positive_note(self):
        mock_llm = MagicMock()
        mock_llm.generate_json = AsyncMock(
            return_value={
                "subject_line": "Great News from Math Class!",
                "email_body": "Dear Parent/Guardian,\n\nI wanted to share some wonderful news...",
                "follow_up_suggestions": ["Celebrate at home!"],
            }
        )

        req = ParentCommRequest(
            comm_type=CommType.POSITIVE_NOTE,
            student_description="a student who aced the last test",
            class_context="Algebra I",
        )

        comm = await generate_parent_comm(req, mock_llm)
        assert comm.comm_type == CommType.POSITIVE_NOTE
        assert "Great News" in comm.subject_line

    @pytest.mark.asyncio
    async def test_generate_all_comm_types(self):
        """Ensure all comm types can be used without error."""
        for ct in CommType:
            mock_llm = MagicMock()
            mock_llm.generate_json = AsyncMock(
                return_value={
                    "subject_line": f"Test {ct.value}",
                    "email_body": "Body text.",
                    "follow_up_suggestions": [],
                }
            )

            req = ParentCommRequest(
                comm_type=ct,
                student_description="a student",
                class_context="a class",
            )
            comm = await generate_parent_comm(req, mock_llm)
            assert comm.comm_type == ct

    @pytest.mark.asyncio
    async def test_generate_passes_tone_to_system_prompt(self):
        mock_llm = MagicMock()
        mock_llm.generate_json = AsyncMock(
            return_value={
                "subject_line": "S",
                "email_body": "B",
                "follow_up_suggestions": [],
            }
        )

        req = ParentCommRequest(
            comm_type=CommType.GENERAL_UPDATE,
            student_description="a student",
            class_context="a class",
            tone="very formal",
        )

        await generate_parent_comm(req, mock_llm)

        call_kwargs = mock_llm.generate_json.call_args
        assert "very formal" in call_kwargs.kwargs["system"]


# ── Text formatting tests ────────────────────────────────────────────


class TestParentCommText:
    def _make_comm(self) -> ParentComm:
        return ParentComm(
            comm_type=CommType.PROGRESS_UPDATE,
            subject_line="Progress Update: Unit 4 WWI",
            email_body="Dear Parent/Guardian,\n\nYour child has been working hard.",
            follow_up_suggestions=[
                "Schedule a conference",
                "Review notes together",
            ],
        )

    def test_text_has_subject_line(self):
        text = parent_comm_to_text(self._make_comm())
        assert "Subject: Progress Update: Unit 4 WWI" in text

    def test_text_has_email_body(self):
        text = parent_comm_to_text(self._make_comm())
        assert "Dear Parent/Guardian" in text
        assert "working hard" in text

    def test_text_has_follow_up_suggestions(self):
        text = parent_comm_to_text(self._make_comm())
        assert "Suggested follow-ups:" in text
        assert "Schedule a conference" in text
        assert "Review notes together" in text

    def test_text_without_follow_ups(self):
        comm = ParentComm(
            comm_type=CommType.POSITIVE_NOTE,
            subject_line="Good job!",
            email_body="Your child did great.",
        )
        text = parent_comm_to_text(comm)
        assert "Subject: Good job!" in text
        assert "Suggested follow-ups:" not in text
