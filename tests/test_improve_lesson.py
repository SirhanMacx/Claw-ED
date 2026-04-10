"""Tests for the improve_lesson tool schema and metadata."""

from __future__ import annotations

from clawed.agent_core.tools.improve_lesson import ImproveLessonTool


def _get_schema() -> dict:
    """Instantiate the tool and return its schema dict."""
    tool = ImproveLessonTool()
    return tool.schema()


def test_tool_name_is_improve_lesson():
    schema = _get_schema()
    assert schema["function"]["name"] == "improve_lesson"


def test_schema_has_required_fields():
    schema = _get_schema()
    params = schema["function"]["parameters"]
    assert "topic" in params["properties"]
    assert "improvement" in params["properties"]
    assert params["required"] == ["topic", "improvement"]


def test_schema_has_section_enum():
    schema = _get_schema()
    section_prop = schema["function"]["parameters"]["properties"]["section"]
    assert "enum" in section_prop
    enum_values = section_prop["enum"]
    assert isinstance(enum_values, list)
    assert len(enum_values) > 0
    # Verify a few known section values are present
    assert "do_now" in enum_values
    assert "exit_ticket" in enum_values
    assert "full_lesson" in enum_values
