"""Spaced repetition flashcard and quiz export for MasterContent.

Generates review materials from vocabulary, guided notes, and exit tickets:
- Anki-compatible TSV (importable as flashcard deck)
- Kahoot-compatible CSV (importable as quiz)
- Plain text study guide

No LLM calls — pure mechanical compilation from MasterContent fields.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.master_content import MasterContent

logger = logging.getLogger(__name__)


def compile_anki_tsv(master: MasterContent, output_dir: Path) -> Path:
    """Export vocabulary + guided notes as Anki-importable TSV.

    Format: front<TAB>back<TAB>tags
    Anki import: File → Import, set separator to Tab.

    Args:
        master: The MasterContent source object.
        output_dir: Directory for the .tsv file.

    Returns:
        Path to the generated .tsv file.
    """
    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cards: list[tuple[str, str, str]] = []
    tag_base = safe_filename(master.title).replace(" ", "_")

    # Vocabulary → flashcards
    for entry in master.vocabulary:
        front = f"{entry.term}"
        ctx = entry.context_sentence or ""
        back = f"{entry.definition}"
        if ctx:
            back += f"\n\nContext: {ctx}"
        cards.append((front, back, f"{tag_base}::vocabulary"))

    # Guided notes → flashcards (prompt = front, answer = back)
    for note in master.guided_notes:
        cards.append((note.prompt, note.answer, f"{tag_base}::guided_notes"))

    # Key points from direct instruction
    for section in master.direct_instruction:
        for kp in section.key_points:
            front = f"Key point from '{section.heading}':"
            cards.append((front, kp, f"{tag_base}::key_points"))

    safe = safe_filename(master.title)
    out_path = output_dir / f"{safe}_anki.tsv"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        for front, back, tags in cards:
            writer.writerow([front, back, tags])

    logger.info("Anki flashcards exported: %d cards to %s", len(cards), out_path)
    return out_path


def compile_kahoot_csv(master: MasterContent, output_dir: Path) -> Path:
    """Export exit ticket + vocabulary as Kahoot-importable CSV.

    Kahoot CSV format:
    Question, Answer 1, Answer 2, Answer 3, Answer 4, Time limit, Correct answer(s)

    We generate multiple-choice questions from vocabulary definitions
    and exit ticket content.

    Args:
        master: The MasterContent source object.
        output_dir: Directory for the .csv file.

    Returns:
        Path to the generated .csv file.
    """
    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[list[str]] = []

    # Vocabulary → "What does X mean?" questions
    vocab = list(master.vocabulary)
    for i, entry in enumerate(vocab):
        question = f"What does '{entry.term}' mean?"
        correct = entry.definition[:75]  # Kahoot answer limit

        # Build distractors from other vocab definitions
        distractors = []
        for j, other in enumerate(vocab):
            if j != i and len(distractors) < 3:
                distractors.append(other.definition[:75])
        # Pad with plausible generic wrong answers (never duplicate)
        _generic_wrong = [
            "None of the above",
            "A type of government system",
            "A geographic feature",
            "A cultural practice",
        ]
        for gw in _generic_wrong:
            if len(distractors) >= 3:
                break
            if gw not in distractors:
                distractors.append(gw)

        rows.append([
            question, correct,
            distractors[0], distractors[1], distractors[2],
            "30", "1",
        ])

    # Exit ticket questions (open-ended → converted to review)
    for et in master.exit_ticket:
        question = et.question[:120]
        answer = et.answer[:75] if et.answer else "See lesson materials"
        rows.append([
            question, answer,
            "I need to review this", "I'm not sure",
            "Ask the teacher", "20", "1",
        ])

    safe = safe_filename(master.title)
    out_path = output_dir / f"{safe}_kahoot.csv"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Kahoot header
        writer.writerow([
            "Question", "Answer 1", "Answer 2", "Answer 3",
            "Answer 4", "Time limit", "Correct answer(s)",
        ])
        for row in rows:
            writer.writerow(row)

    logger.info("Kahoot quiz exported: %d questions to %s", len(rows), out_path)
    return out_path


def compile_study_guide(master: MasterContent, output_dir: Path) -> Path:
    """Export a plain-text study guide for student review.

    Combines vocabulary, key points, and guided note answers into a
    printable review sheet.

    Args:
        master: The MasterContent source object.
        output_dir: Directory for the .txt file.

    Returns:
        Path to the generated .txt file.
    """
    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    buf = io.StringIO()
    buf.write(f"STUDY GUIDE: {master.title}\n")
    buf.write(f"Subject: {master.subject} | Grade: {master.grade_level}\n")
    buf.write(f"Objective: {master.objective}\n")
    buf.write("=" * 60 + "\n\n")

    # Vocabulary
    if master.vocabulary:
        buf.write("VOCABULARY\n")
        buf.write("-" * 40 + "\n")
        for entry in master.vocabulary:
            buf.write(f"• {entry.term}: {entry.definition}\n")
            buf.write(f"  Example: {entry.context_sentence}\n\n")

    # Key points
    buf.write("KEY POINTS\n")
    buf.write("-" * 40 + "\n")
    for section in master.direct_instruction:
        buf.write(f"\n{section.heading}:\n")
        for kp in section.key_points:
            buf.write(f"  • {kp}\n")

    # Guided notes (answers filled in)
    if master.guided_notes:
        buf.write("\n\nGUIDED NOTES (COMPLETED)\n")
        buf.write("-" * 40 + "\n")
        for note in master.guided_notes:
            filled = note.prompt.replace("________", f"**{note.answer}**")
            buf.write(f"• {filled}\n")

    # Review questions from exit ticket
    if master.exit_ticket:
        buf.write("\n\nREVIEW QUESTIONS\n")
        buf.write("-" * 40 + "\n")
        for i, et in enumerate(master.exit_ticket, 1):
            buf.write(f"\nQ{i}: {et.question}\n")
            buf.write(f"Answer: {et.answer}\n")

    safe = safe_filename(master.title)
    out_path = output_dir / f"{safe}_study_guide.txt"
    out_path.write_text(buf.getvalue(), encoding="utf-8")

    logger.info("Study guide exported to %s", out_path)
    return out_path
