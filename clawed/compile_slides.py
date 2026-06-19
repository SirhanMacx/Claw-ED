"""PPTX slide compiler for MasterContent.

Compiles a MasterContent object into a classroom-ready PowerPoint slide deck
that matches the teacher's real exemplar: a sparse, image-forward 16:9 deck
(~15–25 words per slide, NOT paragraphs) on the standard 10.0 x 5.625 in canvas
so it opens cleanly in Keynote/PowerPoint on macOS and imports losslessly into
Google Slides.

Slide order: title -> vocabulary -> instruction sections -> source analysis ->
station overview -> exit ticket.
No LLM calls — pure mechanical compilation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pptx.presentation import Presentation

    from clawed.master_content import MasterContent

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Canvas + grid geometry (standard 16:9, matches the teacher's exemplar deck)
# ═══════════════════════════════════════════════════════════════════════════
#
# The exemplar deck (AgeofExploration…The3Gs) is 10.0 x 5.625 in — the standard
# PowerPoint 16:9 size that imports losslessly into Google Slides and opens
# cleanly in Keynote. We use ONE fixed grid for every content slide so images
# land in the same aligned slot every time and never collide with text:
#
#   ┌──────────────────────────── 10.0 in ────────────────────────────┐
#   │ header bar (full width, 0.7 in)                                  │
#   ├──────────────────────────────────┬──────────────────────────────┤
#   │ TEXT PANEL                        │  IMAGE BOX                    │
#   │ left 0.3 .. 5.7 (width 5.4)       │  left 5.9, w 3.8, top 1.0,    │
#   │                                   │  h 4.3 (aspect-preserved)     │
#   └──────────────────────────────────┴──────────────────────────────┘
#
# Text content_width is hard-capped so its right edge (5.7) sits left of the
# image box left edge (5.9) — guaranteeing no overlap.

SLIDE_W_IN = 10.0
SLIDE_H_IN = 5.625
MARGIN_IN = 0.3
HEADER_H_IN = 0.7

# Right-hand image slot — the SAME box for instruction / source / exit slides.
IMG_BOX_LEFT_IN = 5.9
IMG_BOX_TOP_IN = 1.0
IMG_BOX_W_IN = 3.8
IMG_BOX_H_IN = 4.3

# Text panel when an image is present: 0.3 .. 5.7 (right edge < image box left).
TEXT_PANEL_W_IN = 5.4
# Text panel when no image: full width minus both margins.
FULL_TEXT_W_IN = SLIDE_W_IN - 2 * MARGIN_IN  # 9.4


def _short(text: str, words: int = 12) -> str:
    """Reduce free text to a short phrase of at most ``words`` whitespace tokens.

    This is the single density gate every slide-text call routes through, so the
    deck stays sparse and visual (the exemplar averages ~16 words/slide) instead
    of dumping mid-sentence paragraph slices. Strips trailing punctuation and
    appends an ellipsis only when the text was actually truncated.
    """
    if not text:
        return ""
    tokens = str(text).split()
    if not tokens:
        return ""
    truncated = len(tokens) > words
    kept = tokens[:words]
    out = " ".join(kept).rstrip(",;:.!?—-– ").strip()
    if truncated and out:
        out += "…"
    return out


def _first_sentence(text: str, words: int = 20) -> str:
    """Take the first sentence of ``text``, then cap it to ``words`` tokens.

    Produces a clean phrase boundary instead of a mid-sentence slice. Falls back
    to a plain ``_short`` cut when there is no sentence delimiter.
    """
    if not text:
        return ""
    first = str(text).replace("\n", " ").split(". ")[0]
    return _short(first, words=words)


# ═══════════════════════════════════════════════════════════════════════════
# Low-level shape helpers
# ═══════════════════════════════════════════════════════════════════════════


def _hex_to_rgb(hex_color: str) -> Any:
    """Convert a 6-char hex string to pptx RGBColor."""
    from pptx.dml.color import RGBColor

    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))  # type: ignore[no-untyped-call]  # python-pptx is untyped


def _add_slide(prs: Any, layout_idx: int = 6) -> Any:
    """Add a blank slide and return it."""
    layout = prs.slide_layouts[layout_idx]
    return prs.slides.add_slide(layout)


def _textbox(slide: Any, left: Any, top: Any, width: Any, height: Any, text: str,
             font_size: int = 18, bold: bool = False,
             hex_color: str = "222222", align_center: bool = False,
             italic: bool = False, word_wrap: bool = True) -> Any:
    """Add a textbox to a slide and return the shape."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Pt

    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = word_wrap
    p = tf.paragraphs[0]
    if align_center:
        p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = _hex_to_rgb(hex_color)
    run.font.name = "Calibri"
    return tb


