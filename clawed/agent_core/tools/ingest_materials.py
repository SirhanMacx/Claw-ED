"""Tool: ingest_materials — wraps clawed.ingestor.ingest_path."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class IngestMaterialsTool:
    """Ingest teaching materials from a folder or file to learn the teacher's style."""

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "ingest_materials",
                "description": (
                    "Ingest lesson plans and teaching materials from a folder "
                    "or file path. Extracts text and learns the teacher's style."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Path to a folder or file to ingest "
                                "(PDF, DOCX, PPTX, TXT, MD)"
                            ),
                        },
                    },
                    "required": ["path"],
                },
            },
        }

    MAX_INGEST_FILES = 500

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.ingestor import ingest_path

        raw_path = params["path"]
        resolved = Path(raw_path).expanduser().resolve()

        # Security: only allow ingesting files from the user's home directory
        home = Path.home().resolve()
        if not str(resolved).startswith(str(home)):
            return ToolResult(
                text="Access denied: can only ingest files from your home directory."
            )

        if not resolved.exists():
            return ToolResult(
                text=f"Path not found: {raw_path}. Check the path and try again."
            )

        try:
            docs = ingest_path(resolved, max_files=self.MAX_INGEST_FILES)
            if not docs:
                return ToolResult(
                    text=f"No supported files found in {raw_path}. "
                    "Supported formats: PDF, DOCX, PPTX, TXT, MD."
                )

            # Try to extract persona from ingested docs
            persona = None
            try:
                from clawed.persona import extract_persona, save_persona

                persona = await extract_persona(docs, context.config)
                # Override LLM-inferred name with configured teacher name
                try:
                    if context.config and context.config.teacher_profile and context.config.teacher_profile.name:
                        persona.name = f"{context.config.teacher_profile.name} Teaching Persona"
                except Exception:
                    pass
                try:
                    from clawed.paths import workspace_dir
                    _id_path = workspace_dir() / "identity.md"
                    if _id_path.exists():
                        import re as _re
                        _id_content = _id_path.read_text(encoding="utf-8")
                        _name_match = _re.match(r"^#\s+(.+)", _id_content)
                        if _name_match:
                            _tname = _name_match.group(1).strip()
                            if _tname and _tname != "Teacher":
                                persona.name = f"{_tname} Teaching Persona"
                except Exception:
                    pass
                from clawed.paths import data_dir
                save_persona(persona, data_dir())
                # Track persona changes for evolution
                try:
                    from clawed.persona_evolution import record_ingestion_changes
                    record_ingestion_changes(old_persona=None, new_persona=persona)
                except Exception:
                    pass
            except Exception:
                pass

            # Generate reading report
            summary = f"Ingested {len(docs)} file(s) from {raw_path}."
            try:
                from clawed.reading_report import (
                    format_reading_report,
                    generate_reading_report,
                )

                report = generate_reading_report(docs, persona=persona)
                report_text = format_reading_report(report)
                if report_text:
                    summary = report_text
                    # Store the report for future system prompts

                    from clawed.paths import data_dir as _data_dir_fn
                    data_dir = _data_dir_fn()
                    report_path = data_dir / "workspace" / "reading_report.md"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(report_text, encoding="utf-8")
            except Exception:
                # Fallback to basic summary if report generation fails
                if persona:
                    style = persona.teaching_style.value.replace("_", " ").title()
                    summary += f" Teaching style: {style}, Tone: {persona.tone}."
                else:
                    summary += " (Could not extract style patterns.)"

            # Full pipeline: images + assets + chunks + KG + wiki
            try:
                from clawed.ingestor import full_ingest

                async def _notify(msg: str) -> None:
                    if context.progress_callback:
                        await context.notify_progress(msg)

                ingest_result = full_ingest(
                    raw_path,
                    teacher_id=context.teacher_id,
                    progress_callback=lambda msg: logger.info(msg),
                )
                parts = []
                if ingest_result["chunks_indexed"]:
                    parts.append(
                        f"{ingest_result['chunks_indexed']} searchable sections"
                    )
                if ingest_result["images_extracted"]:
                    parts.append(
                        f"{ingest_result['images_extracted']} images extracted"
                    )
                if ingest_result["kg_entities"]:
                    parts.append(
                        f"{ingest_result['kg_entities']} concepts mapped"
                    )
                if ingest_result["wiki_articles"]:
                    parts.append(
                        f"{ingest_result['wiki_articles']} wiki articles"
                    )
                if parts:
                    summary += "\n\n" + " · ".join(parts)
            except Exception as e:
                logger.debug("Full ingest pipeline failed: %s", e)

            # Update soul.md with what we learned
            try:
                import os as _os
                _data = _os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
                soul_path = Path(_data) / "workspace" / "soul.md"
                soul_path.parent.mkdir(parents=True, exist_ok=True)

                # Build soul updates from reading report
                soul_updates = []
                if report.get("teacher_details", {}).get("name_used"):
                    soul_updates.append(
                        f"Students know me as {report['teacher_details']['name_used']}"
                    )
                if report.get("voice_patterns"):
                    soul_updates.append(
                        "Voice patterns: " + "; ".join(report["voice_patterns"][:3])
                    )
                if report.get("favorite_strategies"):
                    soul_updates.append(
                        "Go-to strategies: " + ", ".join(report["favorite_strategies"][:4])
                    )
                if report.get("signature_moves"):
                    soul_updates.append(
                        "Signature moves: " + ", ".join(report["signature_moves"][:3])
                    )
                if report.get("assessment_patterns"):
                    soul_updates.append(
                        "Assessment style: " + "; ".join(report["assessment_patterns"][:2])
                    )

                if soul_updates:
                    from datetime import date

                    update_text = f"\n\n### Learned from files ({date.today().isoformat()})\n"
                    update_text += "\n".join(f"- {u}" for u in soul_updates) + "\n"

                    if soul_path.exists():
                        current = soul_path.read_text(encoding="utf-8")
                        if "## Agent Observations" in current:
                            current = current.replace(
                                "## Agent Observations",
                                f"## Agent Observations{update_text}",
                            )
                        else:
                            current += f"\n## Agent Observations{update_text}"
                        soul_path.write_text(current, encoding="utf-8")
                    else:
                        template = (
                            "# Teaching Identity\n\n"
                            "## Who I Am\n\n## My Teaching Philosophy\n\n"
                            "## My Voice\n\n## My Classroom Norms\n\n"
                            "## Assessment Approach\n\n"
                            "## What Makes My Teaching Mine\n\n"
                            f"## Agent Observations{update_text}"
                        )
                        soul_path.write_text(template, encoding="utf-8")
            except Exception as e:
                logger.debug("SOUL.md update failed: %s", e)

            # Auto-populate teacher profile from reading report (pending confirmation)
            try:
                from clawed.models import AppConfig
                config = AppConfig.load()
                details = report.get("teacher_details", {})
                pending = {}

                if details.get("name_used") and (
                    not config.teacher_profile.name
                    or config.teacher_profile.name == ""
                ):
                    pending["name"] = details["name_used"]

                if details.get("school") and not config.teacher_profile.school:
                    pending["school"] = details["school"]

                if details.get("subject_guess") and not config.teacher_profile.subjects:
                    pending["subject"] = details["subject_guess"]

                if pending:
                    # Don't write directly — store as pending for confirmation
                    items = ", ".join(f"{k}: '{v}'" for k, v in pending.items())
                    profile_update = (
                        f"\n\nI extracted these details from your files: {items}. "
                        "Reply 'yes' to confirm."
                    )
                else:
                    profile_update = ""
            except Exception as e:
                logger.debug("Auto-profile failed: %s", e)
                profile_update = ""

            return ToolResult(
                text=summary + profile_update,
                data={"files_ingested": len(docs)},
                side_effects=[f"Ingested {len(docs)} files from {raw_path}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to ingest materials: {e}")
