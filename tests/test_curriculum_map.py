"""Tests for year-level curriculum mapping models and utilities."""

import pytest

from clawed.models import (
    AssessmentCalendarEntry,
    BigIdea,
    CurriculumGap,
    PacingGuide,
    PacingWeek,
    SchoolCalendarEvent,
    YearMap,
    YearMapUnit,
)

# ── YearMapUnit model ─────────────────────────────────────────────────


class TestYearMapUnit:
    def test_create_unit(self):
        unit = YearMapUnit(
            unit_number=1,
            title="Foundations of Algebra",
            duration_weeks=4,
            essential_questions=["What is a variable?", "How do patterns become equations?"],
            standards=["CCSS.MATH.8.EE.1", "CCSS.MATH.8.EE.2"],
            description="Students build algebraic thinking from numeric patterns.",
        )
        assert unit.unit_number == 1
        assert unit.title == "Foundations of Algebra"
        assert unit.duration_weeks == 4
        assert len(unit.essential_questions) == 2
        assert len(unit.standards) == 2
        assert "algebraic" in unit.description

    def test_unit_defaults(self):
        unit = YearMapUnit(unit_number=1, title="Test", duration_weeks=3)
        assert unit.essential_questions == []
        assert unit.standards == []
        assert unit.description == ""


# ── BigIdea model ──────────────────────────────────────────────────────


class TestBigIdea:
    def test_create_big_idea(self):
        bi = BigIdea(
            idea="Mathematical modeling connects abstract concepts to real-world problems",
            connected_units=[2, 5, 8],
        )
        assert "modeling" in bi.idea
        assert bi.connected_units == [2, 5, 8]

    def test_big_idea_defaults(self):
        bi = BigIdea(idea="Test idea")
        assert bi.connected_units == []


# ── AssessmentCalendarEntry model ──────────────────────────────────────


class TestAssessmentCalendarEntry:
    def test_create_entry(self):
        entry = AssessmentCalendarEntry(
            unit_number=3,
            assessment_type="summative",
            title="Unit 3 Test: Linear Functions",
            week=12,
        )
        assert entry.unit_number == 3
        assert entry.assessment_type == "summative"
        assert entry.week == 12

    def test_entry_defaults(self):
        entry = AssessmentCalendarEntry(
            unit_number=0,
            title="Diagnostic",
            week=1,
        )
        assert entry.assessment_type == "summative"


# ── YearMap model ──────────────────────────────────────────────────────


class TestYearMap:
    def test_create_full_year_map(self):
        year_map = YearMap(
            subject="Math",
            grade_level="8",
            school_year="2025-26",
            total_weeks=36,
            units=[
                YearMapUnit(unit_number=1, title="Algebra Foundations", duration_weeks=4),
                YearMapUnit(unit_number=2, title="Linear Equations", duration_weeks=4),
                YearMapUnit(unit_number=3, title="Functions", duration_weeks=4),
            ],
            big_ideas=[
                BigIdea(idea="Patterns and structure", connected_units=[1, 2, 3]),
            ],
            assessment_calendar=[
                AssessmentCalendarEntry(unit_number=0, assessment_type="diagnostic", title="BOY Diagnostic", week=1),
                AssessmentCalendarEntry(unit_number=1, title="Unit 1 Test", week=4),
            ],
        )
        assert year_map.subject == "Math"
        assert year_map.grade_level == "8"
        assert year_map.school_year == "2025-26"
        assert year_map.total_weeks == 36
        assert len(year_map.units) == 3
        assert len(year_map.big_ideas) == 1
        assert len(year_map.assessment_calendar) == 2
        assert year_map.units[0].title == "Algebra Foundations"
        assert year_map.big_ideas[0].connected_units == [1, 2, 3]

    def test_year_map_defaults(self):
        ym = YearMap(subject="Science", grade_level="7")
        assert ym.total_weeks == 36
        assert ym.school_year == ""
        assert ym.units == []
        assert ym.big_ideas == []
        assert ym.assessment_calendar == []

    def test_year_map_json_roundtrip(self, tmp_path):
        ym = YearMap(
            subject="History",
            grade_level="10",
            school_year="2025-26",
            units=[
                YearMapUnit(unit_number=1, title="Ancient Civilizations", duration_weeks=5),
            ],
        )
        json_str = ym.model_dump_json()
        loaded = YearMap.model_validate_json(json_str)
        assert loaded.subject == "History"
        assert loaded.units[0].title == "Ancient Civilizations"


# ── SchoolCalendarEvent model ──────────────────────────────────────────


