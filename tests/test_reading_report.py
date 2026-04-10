"""Tests for clawed.reading_report — document analysis and report generation."""

from clawed.models import DocType, Document
from clawed.reading_report import format_reading_report, generate_reading_report


def _make_doc(content: str, doc_type: DocType = DocType.DOCX) -> Document:
    return Document(title="test", content=content, doc_type=doc_type)


def test_detects_teacher_name():
    doc = _make_doc("Teacher: Mr. Mac\n\nDo Now: Alright friends, today we study Dr. King's legacy.")
    report = generate_reading_report([doc])
    assert report["teacher_details"].get("name_used", "") == "Mr. Mac"
    # Should NOT detect "Dr. King" from body content


def test_excludes_historical_figures():
    doc = _make_doc("Dr. King gave a famous speech. Dr. King changed history. Dr. King was born in Atlanta.")
    report = generate_reading_report([doc])
    # "Dr. King" is a historical figure in body text, not the teacher
    assert "King" not in report["teacher_details"].get("name_used", "")


def test_detect_address_terms():
    text = "Alright friends, let's get started. " * 5
    docs = [_make_doc(text)]
    report = generate_reading_report(docs)
    found = [vp for vp in report["voice_patterns"] if "friends" in vp]
    assert len(found) == 1
    assert "friends" in found[0]


def test_detect_topic_coverage():
    docs = [
        _make_doc("The American Revolution changed everything. 1776 was pivotal."),
        _make_doc("The Civil War era saw great conflict at Gettysburg."),
    ]
    report = generate_reading_report(docs)
    assert "American Revolution" in report["topic_coverage"]
    assert "Civil War" in report["topic_coverage"]


def test_detect_strategies():
    docs = [_make_doc("Today's Jigsaw activity will have groups analyze a primary source.")]
    report = generate_reading_report(docs)
    strategies_text = " ".join(report["favorite_strategies"])
    assert "Jigsaw" in strategies_text
    assert "Primary Source" in strategies_text


def test_detect_gaps():
    # Only mention Civil War — other topics should be gaps
    docs = [_make_doc("The Civil War had lasting impacts. Gettysburg was pivotal. " * 3)]
    report = generate_reading_report(docs)
    assert "Cold War" in report["gaps"]
    assert "Immigration" in report["gaps"]


def test_format_produces_readable_text():
    docs = [
        _make_doc("Mr. Smith teaches the American Revolution. Jigsaw activity today."),
        _make_doc("Do Now: What caused the Civil War? Exit Ticket: answer the question."),
    ]
    report = generate_reading_report(docs)
    text = format_reading_report(report)
    assert "I read through 2 files" in text
    assert isinstance(text, str)
    assert len(text) > 50


def test_empty_documents():
    report = generate_reading_report([])
    assert report["doc_stats"] == {}
    assert report["strengths"] == []
    text = format_reading_report(report)
    assert "haven't read" in text


def test_doc_type_stats():
    docs = [
        _make_doc("Content A", DocType.DOCX),
        _make_doc("Content B", DocType.PDF),
        _make_doc("Content C", DocType.DOCX),
    ]
    report = generate_reading_report(docs)
    assert report["doc_stats"]["total"] == 3
    assert report["doc_stats"]["by_type"]["DOCX"] == 2
    assert report["doc_stats"]["by_type"]["PDF"] == 1
