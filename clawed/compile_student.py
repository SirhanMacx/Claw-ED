"""Student-view DOCX compiler for MasterContent.

Compiles a MasterContent object into a student-facing handout Word document.
Answer keys, teacher scripts, and station answer keys are omitted; guided
notes show prompts with blank lines instead of answers.
No LLM calls — pure mechanical compilation.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.master_content import MasterContent

logger = logging.getLogger(__name__)

_BLANK = "_____________"


def _count_syllables(word: str) -> int:
    """Estimate syllable count for a single word using a vowel-group heuristic."""
    word = word.lower().strip()
    if not word:
        return 1
    # Remove trailing silent-e
    if word.endswith("e") and len(word) > 2:
        word = word[:-1]
    # Count vowel groups
    count = len(re.findall(r"[aeiouy]+", word))
    return max(count, 1)


def estimate_reading_level(text: str) -> str:
    """Estimate reading level using Flesch-Kincaid grade level formula.

    FK Grade = 0.39 * (words/sentences) + 11.8 * (syllables/words) - 15.59

    Returns one of:
        "Grade 5-6"  — simple vocabulary, short sentences
        "Grade 7-8"  — standard academic vocabulary
        "Grade 9-10" — complex vocabulary, longer sentences
        "Grade 11-12" — advanced academic language
        "College"    — specialized terminology
    """
    if not text or not text.strip():
        return "Grade 7-8"

    # Split into sentences on . ! ? (with basic filtering for abbreviations)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip().split()) >= 3]
    if not sentences:
        return "Grade 7-8"

    # Split into words (letters/apostrophes only)
    words = re.findall(r"[a-zA-Z']+", text)
    if not words:
        return "Grade 7-8"

    total_words = len(words)
    total_sentences = len(sentences)
    total_syllables = sum(_count_syllables(w) for w in words)

    words_per_sentence = total_words / total_sentences
    syllables_per_word = total_syllables / total_words

    # Flesch-Kincaid Grade Level
    fk_grade = 0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59

    if fk_grade <= 6.5:
        return "Grade 5-6"
    elif fk_grade <= 8.5:
        return "Grade 7-8"
    elif fk_grade <= 10.5:
        return "Grade 9-10"
    elif fk_grade <= 12.5:
        return "Grade 11-12"
    else:
        return "College"


async def compile_student_view(
    master: "MasterContent",
    images: dict[str, Path],
    output_dir: Path,
) -> Path:
    """Compile a student-facing DOCX from a MasterContent object.

    Guided notes show prompts with blank lines (not answers).  Teacher scripts,
    station answer keys, exit-ticket answers, and differentiation notes are all
    omitted — this is the print-ready student handout.

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

    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = Document()

    # ── Page header / footer ────────────────────────────────────────
    section = doc.sections[0]
    # Header: lesson title (left, small gray) + name/date/period fields (right)
    header = section.header
    header.is_linked_to_previous = False
    header_para = header.paragraphs[0]
    # Left-aligned run: lesson title in small gray
    title_run = header_para.add_run(master.title)
    title_run.font.size = Pt(8)
    title_run.font.color.rgb = RGBColor(128, 128, 128)
    title_run.font.name = "Calibri"
    # Tab to push right-aligned content
    header_para.add_run("\t\t")
    # Right-aligned run: student fill-in fields
    fields_run = header_para.add_run("Name: _________ Date: _________ Period: _____")
    fields_run.font.size = Pt(8)
    fields_run.font.color.rgb = RGBColor(128, 128, 128)
    fields_run.font.name = "Calibri"

    # ── helpers ──────────────────────────────────────────────────────

    def _heading(text: str, level: int = 1) -> None:
        doc.add_heading(text, level=level)

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

    def _embed_image(image_spec: str, width_inches: float = 4.5) -> None:
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

    # ── Title / metadata header ───────────────────────────────────────

    doc.add_heading(master.title, level=0)

    # Estimate reading level from all student-facing text
    reading_sample_parts = [master.topic, master.objective]
    for section in master.direct_instruction:
        reading_sample_parts.append(section.content)
    for ps in master.primary_sources:
        reading_sample_parts.append(ps.content_text)
    reading_sample = " ".join(reading_sample_parts)
    reading_level = estimate_reading_level(reading_sample)

    meta_lines = [
        f"Subject: {master.subject}  |  Grade: {master.grade_level}",
        f"Topic: {master.topic}",
        f"Objective: {master.objective}",
    ]
    for line in meta_lines:
        _para(line)

    _para(f"Reading Level: {reading_level}", italic=True, size_pt=9,
          color=(100, 100, 100))

    doc.add_paragraph("Name: ___________________________  Date: ___________  Period: _____")
    doc.add_paragraph("")

    # ── Vocabulary ────────────────────────────────────────────────────

    if master.vocabulary:
        _heading("Vocabulary")
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        for cell, label in zip(hdr_cells, ["Term", "Definition", "Context Sentence"]):
            _shaded_cell(cell, "BDD7EE")
            cell.text = label
            cell.paragraphs[0].runs[0].bold = True

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
            _para(_BLANK)
            _para("")
    doc.add_paragraph("")

    # ── Direct Instruction ────────────────────────────────────────────
    # No teacher script in student view

    _heading("Direct Instruction")
    for section in master.direct_instruction:
        _heading(section.heading, level=2)
        _para(section.content)
        if section.key_points:
            _para("Key Points:", bold=True)
            for kp in section.key_points:
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(kp)
        _embed_image(section.image_spec)
        doc.add_paragraph("")

    # ── Guided Notes (blanks — no answers) ───────────────────────────

    if master.guided_notes:
        _heading("Guided Notes")
        for note in master.guided_notes:
            _para(note.prompt, bold=True)
            _para(_BLANK)
            doc.add_paragraph("")

    # ── Primary Sources ────────────────────────────────────────────────

    if master.primary_sources:
        _heading("Primary Sources")
        for ps in master.primary_sources:
            _heading(ps.title, level=2)
            _para(f"Type: {ps.source_type}  |  Attribution: {ps.attribution}")
            _para(ps.content_text)
            if ps.scaffolding_questions:
                _para("Questions:", bold=True)
                for sq in ps.scaffolding_questions:
                    p = doc.add_paragraph(style="List Bullet")
                    p.add_run(sq)
                    doc.add_paragraph(_BLANK)
            _embed_image(ps.image_spec)
            doc.add_paragraph("")

    # ── Stations (student directions only — no answer key) ────────────

    if master.stations:
        _heading("Learning Stations")
        for station in master.stations:
            _heading(station.title, level=2)
            _para(f"Task: {station.task}")
            _para("Directions:", bold=True)
            _para(station.student_directions)
            _para(_BLANK)
            doc.add_paragraph("")

    # ── Exit Ticket (stimulus + question, no answer) ──────────────────

    if master.exit_ticket:
        _heading("Exit Ticket")
        for i, sq in enumerate(master.exit_ticket, 1):
            _para(f"Q{i}: {sq.stimulus}", bold=True)
            if sq.stimulus_image_spec:
                _embed_image(sq.stimulus_image_spec)
            _para(sq.question)
            _para(_BLANK)
            doc.add_paragraph("")

    # ── Differentiation (visible to students for self-awareness) ──────
    # Per spec: differentiation section is included for student view too

    diff = master.differentiation
    _heading("Support Strategies")
    if diff.struggling:
        _para("If you need extra support:", bold=True)
        for item in diff.struggling:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)
    if diff.advanced:
        _para("Challenge extension:", bold=True)
        for item in diff.advanced:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)
    if diff.ell:
        _para("Language support:", bold=True)
        for item in diff.ell:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)
    doc.add_paragraph("")

    # ── Homework ──────────────────────────────────────────────────────

    if master.homework:
        _heading("Homework")
        _para(master.homework)

    # ── Save ──────────────────────────────────────────────────────────

    safe = safe_filename(master.title)
    out_path = output_dir / f"{safe}_student.docx"
    doc.save(str(out_path))
    logger.info("Student view saved to %s", out_path)
    return out_path