class TestSchoolCalendarEvent:
    def test_create_event(self):
        evt = SchoolCalendarEvent(
            date="2025-11-27",
            end_date="2025-11-28",
            event="Thanksgiving Break",
            type="break",
        )
        assert evt.date == "2025-11-27"
        assert evt.end_date == "2025-11-28"
        assert evt.type == "break"

    def test_event_defaults(self):
        evt = SchoolCalendarEvent(date="2025-09-01", event="Labor Day")
        assert evt.end_date == ""
        assert evt.type == "holiday"


# ── PacingGuide model ─────────────────────────────────────────────────


class TestPacingGuide:
    def test_create_pacing_guide(self):
        guide = PacingGuide(
            subject="Math",
            grade_level="8",
            school_year="2025-26",
            start_date="2025-09-04",
            weeks=[
                PacingWeek(
                    week_number=1,
                    start_date="2025-09-04",
                    end_date="2025-09-08",
                    unit_title="Algebra Foundations",
                    unit_number=1,
                    topics=["Variables and expressions", "Order of operations review"],
                    notes="First week — establish routines",
                ),
                PacingWeek(
                    week_number=2,
                    start_date="2025-09-11",
                    end_date="2025-09-15",
                    unit_title="Algebra Foundations",
                    unit_number=1,
                    topics=["Solving one-step equations", "Solving two-step equations"],
                ),
            ],
        )
        assert guide.subject == "Math"
        assert guide.start_date == "2025-09-04"
        assert len(guide.weeks) == 2
        assert guide.weeks[0].unit_number == 1
        assert len(guide.weeks[0].topics) == 2
        assert guide.weeks[1].notes == ""

    def test_pacing_guide_defaults(self):
        guide = PacingGuide(subject="ELA", grade_level="6", start_date="2025-09-02")
        assert guide.school_year == ""
        assert guide.weeks == []

    def test_pacing_guide_json_roundtrip(self):
        guide = PacingGuide(
            subject="Science",
            grade_level="7",
            start_date="2025-09-04",
            weeks=[
                PacingWeek(
                    week_number=1,
                    start_date="2025-09-04",
                    end_date="2025-09-08",
                    unit_title="Scientific Method",
                    unit_number=1,
                    topics=["Hypothesis formation"],
                ),
            ],
        )
        json_str = guide.model_dump_json()
        loaded = PacingGuide.model_validate_json(json_str)
        assert loaded.weeks[0].unit_title == "Scientific Method"


# ── CurriculumGap model ───────────────────────────────────────────────


class TestCurriculumGap:
    def test_create_gap(self):
        gap = CurriculumGap(
            standard="CCSS.MATH.8.EE.7",
            description="No materials cover solving linear equations with variables on both sides.",
            severity="high",
            suggestion="Add a 2-week unit on multi-step linear equations.",
        )
        assert gap.standard == "CCSS.MATH.8.EE.7"
        assert gap.severity == "high"
        assert "2-week" in gap.suggestion

    def test_gap_defaults(self):
        gap = CurriculumGap(standard="NGSS.MS-LS1-6", description="Missing photosynthesis depth")
        assert gap.severity == "medium"
        assert gap.suggestion == ""


# ── Save/load utilities ───────────────────────────────────────────────


class TestSaveLoad:
    def test_save_and_load_year_map(self, tmp_path):
        from clawed.curriculum_map import load_year_map, save_year_map

        ym = YearMap(
            subject="Math",
            grade_level="8",
            school_year="2025-26",
            units=[
                YearMapUnit(unit_number=1, title="Unit One", duration_weeks=4),
            ],
        )
        path = save_year_map(ym, tmp_path)
        assert path.exists()
        assert "year_map_math_8" in path.name

        loaded = load_year_map(path)
        assert loaded.subject == "Math"
        assert loaded.units[0].title == "Unit One"

    def test_save_and_load_pacing_guide(self, tmp_path):
        from clawed.curriculum_map import load_pacing_guide, save_pacing_guide

        guide = PacingGuide(
            subject="Science",
            grade_level="7",
            start_date="2025-09-04",
            weeks=[
                PacingWeek(
                    week_number=1,
                    start_date="2025-09-04",
                    end_date="2025-09-08",
                    unit_title="Intro",
                    unit_number=1,
                ),
            ],
        )
        path = save_pacing_guide(guide, tmp_path)
        assert path.exists()
        assert "pacing_science_7" in path.name

        loaded = load_pacing_guide(path)
        assert loaded.weeks[0].unit_title == "Intro"

    def test_load_year_map_not_found(self, tmp_path):
        from clawed.curriculum_map import load_year_map

        with pytest.raises(FileNotFoundError):
            load_year_map(tmp_path / "nonexistent.json")

    def test_load_pacing_guide_not_found(self, tmp_path):
        from clawed.curriculum_map import load_pacing_guide

        with pytest.raises(FileNotFoundError):
            load_pacing_guide(tmp_path / "nonexistent.json")


# ── Exporter functions ────────────────────────────────────────────────


