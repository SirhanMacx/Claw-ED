"""Tool: ingest_materials — wraps clawed.ingestor.ingest_path."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class IngestMaterialsTool:
    """Ingest teaching materials from a folder or file to learn the teacher's style."""

    risk_level = "write_local"

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

            persona = await self._extract_and_save_persona(docs, context)
            summary, report = self._generate_reading_summary(docs, persona, raw_path)
            summary = self._run_full_ingest_pipeline(summary, raw_path, context)
            self._update_soul_md(report)
            profile_update = self._build_profile_update(report)

            return ToolResult(
                text=summary + profile_update,
                data={"files_ingested": len(docs)},
                side_effects=[f"Ingested {len(docs)} files from {raw_path}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to ingest materials: {e}")

    async def _extract_and_save_persona(self, docs: list[Any], context: AgentContext) -> Any:
        """Extract persona from docs, override name, save, track evolution."""
        try:
            from clawed.persona import extract_persona, save_persona
            persona = await extract_persona(docs, context.config)
            try:
                if context.config and context.config.teacher_profile and context.config.teacher_profile.name:
                    persona.name = f"{context.config.teacher_profile.name} Teaching Persona"
            except Exception:
                logger.debug("operation_failed", exc_info=True)
            try:
                from clawed.paths import workspace_dir
                _id_path = workspace_dir() / "identity.md"
                if _id_path.exists():
                    import re as _re
                    _name_match = _re.match(r"^#\s+(.+)", _id_path.read_text(encoding="utf-8"))
                    if _name_match:
                        _tname = _name_match.group(1).strip()
                        if _tname and _tname != "Teacher":
                            persona.name = f"{_tname} Teaching Persona"
            except (FileNotFoundError, OSError):
                pass
            from clawed.paths import data_dir
            save_persona(persona, data_dir())
            try:
                from clawed.persona_evolution import record_ingestion_changes
                record_ingestion_changes(old_persona=None, new_persona=persona)  # type: ignore[arg-type]  # None is accepted at runtime for first ingest
            except ImportError:
                pass
            return persona
        except (ImportError, OSError, RuntimeError):
            return None
        except Exception:
            logger.debug("Persona extraction failed", exc_info=True)
            return None

    def _generate_reading_summary(self, docs: list[Any], persona: Any, raw_path: Any) -> tuple[str, dict[str, Any]]:
        """Generate reading report and return (summary, report_dict)."""
        summary = f"Ingested {len(docs)} file(s) from {raw_path}."
        report = {}
        try:
            from clawed.reading_report import format_reading_report, generate_reading_report
            report = generate_reading_report(docs, persona=persona)
            report_text = format_reading_report(report)
            if report_text:
                summary = report_text
                from clawed.paths import data_dir as _data_dir_fn
                report_path = _data_dir_fn() / "workspace" / "reading_report.md"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(report_text, encoding="utf-8")
        except (FileNotFoundError, OSError, ImportError, TypeError):
            if persona:
                try:
                    style = persona.teaching_style.value.replace("_", " ").title()
                    summary += f" Teaching style: {style}, Tone: {persona.tone}."
                except (AttributeError, TypeError):
                    summary += " (Could not extract style patterns.)"
            else:
                summary += " (Could not extract style patterns.)"
        return summary, report

    def _run_full_ingest_pipeline(self, summary: str, raw_path: Any, context: AgentContext) -> str:
        """Run full pipeline: chunks + images + KG + wiki."""
        try:
            from clawed.ingestor import full_ingest
            result = full_ingest(
                raw_path, teacher_id=context.teacher_id,
                progress_callback=lambda msg: logger.info(msg),
            )
            parts = []
            for key, label in [("chunks_indexed", "searchable sections"), ("images_extracted", "images extracted"),
                               ("kg_entities", "concepts mapped"), ("wiki_articles", "wiki articles")]:
                if result.get(key):
                    parts.append(f"{result[key]} {label}")
            if parts:
                summary += "\n\n" + " \u00b7 ".join(parts)
        except Exception as e:
            logger.debug("Full ingest pipeline failed: %s", e)
        return summary

    def _update_soul_md(self, report: dict[str, Any]) -> None:
        """Update soul.md with learnings from reading report."""
        try:
            import os as _os
            data_root = _os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
            soul_path = Path(data_root) / "workspace" / "soul.md"
            soul_path.parent.mkdir(parents=True, exist_ok=True)
            soul_updates = []
            for key, prefix in [("name_used", "Students know me as"), ("voice_patterns", "Voice patterns: "),
                                ("favorite_strategies", "Go-to strategies: "), ("signature_moves", "Signature moves: "),
                                ("assessment_patterns", "Assessment style: ")]:
                if key == "name_used":
                    val = report.get("teacher_details", {}).get(key)
                    if val:
                        soul_updates.append(f"{prefix} {val}")
                else:
                    vals = report.get(key, [])
                    if vals:
                        sep = "; " if "pattern" in key else ", "
                        soul_updates.append(prefix + sep.join(vals[:4]))
            if soul_updates:
                from datetime import date
                items = "\n".join(f"- {u}" for u in soul_updates)
                update_text = f"\n\n### Learned from files ({date.today().isoformat()})\n{items}\n"
                if soul_path.exists():
                    current = soul_path.read_text(encoding="utf-8")
                    if "## Agent Observations" in current:
                        current = current.replace("## Agent Observations", f"## Agent Observations{update_text}")
                    else:
                        current += f"\n## Agent Observations{update_text}"
                    soul_path.write_text(current, encoding="utf-8")
                else:
                    soul_path.write_text(
                        "# Teaching Identity\n\n## Who I Am\n\n## My Teaching Philosophy\n\n"
                        "## My Voice\n\n## My Classroom Norms\n\n## Assessment Approach\n\n"
                        f"## What Makes My Teaching Mine\n\n## Agent Observations{update_text}",
                        encoding="utf-8",
                    )
        except Exception as e:
            logger.debug("SOUL.md update failed: %s", e)

    def _build_profile_update(self, report: dict[str, Any]) -> str:
        """Check if we can auto-populate teacher profile fields."""
        try:
            from clawed.models import AppConfig
            config = AppConfig.load()
            details = report.get("teacher_details", {})
            pending = {}
            if details.get("name_used") and not config.teacher_profile.name:
                pending["name"] = details["name_used"]
            if details.get("school") and not config.teacher_profile.school:
                pending["school"] = details["school"]
            if details.get("subject_guess") and not config.teacher_profile.subjects:
                pending["subject"] = details["subject_guess"]
            if pending:
                items = ", ".join(f"{k}: '{v}'" for k, v in pending.items())
                return f"\n\nI extracted these details from your files: {items}. Reply 'yes' to confirm."
            return ""
        except Exception as e:
            logger.debug("Auto-profile failed: %s", e)
            return ""