def _bullet_textbox(slide: Any, left: Any, top: Any, width: Any, height: Any,
                    items: list[str], font_size: int = 18,
                    hex_color: str = "333333") -> Any:
    """Add a textbox with one paragraph per bullet item."""
    from pptx.util import Pt

    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True

    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        run = p.add_run()
        run.text = f"•  {item}"
        run.font.size = Pt(font_size)
        run.font.color.rgb = _hex_to_rgb(hex_color)
        run.font.name = "Calibri"

    return tb


def _embed_image(slide: Any, image_spec: str, images: dict[str, Path],
                 box_left: Any, box_top: Any, box_w: Any, box_h: Any) -> bool:
    """Embed a pre-fetched image, CONTAINED in the given box, aspect preserved.

    The image is scaled with ``min(box_w/iw, box_h/ih)`` so it always fits the
    box without stretching, then centered inside the box. We pass ONLY the
    scaled draw size to ``add_picture`` (never the raw box dimensions), which is
    what previously stretched images. If Pillow can't read the native size, we
    fall back to fitting by box width (still aspect-correct via add_picture's
    single-dimension mode).

    All coordinates are in EMU. Returns True if an image was embedded.
    """
    if not image_spec:
        return False
    path = images.get(image_spec)
    if not (path and Path(path).exists()):
        return False

    try:
        iw = ih = None
        try:
            from PIL import Image  # type: ignore[import-untyped]

            with Image.open(str(path)) as im:
                iw, ih = im.size
        except Exception as exc:  # noqa: BLE001 — Pillow optional / unreadable file
            logger.debug("Could not read native size for %r: %s", image_spec, exc)

        if iw and ih:
            scale = min(box_w / iw, box_h / ih)
            draw_w = int(iw * scale)
            draw_h = int(ih * scale)
            left = int(box_left + (box_w - draw_w) / 2)
            top = int(box_top + (box_h - draw_h) / 2)
            slide.shapes.add_picture(str(path), left, top, width=draw_w, height=draw_h)
        else:
            # No native size — let pptx preserve aspect from the file by fixing
            # only the width, anchored at the box's top-left.
            slide.shapes.add_picture(str(path), int(box_left), int(box_top), width=int(box_w))
        return True
    except Exception as exc:  # noqa: BLE001 — image embed is best-effort
        logger.debug("Could not embed slide image %r: %s", image_spec, exc)
    return False


