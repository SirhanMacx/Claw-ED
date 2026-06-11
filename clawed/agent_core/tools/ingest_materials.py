"""Tool: ingest_materials — learn the teacher's voice from their files.

Policy (mirrors mac_files):
- Home-bounded: only paths inside the teacher's home directory.
- Secrets-denied: credential folders/files are refused even for reads.
- ONE approval covers the whole folder tree (``approval_scope =
  "per_params"`` keyed on the resolved folder path) — the teacher
  approves "read my materials in <folder>" once, not per file.
- Read-only on the teacher's files; everything written (style profile,
  reading report, search index) stays in the agent's own data dir.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.paths import path_is_within

logger = logging.getLogger(__name__)

# Never readable, even with approval — secrets and credentials.
# (Kept in sync with clawed.agent_core.tools.mac_files.)
_DENY_NAMES = frozenset({
    ".ssh", ".gnupg", ".credentials.json", "secrets.json", "api_token",
    ".pypirc", ".netrc", ".npmrc", ".env", "id_rsa", "id_ed25519",
})

# Per-file cap: anything bigger is skipped (slide decks with embedded
# video, scans). Keeps a junk-heavy folder from wedging the ingest.
_MAX_FILE_BYTES = 25 * 1024 * 1024


class IngestMaterialsTool:
    """Ingest teaching materials from a folder or file to learn the teacher's style."""

    risk_level = "write_local"
    approval_scope = "per_params"

    @staticmethod
    def approval_signature(params: dict[str, Any]) -> str:
        try:
            resolved = Path(str(params.get("path", ""))).expanduser().resolve()
            return f"ingest:{resolved}"
        except (OSError, RuntimeError):
            return f"ingest:{params.get('path', '')}"

    @staticmethod
    def approval_description(params: dict[str, Any]) -> str:
        return (
            f"Read your teaching materials in {params.get('path', '')} "
            "(read-only, whole folder) and learn your style from them. "
            "Everything stays on this Mac."
        )

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "ingest_materials",
                "description": (
                    "Ingest lesson plans and teaching materials from a folder "
                    "or file path. Extracts text, learns the teacher's voice / "
                    "lesson structure / assessment conventions, and saves a "
                    "STYLE PROFILE that future lessons automatically match. "
                    "One approval covers the whole folder tree."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Path to a folder or file to ingest "
                                "(PDF, DOCX, PPTX, TXT, MD, HTML)"
                            ),
                        },
                        "profile_name": {
                            "type": "string",
                            "description": (
                                "Optional name for the style profile (e.g. "
                                "'Global 10'). Defaults to the folder name. "
                                "Use distinct names for distinct courses."
                            ),
                        },
                    },
                    "required": ["path"],
                },
            },
        }

    MAX_INGEST_FILES = 500

    @staticmethod
    def _deny_reason(resolved: Path) -> str | None:
        """Home-bound + secrets checks. Returns an error string or None."""
        home = Path.home().resolve()
        if not path_is_within(resolved, home):
            return "Access denied: can only ingest files from your home directory."
        for part in resolved.parts:
            if part in _DENY_NAMES:
                return f"Access denied: '{part}' holds credentials."
        return None

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.ingestor import ingest_path, scan_directory

        raw_path = params["path"]
        resolved = Path(raw_path).expanduser().resolve()

        deny = self._deny_reason(resolved)
        if deny:
            return ToolResult(text=deny)

        if not resolved.exists():
            return ToolResult(
                text=f"Path not found: {raw_path}. Check the path and try again."
            )

        try:
            # Pre-scan so we can cap oversized files and report skips.
            skipped_oversize = 0
            if resolved.is_dir():
                all_files, _ = scan_directory(resolved)
                for f in all_files:
                    try:
                        if f.stat().st_size > _MAX_FILE_BYTES:
                            skipped_oversize += 1
                    except OSError:
                        continue

            docs = ingest_path(resolved, max_files=self.MAX_INGEST_FILES)
            docs = [
                d for d in docs
                if not (d.source_path and self._too_big(Path(d.source_path)))
            ]
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

            # ── STYLE PROFILE: the voice/structure fingerprint ────────
            style_note = ""
            style_data: dict[str, Any] = {}
            try:
                style_note, style_data = await self._build_style_profile(
                    docs, params, resolved, context,
                    files_skipped=skipped_oversize,
                )
            except Exception as e:
                logger.warning("Style profile build failed: %s", e)
                style_note = (
                    "\n\n(Style profile could not be built this pass — "
                    "your files were still indexed for search.)"
                )

            if skipped_oversize:
                summary += f"\nSkipped {skipped_oversize} oversized file(s) (>25 MB)."

            return ToolResult(
                text=summary + style_note + profile_update,
                data={
                    "files_ingested": len(docs),
                    "files_skipped": skipped_oversize,
                    **style_data,
                },
                side_effects=[f"Ingested {len(docs)} files from {raw_path}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to ingest materials: {e}")

    @staticmethod
    def _too_big(path: Path) -> bool:
        try:
            return path.stat().st_size > _MAX_FILE_BYTES
        except OSError:
            return False

    async def _build_style_profile(
        self,
        docs: list[Any],
        params: dict[str, Any],
        resolved: Path,
        context: AgentContext,
        files_skipped: int = 0,
    ) -> tuple[str, dict[str, Any]]:
        """Build + save + activate the style profile. Returns (note, data)."""
        from clawed import style_profile as sp

        name = str(params.get("profile_name") or "").strip() or resolved.stem or "My Materials"

        llm = None
        try:
            from clawed.demo import is_demo_mode
            from clawed.llm import LLMClient
            if context.config is not None and not is_demo_mode(config=context.config):
                llm = LLMClient(context.config)
        except Exception:
            llm = None

        profile = await sp.build_profile(
            docs,
            name=name,
            source_path=str(resolved),
            llm=llm,
            files_skipped=files_skipped,
            progress_callback=context.notify_progress,
        )
        sp.save_profile(profile)
        sp.set_active_profile(profile.profile_id)

        note_lines = [
            "",
            f"**Style profile \"{profile.name}\" saved and active** — "
            "new lessons and assessments will match your voice.",
        ]
        if profile.structure_summary:
            note_lines.append(profile.structure_summary)
        if profile.voice_description:
            note_lines.append(profile.voice_description)
        return "\n".join(note_lines), {
            "style_profile_id": profile.profile_id,
            "style_profile_name": profile.name,
        }

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
