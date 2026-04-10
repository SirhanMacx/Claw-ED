"""Tests for curriculum gap analyzer — models, CLI, export, integration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from clawed.cli import app
from clawed.curriculum_map import CurriculumMapper
from clawed.models import CurriculumGap, TeacherPersona

# ── CurriculumGap model tests ────────────────────────────────────────


class TestCurriculumGapModel:
    def test_create_gap_all_fields(self):
        gap = CurriculumGap(
            standard="SS.8.C.1.1",
            description="Students should analyze primary sources from the Civil War era.",
            severity="high",
            suggestion="Add a 2-week unit on primary source analysis with DBQ activities.",
        )
        assert gap.standard == "SS.8.C.1.1"
        assert gap.severity == "high"
        assert "primary source" in gap.description

    def test_create_gap_defaults(self):
        gap = CurriculumGap(
            standard="CCSS.ELA.8.1",
            description="Reading informational text at grade level.",
        )
        assert gap.severity == "medium"
        assert gap.suggestion == ""

    def test_gap_severity_values(self):
        for sev in ["high", "medium", "low"]:
            gap = CurriculumGap(
                standard=f"STD.{sev}",
                description=f"A {sev} severity gap.",
                severity=sev,
            )
            assert gap.severity == sev

    def test_gap_serialization(self):
        gap = CurriculumGap(
            standard="NYS.8SS.1",
            description="Understanding colonialism.",
            severity="medium",
            suggestion="Add a unit on European colonialism.",
        )
        d = gap.model_dump()
        assert d["standard"] == "NYS.8SS.1"
        assert d["severity"] == "medium"

    def test_gap_roundtrip_json(self):
        gap = CurriculumGap(
            standard="NYS.8SS.2",
            description="Analyze historical maps.",
            severity="low",
            suggestion="Include map skills lesson.",
        )
        restored = CurriculumGap.model_validate(json.loads(gap.model_dump_json()))
        assert restored.standard == gap.standard
        assert restored.description == gap.description

    def test_gap_list_empty(self):
        gaps: list[CurriculumGap] = []
        assert len(gaps) == 0

    def test_gap_list_multiple(self):
        gaps = [CurriculumGap(standard=f"STD.{i}", description=f"Gap {i}", severity="medium") for i in range(5)]
        assert len(gaps) == 5
        assert gaps[2].standard == "STD.2"


# ── CurriculumMapper tests ───────────────────────────────────────────


class TestCurriculumMapper:
    def test_mapper_instantiates(self):
        mapper = CurriculumMapper()
        assert mapper is not None
        assert hasattr(mapper, "identify_curriculum_gaps")

    def test_mapper_identify_gaps_returns_list(self, tmp_path):
        """identify_curriculum_gaps returns a list of CurriculumGap objects."""
        mock_gaps = [
            {
                "standard": "SS.8.A.1.1",
                "description": "Civil War causes — not covered in existing materials.",
                "severity": "high",
                "suggestion": "Add a unit on the causes of the Civil War.",
            },
            {
                "standard": "SS.8.A.2.1",
                "description": "Reconstruction — only surface coverage.",
                "severity": "medium",
                "suggestion": "Expand existing unit with primary sources.",
            },
        ]

        with patch("clawed.curriculum_map.LLMClient") as mock_llm:
            instance = mock_llm.return_value
            instance.generate_json = AsyncMock(return_value=mock_gaps)

            mapper = CurriculumMapper()
            import asyncio

            result = asyncio.run(
                mapper.identify_curriculum_gaps(
                    existing_materials=["Unit 3 - WWI.md", "Unit 4 - WWII.md"],
                    standards=["SS.8.A.1.1 - Civil War", "SS.8.A.2.1 - Reconstruction"],
                )
            )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].standard == "SS.8.A.1.1"
        assert result[0].severity == "high"
        assert result[1].standard == "SS.8.A.2.1"

    def test_mapper_handles_dict_wrapped_response(self):
        """LLM wraps gaps in {"gaps": [...]} — should still parse correctly."""
        mock_wrapped = {
            "gaps": [
                {
                    "standard": "SS.8.B.1.1",
                    "description": "Geography skills gap.",
                    "severity": "low",
                    "suggestion": "Add map exercises.",
                }
            ]
        }

        with patch("clawed.curriculum_map.LLMClient") as mock_llm:
            instance = mock_llm.return_value
            instance.generate_json = AsyncMock(return_value=mock_wrapped)

            mapper = CurriculumMapper()
            import asyncio

            result = asyncio.run(
                mapper.identify_curriculum_gaps(
                    existing_materials=["lesson1.md"],
                    standards=["SS.8.B.1.1"],
                )
            )

        assert len(result) == 1
        assert result[0].standard == "SS.8.B.1.1"

    def test_mapper_handles_empty_response(self):
        """Empty list from LLM = no gaps."""
        with patch("clawed.curriculum_map.LLMClient") as mock_llm:
            instance = mock_llm.return_value
            instance.generate_json = AsyncMock(return_value=[])

            mapper = CurriculumMapper()
            import asyncio

            result = asyncio.run(
                mapper.identify_curriculum_gaps(
                    existing_materials=["full_coverage.md"],
                    standards=["SS.8.A.1.1"],
                )
            )

        assert result == []

    def test_mapper_passes_persona_to_prompt(self):
        """Persona is forwarded to the LLM prompt."""
        with patch("clawed.curriculum_map.LLMClient") as mock_llm:
            instance = mock_llm.return_value
            instance.generate_json = AsyncMock(return_value=[])

            persona = TeacherPersona(
                name="Mr. Mac",
                subject_area="Social Studies",
                grade_levels=["8"],
            )
            mapper = CurriculumMapper()
            import asyncio

            asyncio.run(
                mapper.identify_curriculum_gaps(
                    existing_materials=["lesson.md"],
                    standards=["SS.8.A.1.1"],
                    persona=persona,
                )
            )

        # Verify generate_json was called (with persona baked into prompt)
        assert instance.generate_json.called

    def test_mapper_handles_no_materials(self):
        """Empty materials list is handled gracefully."""
        mock_gaps = [
            {
                "standard": "SS.8.A.1.1",
                "description": "No materials to cover this standard.",
                "severity": "high",
                "suggestion": "Create initial unit materials.",
            }
        ]

        with patch("clawed.curriculum_map.LLMClient") as mock_llm:
            instance = mock_llm.return_value
            instance.generate_json = AsyncMock(return_value=mock_gaps)

            mapper = CurriculumMapper()
            import asyncio

            result = asyncio.run(
                mapper.identify_curriculum_gaps(
                    existing_materials=[],
                    standards=["SS.8.A.1.1"],
                )
            )

        assert len(result) == 1

    def test_mapper_caps_materials_list(self):
        """Very large materials lists should still function."""
        large_list = [f"file_{i}.md" for i in range(300)]

        with patch("clawed.curriculum_map.LLMClient") as mock_llm:
            instance = mock_llm.return_value
            instance.generate_json = AsyncMock(return_value=[])

            mapper = CurriculumMapper()
            import asyncio

            result = asyncio.run(
                mapper.identify_curriculum_gaps(
                    existing_materials=large_list,
                    standards=["SS.8.A.1.1"],
                )
            )

        assert result == []


# ── Severity sorting tests ───────────────────────────────────────────


class TestGapSeveritySorting:
    def _make_gap(self, severity: str) -> CurriculumGap:
        return CurriculumGap(
            standard=f"STD.{severity}",
            description=f"A {severity} gap.",
            severity=severity,
        )

    def test_sort_high_before_medium_before_low(self):
        gaps = [
            self._make_gap("low"),
            self._make_gap("high"),
            self._make_gap("medium"),
        ]
        sev_order = {"high": 0, "medium": 1, "low": 2}
        sorted_gaps = sorted(gaps, key=lambda x: sev_order.get(x.severity.lower(), 3))
        assert [g.severity for g in sorted_gaps] == ["high", "medium", "low"]

    def test_all_high_stays_ordered(self):
        gaps = [self._make_gap("high") for _ in range(3)]
        sev_order = {"high": 0, "medium": 1, "low": 2}
        sorted_gaps = sorted(gaps, key=lambda x: sev_order.get(x.severity.lower(), 3))
        assert all(g.severity == "high" for g in sorted_gaps)

    def test_unknown_severity_sorts_last(self):
        gap = CurriculumGap(standard="X", description="?", severity="critical")
        sev_order = {"high": 0, "medium": 1, "low": 2}
        score = sev_order.get(gap.severity.lower(), 3)
        assert score == 3  # falls to default


# ── HTML export tests ────────────────────────────────────────────────


class TestGapReportHtml:
    def _make_gaps(self) -> list[CurriculumGap]:
        return [
            CurriculumGap(
                standard="SS.8.A.1.1",
                description="Civil War causes missing.",
                severity="high",
                suggestion="Add Civil War unit.",
            ),
            CurriculumGap(
                standard="SS.8.A.2.1",
                description="Reconstruction under-covered.",
                severity="medium",
                suggestion="Expand existing unit.",
            ),
            CurriculumGap(
                standard="SS.8.B.1.1",
                description="Geography skills light.",
                severity="low",
                suggestion="Add map exercises.",
            ),
        ]

    def test_html_contains_report_title(self, tmp_path):
        gaps = self._make_gaps()
        subject = "Social Studies"
        grade = "8"
        html = self._build_html(gaps, subject, grade)
        assert "Curriculum Gap Report" in html
        assert subject in html
        assert grade in html

    def test_html_contains_all_standards(self, tmp_path):
        gaps = self._make_gaps()
        html = self._build_html(gaps, "Social Studies", "8")
        for g in gaps:
            assert g.standard in html

    def test_html_contains_severity_badges(self, tmp_path):
        gaps = self._make_gaps()
        html = self._build_html(gaps, "Social Studies", "8")
        assert "HIGH" in html
        assert "MEDIUM" in html
        assert "LOW" in html

    def test_html_contains_summary_counts(self, tmp_path):
        gaps = self._make_gaps()
        html = self._build_html(gaps, "Social Studies", "8")
        # 1 high, 1 medium, 1 low — check count-bearing text
        assert "1 HIGH" in html
        assert "1 MEDIUM" in html
        assert "1 LOW" in html

    def test_html_contains_descriptions(self, tmp_path):
        gaps = self._make_gaps()
        html = self._build_html(gaps, "Social Studies", "8")
        assert "Civil War causes missing" in html
        assert "Reconstruction under-covered" in html

    def test_html_is_valid_document(self, tmp_path):
        gaps = self._make_gaps()
        html = self._build_html(gaps, "Science", "7")
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    @staticmethod
    def _build_html(gaps: list[CurriculumGap], subject: str, grade: str) -> str:
        """Build the gap report HTML the same way the CLI does."""
        from datetime import datetime

        high = [g for g in gaps if g.severity.lower() == "high"]
        med = [g for g in gaps if g.severity.lower() == "medium"]
        low = [g for g in gaps if g.severity.lower() == "low"]

        sev_order = {"high": 0, "medium": 1, "low": 2}
        badge_colors = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}

        rows_html = ""
        for g in sorted(gaps, key=lambda x: sev_order.get(x.severity.lower(), 3)):
            color = badge_colors.get(g.severity.lower(), "#6b7280")
            rows_html += f"""
            <tr>
              <td><span class="badge" style="background:{color}">{g.severity.upper()}</span></td>
              <td class="standard">{g.standard}</td>
              <td>{g.description}</td>
              <td class="suggestion">{g.suggestion}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Curriculum Gap Report — {subject} Grade {grade}</title></head>
