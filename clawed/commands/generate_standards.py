"""Curriculum gap analyzer command — split from generate.py for maintainability."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

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
from clawed.commands.generate import generate_app
from clawed.io import safe_filename as _safe_filename
from clawed.models import AppConfig

# ── Curriculum gap analyzer ──────────────────────────────────────────────


def _gap_analyze_json(*, subject, grade, standards, materials_dir):
    """Run gap analysis and return structured result for JSON output."""
    from clawed.curriculum_map import CurriculumMapper
    from clawed.models import CurriculumGap, TeacherPersona

    persona = load_persona_or_exit()

    # Resolve standards
    standards_list: list[str] = []
    if standards:
        p = Path(standards).expanduser()
        if p.exists():
            standards_list = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            standards_list = [s.strip() for s in standards.split(",") if s.strip()]

    if not standards_list:
        standards_list = [f"Grade {grade} {subject} — Core Standards (auto-inferred from materials)"]

    # Collect existing materials
    mat_path: Path | None = None
    if materials_dir:
        mat_path = Path(materials_dir).expanduser().resolve()
    else:
        cfg = AppConfig.load()
        from clawed.paths import data_dir

        corpus_base = data_dir()
        if getattr(cfg, "active_teacher_id", None):
            corpus_base = corpus_base / "teachers" / cfg.active_teacher_id / "corpus"
        else:
            corpus_base = corpus_base / "corpus"
        if corpus_base.is_dir():
            mat_path = corpus_base

    materials_list: list[str] = []
    if mat_path and mat_path.is_dir():
        exts = {".txt", ".md", ".pdf", ".docx", ".json"}
        files = [f for f in mat_path.rglob("*") if f.suffix.lower() in exts and f.is_file()]
        materials_list = [f.name for f in files[:200]]

    if not materials_list:
        materials_list = ["(no materials found -- analysis is standards-only)"]

    mapper = CurriculumMapper()
    teacher_persona = TeacherPersona(
        name=getattr(persona, "name", ""),
        grade_levels=[grade],
        subject_area=subject,
    )

    gaps: list[CurriculumGap] = _run_async(
        mapper.identify_curriculum_gaps(
            existing_materials=materials_list,
            standards=standards_list,
            persona=teacher_persona,
        )
    )

    return {
        "data": {
            "subject": subject,
            "grade": grade,
            "standards_count": len(standards_list),
            "materials_count": len(materials_list),
            "gaps": [g.model_dump() for g in gaps] if gaps else [],
            "summary": {
                "high": len([g for g in gaps if g.severity.lower() == "high"]),
                "medium": len([g for g in gaps if g.severity.lower() == "medium"]),
                "low": len([g for g in gaps if g.severity.lower() == "low"]),
            },
        },
        "files": [],
    }


@generate_app.command(name="gap-analyze")
def gap_analyze(
    subject: str = typer.Option(..., "--subject", "-s", help="Subject area (e.g. 'Social Studies')"),
    grade: str = typer.Option(..., "--grade", "-g", help="Grade level (e.g. '8')"),
    standards: Optional[str] = typer.Option(
        None,
        "--standards",
        help="Comma-separated standards codes/descriptions, or path to a .txt file (one per line)",
    ),
    materials_dir: Optional[str] = typer.Option(
        None,
        "--materials-dir",
        "-m",
        help="Directory of teacher materials to scan (defaults to persona corpus dir)",
    ),
    fmt: str = typer.Option("html", "--format", "-f", help="Output format: html or markdown"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Analyze existing materials against standards and identify curriculum gaps.

    Scans teacher materials, compares them to the provided standards, and
    outputs a prioritized gap report with severity ratings and suggestions.

    Example:\n
        clawed gap-analyze --subject "Social Studies" --grade 8 \\
            --standards "8.1.a,8.2.b,8.3.c"
    """
    if json_output:
        run_json_command(
            "gen.gap-analyze",
            _gap_analyze_json,
            subject=subject,
            grade=grade,
            standards=standards,
            materials_dir=materials_dir,
        )
        return

    check_api_key_or_exit()

    from datetime import datetime

    from clawed.curriculum_map import CurriculumMapper
    from clawed.models import CurriculumGap, TeacherPersona

    persona = load_persona_or_exit()

    # ── Resolve standards ──────────────────────────────────────────────
    standards_list: list[str] = []
    if standards:
        p = Path(standards).expanduser()
        if p.exists():
            standards_list = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            standards_list = [s.strip() for s in standards.split(",") if s.strip()]

    if not standards_list:
        standards_list = [f"Grade {grade} {subject} — Core Standards (auto-inferred from materials)"]

    # ── Collect existing materials ─────────────────────────────────────
    mat_path: Path | None = None
    if materials_dir:
        mat_path = Path(materials_dir).expanduser().resolve()
        if not mat_path.is_dir():
            console.print(f"[red]Materials directory not found:[/red] {mat_path}")
            raise typer.Exit(1)
    else:
        cfg = AppConfig.load()
        from clawed.paths import data_dir

        corpus_base = data_dir()
        if getattr(cfg, "active_teacher_id", None):
            corpus_base = corpus_base / "teachers" / cfg.active_teacher_id / "corpus"
        else:
            corpus_base = corpus_base / "corpus"
        if corpus_base.is_dir():
            mat_path = corpus_base

    materials_list: list[str] = []
    if mat_path and mat_path.is_dir():
        exts = {".txt", ".md", ".pdf", ".docx", ".json"}
        files = [f for f in mat_path.rglob("*") if f.suffix.lower() in exts and f.is_file()]
        materials_list = [f.name for f in files[:200]]

    if not materials_list:
        materials_list = ["(no materials found — analysis is standards-only)"]

    # ── Run gap analysis ───────────────────────────────────────────────
    console.print(
        Panel(
            f"[bold]{subject} — Grade {grade}[/bold]\n"
            f"Standards: {len(standards_list)}  |  Materials: {len(materials_list)} files",
            title="Curriculum Gap Analyzer",
        )
    )

    mapper = CurriculumMapper()
    teacher_persona = TeacherPersona(
        name=getattr(persona, "name", ""),
        grade_levels=[grade],
        subject_area=subject,
    )

    with _safe_progress(console=console) as progress:
        task = progress.add_task("Analyzing curriculum gaps...", total=None)
        try:
            gaps: list[CurriculumGap] = _run_async(
                mapper.identify_curriculum_gaps(
                    existing_materials=materials_list,
                    standards=standards_list,
                    persona=teacher_persona,
                )
            )
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1)
        progress.update(task, description="Analysis complete!")

    if not gaps:
        console.print("[green]No curriculum gaps identified! Coverage looks complete.[/green]")
        return

    # ── Severity counts ────────────────────────────────────────────────
    high = [g for g in gaps if g.severity.lower() == "high"]
    med = [g for g in gaps if g.severity.lower() == "medium"]
    low = [g for g in gaps if g.severity.lower() == "low"]

    # ── Display summary table ──────────────────────────────────────────
    table = Table(title=f"Curriculum Gaps — {subject} Grade {grade}")
    table.add_column("Severity", style="bold", justify="center")
    table.add_column("Standard", style="dim")
    table.add_column("Description")
    table.add_column("Suggestion")

    sev_order = {"high": 0, "medium": 1, "low": 2}
    for g in sorted(gaps, key=lambda x: sev_order.get(x.severity.lower(), 3)):
        sev_colors = {"high": "red", "medium": "yellow", "low": "green"}
        color = sev_colors.get(g.severity.lower(), "white")
        table.add_row(
            f"[{color}]{g.severity.upper()}[/{color}]",
            g.standard,
            g.description[:80] + ("..." if len(g.description) > 80 else ""),
            g.suggestion[:60] + ("..." if len(g.suggestion) > 60 else ""),
        )
    console.print(table)
    console.print(f"\n[bold]Summary:[/bold] {len(high)} HIGH  |  {len(med)} MEDIUM  |  {len(low)} LOW")

    # ── Export ─────────────────────────────────────────────────────────
    out_dir = _output_dir() / "gap-reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _safe_filename(f"{subject}_grade{grade}")

    if fmt == "html":
        html_path = out_dir / f"{slug}_gap_report.html"
        rows_html = ""
        badge_colors = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}
        for g in sorted(gaps, key=lambda x: sev_order.get(x.severity.lower(), 3)):
            color = badge_colors.get(g.severity.lower(), "#6b7280")
            rows_html += f"""
            <tr>
              <td><span class="badge" style="background:{color}">{g.severity.upper()}</span></td>
              <td class="standard">{g.standard}</td>
              <td>{g.description}</td>
              <td class="suggestion">{g.suggestion}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Curriculum Gap Report — {subject} Grade {grade}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1100px;
    margin: 2rem auto; padding: 0 1.5rem; color: #1f2937; }}
  h1 {{ font-size: 1.75rem; margin-bottom: .25rem; }}
  .meta {{ color: #6b7280; font-size: .9rem; margin-bottom: 2rem; }}
  .summary-bar {{ display: flex; gap: 1rem; margin-bottom: 2rem; }}
  .pill {{ padding: .4rem 1rem; border-radius: 9999px; font-weight: 600; font-size: .85rem; color: #fff; }}
  .pill.high {{ background: #ef4444; }} .pill.med {{ background: #f59e0b; }} .pill.low {{ background: #22c55e; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
  th {{ text-align: left; padding: .6rem .8rem; background: #f3f4f6; border-bottom: 2px solid #e5e7eb; }}
  td {{ padding: .6rem .8rem; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
  tr:hover td {{ background: #f9fafb; }}
  .badge {{ display: inline-block; padding: .2rem .6rem; border-radius: .3rem;
    color: #fff; font-size: .75rem; font-weight: 700; }}
  .standard {{ font-family: monospace; white-space: nowrap; color: #4b5563; }}
  .suggestion {{ font-style: italic; color: #374151; }}
  @media print {{ body {{ max-width: 100%; }} .summary-bar {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>Curriculum Gap Report</h1>
<div class="meta">{subject} · Grade {grade} · Generated {datetime.now().strftime("%B %d, %Y")}</div>
<div class="summary-bar">
  <span class="pill high">{len(high)} HIGH</span>
  <span class="pill med">{len(med)} MEDIUM</span>
  <span class="pill low">{len(low)} LOW</span>
</div>
<table>
  <thead><tr><th>Severity</th><th>Standard</th><th>Gap Description</th><th>Suggestion</th></tr></thead>
  <tbody>{rows_html}
  </tbody>
</table>
<p class="meta" style="margin-top:2rem">
  Generated by Claw-ED · {len(materials_list)} materials analyzed · {len(standards_list)} standards checked
</p>
</body>
</html>"""
        html_path.write_text(html, encoding="utf-8")
        console.print(f"\n[green]Gap report saved:[/green] {html_path}")

    else:
        md_path = out_dir / f"{slug}_gap_report.md"
        lines = [
            f"# Curriculum Gap Report — {subject} Grade {grade}\n",
            f"**Generated:** {datetime.now().strftime('%B %d, %Y')}  \n",
            f"**Summary:** {len(high)} HIGH | {len(med)} MEDIUM | {len(low)} LOW\n",
            "",
            "| Severity | Standard | Description | Suggestion |",
            "|----------|----------|-------------|------------|",
        ]
        for g in sorted(gaps, key=lambda x: sev_order.get(x.severity.lower(), 3)):
            lines.append(f"| **{g.severity.upper()}** | `{g.standard}` | {g.description} | {g.suggestion} |")
        md_path.write_text("\n".join(lines), encoding="utf-8")
        console.print(f"\n[green]Gap report saved:[/green] {md_path}")
