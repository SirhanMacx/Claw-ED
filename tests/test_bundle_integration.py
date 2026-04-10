"""End-to-end bundle integration test with alignment validation."""

import json
from pathlib import Path

DEMO_DIR = Path(__file__).parent.parent / "clawed" / "demo"


class TestBundleIntegration:
    """Tests that the demo fixture flows through the full pipeline."""

    def test_demo_master_content_fixture_loads(self):
        """demo_master_content.json loads and validates."""
        from clawed.master_content import MasterContent

        fixture_path = DEMO_DIR / "demo_master_content.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        mc = MasterContent.model_validate(data)
        assert mc.title
        assert len(mc.guided_notes) >= 5
        assert len(mc.exit_ticket) >= 1

    def test_demo_master_content_to_daily_lesson(self):
        """MasterContent can convert to DailyLesson."""
        from clawed.master_content import MasterContent
        from clawed.models import DailyLesson

        fixture_path = DEMO_DIR / "demo_master_content.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        mc = MasterContent.model_validate(data)
        dl = mc.to_daily_lesson()
        assert isinstance(dl, DailyLesson)
        assert dl.title == mc.title

    def test_demo_quiz_fixture_validates(self):
        """demo_quiz.json validates against Quiz model."""
        from clawed.models import Quiz

        fixture_path = DEMO_DIR / "demo_quiz.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        quiz = Quiz.model_validate(data)
        assert len(quiz.questions) >= 1

    def test_demo_rubric_fixture_validates(self):
        """demo_rubric.json validates against Rubric model."""
        from clawed.models import Rubric

        fixture_path = DEMO_DIR / "demo_rubric.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        rubric = Rubric.model_validate(data)
        assert len(rubric.criteria) >= 1

    def test_demo_year_map_fixture_validates(self):
        """demo_year_map.json validates against YearMap model."""
        from clawed.models import YearMap

        fixture_path = DEMO_DIR / "demo_year_map.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        ym = YearMap.model_validate(data)
        assert len(ym.units) >= 1

    def test_demo_formative_fixture_validates(self):
        """demo_formative_assessment.json validates against FormativeAssessment."""
        from clawed.models import FormativeAssessment

        fixture_path = DEMO_DIR / "demo_formative_assessment.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        fa = FormativeAssessment.model_validate(data)
        assert len(fa.questions) >= 1

    def test_demo_pacing_guide_fixture_validates(self):
        """demo_pacing_guide.json validates against PacingGuide."""
        from clawed.models import PacingGuide

        fixture_path = DEMO_DIR / "demo_pacing_guide.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        pg = PacingGuide.model_validate(data)
        assert len(pg.weeks) >= 1

    def test_alignment_check_on_master_content(self):
        """validate_alignment returns a score for the demo fixture."""
        from clawed.master_content import MasterContent
        from clawed.validation import validate_alignment

        fixture_path = DEMO_DIR / "demo_master_content.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        mc = MasterContent.model_validate(data)
        score, issues = validate_alignment(mc)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_self_contained_check_on_master_content(self):
        """check_self_contained finds no delegation phrases in demo fixture."""
        from clawed.master_content import MasterContent
        from clawed.validation import check_self_contained

        fixture_path = DEMO_DIR / "demo_master_content.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        mc = MasterContent.model_validate(data)
        # Check all text fields for delegation phrases
        all_text = mc.title + " " + mc.objective
        for section in mc.direct_instruction:
            all_text += " " + section.content
        violations = check_self_contained(all_text)
        # Demo fixture should be clean
        assert len(violations) == 0, f"Demo fixture has delegation phrases: {violations}"

    def test_generation_report_model(self):
        """GenerationReport accumulates warnings and produces summary."""
        from clawed.generation_report import GenerationReport

        report = GenerationReport()
        assert report.warnings == []
        report.warnings.append("test warning")
        assert len(report.warnings) == 1
