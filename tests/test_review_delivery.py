"""Delivery must report verified required files, independent of optional extras."""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawed.agent_core.context import AgentContext
from clawed.agent_core.tools import generate_lesson_bundle as bundle
from clawed.generation_report import GenerationReport
from clawed.models import AppConfig


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_role", ["teacher", "student", "slides", None])
async def test_core_output_failures_are_visible_even_with_extra_docx(tmp_path, monkeypatch, failed_role):
    compilers = {"teacher": "clawed.compile_teacher.compile_teacher_view",
                 "student": "clawed.compile_student.compile_student_view",
                 "slides": "clawed.compile_slides.compile_slides"}
    for role, target in compilers.items():
        output = tmp_path / f"{role}.{'pptx' if role == 'slides' else 'docx'}"
        output.write_bytes(b"compiler output")
        mock = AsyncMock(side_effect=RuntimeError("test compile failure")) if role == failed_role else AsyncMock(
            return_value=output,
        )
        monkeypatch.setattr(target, mock)
    files, effects, errors, core = await bundle._compile_core_views(None, {}, tmp_path, None)
    extra = tmp_path / "extra.docx"
    extra.write_bytes(b"optional output")
    files.append(extra)
    report = GenerationReport(quality_review_passed=True, voice_check_passed=True)
    response = bundle._build_bundle_response(SimpleNamespace(title="Lesson"), files, errors, effects,
                                            "", report, [], 4.0, core)
    assert response.data["status"] == ("partial" if failed_role else "complete")
    assert response.data["missing_outputs"] == ([failed_role] if failed_role else [])
    if failed_role:
        assert "Complete teaching package" not in response.text
        assert "test compile failure" in response.text
        assert failed_role in response.text
    assert str(extra) not in response.data["required_outputs"].values()


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_file", [True, False])
async def test_compiler_must_actually_write_a_nonempty_file(tmp_path, monkeypatch, empty_file):
    output = tmp_path / "missing.docx"
    if empty_file:
        output.touch()
    for target in ("clawed.compile_teacher.compile_teacher_view", "clawed.compile_student.compile_student_view",
                   "clawed.compile_slides.compile_slides"):
        monkeypatch.setattr(target, AsyncMock(return_value=output))
    files, effects, errors, core = await bundle._compile_core_views(None, {}, tmp_path, None)
    response = bundle._build_bundle_response(SimpleNamespace(title="Lesson"), files, errors, effects,
                                            "", GenerationReport(), [], None, core)
    assert response.data["status"] == "failed"
    assert not response.files
    assert len(errors) == 3


def test_failed_review_yields_draft_even_with_all_outputs(tmp_path):
    core = {role: tmp_path / f"{role}.docx" for role in ("teacher", "student", "slides")}
    result = bundle._build_bundle_response(SimpleNamespace(title="Lesson"), list(core.values()), [], [], "",
                                          GenerationReport(quality_review_passed=False), [], None, core)
    assert result.data["status"] == "draft"
    assert "Draft teaching package" in result.text


@pytest.mark.asyncio
async def test_bundle_tool_stops_extras_after_core_failure(tmp_path, monkeypatch):
    from clawed.agent_core.loop import run_agent_loop
    from clawed.agent_core.tools.base import ToolRegistry
    from clawed.master_content import MasterContent

    fixture = Path(__file__).parent.parent / "clawed/demo/demo_master_content.json"
    master = MasterContent.model_validate_json(fixture.read_text())
    monkeypatch.setattr("clawed.lesson.generate_master_content", AsyncMock(return_value=master))
    monkeypatch.setattr(bundle, "_search_teacher_materials", AsyncMock(return_value=("", "")))
    monkeypatch.setattr(bundle, "_validate_and_humanize", lambda *args: None)
    monkeypatch.setattr(bundle, "_run_quality_review", AsyncMock(return_value=None))
    extras = AsyncMock()
    monkeypatch.setattr(bundle, "_run_auto_chain", extras)
    monkeypatch.setattr("clawed.compile_teacher.compile_teacher_view", AsyncMock(side_effect=RuntimeError("broken")))
    for target in ("clawed.compile_student.compile_student_view", "clawed.compile_slides.compile_slides"):
        monkeypatch.setattr(target, AsyncMock(side_effect=RuntimeError("broken")))
    ctx = AgentContext(teacher_id="test", config=AppConfig(output_dir=str(tmp_path / "exports")),
                       teacher_profile={}, persona=None, session_history=[], improvement_context="")
    registry = ToolRegistry()
    registry.register(bundle.GenerateLessonBundleTool())
    llm = MagicMock(generate=AsyncMock(side_effect=[
        {"type": "tool_calls", "tool_calls": [{"name": "generate_lesson_bundle", "id": "1",
          "arguments": {"topic": "Cells", "include_images": False}}]},
        {"type": "text", "content": "Everything is complete!"},
    ]))
    response = await run_agent_loop(message="Make a lesson", system="", context=ctx, llm=llm, registry=registry)
    assert "Failed to generate package" in response.text
    assert "broken" in response.text
    assert not response.files
    extras.assert_not_awaited()
    llm.generate.assert_awaited_once()


def test_widget_javascript_sends_share_and_conversation_tokens():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required for browser-widget JavaScript regression")
    script = Path(__file__).with_name("widget_integration.cjs")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
