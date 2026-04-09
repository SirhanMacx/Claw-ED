"""Project packet DOCX compiler for ProjectArc.

Compiles a ProjectArc into a student-facing project packet with day-by-day
roadmap, choice boards, graphic organizer, research databases, rubric,
debate prep sheet, and culminating performance instructions.
No LLM calls — pure mechanical compilation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.models import ProjectArc

logger = logging.getLogger(__name__)


async def compile_project_packet(
    project: "ProjectArc",
    output_dir: Path,
) -> Path:
    """Compile a student-facing project packet DOCX from a ProjectArc.

    Args:
        project: The ProjectArc source object.
        output_dir: Directory where the .docx file will be written.

    Returns:
        Path to the generated .docx file.
    """
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    from clawed.export_theme import get_color_theme
    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = Document()

    # ── theme ────────────────────────────────────────────────────────
    theme = get_color_theme("history")  # default; could be parameterized
    primary_hex = theme["primary"]

    def _hex_rgb(h: str) -> RGBColor:
        return RGBColor(int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _shaded_cell(cell, fill_hex: str) -> None:
        tc = cell._tc
        tc_pr = tc.get_or_add_tcPr()
        shd = tc_pr.makeelement(qn("w:shd"), {
            qn("w:val"): "clear",
            qn("w:color"): "auto",
            qn("w:fill"): fill_hex,
        })
        tc_pr.append(shd)

    def _para(text: str, bold: bool = False, italic: bool = False,
              size_pt: int = 11) -> None:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = bold
        run.italic = italic
        run.font.size = Pt(size_pt)
        run.font.name = "Calibri"

    # ── Title page ───────────────────────────────────────────────────

    title_heading = doc.add_heading(project.title, level=0)
    for run in title_heading.runs:
        run.font.color.rgb = _hex_rgb(primary_hex)

    if project.essential_question:
        eq_para = doc.add_paragraph()
        eq_run = eq_para.add_run(f'Essential Question: "{project.essential_question}"')
        eq_run.bold = True
        eq_run.italic = True
        eq_run.font.size = Pt(14)
        eq_run.font.name = "Calibri"

    doc.add_paragraph("")
    doc.add_paragraph("Name: ___________________________  Date: ___________  Period: _____")
    doc.add_paragraph("")

    # ── Day-by-Day Roadmap ───────────────────────────────────────────

    doc.add_heading("Day-by-Day Roadmap", level=1)
    _para(
        "Track your progress! Check off each phase as you complete it.",
        italic=True,
    )
    doc.add_paragraph("")

    for phase in project.phases:
        phase_text = f"[ ] {phase.title}"
        if phase.objective:
            phase_text += f" — {phase.objective}"
        _para(phase_text, bold=True)
        if phase.student_deliverable:
            _para(f"    Deliverable: {phase.student_deliverable}")
        doc.add_paragraph("")

    doc.add_page_break()

    # ── Topic Options ────────────────────────────────────────────────

    if project.movement_options:
        doc.add_heading("Choose Your Topic", level=1)
        _para("Select ONE of the following topics to specialize in:")
        doc.add_paragraph("")
        for i, option in enumerate(project.movement_options, 1):
            _para(f"{i}. {option}")
        doc.add_paragraph("")
        _para("My Choice: _______________________________________", bold=True)
        doc.add_paragraph("")

    # ── Format Options ───────────────────────────────────────────────

    if project.format_options:
        doc.add_heading("Choose Your Project Format", level=1)
        _para("How will you show what you know? Choose ONE:")
        doc.add_paragraph("")
        for option in project.format_options:
            _para(f"\u2022 {option}")
        doc.add_paragraph("")
        _para("My Choice: _______________________________________", bold=True)
        doc.add_paragraph("")

    doc.add_page_break()

    # ── Graphic Organizer ────────────────────────────────────────────

    if project.graphic_organizer:
        doc.add_heading("Research Notes", level=1)
        cols = [c.strip() for c in project.graphic_organizer.split("|") if c.strip()]
        if cols:
            tbl = doc.add_table(rows=6, cols=len(cols))
            tbl.style = "Table Grid"
            for j, col_name in enumerate(cols):
                cell = tbl.rows[0].cells[j]
                _shaded_cell(cell, primary_hex)
                cell.text = col_name
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.bold = True
                        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                        run.font.name = "Calibri"
        doc.add_paragraph("")

    # ── Research Resource Library ────────────────────────────────────

    if project.resource_library:
        doc.add_heading("Research Resource Library", level=1)
        _para(
            "Skip the basic Google search! Use these trusted databases:",
            italic=True,
        )
        doc.add_paragraph("")
        for resource in project.resource_library:
            name = resource.get("name", "")
            url = resource.get("url", "")
            desc = resource.get("description", "")
            _para(f"\u2022 {name}", bold=True)
            if url:
                _para(f"  {url}")
            if desc:
                _para(f"  {desc}", italic=True)
        doc.add_paragraph("")

    doc.add_page_break()

    # ── Debate Prep Sheet ────────────────────────────────────────────

    if project.debate_prep_template:
        doc.add_heading("Debate Prep Sheet", level=1)
        for line in project.debate_prep_template.split("\n"):
            if line.strip():
                _para(line)
            else:
                doc.add_paragraph("")
        doc.add_paragraph("")

    # ── Rubric ───────────────────────────────────────────────────────

    if project.rubric_text:
        doc.add_heading("Grading Rubric", level=1)
        # Parse markdown table into real DOCX table
        raw_lines = project.rubric_text.strip().split("\n")
        lines = [
            ln for ln in raw_lines
            if ln.strip() and not ln.strip().startswith("|---")
        ]
        if lines:
            rows_data = []
            for line in lines:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if cells:
                    rows_data.append(cells)
            if rows_data:
                num_cols = max(len(r) for r in rows_data)
                tbl = doc.add_table(rows=len(rows_data), cols=num_cols)
                tbl.style = "Table Grid"
                for i, row_data in enumerate(rows_data):
                    for j, cell_text in enumerate(row_data):
                        if j < num_cols:
                            cell = tbl.rows[i].cells[j]
                            cell.text = cell_text
                            if i == 0:
                                _shaded_cell(cell, primary_hex)
                                for p in cell.paragraphs:
                                    for run in p.runs:
                                        run.bold = True
                                        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        doc.add_paragraph("")

    # ── Culminating Performance ──────────────────────────────────────

    perf = project.culminating_performance
    if perf and perf.title:
        doc.add_page_break()
        doc.add_heading(f"Culminating Event: {perf.title}", level=1)
        if perf.format:
            _para(f"Format: {perf.format.replace('_', ' ').title()}  |  "
                  f"Duration: {perf.duration_minutes} minutes")
        if perf.setup_instructions:
            _para("Setup:", bold=True)
            _para(perf.setup_instructions)
        if perf.student_prep:
            _para("What You Need Ready:", bold=True)
            _para(perf.student_prep)
        if perf.evaluation_criteria:
            _para("You Will Be Evaluated On:", bold=True)
            for criterion in perf.evaluation_criteria:
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(criterion)

    # ── Save ─────────────────────────────────────────────────────────

    safe = safe_filename(project.title)
    out_path = output_dir / f"{safe}_project_packet.docx"
    doc.save(str(out_path))
    logger.info("Project packet saved to %s", out_path)
    return out_path
