"""Generation commands — main module and entry point.

Core command kept here: lesson.

Split modules (imported at bottom):
  - generate_ingest.py     — ingest, transcribe
  - generate_diff.py       — differentiate (IEP / 504 / tiered)
  - generate_comms.py      — sub-packet, parent-note
  - generate_standards.py  — gap-analyze
  - generate_unit.py       — unit, year-map, pacing, full, course
  - generate_assessment.py — materials, assess, rubric, score, improve, evaluate
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

from clawed._json_output import run_json_command
from clawed.commands._helpers import (
    _safe_progress,
    check_api_key_or_exit,
    console,
    friendly_error,
    load_persona_or_exit,
)
from clawed.commands._helpers import output_dir as _output_dir
from clawed.commands._helpers import run_async as _run_async
from clawed.models import AppConfig

logger = logging.getLogger(__name__)

generate_app = typer.Typer()


# ── Lesson generation ────────────────────────────────────────────────────


def _lesson_json(*, topic, grade, subject, fmt, unit_file=None, lesson_number=1):
    """Run lesson generation and return structured result for JSON output."""
    from clawed.export_markdown import export_lesson
    from clawed.lesson import generate_lesson, save_lesson
    from clawed.models import LessonBrief, UnitPlan

    persona = load_persona_or_exit()

    if unit_file:
        from clawed.planner import load_unit
        unit_plan = load_unit(Path(unit_file))
    else:
        unit_plan = UnitPlan(
            title=f"{topic} Lesson",
            subject=subject,
            grade_level=grade,
            topic=topic,
            duration_weeks=1,
            overview=f"A standalone lesson on {topic} for grade {grade} {subject}.",
            essential_questions=[f"What are the key concepts of {topic}?"],
            daily_lessons=[
                LessonBrief(
                    lesson_number=1,
                    topic=topic,
                    description=f"Explore the key concepts, events, and significance of {topic}.",
                    lesson_type="direct_instruction",
                )
            ],
        )
        lesson_number = 1

    daily = _run_async(
        generate_lesson(
            lesson_number=lesson_number,
            unit=unit_plan,
            persona=persona,
            include_homework=True,
        )
    )

    out_dir = _output_dir()
    json_path = save_lesson(daily, out_dir)
    export_path = export_lesson(daily, out_dir, fmt=fmt)

    files = [str(json_path)]
    if export_path:
        files.append(str(export_path))

    return {
        "data": daily.model_dump() if hasattr(daily, "model_dump") else None,
        "files": files,
    }


@generate_app.command()
def lesson(
    topic: str = typer.Argument(..., help="Lesson topic (e.g. 'The American Revolution')"),
    unit_file: Optional[str] = typer.Option(
        None, "--unit-file", "-u", help="Path to unit plan JSON (omit for standalone lesson)"
    ),
    lesson_num: int = typer.Option(
        1, "--lesson-num", "-n", help="Lesson number in unit"
    ),
    grade: str = typer.Option(
        "8", "--grade", "-g", help="Grade level (for standalone lesson)"
    ),
    subject: Optional[str] = typer.Option(
        None, "--subject", "-s", help="Subject area (reads from your profile if not set)"
    ),
    homework: bool = typer.Option(
        True, "--homework/--no-homework", help="Include homework"
    ),
    multi_agent: bool = typer.Option(
        True, "--multi-agent/--single-agent",
        help="Multi-agent pipeline (researcher→writer→reviewer) for higher quality. Use --single-agent for speed.",
    ),
    game: bool = typer.Option(
        False, "--game/--no-game",
        help="Also generate an interactive HTML learning game",
    ),
    narrate: bool = typer.Option(
        False, "--narrate",
        help="Generate voice narration MP3 files for slides",
    ),
    fmt: str = typer.Option(
        "handout", "--format", "-f",
        help="Export: handout, docx, pptx, pdf, markdown",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Generate a detailed daily lesson plan.

    \b
    Standalone mode (no unit plan needed):
        clawed lesson "The American Revolution" --grade 8 --subject "social studies"

    Multi-agent mode (higher quality, 3x slower):
        clawed lesson "The Missouri Compromise" -g 8 --multi-agent

    From a unit plan:
        clawed lesson "Photosynthesis" --unit-file output/unit_photosynthesis.json -n 1
    """
    # Resolve subject from teacher profile if not provided
    if subject is None:
        from clawed.commands._helpers import get_default_subject
        subject = get_default_subject()

    if json_output:
        run_json_command(
            "gen.lesson",
            _lesson_json,
            topic=topic,
            grade=grade,
            subject=subject,
            fmt=fmt,
            unit_file=unit_file,
            lesson_number=lesson_num,
        )
        return

    check_api_key_or_exit()

    from clawed.export_markdown import export_lesson
    from clawed.lesson import generate_lesson, save_lesson

    persona = load_persona_or_exit()

    if unit_file:
        from clawed.planner import load_unit
        unit_plan = load_unit(Path(unit_file))
    else:
        # Standalone mode: create a minimal unit plan from the topic
        from clawed.models import LessonBrief, UnitPlan
        unit_plan = UnitPlan(
            title=f"{topic} Lesson",
            subject=subject,
            grade_level=grade,
            topic=topic,
            duration_weeks=1,
            overview=f"A standalone lesson on {topic} for grade {grade} {subject}.",
            essential_questions=[f"What are the key concepts of {topic}?"],
            daily_lessons=[
                LessonBrief(
                    lesson_number=1,
                    topic=topic,
                    description=f"Explore the key concepts, events, and significance of {topic}.",
                    lesson_type="direct_instruction",
                )
            ],
        )
        lesson_num = 1

    # ── Search for teacher's existing materials (assets + KB) ──────
    kb_prompt_section = ""

    # Asset-level search (files, YouTube links, images)
    try:
        from clawed.asset_registry import AssetRegistry
        registry = AssetRegistry()
        assets = registry.search_assets("default", topic, top_k=5)
        yt_links = registry.get_youtube_links("default", topic, top_k=3)
        if assets or yt_links:
            asset_summary = registry.format_asset_summary(assets, yt_links)
            kb_prompt_section = asset_summary
            # Show teacher what was found
            for a in assets:
                type_label = a["material_type"].replace("_", " ").title()
                console.print(f"[dim]Found [{type_label}] \"{a['title']}\"[/dim]")
            for link in yt_links:
                console.print(f"[dim]Found YouTube: {link['url']}[/dim]")
    except Exception:
        pass

    # KB chunk-level search (supplements asset search)
    try:
        from clawed.agent_core.memory.curriculum_kb import CurriculumKB
        kb = CurriculumKB()
        kb_results = kb.search("default", topic, top_k=3)
        if kb_results:
            kb_parts = [r for r in kb_results if r.get("similarity", 0) > 0.1]
            if kb_parts:
                chunk_section = "\n\n".join(
                    f"From \"{r['doc_title']}\":\n{r['chunk_text'][:500]}"
                    for r in kb_parts
                )
                if kb_prompt_section:
                    kb_prompt_section += "\n\n" + chunk_section
                else:
                    kb_prompt_section = (
                        "Teacher's Existing Materials on This Topic\n"
                        "The teacher has created content on this topic before. "
                        "Reference and build on their existing work:\n\n"
                        + chunk_section
                    )
                if not assets:
                    console.print(f"[dim]Found {len(kb_parts)} related materials in knowledge base[/dim]")
    except Exception:
        pass

    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            f"Generating lesson {lesson_num}{'  [multi-agent]' if multi_agent else ''}...",
            total=None,
        )
        try:
            if multi_agent:
                # Multi-agent pipeline: researcher → writer → reviewer
                from clawed.compile_teacher import compile_teacher_view
                from clawed.multi_agent import multi_agent_generate_master_content
                console.print("[dim]Using multi-agent pipeline (researcher→writer→reviewer)...[/dim]")
                _ma_config = AppConfig.load()
                try:
                    master = _run_async(
                        multi_agent_generate_master_content(
                            topic=topic,
                            grade=grade,
                            subject=subject,
                            persona=persona,
                            config=_ma_config,
                            unit_context=kb_prompt_section,
                        )
                    )
                except Exception:
                    master = None
                if master is None:
                    console.print(
                        "[yellow]Multi-agent didn't complete. Using single-agent instead...[/yellow]"
                    )
                    daily = _run_async(
                        generate_lesson(
                            lesson_number=lesson_num, unit=unit_plan,
                            persona=persona, include_homework=homework,
                            teacher_materials=kb_prompt_section,
                        )
                    )
                else:
                    daily = master.to_daily_lesson()
                    # v4.11.2026: when we already have the MasterContent
                    # in hand (multi-agent path), produce the full
                    # teacher DOCX + student DOCX + classroom PPTX
                    # bundle, matching the batch generator. Before this
                    # fix, only the teacher DOCX was written; the PPTX
                    # wiring in generate_and_compile was unreachable
                    # from any production CLI/HTTP call.
                    try:
                        from clawed.compile_slides import compile_slides
                        from clawed.compile_student import compile_student_view
                        _out = _output_dir()
                        _run_async(
                            compile_teacher_view(master, images={}, output_dir=_out)
                        )
                        _run_async(
                            compile_student_view(master, images={}, output_dir=_out)
                        )
                        _run_async(
                            compile_slides(master, images={}, output_dir=_out)
                        )
                    except Exception as _exc:
                        logger.debug(
                            "Bundle compile (DOCX + PPTX) failed: %s", _exc
                        )
            else:
                daily = _run_async(
                    generate_lesson(
                        lesson_number=lesson_num,
                        unit=unit_plan,
                        persona=persona,
                        include_homework=homework,
                        teacher_materials=kb_prompt_section,
                    )
                )
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1)
        progress.update(task, description="Lesson plan complete!")

    # ── Voice scoring ────────────────────────────────────────────
    try:
        from clawed.persona import load_persona as _load_p
        from clawed.quality import score_voice_match
        _pp = _output_dir() / "persona.json"
        if _pp.exists():
            _persona = _load_p(_pp)
            _lesson_text = (
                str(daily.objective) + " " + str(daily.do_now)
                + " " + str(getattr(daily, "direct_instruction", ""))
            )
            _voice_score = _run_async(score_voice_match(_lesson_text, _persona.to_prompt_context()))
            if _voice_score and _voice_score > 0:
                _color = "green" if _voice_score >= 3.5 else "yellow" if _voice_score >= 2.5 else "red"
                console.print(f"  Voice match: [{_color}]{_voice_score:.1f}/5.0[/{_color}]")
    except Exception:
        pass  # Non-blocking — don't fail lesson delivery on scoring error

    out_dir = _output_dir()
    json_path = save_lesson(daily, out_dir)

    # For doc formats (pptx/docx/pdf/handout), use doc_export directly;
    # export_lesson only handles markdown/pdf/docx natively.
    export_path = None
    if fmt in ("pptx", "docx", "pdf", "handout"):
        try:
            from clawed.doc_export import (
                export_lesson_docx,
                export_lesson_pdf,
                export_lesson_pptx,
                export_student_handout,
            )
            if fmt == "pptx":
                doc_path = export_lesson_pptx(daily, persona, out_dir, narrate=narrate)
            elif fmt == "docx":
                doc_path = export_lesson_docx(daily, persona, out_dir)
            elif fmt == "handout":
                doc_path = export_student_handout(daily, persona, out_dir)
            else:
                doc_path = export_lesson_pdf(daily, persona, out_dir)
            export_path = doc_path
            console.print(f"[green]Document exported:[/green] {doc_path}")
        except Exception as e:
            console.print(f"[yellow]Document export failed: {e}[/yellow]")
            # Fall back to markdown
            export_path = export_lesson(daily, out_dir, fmt="markdown")
    else:
        export_path = export_lesson(daily, out_dir, fmt=fmt)

    console.print(f"\n[green]Lesson saved:[/green] {json_path}")
    if export_path:
        console.print(f"[green]Exported:[/green] {export_path}")

    # ── Quality review ────────────────────────────────────────────
    if export_path:
        try:
            from clawed.review_output import (
                review_docx,
                review_pptx,
            )
            export_p = Path(export_path) if not isinstance(export_path, Path) else export_path
            if export_p.suffix == ".pptx":
                review = review_pptx(export_p)
            elif export_p.suffix == ".docx":
                review = review_docx(export_p)
            else:
                review = None
            if review:
                if review.passed:
                    console.print(
                        f"  Quality: [green]{review.score:.1f}/10[/green]"
                    )
                else:
                    console.print(
                        f"  Quality: [red]{review.score:.1f}/10 "
                        f"({len(review.issues)} issues)[/red]"
                    )
                    for issue in review.issues[:5]:
                        _sev = {"critical": "red", "major": "yellow", "minor": "dim"}
                        console.print(
                            f"    [{_sev.get(issue['severity'], 'dim')}]"
                            f"{issue['location']}: "
                            f"{issue['description']}[/{_sev.get(issue['severity'], 'dim')}]"
                        )
        except Exception:
            pass

    console.print(
        Panel(
            f"[bold]Objective:[/bold] {daily.objective}\n"
            f"[bold]Standards:[/bold] {', '.join(daily.standards)}",
            title=f"Lesson {daily.lesson_number}: {daily.title}",
        )
    )

    # Generate game if requested
    if game:
        try:
            from clawed.compile_game import compile_game
            with _safe_progress(console=console) as gprog:
                gtask = gprog.add_task(
                    "Designing learning game...", total=None
                )
                game_path = _run_async(
                    compile_game(
                        master=daily,
                        persona=persona,
                        output_dir=_output_dir(),
                    )
                )
                gprog.update(gtask, description="Game ready!")
            if game_path:
                console.print(
                    f"[green]Game created:[/green] {game_path}\n"
                    f"[dim]Open: open {game_path}[/dim]"
                )
        except Exception as e:
            console.print(
                f"[yellow]Game generation failed:[/yellow] {e}"
            )

    # Star prompt — show once per session, not every time
    import os
    if not os.environ.get("_CLAWED_STAR_SHOWN"):
        os.environ["_CLAWED_STAR_SHOWN"] = "1"
        console.print(
            "\n[dim]Claw-ED is free and open source. "
            "If it saved you time, consider starring the repo:[/dim]\n"
            "[dim]  https://github.com/SirhanMacx/Claw-ED[/dim]\n"
        )



# ── Import split modules so their commands register on generate_app ──────
# NOTE: These imports MUST stay at the bottom to avoid circular imports.
# Each module imports generate_app from this file and registers commands on it.
import clawed.commands.generate_assessment  # noqa: E402, F401
import clawed.commands.generate_comms  # noqa: E402, F401
import clawed.commands.generate_diff  # noqa: E402, F401
import clawed.commands.generate_ingest  # noqa: E402, F401
import clawed.commands.generate_standards  # noqa: E402, F401
import clawed.commands.generate_unit  # noqa: E402, F401
