"""Tests for the ingestion pipeline — format detection, extractors, dry-run, progress."""

import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

from clawed.ingestor import (
    EXTENSION_MAP,
    SUPPORTED_EXTENSIONS,
    _collect_files,
    _detect_type,
    _dry_run_results,
    _extract_single,
    _extract_text,
    _format_summary,
    ingest_directory,
    ingest_path,
    scan_directory,
)
from clawed.models import DocType

# ── Extension map ────────────────────────────────────────────────────


class TestExtensionMap:
    def test_all_supported_extensions_in_map(self):
        assert SUPPORTED_EXTENSIONS == set(EXTENSION_MAP.keys())

    def test_new_formats_in_map(self):
        assert ".notebook" in EXTENSION_MAP
        assert ".xbk" in EXTENSION_MAP
        assert ".flipchart" in EXTENSION_MAP
        assert EXTENSION_MAP[".notebook"] == DocType.NOTEBOOK
        assert EXTENSION_MAP[".xbk"] == DocType.XBK
        assert EXTENSION_MAP[".flipchart"] == DocType.FLIPCHART


# ── Type detection ───────────────────────────────────────────────────


class TestDetectType:
    @pytest.mark.parametrize(
        "ext,expected",
        [
            (".pdf", DocType.PDF),
            (".docx", DocType.DOCX),
            (".pptx", DocType.PPTX),
            (".txt", DocType.TXT),
            (".md", DocType.MD),
            (".notebook", DocType.NOTEBOOK),
            (".xbk", DocType.XBK),
            (".flipchart", DocType.FLIPCHART),
        ],
    )
    def test_known_extensions(self, ext, expected):
        assert _detect_type(Path(f"lesson{ext}")) == expected

    def test_unknown_extension(self):
        assert _detect_type(Path("lesson.xyz")) == DocType.UNKNOWN

    def test_case_insensitive(self):
        assert _detect_type(Path("LESSON.PDF")) == DocType.PDF
        assert _detect_type(Path("file.NOTEBOOK")) == DocType.NOTEBOOK


# ── Plain text extraction ────────────────────────────────────────────