class TestExporters:
    def test_year_map_to_markdown(self):
        from clawed.export_markdown import year_map_to_markdown

        ym = YearMap(
            subject="Math",
            grade_level="8",
            school_year="2025-26",
            units=[
                YearMapUnit(
                    unit_number=1,
                    title="Algebra Foundations",
                    duration_weeks=4,
                    essential_questions=["What is a variable?"],
                    standards=["CCSS.MATH.8.EE.1"],
                    description="Intro to algebra.",
                ),
            ],
            big_ideas=[
                BigIdea(idea="Patterns and structure", connected_units=[1]),
            ],
            assessment_calendar=[
                AssessmentCalendarEntry(unit_number=1, title="Unit 1 Test", week=4),
            ],
        )
        md = year_map_to_markdown(ym)
        assert "Math" in md
        assert "Grade 8" in md
        assert "Algebra Foundations" in md
        assert "What is a variable?" in md
        assert "Patterns and structure" in md
        assert "Unit 1 Test" in md

    def test_pacing_guide_to_markdown(self):
        from clawed.export_markdown import pacing_guide_to_markdown

        guide = PacingGuide(
            subject="Science",
            grade_level="7",
            start_date="2025-09-04",
            weeks=[
                PacingWeek(
                    week_number=1,
                    start_date="2025-09-04",
                    end_date="2025-09-08",
                    unit_title="Scientific Method",
                    unit_number=1,
                    topics=["Hypothesis", "Variables"],
                    notes="First week",
                ),
            ],
        )
        md = pacing_guide_to_markdown(guide)
        assert "Science" in md
        assert "Grade 7" in md
        assert "Scientific Method" in md
        assert "Hypothesis" in md
        assert "First week" in md

    def test_export_year_map_markdown(self, tmp_path):
        from clawed.export_markdown import export_year_map

        ym = YearMap(subject="ELA", grade_level="9", units=[])
        path = export_year_map(ym, tmp_path, fmt="markdown")
        assert path.exists()
        assert path.suffix == ".md"
        assert "ELA" in path.read_text()

    def test_export_pacing_guide_markdown(self, tmp_path):
        from clawed.export_markdown import export_pacing_guide

        guide = PacingGuide(subject="History", grade_level="10", start_date="2025-09-04")
        path = export_pacing_guide(guide, tmp_path, fmt="markdown")
        assert path.exists()
        assert path.suffix == ".md"
        assert "History" in path.read_text()


# ── Intent router ────────────────────────────────────────────────────


class TestIntentRouter:
    def test_year_map_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("create a year map for 8th grade math")
        assert result.intent == Intent.GENERATE_YEAR_MAP

    def test_curriculum_map_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("build a curriculum map for my science class")
        assert result.intent == Intent.GENERATE_YEAR_MAP

    def test_scope_and_sequence_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("I need a scope and sequence for 10th grade history")
        assert result.intent == Intent.GENERATE_YEAR_MAP

    def test_full_year_plan_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("plan the full year for my class")
        assert result.intent == Intent.GENERATE_YEAR_MAP

    def test_pacing_guide_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("create a pacing guide for the year")
        assert result.intent == Intent.GENERATE_PACING_GUIDE

    def test_week_by_week_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("I need a week by week pacing calendar")
        assert result.intent == Intent.GENERATE_PACING_GUIDE

    def test_year_map_needs_clarification(self):
        from clawed.router import Intent, needs_clarification, parse_intent

        parsed = parse_intent("create a year map")
        assert parsed.intent == Intent.GENERATE_YEAR_MAP
        clarify = needs_clarification(parsed)
        assert clarify is not None
        assert "subject" in clarify.lower() or "grade" in clarify.lower()


# ── Model router ─────────────────────────────────────────────────────


class TestModelRouter:
    def test_year_map_routes_to_strong_model(self):
        from clawed.model_router import DEFAULT_TIER_MODELS, TASK_TIERS, ModelTier

        assert "year_map" in TASK_TIERS
        assert TASK_TIERS["year_map"] == ModelTier.DEEP
        assert DEFAULT_TIER_MODELS["work"]  # work tier has a model set

    def test_pacing_guide_routes_to_strong_model(self):
        from clawed.model_router import DEFAULT_TIER_MODELS, TASK_TIERS, ModelTier

        assert "pacing_guide" in TASK_TIERS
        assert TASK_TIERS["pacing_guide"] == ModelTier.DEEP
        assert DEFAULT_TIER_MODELS["work"]  # work tier has a model set

    def test_curriculum_gaps_routes_to_strong_model(self):
        from clawed.model_router import TASK_TIERS, ModelTier

        assert "curriculum_gaps" in TASK_TIERS
        assert TASK_TIERS["curriculum_gaps"] == ModelTier.DEEP
