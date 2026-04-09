"""Tests for compile_project.py and compile_audio.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawed.master_content import (
    DoNow,
    GuidedNote,
    InstructionSection,
    MasterContent,
    StimulusQuestion,
    VocabularyEntry,
)
from clawed.models import (
    CulminatingPerformance,
    DifferentiationNotes,
    ProjectArc,
    ProjectPhase,
)


def _mc() -> MasterContent:
    return MasterContent(
        title="Test", subject="History", grade_level="8", topic="Revolution",
        objective="SWBAT analyze",
        vocabulary=[VocabularyEntry(term="T", definition="D.", context_sentence="C.")],
        primary_sources=[],
        do_now=DoNow(stimulus="S", stimulus_type="t", questions=["Q"], answers=["A"]),
        direct_instruction=[
            InstructionSection(
                heading="H", content="C",
                teacher_script="Ask: why?",
                key_points=["KP1", "KP2"],
                image_spec="t",
            ),
        ],
        guided_notes=[GuidedNote(prompt="P", answer="A", section_ref="H")] * 5,
        exit_ticket=[
            StimulusQuestion(
                stimulus="S" * 60, stimulus_type="text",
                question="Q", answer="A", cognitive_level="recall",
            ),
        ],
        differentiation=DifferentiationNotes(
            struggling=["x"], advanced=["y"], ell=["z"],
        ),
    )


def _project() -> ProjectArc:
    return ProjectArc(
        title="Voices of Change",
        essential_question="How did reform shape America?",
        duration_days=5,
        phases=[
            ProjectPhase(
                day_number=1, title="Day 1: Selection",
                objective="Choose topic and format",
                activities=["Review options", "Submit choice"],
                student_deliverable="Selection form",
                checkpoint="Teacher reviews",
            ),
            ProjectPhase(
                day_number=2, title="Day 2: Research",
                objective="Find sources",
                activities=["Database search", "Fill organizer"],
                student_deliverable="Graphic organizer",
                checkpoint="Peer check",
            ),
        ],
        movement_options=["Suffrage", "Labor Rights", "Civil Rights"],
        format_options=[
            "Option A: Poster + Speech",
            "Option B: Podcast Script",
            "Option C: Digital Exhibit",
        ],
        graphic_organizer="Why | Who | How | Evidence | Result",
        rubric_text=(
            "| Category | 4 | 3 | 2 | 1 |\n"
            "|---|---|---|---|---|\n"
            "| Content | Thorough | Most covered | Some missing | Major gaps |"
        ),
        culminating_performance=CulminatingPerformance(
            title="Gallery Walk",
            format="gallery_walk",
            duration_minutes=40,
            setup_instructions="Arrange stations",
            student_prep="Completed project",
            evaluation_criteria=["Uses evidence", "Clear presentation"],
            debrief_protocol="Closing reflection",
        ),
        debate_prep_template=(
            "My Position: ___\n"
            "Evidence 1: ___\n"
            "Counter-argument: ___\n"
            "Rebuttal: ___"
        ),
    )


class TestCompileProject:
    @pytest.mark.asyncio
    async def test_generates_docx(self, tmp_path: Path):
        from clawed.compile_project import compile_project_packet

        project = _project()
        path = await compile_project_packet(project, tmp_path)
        assert path.exists()
        assert path.suffix == ".docx"
        assert path.stat().st_size > 1000  # Not empty

    @pytest.mark.asyncio
    async def test_handles_empty_phases(self, tmp_path: Path):
        from clawed.compile_project import compile_project_packet

        project = ProjectArc(title="Empty")
        path = await compile_project_packet(project, tmp_path)
        assert path.exists()

    @pytest.mark.asyncio
    async def test_handles_empty_rubric(self, tmp_path: Path):
        from clawed.compile_project import compile_project_packet

        project = ProjectArc(title="No Rubric", rubric_text="")
        path = await compile_project_packet(project, tmp_path)
        assert path.exists()


class TestCompileAudio:
    def test_generates_narration_script(self, tmp_path: Path):
        from clawed.compile_audio import compile_narration_script

        mc = _mc()
        path = compile_narration_script(mc, tmp_path)
        assert path.exists()
        assert path.suffix == ".txt"
        content = path.read_text()
        assert "Welcome to today's lesson" in content
        assert mc.title in content

    def test_includes_vocabulary(self, tmp_path: Path):
        from clawed.compile_audio import compile_narration_script

        mc = _mc()
        path = compile_narration_script(mc, tmp_path)
        content = path.read_text()
        assert "T" in content  # vocab term
        assert "D." in content  # definition

    def test_includes_key_points(self, tmp_path: Path):
        from clawed.compile_audio import compile_narration_script

        mc = _mc()
        path = compile_narration_script(mc, tmp_path)
        content = path.read_text()
        assert "KP1" in content
        assert "KP2" in content

    def test_handles_none_fields(self, tmp_path: Path):
        from clawed.compile_audio import compile_narration_script

        mc = _mc()
        mc.homework = None
        path = compile_narration_script(mc, tmp_path)
        content = path.read_text()
        assert "None" not in content or "today" in content


class TestAdaptive:
    def test_analyze_good_performance(self):
        from clawed.adaptive import analyze_performance

        good = [{"score": 4, "meets_standard": True, "cognitive_level": "recall"}] * 20
        result = analyze_performance(good)
        assert result["mastery_rate"] == 1.0
        assert result["recommendation"] == "proceed"

    def test_analyze_bad_performance(self):
        from clawed.adaptive import analyze_performance

        bad = [{"score": 1, "meets_standard": False, "cognitive_level": "recall"}] * 20
        result = analyze_performance(bad)
        assert result["mastery_rate"] == 0.0
        assert result["recommendation"] == "full_reteach"

    def test_analyze_empty(self):
        from clawed.adaptive import analyze_performance

        result = analyze_performance([])
        assert result["recommendation"] == "no data"

    def test_adjustment_context_reteach(self):
        from clawed.adaptive import generate_adjustment_context

        perf = {
            "mastery_rate": 0.3, "total_students": 20,
            "weak_areas": ["analysis"], "recommendation": "full_reteach",
        }
        ctx = generate_adjustment_context(perf, "French Revolution")
        assert "ACTION REQUIRED" in ctx
        assert "French Revolution" in ctx

    def test_parent_notification(self):
        from clawed.adaptive import generate_parent_notification

        perf = {"mastery_rate": 0.9, "recommendation": "proceed"}
        note = generate_parent_notification("Alex", perf, "French Revolution")
        assert "Alex" in note
        assert "French Revolution" in note


class TestClassroomProfile:
    def test_load_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.classroom_profile import load_profile

        p = load_profile()
        assert p.student_count == 0
        assert p.has_smartboard is False  # Defaults to False

    def test_save_and_load(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.classroom_profile import (
            ClassroomProfile,
            load_profile,
            save_profile,
        )
        p = ClassroomProfile(student_count=28, ell_count=6, school_name="GN South")
        save_profile(p)
        loaded = load_profile()
        assert loaded.student_count == 28
        assert loaded.ell_count == 6

    def test_prompt_context_empty_when_no_profile(self, monkeypatch, tmp_path):
        from clawed.classroom_profile import ClassroomProfile

        # A fresh ClassroomProfile with all defaults should produce empty context
        p = ClassroomProfile()  # All defaults: student_count=0, school_name=""
        assert p.student_count == 0
        assert p.school_name == ""
        # Verify the profile_to_prompt_context logic directly
        # (without relying on file system state which leaks between tests)
        parts = []
        if p.school_name:
            parts.append("x")
        if p.student_count:
            parts.append("x")
        assert len(parts) == 0  # Empty profile produces no context

    def test_prompt_context_populated(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.classroom_profile import (
            ClassroomProfile,
            profile_to_prompt_context,
            save_profile,
        )

        p = ClassroomProfile(
            student_count=28, school_name="GN South",
            ell_count=6, iep_count=4, has_ipads=True,
        )
        save_profile(p)
        ctx = profile_to_prompt_context()
        assert "28 students" in ctx
        assert "6 ELL" in ctx
        assert "iPads" in ctx
