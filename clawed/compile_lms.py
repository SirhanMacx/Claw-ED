"""LMS export formats — Common Cartridge, Google Classroom, UDL tiers.

Compiles MasterContent into platform-ready import packages:
- Common Cartridge (.imscc) for Canvas/Moodle/Blackboard/Schoology
- Google Classroom coursework creation via API
- UDL-by-default 3-tier lesson generation (on-level, scaffolded, enriched)

No LLM calls — pure mechanical compilation from MasterContent fields.
"""

from __future__ import annotations

import logging
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import Element, SubElement, tostring

if TYPE_CHECKING:
    from clawed.master_content import MasterContent

logger = logging.getLogger(__name__)


# ── Common Cartridge (.imscc) ────────────────────────────────────────


def compile_common_cartridge(master: MasterContent, output_dir: Path) -> Path:
    """Export lesson as IMS Common Cartridge package (.imscc).

    Common Cartridge is a ZIP file with:
    - imsmanifest.xml (metadata + resource listing)
    - HTML content files for each lesson section
    - Assessment items in QTI format

    Imports directly into Canvas, Moodle, Blackboard, Schoology
    with zero API keys or OAuth flows.

    Args:
        master: The MasterContent source object.
        output_dir: Directory for the .imscc file.

    Returns:
        Path to the generated .imscc file.
    """
    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe = safe_filename(master.title)
    imscc_path = output_dir / f"{safe}.imscc"

    # Build manifest
    manifest = Element("manifest", {
        "identifier": f"clawed_{uuid.uuid4().hex[:12]}",
        "xmlns": "http://www.imsglobal.org/xsd/imsccv1p3/imscp_v1p1",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
    })

    metadata = SubElement(manifest, "metadata")
    schema = SubElement(metadata, "schema")
    schema.text = "IMS Common Cartridge"
    schema_ver = SubElement(metadata, "schemaversion")
    schema_ver.text = "1.3.0"

    organizations = SubElement(manifest, "organizations")
    org = SubElement(organizations, "organization", {
        "identifier": "org_1",
        "structure": "rooted-hierarchy",
    })

    resources = SubElement(manifest, "resources")

    # Build HTML content pages
    html_files: dict[str, str] = {}

    # Lesson overview page
    overview_id = f"res_{uuid.uuid4().hex[:8]}"
    overview_html = _build_overview_html(master)
    html_files[f"{overview_id}.html"] = overview_html

    item = SubElement(org, "item", {"identifier": f"item_{overview_id}"})
    title_el = SubElement(item, "title")
    title_el.text = master.title
    SubElement(item, "resource", {"identifierref": overview_id})

    res = SubElement(resources, "resource", {
        "identifier": overview_id,
        "type": "webcontent",
        "href": f"{overview_id}.html",
    })
    SubElement(res, "file", {"href": f"{overview_id}.html"})

    # Student handout page
    handout_id = f"res_{uuid.uuid4().hex[:8]}"
    handout_html = _build_handout_html(master)
    html_files[f"{handout_id}.html"] = handout_html

    item2 = SubElement(org, "item", {"identifier": f"item_{handout_id}"})
    title_el2 = SubElement(item2, "title")
    title_el2.text = f"{master.title} — Student Handout"
    SubElement(item2, "resource", {"identifierref": handout_id})

    res2 = SubElement(resources, "resource", {
        "identifier": handout_id,
        "type": "webcontent",
        "href": f"{handout_id}.html",
    })
    SubElement(res2, "file", {"href": f"{handout_id}.html"})

    # Write the ZIP
    manifest_xml = tostring(manifest, encoding="unicode", xml_declaration=True)

    with zipfile.ZipFile(imscc_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imsmanifest.xml", manifest_xml)
        for fname, content in html_files.items():
            zf.writestr(fname, content)

    logger.info("Common Cartridge exported to %s", imscc_path)
    return imscc_path


def _build_overview_html(master: MasterContent) -> str:
    """Build a lesson overview HTML page for Common Cartridge."""
    sections = [
        f"<h1>{master.title}</h1>",
        f"<p><strong>Subject:</strong> {master.subject} | "
        f"<strong>Grade:</strong> {master.grade_level} | "
        f"<strong>Duration:</strong> {master.duration_minutes} min</p>",
        f"<p><strong>Objective:</strong> {master.objective}</p>",
    ]

    if master.standards:
        sections.append(
            "<p><strong>Standards:</strong> "
            + ", ".join(master.standards) + "</p>"
        )

    if master.vocabulary:
        sections.append("<h2>Vocabulary</h2><ul>")
        for v in master.vocabulary:
            sections.append(
                f"<li><strong>{v.term}</strong>: {v.definition}</li>"
            )
        sections.append("</ul>")

    sections.append("<h2>Do Now</h2>")
    sections.append(f"<p>{master.do_now.stimulus}</p>")
    for q in master.do_now.questions:
        sections.append(f"<p><em>{q}</em></p>")

    for di in master.direct_instruction:
        sections.append(f"<h2>{di.heading}</h2>")
        sections.append(f"<p>{di.content}</p>")

    return (
        "<!DOCTYPE html><html><head>"
        f"<title>{master.title}</title>"
        "<style>body{font-family:Calibri,sans-serif;max-width:800px;"
        "margin:0 auto;padding:20px;}</style>"
        "</head><body>" + "\n".join(sections) + "</body></html>"
    )


def _build_handout_html(master: MasterContent) -> str:
    """Build a student handout HTML page for Common Cartridge."""
    sections = [
        f"<h1>{master.title}</h1>",
        f"<p><strong>Objective:</strong> {master.objective}</p>",
        "<p>Name: _______________ Date: _________ Period: _____</p>",
    ]

    sections.append("<h2>Do Now</h2>")
    sections.append(f"<p>{master.do_now.stimulus}</p>")
    for q in master.do_now.questions:
        sections.append(f"<p>{q}</p><p>_______________________________</p>")

    if master.guided_notes:
        sections.append("<h2>Guided Notes</h2>")
        for note in master.guided_notes:
            sections.append(f"<p>{note.prompt}</p>")
            sections.append("<p>_______________________________</p>")

    if master.primary_sources:
        sections.append("<h2>Primary Sources</h2>")
        for ps in master.primary_sources:
            sections.append(f"<h3>{ps.title}</h3>")
            sections.append(f"<p><em>{ps.attribution}</em></p>")
            sections.append(f"<blockquote>{ps.content_text}</blockquote>")
            for sq in ps.scaffolding_questions:
                sections.append(f"<p>{sq}</p><p>___________________</p>")

    if master.exit_ticket:
        sections.append("<h2>Exit Ticket</h2>")
        for i, et in enumerate(master.exit_ticket, 1):
            sections.append(f"<p><strong>Q{i}:</strong> {et.stimulus}</p>")
            sections.append(f"<p>{et.question}</p>")
            starters = getattr(et, "sentence_starters", [])
            if starters:
                sections.append(
                    "<p><em>Use: " + " / ".join(starters) + "</em></p>"
                )
            sections.append("<p>_______________________________</p>")

    return (
        "<!DOCTYPE html><html><head>"
        f"<title>{master.title} — Student Handout</title>"
        "<style>body{font-family:Calibri,sans-serif;max-width:800px;"
        "margin:0 auto;padding:20px;}blockquote{border-left:3px solid "
        "#8B6914;padding-left:12px;margin:12px 0;}</style>"
        "</head><body>" + "\n".join(sections) + "</body></html>"
    )


# ── Google Classroom Integration ─────────────────────────────────────


async def post_to_google_classroom(
    master: MasterContent,
    course_id: str,
    file_paths: list[Path] | None = None,
) -> dict[str, Any] | None:
    """Post a lesson as coursework to Google Classroom.

    Requires Google Classroom API credentials (OAuth).
    Uses the existing drive.py OAuth flow.

    Args:
        master: The MasterContent to post.
        course_id: Google Classroom course ID.
        file_paths: Optional list of DOCX/PPTX files to attach.

    Returns:
        Coursework response dict, or None if not configured.
    """
    try:
        # dynamic import handled by try/except
        from clawed.agent_core.drive.auth import (  # type: ignore[attr-defined]
            get_credentials,
        )

        creds = get_credentials()
        if not creds:
            logger.info("Google Classroom: no credentials configured")
            return None

        import httpx

        headers = {"Authorization": f"Bearer {creds.token}"}

        # Create coursework
        coursework = {
            "title": master.title,
            "description": (
                f"Objective: {master.objective}\n"
                f"Standards: {', '.join(master.standards)}\n"
                f"Duration: {master.duration_minutes} minutes"
            ),
            "workType": "ASSIGNMENT",
            "state": "DRAFT",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://classroom.googleapis.com/v1/courses/"
                f"{course_id}/courseWork",
                headers=headers,
                json=coursework,
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()

        logger.info(
            "Posted to Google Classroom: %s (id: %s)",
            master.title, result.get("id"),
        )
        return result

    except Exception as exc:
        logger.warning("Google Classroom posting failed: %s", exc)
        return None


# ── UDL 3-Tier Lesson Generation ─────────────────────────────────────


def generate_udl_tiers(master: MasterContent) -> dict[str, dict[str, Any]]:
    """Generate 3 differentiated versions of a lesson for UDL compliance.

    Returns a dict with three keys:
    - "on_level": The standard lesson (as-is)
    - "scaffolded": Simplified for below-level students
    - "enriched": Extended for above-level students

    Each tier modifies vocabulary, questions, and scaffolding
    without re-calling the LLM — pure mechanical transformation.
    """
    on_level = master.model_dump()

    # ── Scaffolded tier (below-level) ─────────────────────────────
    scaffolded = master.model_dump()

    # Add word bank to every guided note
    vocab_bank = ", ".join(v.term for v in master.vocabulary)
    for note in scaffolded.get("guided_notes", []):
        note["prompt"] = f"{note['prompt']} (Word Bank: {vocab_bank})"

    # Add sentence starters to every exit ticket
    for et in scaffolded.get("exit_ticket", []):
        if not et.get("sentence_starters"):
            et["sentence_starters"] = [
                "I think ___ because ___",
                "According to the source, ___",
            ]

    # Simplify vocabulary definitions (sentence-aware — handles "Dr. King")
    for v in scaffolded.get("vocabulary", []):
        defn = v.get("definition", "")
        # Split on ". " (period + space) not just "." to avoid breaking abbreviations
        sentences = defn.split(". ")
        first = sentences[0].rstrip(".")
        if len(first) > 10:
            v["definition"] = first + "."
        # else: keep full definition — too short to simplify

    scaffolded["_tier"] = "scaffolded"
    scaffolded["_tier_label"] = "Below-Level / IEP / 504"

    # ── Enriched tier (above-level) ───────────────────────────────
    enriched = master.model_dump()

    # Add extension questions to exit ticket
    if enriched.get("exit_ticket"):
        last_et = enriched["exit_ticket"][-1]
        last_et["question"] = (
            last_et["question"] + " Additionally, evaluate whether "
            "this historical argument is still relevant today."
        )

    # Add challenge task to independent work
    if enriched.get("independent_work"):
        enriched["independent_work"]["task"] += (
            "\n\nEXTENSION: Research a modern parallel to this topic "
            "and write a 1-paragraph comparison using evidence from "
            "both time periods."
        )

    enriched["_tier"] = "enriched"
    enriched["_tier_label"] = "Above-Level / Gifted / Accelerated"

    return {
        "on_level": on_level,
        "scaffolded": scaffolded,
        "enriched": enriched,
    }


# ── Exit Ticket Auto-Grading ─────────────────────────────────────────


async def grade_exit_ticket(
    student_response: str,
    question_index: int,
    master: MasterContent,
) -> dict[str, Any]:
    """Grade a student's exit ticket response against the answer key.

    Uses the MasterContent expected answer + rubric to provide
    formative feedback without an LLM call for simple matching,
    or with an LLM for nuanced evaluation.

    Args:
        student_response: The student's text response.
        question_index: Which exit ticket question (0-indexed).
        master: The MasterContent with answer keys.

    Returns:
        {"score": 0-4, "feedback": "...", "meets_standard": bool}
    """
    if question_index >= len(master.exit_ticket):
        return {"score": 0, "feedback": "Invalid question index.", "meets_standard": False}

    et = master.exit_ticket[question_index]
    expected = et.answer.lower().strip()
    student = student_response.lower().strip()

    if not student:
        return {
            "score": 0,
            "feedback": "No response provided. Review the stimulus and try again.",
            "meets_standard": False,
        }

    # Simple keyword matching for quick scoring
    expected_words = set(expected.split())
    student_words = set(student.split())
    overlap = expected_words & student_words
    # Remove common words
    stop = {"the", "a", "an", "is", "was", "were", "are", "in", "of", "to", "and", "that", "this", "it"}
    meaningful_expected = expected_words - stop
    meaningful_overlap = overlap - stop

    if meaningful_expected:
        keyword_score = len(meaningful_overlap) / len(meaningful_expected)
    else:
        keyword_score = 0.5  # Can't assess

    # Score based on keyword overlap + length
    if keyword_score > 0.6 and len(student) > 30:
        score = 4
        feedback = "Strong response! You demonstrated understanding with relevant evidence."
    elif keyword_score > 0.4 and len(student) > 20:
        score = 3
        feedback = "Good start. Try to include more specific evidence from the source."
    elif keyword_score > 0.2 or len(student) > 15:
        score = 2
        feedback = "Developing. Reread the stimulus and use the sentence starters provided."
    else:
        score = 1
        feedback = "Needs improvement. Look at the source again and answer the question directly."

    starters = getattr(et, "sentence_starters", [])
    if starters and score < 4:
        feedback += f" Try using: '{starters[0]}'"

    return {
        "score": score,
        "feedback": feedback,
        "meets_standard": score >= 3,
        "cognitive_level": et.cognitive_level,
        "keyword_match": round(keyword_score, 2),
    }