def _header_bar(slide: Any, prs_width: Any, text: str, hex_color: str) -> None:
    """Add a colored header bar with the section title at the top of a slide."""
    from pptx.util import Inches

    rect = slide.shapes.add_shape(1, Inches(0), Inches(0), prs_width, Inches(HEADER_H_IN))
    rect.fill.solid()
    rect.fill.fore_color.rgb = _hex_to_rgb(hex_color)
    rect.line.fill.background()
    _textbox(
        slide,
        left=Inches(0.25), top=Inches(0.07),
        width=prs_width - Inches(0.5), height=Inches(HEADER_H_IN - 0.1),
        text=_short(text, words=10),
        font_size=22, bold=True,
        hex_color="FFFFFF",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Per-slide-type builders
# ═══════════════════════════════════════════════════════════════════════════


# Palette constants
_C_TITLE_BG = "1F3864"
_C_SECTION_BG = "2E75B6"
_C_WHITE = "FFFFFF"
_C_DARK = "222222"
_C_ACCENT = "BDD7EE"


def _build_title_slide(prs: Presentation, master: MasterContent) -> None:
    """Slide 1: Title with subject, grade, and objective."""
    from pptx.util import Inches

    W = prs.slide_width  # noqa: N806
    slide = _add_slide(prs)

    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = _hex_to_rgb(_C_TITLE_BG)

    _textbox(
        slide,
        left=Inches(0.6), top=Inches(1.5),
        width=W - Inches(1.2), height=Inches(1.4),
        text=master.title,
        font_size=36, bold=True,
        hex_color=_C_WHITE, align_center=True,
    )
    meta = f"{master.subject}  |  Grade {master.grade_level}  |  {master.duration_minutes} min"
    _textbox(
        slide,
        left=Inches(0.6), top=Inches(3.0),
        width=W - Inches(1.2), height=Inches(0.5),
        text=meta,
        font_size=16, bold=False,
        hex_color=_C_ACCENT, align_center=True,
    )
    _textbox(
        slide,
        left=Inches(0.6), top=Inches(3.7),
        width=W - Inches(1.2), height=Inches(1.2),
        text=f"Objective: {_short(master.objective, words=10)}",
        font_size=15,
        hex_color=_C_WHITE, align_center=True,
    )


def _build_vocabulary_slides(prs: Presentation, master: MasterContent) -> None:
    """Vocabulary slides (up to 5 terms per slide). Definitions stay sparse."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    if not master.vocabulary:
        return

    W = prs.slide_width  # noqa: N806
    TERMS_PER_SLIDE = 3  # noqa: N806

    vocab_chunks = [
        master.vocabulary[i: i + TERMS_PER_SLIDE]
        for i in range(0, len(master.vocabulary), TERMS_PER_SLIDE)
    ]
    for chunk_idx, chunk in enumerate(vocab_chunks):
        slide = _add_slide(prs)
        heading_label = "Vocabulary" if len(vocab_chunks) == 1 else f"Vocabulary ({chunk_idx + 1})"

        # Section header bar (filled rect, then label on top).
        rect = slide.shapes.add_shape(1, Inches(0), Inches(0), W, Inches(HEADER_H_IN))
        rect.fill.solid()
        rect.fill.fore_color.rgb = _hex_to_rgb(_C_SECTION_BG)
        rect.line.fill.background()
        bar = slide.shapes.add_textbox(Inches(0.25), Inches(0.07), W - Inches(0.5), Inches(HEADER_H_IN - 0.1))
        bar_tf = bar.text_frame
        bar_tf.word_wrap = False
        bar_p = bar_tf.paragraphs[0]
        bar_p.alignment = PP_ALIGN.LEFT
        bar_run = bar_p.add_run()
        bar_run.text = heading_label
        bar_run.font.size = Pt(22)
        bar_run.font.bold = True
        bar_run.font.color.rgb = _hex_to_rgb(_C_WHITE)
        bar_run.font.name = "Calibri"

        # Term entries — term on the left, a SHORT definition on the right.
        top_offset: Any = Inches(0.95)
        row_height = Inches(0.85)
        for entry in chunk:
            _textbox(
                slide,
                left=Inches(0.3), top=top_offset,
                width=Inches(2.7), height=row_height,
                text=_short(entry.term, words=4),
                font_size=16, bold=True,
                hex_color=_C_DARK,
            )
            _textbox(
                slide,
                left=Inches(3.1), top=top_offset,
                width=Inches(6.6), height=row_height,
                text=_short(entry.definition, words=4),
                font_size=14,
                hex_color=_C_DARK,
            )
            top_offset += row_height + Inches(0.05)


def _build_instruction_slides(prs: Presentation, master: MasterContent,
                              images: dict[str, Path]) -> None:
    """One sparse slide per InstructionSection: ≤3 short bullets + one visual."""
    from pptx.util import Inches

    W = prs.slide_width  # noqa: N806

    for section in master.direct_instruction:
        slide = _add_slide(prs)
        _header_bar(slide, W, section.heading, _C_SECTION_BG)

        has_image = bool(section.image_spec and section.image_spec in images)
        content_w = Inches(TEXT_PANEL_W_IN) if has_image else Inches(FULL_TEXT_W_IN)
        content_left = Inches(MARGIN_IN)

        # Build ≤3 short bullets. Prefer key_points; otherwise fall back to the
        # short slide_summary, then a first-sentence slice of content. Each
        # bullet is capped tight so the slide stays near the exemplar density.
        bullets = [_short(kp, words=6) for kp in section.key_points if kp.strip()][:2]
        if not bullets:
            summary = getattr(section, "slide_summary", "") or ""
            phrase = _short(summary, words=14) if summary.strip() else _first_sentence(section.content, words=14)
            if phrase:
                bullets = [phrase]

        if bullets:
            _bullet_textbox(
                slide,
                left=content_left, top=Inches(1.1),
                width=content_w, height=Inches(3.6),
                items=bullets,
                font_size=18,
                hex_color=_C_DARK,
            )

        if has_image:
            _embed_image(
                slide, section.image_spec, images,
                box_left=Inches(IMG_BOX_LEFT_IN), box_top=Inches(IMG_BOX_TOP_IN),
                box_w=Inches(IMG_BOX_W_IN), box_h=Inches(IMG_BOX_H_IN),
            )


def _build_source_slides(prs: Presentation, master: MasterContent,
                         images: dict[str, Path]) -> None:
    """One sparse slide per primary source: attribution + a short excerpt phrase."""
    from pptx.util import Inches

    W = prs.slide_width  # noqa: N806

    for ps in master.primary_sources:
        slide = _add_slide(prs)
        _header_bar(slide, W, f"Source: {ps.title}", "C55A11")

        has_image = bool(ps.image_spec and ps.image_spec in images)
        text_w = Inches(TEXT_PANEL_W_IN) if has_image else Inches(FULL_TEXT_W_IN)

        _textbox(
            slide,
            left=Inches(MARGIN_IN), top=Inches(0.9),
            width=text_w, height=Inches(0.4),
            text=_short(f"{ps.source_type.replace('_', ' ').title()}  |  {ps.attribution}", words=7),
            font_size=12, italic=True,
            hex_color="666666",
        )

        excerpt = getattr(ps, "slide_excerpt", "") or ""
        excerpt = _short(excerpt, words=12) if excerpt.strip() else _first_sentence(ps.content_text, words=12)
        if excerpt:
            _textbox(
                slide,
                left=Inches(MARGIN_IN), top=Inches(1.5),
                width=text_w, height=Inches(2.8),
                text=f'"{excerpt}"',
                font_size=16, italic=True,
                hex_color=_C_DARK,
            )

        if has_image:
            _embed_image(
                slide, ps.image_spec, images,
                box_left=Inches(IMG_BOX_LEFT_IN), box_top=Inches(IMG_BOX_TOP_IN),
                box_w=Inches(IMG_BOX_W_IN), box_h=Inches(IMG_BOX_H_IN),
            )


def _build_station_slide(prs: Presentation, master: MasterContent) -> None:
    """Station overview slide (if stations exist) — short titles + directions."""
    from pptx.util import Inches

    if not master.stations:
        return

    W = prs.slide_width  # noqa: N806
    slide = _add_slide(prs)
    _header_bar(slide, W, "Learning Stations", "375623")

    top_offset = Inches(1.0)
    usable = SLIDE_W_IN - 2 * MARGIN_IN
    n = max(len(master.stations), 1)
    col_w = Inches(usable / n)
    for i, station in enumerate(master.stations):
        left = Inches(MARGIN_IN + (usable / n) * i)
        _textbox(
            slide,
            left=left,
            top=top_offset,
            width=col_w - Inches(0.1),
            height=Inches(0.8),
            text=_short(station.title, words=8),
            font_size=16, bold=True,
            hex_color=_C_DARK,
        )
        _textbox(
            slide,
            left=left,
            top=top_offset + Inches(0.9),
            width=col_w - Inches(0.1),
            height=Inches(3.4),
            text=_short(station.student_directions, words=18),
            font_size=14,
            hex_color="444444",
        )


def _build_exit_ticket_slide(prs: Presentation, master: MasterContent,
                             images: dict[str, Path]) -> None:
    """Exit ticket — ONE question per slide, sparse, questions only (no answers)."""
    from pptx.util import Inches

    if not master.exit_ticket:
        return

    W = prs.slide_width  # noqa: N806

    for i, sq in enumerate(master.exit_ticket, 1):
        slide = _add_slide(prs)
        _header_bar(slide, W, "Exit Ticket", "7030A0")

        has_image = bool(sq.stimulus_image_spec and sq.stimulus_image_spec in images)
        text_w = Inches(TEXT_PANEL_W_IN) if has_image else Inches(FULL_TEXT_W_IN)

        stim = getattr(sq, "slide_stimulus", "") or ""
        stim = _short(stim, words=15) if stim.strip() else _short(sq.stimulus, words=15)
        if stim:
            _textbox(
                slide,
                left=Inches(MARGIN_IN), top=Inches(1.1),
                width=text_w, height=Inches(1.4),
                text=stim,
                font_size=14, italic=True,
                hex_color="444444",
            )
        _textbox(
            slide,
            left=Inches(MARGIN_IN), top=Inches(2.6),
            width=text_w, height=Inches(1.8),
            text=f"Q{i}: {_short(sq.question, words=20)}",
            font_size=18, bold=True,
            hex_color=_C_DARK,
        )
        if has_image:
            _embed_image(
                slide, sq.stimulus_image_spec, images,
                box_left=Inches(IMG_BOX_LEFT_IN), box_top=Inches(IMG_BOX_TOP_IN),
                box_w=Inches(IMG_BOX_W_IN), box_h=Inches(IMG_BOX_H_IN),
            )


def _build_speaker_notes(prs: Presentation, master: MasterContent) -> None:
    """Attach misconceptions/formative checks as speaker notes."""
    notes_parts: list[str] = []
    if getattr(master, "misconceptions", None):
        notes_parts.append("MISCONCEPTIONS TO WATCH FOR:")
        for m in master.misconceptions:
            notes_parts.append(f"  - {m}")
    if getattr(master, "formative_checks", None):
        notes_parts.append("\nMID-LESSON CHECKS:")
        for fc in master.formative_checks:
            notes_parts.append(f"  - {fc}")
    if getattr(master, "prerequisite_skills", None):
        notes_parts.append("\nPREREQUISITES:")
        for ps in master.prerequisite_skills:
            notes_parts.append(f"  - {ps}")

    if notes_parts and len(prs.slides) > 1:
        try:
            target_slide = prs.slides[1]
            if not target_slide.has_notes_slide:
                target_slide.notes_slide  # creates notes slide
            notes_tf = target_slide.notes_slide.notes_text_frame
            notes_tf.text = "\n".join(notes_parts)
        except Exception as exc:
            # Notes are optional enhancement, never block export
            logger.debug("Could not add speaker notes: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════
# Public API (unchanged signature)
# ═══════════════════════════════════════════════════════════════════════════


async def compile_slides(
    master: MasterContent,
    images: dict[str, Path],
    output_dir: Path,
) -> Path:
    """Compile a classroom-ready PPTX from a MasterContent object.

    The deck is a sparse, image-forward 16:9 presentation (~15–25 words/slide)
    on the standard 10.0 x 5.625 in canvas — opens cleanly on macOS and imports
    losslessly into Google Slides.

    Slide order:
        1. Title slide (title, subject, grade, objective)
        2. Vocabulary slide(s) (up to 5 terms per slide)
        3. One slide per InstructionSection (heading, ≤3 short bullets, image)
        4. Source analysis slides (one per primary source)
        5. Station overview (if stations exist)
        6. Exit ticket slides (one question per slide, no answers)

    Args:
        master: The MasterContent source-of-truth object.
        images: Mapping of image_spec strings to local file Paths.
        output_dir: Directory where the .pptx file will be written.

    Returns:
        Path to the generated .pptx file.
    """
    from pptx import Presentation
    from pptx.util import Inches

    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W_IN)
    prs.slide_height = Inches(SLIDE_H_IN)

    # Build all slide types
    _build_title_slide(prs, master)
    _build_vocabulary_slides(prs, master)
    _build_instruction_slides(prs, master, images)
    _build_source_slides(prs, master, images)
    _build_station_slide(prs, master)
    _build_exit_ticket_slide(prs, master, images)
    _build_speaker_notes(prs, master)

    # Save
    safe = safe_filename(master.title)
    out_path = output_dir / f"{safe}_slides.pptx"
    prs.save(str(out_path))

    # Post-save smoke check: the deck must be a standard 16:9 canvas so it opens
    # cleanly on macOS Keynote/PowerPoint and imports losslessly into Google
    # Slides. A non-standard canvas was the original macOS/Slides failure mode.
    from pptx.util import Emu
    w_in = round(Emu(int(prs.slide_width)).inches, 3)
    h_in = round(Emu(int(prs.slide_height)).inches, 3)
    if (w_in, h_in) != (SLIDE_W_IN, SLIDE_H_IN):
        logger.warning(
            "Slide deck canvas is %sx%s in, expected %sx%s — Slides/macOS import may scale.",
            w_in, h_in, SLIDE_W_IN, SLIDE_H_IN,
        )

    logger.info("Slides saved to %s (%d slides, %sx%s in)", out_path, len(prs.slides._sldIdLst), w_in, h_in)
    return out_path