class TestExtractText:
    def test_reads_txt(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Today we learned about photosynthesis.", encoding="utf-8")
        assert _extract_text(f) == "Today we learned about photosynthesis."

    def test_reads_md(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("# Lesson Plan\n\nObjective: ...", encoding="utf-8")
        result = _extract_text(f)
        assert "# Lesson Plan" in result


# ── SMART Notebook extraction ────────────────────────────────────────


def _make_notebook_zip(dest: Path, pages: list[str]) -> Path:
    """Create a minimal .notebook (ZIP with XML pages)."""
    notebook_path = dest / "lesson.notebook"
    with zipfile.ZipFile(str(notebook_path), "w") as zf:
        for i, text in enumerate(pages):
            root = Element("page")
            child = SubElement(root, "text")
            child.text = text
            zf.writestr(f"page{i:03d}.xml", tostring(root, encoding="unicode"))
    return notebook_path


class TestNotebookExtractor:
    def test_extracts_text(self, tmp_path):
        path = _make_notebook_zip(tmp_path, ["Slide 1: Intro", "Slide 2: Main idea"])
        doc = _extract_single(path)
        assert doc is not None
        assert doc.doc_type == DocType.NOTEBOOK
        assert "Slide 1: Intro" in doc.content
        assert "Slide 2: Main idea" in doc.content

    def test_empty_notebook(self, tmp_path):
        path = _make_notebook_zip(tmp_path, [])
        doc = _extract_single(path)
        assert doc is None

    def test_corrupt_notebook(self, tmp_path):
        path = tmp_path / "bad.notebook"
        path.write_bytes(b"not a zip file")
        doc = _extract_single(path)
        assert doc is None


# ── XBK extraction ───────────────────────────────────────────────────


def _make_xbk_zip(dest: Path, texts: list[str]) -> Path:
    """Create a minimal .xbk (ZIP with XML pages)."""
    xbk_path = dest / "lesson.xbk"
    with zipfile.ZipFile(str(xbk_path), "w") as zf:
        for i, text in enumerate(texts):
            root = Element("board")
            child = SubElement(root, "content")
            child.text = text
            zf.writestr(f"page{i:03d}.xml", tostring(root, encoding="unicode"))
    return xbk_path


def _make_xbk_plain_xml(dest: Path, text: str) -> Path:
    """Create a plain-XML .xbk file."""
    xbk_path = dest / "lesson.xbk"
    root = Element("board")
    child = SubElement(root, "content")
    child.text = text
    xbk_path.write_bytes(tostring(root))
    return xbk_path


class TestXbkExtractor:
    def test_zip_based_xbk(self, tmp_path):
        path = _make_xbk_zip(tmp_path, ["Page 1 content", "Page 2 content"])
        doc = _extract_single(path)
        assert doc is not None
        assert doc.doc_type == DocType.XBK
        assert "Page 1 content" in doc.content

    def test_plain_xml_xbk(self, tmp_path):
        path = _make_xbk_plain_xml(tmp_path, "Board lesson text")
        doc = _extract_single(path)
        assert doc is not None
        assert "Board lesson text" in doc.content

    def test_corrupt_xbk(self, tmp_path):
        path = tmp_path / "bad.xbk"
        path.write_bytes(b"\x00\x01\x02")
        doc = _extract_single(path)
        assert doc is None


# ── Flipchart extraction ─────────────────────────────────────────────


def _make_flipchart_zip(dest: Path, pages: list[str]) -> Path:
    """Create a minimal .flipchart (ZIP with XML pages)."""
    fc_path = dest / "lesson.flipchart"
    with zipfile.ZipFile(str(fc_path), "w") as zf:
        for i, text in enumerate(pages):
            root = Element("flipchart-page")
            child = SubElement(root, "annotation")
            child.text = text
            zf.writestr(f"page{i:03d}.xml", tostring(root, encoding="unicode"))
    return fc_path


class TestFlipchartExtractor:
    def test_extracts_text(self, tmp_path):
        path = _make_flipchart_zip(tmp_path, ["Welcome to class", "Today's objective"])
        doc = _extract_single(path)
        assert doc is not None
        assert doc.doc_type == DocType.FLIPCHART
        assert "Welcome to class" in doc.content

    def test_empty_flipchart(self, tmp_path):
        path = _make_flipchart_zip(tmp_path, [])
        doc = _extract_single(path)
        assert doc is None


# ── Format summary ───────────────────────────────────────────────────


class TestFormatSummary:
    def test_summary_output(self, tmp_path):
        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.pdf").touch()
        (tmp_path / "c.docx").touch()
        (tmp_path / "d.txt").touch()
        files = _collect_files(tmp_path)
        summary = _format_summary(files)
        assert "2 PDF" in summary
        assert "1 DOCX" in summary
        assert "1 TXT" in summary
        assert "analyzing..." in summary

    def test_empty_summary(self):
        assert _format_summary([]) == "Found  — analyzing..."


# ── Scan directory ───────────────────────────────────────────────────


class TestScanDirectory:
    def test_scan_returns_files_and_summary(self, tmp_path):
        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.txt").touch()
        (tmp_path / "c.jpg").touch()  # unsupported
        files, summary = scan_directory(tmp_path)
        assert len(files) == 2
        assert "PDF" in summary
        assert "TXT" in summary

    def test_scan_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            scan_directory(tmp_path / "nope")


# ── Dry run ──────────────────────────────────────────────────────────


class TestDryRun:
    def test_dry_run_returns_placeholders(self, tmp_path):
        (tmp_path / "a.txt").write_text("Hello", encoding="utf-8")
        (tmp_path / "b.md").write_text("# Plan", encoding="utf-8")
        docs = ingest_path(tmp_path, dry_run=True)
        assert len(docs) == 2
        for doc in docs:
            assert doc.content == "[dry-run: content not extracted]"
            assert doc.source_path is not None

    def test_dry_run_skips_unsupported(self, tmp_path):
        (tmp_path / "a.txt").write_text("Hello", encoding="utf-8")
        (tmp_path / "b.jpg").write_bytes(b"\xff\xd8")
        docs = ingest_path(tmp_path, dry_run=True)
        assert len(docs) == 1

    def test_dry_run_results_helper(self, tmp_path):
        files = [tmp_path / "a.txt", tmp_path / "b.docx", tmp_path / "c.xyz"]
        for f in files:
            f.touch()
        results = _dry_run_results(files)
        assert len(results) == 2  # .xyz is UNKNOWN, skipped
        assert all(d.content == "[dry-run: content not extracted]" for d in results)


# ── Progress callback ────────────────────────────────────────────────


class TestProgressCallback:
    def test_callback_invoked(self, tmp_path):
        (tmp_path / "a.txt").write_text("Hello", encoding="utf-8")
        (tmp_path / "b.txt").write_text("World", encoding="utf-8")
        calls: list[tuple[int, int]] = []
        ingest_directory(tmp_path, progress_callback=lambda c, t: calls.append((c, t)))
        assert len(calls) == 2
        assert calls[-1] == (2, 2)


# ── Ingest directory with new formats ─────────────────────────────────


class TestIngestDirectoryNewFormats:
    def test_txt_and_md(self, tmp_path):
        (tmp_path / "notes.txt").write_text("Lesson notes here.", encoding="utf-8")
        (tmp_path / "plan.md").write_text("# Unit Plan\n\nDetails...", encoding="utf-8")
        docs = ingest_directory(tmp_path)
        assert len(docs) == 2
        types = {d.doc_type for d in docs}
        assert DocType.TXT in types
        assert DocType.MD in types

    def test_notebook_in_directory(self, tmp_path):
        _make_notebook_zip(tmp_path, ["Interactive lesson content"])
        docs = ingest_directory(tmp_path)
        assert len(docs) == 1
        assert docs[0].doc_type == DocType.NOTEBOOK

    def test_mixed_formats(self, tmp_path):
        (tmp_path / "notes.txt").write_text("Text content", encoding="utf-8")
        _make_notebook_zip(tmp_path, ["Notebook content"])
        _make_xbk_zip(tmp_path, ["XBK content"])
        _make_flipchart_zip(tmp_path, ["Flipchart content"])
        docs = ingest_directory(tmp_path)
        types = {d.doc_type for d in docs}
        assert DocType.TXT in types
        assert DocType.NOTEBOOK in types
        assert DocType.XBK in types
        assert DocType.FLIPCHART in types


# ── Title extraction ──────────────────────────────────────────────────


class TestTitleExtraction:
    def test_title_from_filename(self, tmp_path):
        f = tmp_path / "my_lesson-plan.txt"
        f.write_text("content", encoding="utf-8")
        doc = _extract_single(f)
        assert doc is not None
        assert doc.title == "My Lesson Plan"

    def test_unknown_extension_returns_none(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG")
        doc = _extract_single(f)
        assert doc is None
