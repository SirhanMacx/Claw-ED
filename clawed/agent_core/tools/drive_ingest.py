"""Drive ingest tool — Ed can pull curriculum from Google Drive into his KB."""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class DriveIngestTool:
    """Ingest curriculum files from a Google Drive folder into the KB."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "drive_ingest",
                "description": (
                    "Ingest curriculum files from a Google Drive folder into "
                    "the knowledge base. Downloads supported files (PDF, DOCX, "
                    "PPTX, TXT, Google Docs) and indexes them for search."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "folder_id": {
                            "type": "string",
                            "description": "Google Drive folder ID or URL",
                        },
                    },
                    "required": ["folder_id"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        folder_input = params.get("folder_id", "")
        if not folder_input:
            return ToolResult(text="ERROR: folder_id is required")

        # Extract ID from URL if needed
        import re

        match = re.search(r"folders/([a-zA-Z0-9_-]+)", folder_input)
        folder_id = match.group(1) if match else folder_input

        try:
            from clawed.agent_core.drive.auth import is_authenticated

            if not is_authenticated():
                from clawed.agent_core.drive.auth import get_auth_url

                url = get_auth_url()
                if url:
                    return ToolResult(
                        text=f"I need Google Drive access first. Please visit this URL to authorize:\n{url}"
                    )
                return ToolResult(text="Google Drive is not set up yet. Run `clawed drive auth` to connect your Drive.")

            from clawed.agent_core.drive.client import DriveClient
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB

            client = DriveClient()
            kb = CurriculumKB()
            teacher_id = context.teacher_id

            files = client.list_files(folder_id=folder_id)
            if not files:
                return ToolResult(text="No files found in that Drive folder.")

            supported_mimes = {
                "application/pdf",
                "application/vnd.google-apps.document",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "text/plain",
                "text/markdown",
            }
            ingestable = [f for f in files if f.get("mimeType") in supported_mimes]

            if not ingestable:
                return ToolResult(
                    text=(
                        f"Found {len(files)} files but none are supported "
                        "formats (PDF, DOCX, PPTX, TXT, MD, Google Docs)."
                    )
                )

            total_chunks = 0
            ingested = []
            errors = []

            for f in ingestable:
                try:
                    content_data = client.read_file(f["id"])
                    content = content_data.get("content", "")
                    if not content or len(content.strip()) < 50:
                        continue

                    chunks = kb.index(
                        teacher_id=teacher_id,
                        doc_title=f["name"],
                        source_path=f"drive://{f['id']}",
                        full_text=content,
                        metadata={"source": "google_drive", "mime_type": f.get("mimeType", "")},
                    )
                    total_chunks += chunks
                    ingested.append(f["name"])
                except Exception as e:
                    errors.append(f"{f['name']}: {e}")

            stats = kb.stats(teacher_id)
            parts = [
                f"Ingested {len(ingested)} files ({total_chunks} chunks).",
                f"Knowledge base: {stats['doc_count']} docs, {stats['chunk_count']} total chunks.",
            ]
            if errors:
                parts.append(f"Errors: {'; '.join(errors[:3])}")

            return ToolResult(text="\n".join(parts))

        except Exception as e:
            logger.error("Drive ingest failed: %s", e)
            return ToolResult(text=f"Drive ingest failed: {e}")
