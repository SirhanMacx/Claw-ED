"""Tool: standards_dashboard — show teachers their standards coverage across all generated lessons."""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class StandardsDashboardTool:
    """Show a teacher their standards coverage across all generated lessons."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "standards_dashboard",
                "description": (
                    "Show the teacher a compliance dashboard of which state "
                    "standards have been covered across all their generated "
                    "lessons, which are missing, and what to teach next."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {
                            "type": "string",
                            "description": (
                                "Subject to check coverage for "
                                "(e.g. 'Math', 'ELA', 'Science', 'History'). "
                                "If omitted, uses the teacher's profile subject."
                            ),
                        },
                        "grade": {
                            "type": "string",
                            "description": (
                                "Grade level to check (e.g. '8', 'K', '9-12'). "
                                "If omitted, uses the teacher's profile grade."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.standards import get_standards
        from clawed.state import _get_conn, init_db

        # ── Resolve subject and grade from params or teacher profile ──
        subject = params.get("subject", "")
        grade = params.get("grade", "")

        if not subject and context.teacher_profile:
            subject = context.teacher_profile.get("subject", "")
        if not grade and context.teacher_profile:
            grade = context.teacher_profile.get("grade", "")

        if not subject:
            return ToolResult(
                text=(
                    "I need a subject to check standards coverage. "
                    "Please specify a subject (e.g. Math, ELA, Science, History)."
                )
            )

        state = ""
        if context.config and context.config.teacher_profile:
            state = context.config.teacher_profile.state or ""

        # ── Get the full set of standards for this subject/grade ──────
        all_standards = get_standards(subject, grade if grade else None)
        if not all_standards:
            return ToolResult(
                text=(
                    f"No standards found for {subject}"
                    f"{' grade ' + grade if grade else ''}. "
                    "Check that the subject name is correct."
                ),
                data={"total": 0, "covered": 0},
            )

        full_standard_codes = {code for code, _desc, _band in all_standards}
        standard_descriptions = {code: desc for code, desc, _band in all_standards}

        # ── Query all generated lessons for this teacher ─────────────
        init_db()
        covered_counter: Counter[str] = Counter()
        lesson_count = 0

        try:
            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT lesson_json FROM generated_lessons WHERE teacher_id = ?",
                    (context.teacher_id,),
                ).fetchall()

            for row in rows:
                lesson_count += 1
                try:
                    lesson_data = json.loads(row["lesson_json"])
                    lesson_standards = lesson_data.get("standards", [])
                    for std_entry in lesson_standards:
                        # Standards may be stored as "CODE: description" or
                        # just "CODE". Extract the code portion.
                        code = std_entry.split(":")[0].strip()
                        if code in full_standard_codes:
                            covered_counter[code] += 1
                except (json.JSONDecodeError, TypeError, KeyError) as exc:
                    logger.debug("Skipping unparseable lesson: %s", exc)
        except Exception as e:
            logger.error("Failed to query lessons: %s", e)
            return ToolResult(text=f"Failed to query lesson database: {e}")

        # ── Compute coverage ─────────────────────────────────────────
        covered_codes = set(covered_counter.keys())
        gap_codes = full_standard_codes - covered_codes

        total = len(full_standard_codes)
        covered = len(covered_codes)
        pct = (covered / total * 100) if total > 0 else 0

        # Most-covered: standards hit 2+ times, sorted descending
        multi_hit = [(code, count) for code, count in covered_counter.most_common() if count >= 2]

        # ── Build markdown report ────────────────────────────────────
        subject_label = subject.replace("_", " ").title()
        grade_label = f" Grade {grade}" if grade else ""
        state_label = f" ({state})" if state else ""

        lines: list[str] = []
        lines.append(f"## Standards Coverage Dashboard{state_label}")
        lines.append(f"**{subject_label}{grade_label}**")
        lines.append(f"Based on {lesson_count} generated lesson(s)\n")

        lines.append(f"- **Total standards:** {total}")
        lines.append(f"- **Covered:** {covered} ({pct:.0f}%)")
        lines.append(f"- **Gaps:** {len(gap_codes)}")
        lines.append("")

        # Coverage bar
        filled = int(pct / 5)  # 20-char bar
        bar = "[" + "#" * filled + "-" * (20 - filled) + "]"
        lines.append(f"Progress: {bar} {pct:.0f}%\n")

        # Gaps section
        if gap_codes:
            lines.append("### Uncovered Standards")
            sorted_gaps = sorted(gap_codes)
            for code in sorted_gaps[:15]:
                desc = standard_descriptions.get(code, "")
                lines.append(f"- **{code}**: {desc}")
            if len(sorted_gaps) > 15:
                lines.append(f"- ... and {len(sorted_gaps) - 15} more")
            lines.append("")

        # Most-covered section
        if multi_hit:
            lines.append("### Most-Covered Standards")
            for code, count in multi_hit[:10]:
                desc = standard_descriptions.get(code, "")
                lines.append(f"- **{code}** ({count}x): {desc}")
            lines.append("")

        # Recommendation
        lines.append("### Recommendation")
        if gap_codes:
            # Pick a gap standard to recommend next
            next_code = sorted(gap_codes)[0]
            next_desc = standard_descriptions.get(next_code, "")
            lines.append(f"Consider covering **{next_code}** next: {next_desc}")
            if len(gap_codes) > 1:
                second = sorted(gap_codes)[1]
                second_desc = standard_descriptions.get(second, "")
                lines.append(f"Also consider **{second}**: {second_desc}")
        else:
            lines.append(
                "All standards are covered! Consider revisiting standards with only one lesson for deeper mastery."
            )

        report_text = "\n".join(lines)

        return ToolResult(
            text=report_text,
            data={
                "total": total,
                "covered": covered,
                "coverage_pct": round(pct, 1),
                "gaps": sorted(gap_codes),
                "multi_hit": [{"code": c, "count": n} for c, n in multi_hit],
                "lesson_count": lesson_count,
            },
            side_effects=["Generated standards coverage dashboard"],
        )
