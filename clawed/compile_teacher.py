"""Teacher-view DOCX compiler for MasterContent.

Compiles a MasterContent object into a teacher-facing Word document with
full answer keys, teacher scripts, and all instructional notes.
No LLM calls — pure mechanical compilation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.master_content import MasterContent

logger = logging.getLogger(__name__)


async def compile_teacher_view(
    master: MasterContent,
    images: dict[str, Path],
    output_dir: Path,
) -> Path:
    """Compile a teacher-facing DOCX from a MasterContent object.

    Includes full answer keys, teacher scripts (italicised), guided notes
    with answers filled in, station answer keys, and differentiation notes.

    Args:
        master: The MasterContent source-of-truth object.
        images: Mapping of image_spec strings to local file Paths.
        output_dir: Directory where the .docx file will be written.

    Returns:
        Path to the generated .docx file.
    """
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    from clawed.export_theme import get_color_theme
    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = Document()

    # ── subject-aware color theme ───────────────────────────────────
    theme = get_color_theme(master.subject)
    primary_hex = theme["primary"]
    accent_hex = theme["accent"]
    bg_light_hex = theme["bg_light"]

    def _hex_rgb(h: str) -> RGBColor:
        return RGBColor(int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    # ── helpers ──────────────────────────────────────────────────────

    def _heading(text: str, level: int = 1) -> None:
        h = doc.add_heading(text, level=level)
        # Theme the heading color
        if level <= 2:
            for run in h.runs:
                run.font.color.rgb = _hex_rgb(primary_hex)

    def _para(text: str, bold: bool = False, italic: bool = False,
               size_pt: int = 11, color: tuple[int, int, int] | None = None) -> None:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = bold
        run.italic = italic
        run.font.size = Pt(size_pt)
        run.font.name = "Calibri"
        if color:
            run.font.color.rgb = RGBColor(*color)

    def _page_break() -> None:
        doc.add_page_break()

    def _embed_image(image_spec: str, width_inches: float = 4.5) -> None:
        """Embed a pre-fetched image if its spec is in the images dict."""
        if not image_spec:
            return
        path = images.get(image_spec)
        if path and Path(path).exists():
            try:
                doc.add_picture(str(path), width=Inches(width_inches))
                last_para = doc.paragraphs[-1]
                last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception as exc:
                logger.debug("Could not embed image %r: %s", image_spec, exc)

    def _shaded_cell(cell, fill_hex: str) -> None:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()  # noqa: N806
        shd = tcPr.makeelement(qn("w:shd"), {
            qn("w:val"): "clear",
            qn("w:color"): "auto",
            qn("w:fill"): fill_hex,
        })
        tcPr.append(shd)

    def _callout_box(title: str, items: list[str], fill_hex: str,
                     title_hex: str = "FFFFFF") -> None:
        """Render a colored callout box as a single-column table."""
        tbl = doc.add_table(rows=1 + len(items), cols=1)
        tbl.style = "Table Grid"
        # Header row
        hdr = tbl.rows[0].cells[0]
        _shaded_cell(hdr, fill_hex)
        run = hdr.paragraphs[0].add_run(title)
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = _hex_rgb(title_hex)
        run.font.name = "Calibri"
        # Item rows
        for i, item in enumerate(items):
            cell = tbl.rows[i + 1].cells[0]
            _shaded_cell(cell, bg_light_hex)
            run = cell.paragraphs[0].add_run(f"\u2022 {item}")
            run.font.size = Pt(10)
            run.font.name = "Calibri"
        doc.add_paragraph("")

    # ── Title / metadata header ───────────────────────────────────────

    doc.add_heading(master.title, level=0)

    meta_lines = [
        f"Subject: {master.subject}  |  Grade: {master.grade_level}  |  "
        f"Duration: {master.duration_minutes} min",
        f"Topic: {master.topic}",
        f"Objective: {master.objective}",
    ]
    for line in meta_lines:
        _para(line)

    if master.standards:
        _para("Standards: " + ", ".join(master.standards), bold=True)

    if master.materials_needed:
        _para("Materials: " + ", ".join(master.materials_needed))

    doc.add_paragraph("")

    # ── Materials at a Glance ────────────────────────────────────────

    glance_format = getattr(master, "lesson_format", None) or "document_analysis"
    glance_format_display = glance_format.replace("_", " ").title()
    glance_standards = ", ".join(master.standards) if master.standards else "N/A"
    glance_ps_count = len(master.primary_sources) if master.primary_sources else 0
    glance_vocab_count = len(master.vocabulary) if master.vocabulary else 0
    glance_et_count = len(master.exit_ticket) if master.exit_ticket else 0

    diff = master.differentiation
    glance_iep = "IEP \u2713" if diff.struggling else "IEP \u2717"
    glance_ell = "ELL \u2713" if diff.ell else "ELL \u2717"
    glance_gifted = "Gifted \u2713" if diff.advanced else "Gifted \u2717"

    glance_table = doc.add_table(rows=4, cols=1)
    glance_table.style = "Table Grid"

    header_cell = glance_table.rows[0].cells[0]
    _shaded_cell(header_cell, primary_hex)
    header_run = header_cell.paragraphs[0].add_run("MATERIALS AT A GLANCE")
    header_run.bold = True
    header_run.font.size = Pt(13)
    header_run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    header_run.font.name = "Calibri"
    header_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    row1_cell = glance_table.rows[1].cells[0]
    _shaded_cell(row1_cell, accent_hex)
    row1_run = row1_cell.paragraphs[0].add_run(
        f"Duration: {master.duration_minutes} min  |  "
        f"Format: {glance_format_display}  |  "
        f"Standards: {glance_standards}"
    )
    row1_run.font.size = Pt(10)
    row1_run.font.name = "Calibri"

    row2_cell = glance_table.rows[2].cells[0]
    _shaded_cell(row2_cell, accent_hex)
    row2_run = row2_cell.paragraphs[0].add_run(
        f"Primary Sources: {glance_ps_count}  |  "
        f"Vocabulary Terms: {glance_vocab_count}  |  "
        f"Exit Ticket: {glance_et_count} questions"
    )
    row2_run.font.size = Pt(10)
    row2_run.font.name = "Calibri"

    row3_cell = glance_table.rows[3].cells[0]
    _shaded_cell(row3_cell, accent_hex)
    row3_run = row3_cell.paragraphs[0].add_run(
        f"Differentiation: {glance_iep}  |  {glance_ell}  |  {glance_gifted}"
    )
    row3_run.font.size = Pt(10)
    row3_run.font.name = "Calibri"

    doc.add_paragraph("")

    # ── Vocabulary ────────────────────────────────────────────────────

    if master.vocabulary:
        _heading("Vocabulary")
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        for cell, label in zip(hdr_cells, ["Term", "Definition", "Context Sentence"], strict=False):
            _shaded_cell(cell, primary_hex)
            cell.text = label
            cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

        for entry in master.vocabulary:
            row = table.add_row().cells
            row[0].text = entry.term
            row[1].text = entry.definition
            row[2].text = entry.context_sentence
            if entry.image_spec:
                _embed_image(entry.image_spec, width_inches=1.5)

        doc.add_paragraph("")

    # ── Do Now ────────────────────────────────────────────────────────

    _heading("Do Now")
    _para(master.do_now.stimulus)
    if master.do_now.questions:
        for i, q in enumerate(master.do_now.questions, 1):
            _para(f"{i}. {q}")
    # Teacher answer key
    if master.do_now.answers:
        _para("ANSWERS:", bold=True, color=(0x00, 0x70, 0xC0))
        for i, ans in enumerate(master.do_now.answers, 1):
            _para(f"{i}. {ans}", italic=True)
    doc.add_paragraph("")

    # ── Direct Instruction ────────────────────────────────────────────

    _heading("Direct Instruction")
    for section in master.direct_instruction:
        _heading(section.heading, level=2)
        _para(section.content)
        if section.key_points:
            _para("Key Points:", bold=True)
            for kp in section.key_points:
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(kp)
        # Teacher script in italics
        if section.teacher_script:
            _para("Teacher Script:", bold=True, color=(0x70, 0x30, 0xA0))
            _para(section.teacher_script, italic=True, color=(0x70, 0x30, 0xA0))
        _embed_image(section.image_spec)
        doc.add_paragraph("")

    # ── Guided Notes (answers filled in) ─────────────────────────────

    if master.guided_notes:
        _heading("Guided Notes (Answer Key)")
        for note in master.guided_notes:
            _para(f"Prompt: {note.prompt}", bold=True)
            _para(f"Answer: {note.answer}", italic=True, color=(0x00, 0x70, 0xC0))
            if note.section_ref:
                _para(f"(Ref: {note.section_ref})", size_pt=9, color=(0x66, 0x66, 0x66))
            doc.add_paragraph("")

    # ── Primary Sources ────────────────────────────────────────────────

    if master.primary_sources:
        _page_break()
        _heading("Primary Sources")
        for ps in master.primary_sources:
            _heading(ps.title, level=2)
            _para(f"Type: {ps.source_type}  |  Attribution: {ps.attribution}")
            _para(ps.content_text)
            if ps.scaffolding_questions:
                _para("Scaffolding Questions:", bold=True)
                for sq in ps.scaffolding_questions:
                    p = doc.add_paragraph(style="List Bullet")
                    p.add_run(sq)
            _embed_image(ps.image_spec)
            doc.add_paragraph("")

    # ── Stations (with answer keys) ───────────────────────────────────

    if master.stations:
        _heading("Learning Stations")
        for station in master.stations:
            _heading(station.title, level=2)
            _para(f"Source: {station.source_ref}")
            _para(f"Task: {station.task}")
            _para("Student Directions:", bold=True)
            _para(station.student_directions)
            _para("Answer Key:", bold=True, color=(0xC0, 0x00, 0x00))
            _para(station.teacher_answer_key, italic=True, color=(0xC0, 0x00, 0x00))
            doc.add_paragraph("")

    # ── Jigsaw Structure (if present) ───────────────────────────────────

    jigsaw = getattr(master, "jigsaw", None)
    if jigsaw:
        _heading("Jigsaw Activity Structure")
        _para(f"Expert Groups: {jigsaw.num_expert_groups} groups", bold=True)
        _para(f"Expert Phase: {jigsaw.expert_phase_minutes} minutes  |  "
              f"Teaching Phase: {jigsaw.teaching_phase_minutes} minutes")
        if jigsaw.documents_per_group:
            _para("Documents per group: " + ", ".join(jigsaw.documents_per_group))
        if jigsaw.share_out_protocol:
            _para("Share-Out Protocol:", bold=True)
            _para(jigsaw.share_out_protocol)
        if jigsaw.graphic_organizer:
            _para("Graphic Organizer Columns:", bold=True)
            _para(jigsaw.graphic_organizer)
        if jigsaw.debrief_question:
            _para("Debrief Question:", bold=True)
            _para(jigsaw.debrief_question)
        doc.add_paragraph("")

    # ── Creative Activity (if present) ────────────────────────────────

    creative = getattr(master, "creative_activity", None)
    if creative and creative.title:
        _heading(f"Creative Activity: {creative.title}")
        if creative.activity_type:
            _para(f"Type: {creative.activity_type.replace('_', ' ').title()}  |  "
                  f"Time: {creative.time_minutes} minutes")
        if creative.scenario:
            _para("Scenario:", bold=True)
            _para(creative.scenario)
        if creative.roles:
            _para("Roles:", bold=True)
            for role in creative.roles:
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(role)
        if creative.student_directions:
            _para("Student Directions:", bold=True)
            _para(creative.student_directions)
        if creative.deliverable:
            _para(f"Deliverable: {creative.deliverable}", bold=True)
        if creative.debrief:
            _para("Debrief:", bold=True)
            _para(creative.debrief)
        doc.add_paragraph("")

    # ── Exit Ticket (with answers) ────────────────────────────────────

    if master.exit_ticket:
        _page_break()
        _heading("Exit Ticket")
        for i, sq in enumerate(master.exit_ticket, 1):
            _para(f"Q{i} Stimulus ({sq.stimulus_type}): {sq.stimulus}", bold=True)
            if sq.stimulus_image_spec:
                _embed_image(sq.stimulus_image_spec)
            _para(f"Question: {sq.question}")
            # Sentence starters for students
            starters = getattr(sq, "sentence_starters", [])
            if starters:
                _para("Sentence Starters:", bold=True, color=(0x00, 0x70, 0xC0))
                for starter in starters:
                    _para(f"  \u2022 {starter}", color=(0x00, 0x70, 0xC0))
            _para(f"Expected Answer: {sq.answer}", italic=True, color=(0xC0, 0x00, 0x00))
            if sq.cognitive_level:
                _para(f"Cognitive Level: {sq.cognitive_level}", size_pt=9, color=(0x66, 0x66, 0x66))
            doc.add_paragraph("")

    # ── Differentiation (themed callout boxes) ─────────────────────────

    diff = master.differentiation
    if diff.struggling or diff.advanced or diff.ell:
        _page_break()
    _heading("Differentiation")
    if diff.struggling:
        _callout_box(
            "\u2691 IEP / 504 Accommodations",
            diff.struggling,
            fill_hex="D4A017",  # Gold
            title_hex="FFFFFF",
        )
    if diff.advanced:
        _callout_box(
            "\u2605 Advanced / Gifted Extensions",
            diff.advanced,
            fill_hex="2B7A98",  # Teal
            title_hex="FFFFFF",
        )
    if diff.ell:
        _callout_box(
            "\u2709 ELL Language Supports",
            diff.ell,
            fill_hex="2D8B4E",  # Green
            title_hex="FFFFFF",
        )

    # ── Independent Work ──────────────────────────────────────────────

    if master.independent_work:
        _heading("Independent Work")
        _para(master.independent_work.task)
        if master.independent_work.rubric_snippet:
            _para("Rubric:", bold=True)
            _para(master.independent_work.rubric_snippet)
        if master.independent_work.exemplar:
            _para("Exemplar:", bold=True)
            _para(master.independent_work.exemplar)
        doc.add_paragraph("")

    # ── Homework ──────────────────────────────────────────────────────

    if master.homework:
        _heading("Homework")
        _para(master.homework)

    # ── Misconceptions (teacher-only) ────────────────────────────────

    if getattr(master, "misconceptions", None):
        _heading("Common Misconceptions to Watch For")
        _para(
            "Students often have these misunderstandings about this topic. "
            "Listen for them during discussion and address directly.",
            size_pt=10, italic=True, color=(0x66, 0x66, 0x66),
        )
        for item in master.misconceptions:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)
        doc.add_paragraph("")

    # ── Formative Checks (teacher-only) ──────────────────────────────

    if getattr(master, "formative_checks", None):
        _heading("Mid-Lesson Check-for-Understanding")
        _para(
            "Ask these during instruction — verbal or show-of-hands. "
            "Catch confusion before it compounds.",
            size_pt=10, italic=True, color=(0x66, 0x66, 0x66),
        )
        for item in master.formative_checks:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)
        doc.add_paragraph("")

    # ── Prerequisites (teacher-only) ─────────────────────────────────

    if getattr(master, "prerequisite_skills", None):
        _heading("Prerequisite Skills")
        _para(
            "Students should have these before this lesson. "
            "If not, plan a quick review.",
            size_pt=10, italic=True, color=(0x66, 0x66, 0x66),
        )
        for item in master.prerequisite_skills:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)
        doc.add_paragraph("")

    # ── Save ──────────────────────────────────────────────────────────

    safe = safe_filename(master.title)
    out_path = output_dir / f"{safe}_teacher.docx"
    doc.save(str(out_path))
    logger.info("Teacher view saved to %s", out_path)
    return out_path