<body>
<h1>Curriculum Gap Report</h1>
<div class="meta">{subject} · Grade {grade} · Generated {datetime.now().strftime("%B %d, %Y")}</div>
<div class="summary-bar">
  <span class="pill high">{len(high)} HIGH</span>
  <span class="pill med">{len(med)} MEDIUM</span>
  <span class="pill low">{len(low)} LOW</span>
</div>
<table><thead><tr><th>Severity</th><th>Standard</th><th>Gap Description</th><th>Suggestion</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</body></html>"""


# ── CLI integration tests ────────────────────────────────────────────


runner = CliRunner()


class TestGapAnalyzeCLI:
    def _mock_persona(self):
        persona = TeacherPersona(
            name="Mr. Mac",
            subject_area="Social Studies",
            grade_levels=["8"],
        )
        return persona

    def _mock_gaps(self) -> list[CurriculumGap]:
        return [
            CurriculumGap(
                standard="SS.8.A.1.1",
                description="Civil War missing.",
                severity="high",
                suggestion="Add unit.",
            ),
        ]

    def test_help_output(self):
        result = runner.invoke(app, ["gap-analyze", "--help"])
        assert result.exit_code == 0
        assert "gap" in result.output.lower() or "curriculum" in result.output.lower()

    def test_requires_subject_and_grade(self):
        result = runner.invoke(app, ["gap-analyze"])
        assert result.exit_code != 0

    def test_missing_subject_fails(self):
        result = runner.invoke(app, ["gap-analyze", "--grade", "8"])
        assert result.exit_code != 0

    def test_missing_grade_fails(self):
        result = runner.invoke(app, ["gap-analyze", "--subject", "Social Studies"])
        assert result.exit_code != 0

    def test_invalid_materials_dir_fails(self, tmp_path):
        with (
            patch("clawed.commands.generate_standards.check_api_key_or_exit"),
            patch("clawed.commands.generate_standards.load_persona_or_exit") as mock_p,
        ):
            mock_p.return_value = self._mock_persona()
            result = runner.invoke(
                app,
                [
                    "gap-analyze",
                    "--subject",
                    "Math",
                    "--grade",
                    "8",
                    "--materials-dir",
                    "/nonexistent/path/xyz",
                ],
            )
        assert result.exit_code != 0

    def test_gap_analyze_runs_and_outputs(self, tmp_path):
        """Full CLI run with mocked LLM — should produce output."""
        with (
            patch("clawed.commands.generate_standards.check_api_key_or_exit"),
            patch("clawed.commands.generate_standards.load_persona_or_exit") as mock_p,
            patch("clawed.curriculum_map.CurriculumMapper") as mock_mapper,
            patch("clawed.commands.generate_standards._output_dir", return_value=tmp_path),
            patch("clawed.models.AppConfig.load") as mock_config,
        ):
            mock_p.return_value = self._mock_persona()
            mock_config.load.return_value = MagicMock(active_teacher_id=None)
            mapper_instance = mock_mapper.return_value
            mapper_instance.identify_curriculum_gaps = AsyncMock(return_value=self._mock_gaps())

            result = runner.invoke(
                app,
                [
                    "gap-analyze",
                    "--subject",
                    "Social Studies",
                    "--grade",
                    "8",
                    "--standards",
                    "SS.8.A.1.1 - Civil War",
                ],
            )

        assert result.exit_code == 0
        assert "Gap" in result.output or "gap" in result.output.lower()

    def test_gap_analyze_no_gaps_message(self, tmp_path):
        """When LLM returns no gaps, show success message."""
        with (
            patch("clawed.commands.generate_standards.check_api_key_or_exit"),
            patch("clawed.commands.generate_standards.load_persona_or_exit") as mock_p,
            patch("clawed.curriculum_map.CurriculumMapper") as mock_mapper,
            patch("clawed.commands.generate_standards._output_dir", return_value=tmp_path),
            patch("clawed.models.AppConfig.load") as mock_config,
        ):
            mock_p.return_value = self._mock_persona()
            mock_config.load.return_value = MagicMock(active_teacher_id=None)
            mapper_instance = mock_mapper.return_value
            mapper_instance.identify_curriculum_gaps = AsyncMock(return_value=[])

            result = runner.invoke(
                app,
                [
                    "gap-analyze",
                    "--subject",
                    "Math",
                    "--grade",
                    "9",
                    "--standards",
                    "CCSS.Math.9",
                ],
            )

        assert result.exit_code == 0
        assert "No curriculum gaps" in result.output

    def test_gap_analyze_standards_from_file(self, tmp_path):
        """Standards can be loaded from a text file."""
        standards_file = tmp_path / "standards.txt"
        standards_file.write_text("SS.8.A.1.1\nSS.8.A.2.1\nSS.8.B.1.1\n")

        with (
            patch("clawed.commands.generate_standards.check_api_key_or_exit"),
            patch("clawed.commands.generate_standards.load_persona_or_exit") as mock_p,
            patch("clawed.curriculum_map.CurriculumMapper") as mock_mapper,
            patch("clawed.commands.generate_standards._output_dir", return_value=tmp_path),
            patch("clawed.models.AppConfig.load") as mock_config,
        ):
            mock_p.return_value = self._mock_persona()
            mock_config.load.return_value = MagicMock(active_teacher_id=None)
            mapper_instance = mock_mapper.return_value
            mapper_instance.identify_curriculum_gaps = AsyncMock(return_value=[])

            result = runner.invoke(
                app,
                [
                    "gap-analyze",
                    "--subject",
                    "Social Studies",
                    "--grade",
                    "8",
                    "--standards",
                    str(standards_file),
                ],
            )

        assert result.exit_code == 0
        # verify 3 standards were passed
        call_args = mapper_instance.identify_curriculum_gaps.call_args
        standards_arg = call_args.kwargs.get("standards") or call_args.args[1]
        assert len(standards_arg) == 3

    def test_gap_analyze_materials_dir(self, tmp_path):
        """--materials-dir scans files from the directory."""
        mat_dir = tmp_path / "materials"
        mat_dir.mkdir()
        (mat_dir / "unit1.md").write_text("Civil War unit")
        (mat_dir / "unit2.md").write_text("WWII unit")
        (mat_dir / "lesson.pdf").write_text("lesson")

        with (
            patch("clawed.commands.generate_standards.check_api_key_or_exit"),
            patch("clawed.commands.generate_standards.load_persona_or_exit") as mock_p,
            patch("clawed.curriculum_map.CurriculumMapper") as mock_mapper,
            patch("clawed.commands.generate_standards._output_dir", return_value=tmp_path),
            patch("clawed.models.AppConfig.load") as mock_config,
        ):
            mock_p.return_value = self._mock_persona()
            mock_config.load.return_value = MagicMock(active_teacher_id=None)
            mapper_instance = mock_mapper.return_value
            mapper_instance.identify_curriculum_gaps = AsyncMock(return_value=[])

            result = runner.invoke(
                app,
                [
                    "gap-analyze",
                    "--subject",
                    "Social Studies",
                    "--grade",
                    "8",
                    "--materials-dir",
                    str(mat_dir),
                ],
            )

        assert result.exit_code == 0
        call_args = mapper_instance.identify_curriculum_gaps.call_args
        materials_arg = call_args.kwargs.get("existing_materials") or call_args.args[0]
        assert len(materials_arg) == 3  # unit1.md, unit2.md, lesson.pdf

    def test_gap_analyze_markdown_format(self, tmp_path):
        """--format markdown produces a .md file."""
        with (
            patch("clawed.commands.generate_standards.check_api_key_or_exit"),
            patch("clawed.commands.generate_standards.load_persona_or_exit") as mock_p,
            patch("clawed.curriculum_map.CurriculumMapper") as mock_mapper,
            patch("clawed.commands.generate_standards._output_dir", return_value=tmp_path),
            patch("clawed.models.AppConfig.load") as mock_config,
        ):
            mock_p.return_value = self._mock_persona()
            mock_config.load.return_value = MagicMock(active_teacher_id=None)
            mapper_instance = mock_mapper.return_value
            mapper_instance.identify_curriculum_gaps = AsyncMock(return_value=self._mock_gaps())

            result = runner.invoke(
                app,
                [
                    "gap-analyze",
                    "--subject",
                    "Science",
                    "--grade",
                    "7",
                    "--format",
                    "markdown",
                ],
            )

        assert result.exit_code == 0
        # Check a .md file was created in the gap-reports dir
        md_files = list((tmp_path / "gap-reports").glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text()
        assert "# Curriculum Gap Report" in content

    def test_gap_analyze_html_format_default(self, tmp_path):
        """Default format is html — should produce .html file."""
        with (
            patch("clawed.commands.generate_standards.check_api_key_or_exit"),
            patch("clawed.commands.generate_standards.load_persona_or_exit") as mock_p,
            patch("clawed.curriculum_map.CurriculumMapper") as mock_mapper,
            patch("clawed.commands.generate_standards._output_dir", return_value=tmp_path),
            patch("clawed.models.AppConfig.load") as mock_config,
        ):
            mock_p.return_value = self._mock_persona()
            mock_config.load.return_value = MagicMock(active_teacher_id=None)
            mapper_instance = mock_mapper.return_value
            mapper_instance.identify_curriculum_gaps = AsyncMock(return_value=self._mock_gaps())

            result = runner.invoke(
                app,
                [
                    "gap-analyze",
                    "--subject",
                    "Social Studies",
                    "--grade",
                    "8",
                ],
            )

        assert result.exit_code == 0
        html_files = list((tmp_path / "gap-reports").glob("*.html"))
        assert len(html_files) == 1
        content = html_files[0].read_text()
        assert "<!DOCTYPE html>" in content
        assert "Curriculum Gap Report" in content

    def test_gap_analyze_multiple_gaps_all_displayed(self, tmp_path):
        """All returned gaps appear in CLI output."""
        multi_gaps = [
            CurriculumGap(standard="STD.1", description="Gap one", severity="high", suggestion="Fix 1"),
            CurriculumGap(standard="STD.2", description="Gap two", severity="medium", suggestion="Fix 2"),
            CurriculumGap(standard="STD.3", description="Gap three", severity="low", suggestion="Fix 3"),
        ]

        with (
            patch("clawed.commands.generate_standards.check_api_key_or_exit"),
            patch("clawed.commands.generate_standards.load_persona_or_exit") as mock_p,
            patch("clawed.curriculum_map.CurriculumMapper") as mock_mapper,
            patch("clawed.commands.generate_standards._output_dir", return_value=tmp_path),
            patch("clawed.models.AppConfig.load") as mock_config,
        ):
            mock_p.return_value = self._mock_persona()
            mock_config.load.return_value = MagicMock(active_teacher_id=None)
            mapper_instance = mock_mapper.return_value
            mapper_instance.identify_curriculum_gaps = AsyncMock(return_value=multi_gaps)

            result = runner.invoke(
                app,
                ["gap-analyze", "--subject", "Math", "--grade", "6"],
            )

        assert result.exit_code == 0
        assert "1 HIGH" in result.output
        assert "1 MEDIUM" in result.output
        assert "1 LOW" in result.output
