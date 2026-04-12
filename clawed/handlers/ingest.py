"""File and path ingestion handler. Extracted from tg.py lines 1361-1481.

v2.3.7: Background ingestion — returns immediately with acknowledgment,
runs the heavy work in a background thread, and sends a completion
message via progress_callback when finished.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from clawed.gateway_response import GatewayResponse

logger = logging.getLogger(__name__)

MAX_INGEST_FILES = 500

# Limit concurrent ingestion threads to prevent resource exhaustion
_ingest_semaphore = threading.Semaphore(3)


def ingest_path(path, **kwargs):
    from clawed.ingestor import ingest_path as _ingest
    return _ingest(path, **kwargs)


async def extract_persona(documents, config=None):
    from clawed.persona import extract_persona as _extract
    return await _extract(documents, config)


class IngestHandler:
    async def handle(
        self,
        teacher_id: str,
        files: list[Path] | None = None,
        path: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> GatewayResponse:
        if not files and not path:
            return GatewayResponse(
                text="Send me your teaching files (PDF, DOCX, PPTX, TXT) or paste a folder path "
                "and I'll learn your teaching style."
            )
        target = Path(path).expanduser().resolve() if path else None

        # Guard: check total file count before ingesting a directory
        try:
            if target and target.is_dir():
                all_files = list(target.rglob("*"))
                all_files = [f for f in all_files if f.is_file()]
                if len(all_files) > MAX_INGEST_FILES:
                    logger.warning(
                        "Ingestion path has %d files, truncating to %d",
                        len(all_files), MAX_INGEST_FILES,
                    )
                    return GatewayResponse(
                        text=f"Found {len(all_files)} files, which exceeds the "
                             f"maximum of {MAX_INGEST_FILES}. Please narrow the "
                             f"folder or split into smaller batches."
                    )
            if files and len(files) > MAX_INGEST_FILES:
                return GatewayResponse(
                    text=f"Received {len(files)} files, which exceeds the "
                         f"maximum of {MAX_INGEST_FILES}. Please send fewer files."
                )
        except Exception as e:
            logger.error("Pre-flight check failed: %s", e)
            return GatewayResponse(text=f"Could not check files: {e}")

        # Limit concurrent ingestions
        if not _ingest_semaphore.acquire(blocking=False):
            return GatewayResponse(
                text="I'm still processing previous files. Please wait a moment."
            )

        # Launch background ingestion and return immediately
        if files:
            ack_text = f"Starting to index {len(files)} file(s) now. I'll let you know when it's done."
        else:
            ack_text = "Starting to index your files now. I'll let you know when it's done."

        thread = threading.Thread(
            target=self._ingest_sync,
            args=(teacher_id, files, target, progress_callback),
            daemon=False,
        )
        thread.start()

        return GatewayResponse(text=ack_text)

    def _ingest_sync(
        self,
        teacher_id: str,
        files: list[Path] | None,
        target: Path | None,
        progress_callback: Callable[[str], None] | None,
    ) -> None:
        """Run ingestion synchronously in a background thread."""
        try:
            documents, failures = self._extract_documents(files, target, progress_callback)
            if not documents:
                self._notify(progress_callback, "No documents found to ingest.")
                return

            self._notify(
                progress_callback,
                f"Extracted {len(documents)} document(s). Now learning your teaching style..."
            )

            style_info = self._extract_persona_sync(documents)
            kb_info = self._index_documents(teacher_id, documents, progress_callback)
            asset_info = self._register_assets(teacher_id, documents)

            summary = f"Done! Ingested {len(documents)} document(s).{style_info}{kb_info}{asset_info}"
            if failures:
                summary += f"\n({failures} file(s) could not be parsed — check logs for details.)"
            self._notify(progress_callback, summary)

        except Exception as e:
            logger.error("Background ingestion failed: %s", e)
            self._notify(progress_callback, f"Ingestion failed: {e}")
        finally:
            _ingest_semaphore.release()

    def _extract_documents(
        self,
        files: list[Path] | None,
        target: Path | None,
        progress_callback: Callable[[str], None] | None,
    ) -> tuple[list, int]:
        """Extract documents from files or directory.

        Returns:
            (documents, failure_count) tuple.
        """
        documents = []
        failures = 0
        if target and target.exists():
            try:
                documents = ingest_path(str(target))
            except Exception as e:
                logger.warning("Failed to parse %s: %s", target, e)
                failures += 1
        elif files:
            for i, f in enumerate(files):
                try:
                    documents.extend(ingest_path(str(f)))
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", f, e)
                    failures += 1
                if progress_callback and len(files) > 1 and (i + 1) % 5 == 0:
                    self._notify(
                        progress_callback,
                        f"Processed {i + 1}/{len(files)} files..."
                    )
        return documents, failures

    def _extract_persona_sync(self, documents: list) -> str:
        """Extract persona from documents (runs async in sync context)."""
        try:
            from clawed.models import AppConfig
            loop = asyncio.new_event_loop()
            try:
                persona = loop.run_until_complete(
                    extract_persona(documents, AppConfig.load())
                )
            finally:
                loop.close()

            # Override LLM-inferred name with configured teacher name
            try:
                config = AppConfig.load()
                if config.teacher_profile and config.teacher_profile.name:
                    persona.name = f"{config.teacher_profile.name} Teaching Persona"
            except Exception:
                logger.debug("operation_failed", exc_info=True)
            try:
                from clawed.paths import workspace_dir as _ws_dir
                _id_path = _ws_dir() / "identity.md"
                if _id_path.exists():
                    import re as _re
                    _id_content = _id_path.read_text(encoding="utf-8")
                    _name_match = _re.match(r"^#\s+(.+)", _id_content)
                    if _name_match:
                        _tname = _name_match.group(1).strip()
                        if _tname and _tname != "Teacher":
                            persona.name = f"{_tname} Teaching Persona"
            except (FileNotFoundError, OSError):
                pass

            from clawed.paths import data_dir as _dd
            from clawed.persona import save_persona
            save_persona(persona, _dd())

            style_info = f"\nLearned teaching style: {persona.teaching_style}"
            if persona.tone:
                style_info += f", Tone: {persona.tone}"
            if persona.subject_area:
                style_info += f", Subject: {persona.subject_area}"
            return style_info
        except Exception as e:
            logger.debug("Persona extraction skipped: %s", e)
            return ""

    def _index_documents(
        self,
        teacher_id: str,
        documents: list,
        progress_callback: Callable[[str], None] | None,
    ) -> str:
        """Index documents into curriculum knowledge base with progress."""
        try:
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB
            kb = CurriculumKB()
            total_chunks = 0
            for i, doc in enumerate(documents):
                doc_type_val = doc.doc_type.value if hasattr(doc.doc_type, "value") else str(doc.doc_type)
                chunks_added = kb.index(
                    teacher_id=teacher_id,
                    doc_title=doc.title,
                    source_path=doc.source_path or "",
                    full_text=doc.content,
                    metadata={"doc_type": doc_type_val},
                )
                total_chunks += chunks_added
                if progress_callback and len(documents) > 20 and (i + 1) % 50 == 0:
                    self._notify(
                        progress_callback,
                        f"Indexed {i + 1}/{len(documents)} documents ({total_chunks} searchable sections)..."
                    )

            stats = kb.stats(teacher_id)
            return (
                f"\n\nAdded to your curriculum library — I now have "
                f"{stats['doc_count']} document(s) ({stats['chunk_count']} "
                f"searchable sections). I'll reference your materials when "
                f"creating new content."
            )
        except Exception as e:
            logger.debug("KB indexing skipped: %s", e)
            return ""

    def _register_assets(self, teacher_id: str, documents: list) -> str:
        """Register assets (files, images, YouTube links) for search."""
        try:
            from clawed.asset_registry import AssetRegistry
            registry = AssetRegistry()
            asset_count = 0
            for doc in documents:
                doc_type_val = doc.doc_type.value if hasattr(doc.doc_type, "value") else str(doc.doc_type)
                extraction = None
                if doc.source_path:
                    try:
                        from clawed.ingestor import extract_rich
                        extraction = extract_rich(Path(doc.source_path))
                    except (FileNotFoundError, OSError):
                        pass
                aid = registry.register_asset(
                    teacher_id=teacher_id,
                    source_path=doc.source_path or "",
                    title=doc.title,
                    doc_type=doc_type_val,
                    text=doc.content,
                    extraction=extraction,
                )
                if aid:
                    asset_count += 1
            if asset_count:
                return f" ({asset_count} files catalogued with images and links)"
        except Exception as e:
            logger.debug("Asset registration skipped: %s", e)
        return ""

    @staticmethod
    def _notify(callback: Callable[[str], None] | None, msg: str) -> None:
        """Send a progress notification if callback is available."""
        if callback:
            try:
                callback(msg)
            except Exception as e:
                logger.debug("Progress notification failed: %s", e)
