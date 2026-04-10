"""Tests for LLM-enhanced reading report — qualitative observations layer.

Tests the excerpt selection, prompt building, LLM integration, and
graceful fallback when the LLM call fails.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from clawed.models import DocType, Document
from clawed.reading_report import (
    _build_llm_reading_prompt,
    _select_representative_excerpts,
    format_reading_report,
    generate_reading_report,
)

# ── Fixture helper ────────────────────────────────────────────────────


def _make_docs(n: int) -> list[Document]:
    """Create *n* sample Documents with varied doc types and content.

    Cycles through doc types and topics so selection tests can verify
    diversity.
    """
    types = [DocType.DOCX, DocType.PDF, DocType.PPTX, DocType.TXT]
    topics = [
        (
            "American Revolution Lesson Plan\n"
            "Teacher: Mr. Mac\n"
            "Do Now: Alright friends, what does 'revolution' mean?\n"
            "Students will analyze primary sources from 1776.\n"
            "Exit Ticket: Name two causes of the American Revolution."
        ),
        (
            "Civil War DBQ Activity\n"
            "AIM: How did the Civil War change America?\n"
            "Gallery Walk: Students examine photographs from Gettysburg.\n"
            "Think-Pair-Share: Discuss the Emancipation Proclamation."
        ),
        (
            "Constitution Jigsaw\n"
            "SWBAT: Explain the Bill of Rights\n"
            "Station Rotation: Groups analyze different amendments.\n"
            "Socratic Seminar: Is the Constitution a living document?"
        ),
        (
            "Cold War Unit Overview\n"
            "Essential Question: How did fear shape American policy?\n"
            "Primary Source Analysis: Kennedy's inaugural address.\n"
            "Debate: Was containment the right strategy?"
        ),
        (
            "Immigration Through Ellis Island\n"
            "Do Now: Okay scholars, imagine you just arrived in a new country.\n"
            "Vocabulary: nativism, assimilation, tenement\n"
            "Exit Ticket: Compare two immigrant experiences."
        ),
    ]
    docs = []
    for i in range(n):
        doc_type = types[i % len(types)]
        topic = topics[i % len(topics)]
        docs.append(
            Document(
                title=f"Doc {i + 1}",
                content=topic,
                doc_type=doc_type,
                source_path=f"/fake/path/doc_{i + 1}.{doc_type.value}",
            )
        )
    return docs


# ── _select_representative_excerpts ──────────────────────────────────


class TestSelectRepresentativeExcerpts:
    def test_picks_varied_doc_types(self):
        """Excerpts should include documents from multiple doc types."""
        docs = _make_docs(12)
        excerpts = _select_representative_excerpts(docs, max_excerpts=8)

        # Should have selected at most 8
        assert len(excerpts) <= 8
        assert len(excerpts) >= 1

        # Should include more than one doc type
        types_seen = {doc.doc_type for doc in excerpts}
        assert len(types_seen) > 1, f"Expected multiple doc types, got only {types_seen}"

    def test_respects_max_excerpts(self):
        docs = _make_docs(20)
        excerpts = _select_representative_excerpts(docs, max_excerpts=5)
        assert len(excerpts) == 5

    def test_handles_fewer_docs_than_max(self):
        docs = _make_docs(3)
        excerpts = _select_representative_excerpts(docs, max_excerpts=8)
        assert len(excerpts) == 3

    def test_empty_docs_returns_empty(self):
        excerpts = _select_representative_excerpts([], max_excerpts=8)
        assert excerpts == []

    def test_single_doc(self):
        docs = _make_docs(1)
        excerpts = _select_representative_excerpts(docs, max_excerpts=8)
        assert len(excerpts) == 1

    def test_varied_topics(self):
        """With enough docs, excerpts should cover different content."""
        docs = _make_docs(10)
        excerpts = _select_representative_excerpts(docs, max_excerpts=8)
        # All excerpts should have content (not empty)
        for doc in excerpts:
            assert len(doc.content) > 0


# ── _build_llm_reading_prompt ────────────────────────────────────────


class TestBuildLlmReadingPrompt:
    def test_includes_regex_data(self):
        """Prompt should contain stats from the regex report."""
        report = generate_reading_report(_make_docs(5))
        excerpts = _select_representative_excerpts(_make_docs(5), max_excerpts=3)
        prompt = _build_llm_reading_prompt(report, excerpts)

        # Should mention the document count
        assert "5" in prompt
        # Should include at least one topic from coverage
        assert any(topic in prompt for topic in ["American Revolution", "Civil War", "Constitution"])

    def test_includes_excerpts(self):
        """Prompt should contain actual document text."""
        docs = _make_docs(3)
        report = generate_reading_report(docs)
        excerpts = _select_representative_excerpts(docs, max_excerpts=3)
        prompt = _build_llm_reading_prompt(report, excerpts)

        # Should contain text from the excerpts
        assert "Doc 1" in prompt or "revolution" in prompt.lower()

    def test_prompt_requests_json_array(self):
        """Prompt should instruct the LLM to return a JSON array."""
        report = generate_reading_report(_make_docs(2))
        excerpts = _select_representative_excerpts(_make_docs(2), max_excerpts=2)
        prompt = _build_llm_reading_prompt(report, excerpts)
        assert "JSON" in prompt


# ── generate_reading_report (without LLM) ───────────────────────────


class TestGenerateReadingReportWithoutLlm:
    def test_report_has_llm_observations_none(self):
        """Before LLM pass, llm_observations should be None."""
        report = generate_reading_report(_make_docs(5))
        assert "llm_observations" in report
        assert report["llm_observations"] is None

    def test_report_has_excerpts_for_llm(self):
        """Report should store excerpts for the async LLM pass."""
        report = generate_reading_report(_make_docs(8))
        assert "_excerpts_for_llm" in report
        assert isinstance(report["_excerpts_for_llm"], list)
        assert len(report["_excerpts_for_llm"]) > 0

    def test_regex_analysis_still_works(self):
        """All existing regex-based fields should still be populated."""
        docs = _make_docs(5)
        report = generate_reading_report(docs)
        assert report["doc_stats"]["total"] == 5
        assert len(report["topic_coverage"]) > 0
        assert len(report["favorite_strategies"]) > 0

    def test_empty_docs_has_llm_observations_none(self):
        """Even with no docs, llm_observations should be None (not missing)."""
        report = generate_reading_report([])
        assert report["llm_observations"] is None


# ── enhance_reading_report_with_llm ─────────────────────────────────


class TestEnhanceReadingReportWithLlm:
    @pytest.mark.asyncio
    async def test_stores_observations_on_success(self):
        """Successful LLM call should populate llm_observations."""
        from clawed.reading_report import enhance_reading_report_with_llm

        report = generate_reading_report(_make_docs(5))
        fake_observations = [
            "Your Do Nows consistently use open-ended questions that activate prior knowledge.",
            "There is a clear progression from teacher-led to student-centered activities.",
            "Your assessment questions align well with the stated learning objectives.",
        ]

        with patch("clawed.llm.LLMClient") as mock_client:
            instance = mock_client.return_value
            instance.generate_json = AsyncMock(return_value=fake_observations)
            await enhance_reading_report_with_llm(report)

        assert report["llm_observations"] == fake_observations

    @pytest.mark.asyncio
    async def test_falls_back_on_llm_failure(self):
        """If LLM call raises, llm_observations should become empty list."""
        from clawed.reading_report import enhance_reading_report_with_llm

        report = generate_reading_report(_make_docs(5))

        with patch("clawed.llm.LLMClient") as mock_client:
            instance = mock_client.return_value
            instance.generate_json = AsyncMock(side_effect=ConnectionError("No API key"))
            await enhance_reading_report_with_llm(report)

        # Should be empty list (ran but got nothing), not None (not yet run)
        assert report["llm_observations"] == []

    @pytest.mark.asyncio
    async def test_falls_back_on_invalid_response(self):
        """If LLM returns non-list, llm_observations should become empty list."""
        from clawed.reading_report import enhance_reading_report_with_llm

        report = generate_reading_report(_make_docs(5))

        with patch("clawed.llm.LLMClient") as mock_client:
            instance = mock_client.return_value
            # LLM returns a dict instead of a list
            instance.generate_json = AsyncMock(return_value={"error": "unexpected format"})
            await enhance_reading_report_with_llm(report)

        assert report["llm_observations"] == []

    @pytest.mark.asyncio
    async def test_no_excerpts_skips_llm(self):
        """If report has no excerpts, LLM call should be skipped."""
        from clawed.reading_report import enhance_reading_report_with_llm

        report = generate_reading_report([])

        with patch("clawed.llm.LLMClient") as mock_client:
            instance = mock_client.return_value
            instance.generate_json = AsyncMock()
            await enhance_reading_report_with_llm(report)
            instance.generate_json.assert_not_called()

        assert report["llm_observations"] is None


# ── format_reading_report with LLM observations ─────────────────────


class TestFormatReadingReportWithLlm:
    def test_includes_llm_section_when_present(self):
        """Formatted report should include LLM observations section."""
        report = generate_reading_report(_make_docs(5))
        report["llm_observations"] = [
            "Your lessons show a strong commitment to primary source analysis.",
            "The Do Now prompts create genuine curiosity, not just recall.",
        ]
        text = format_reading_report(report)
        assert "what stood out to me" in text.lower()
        assert "primary source analysis" in text

    def test_omits_llm_section_when_none(self):
        """When llm_observations is None, no LLM section should appear."""
        report = generate_reading_report(_make_docs(5))
        assert report["llm_observations"] is None
        text = format_reading_report(report)
        assert "what stood out" not in text.lower()

    def test_omits_llm_section_when_empty(self):
        """When llm_observations is empty list, no LLM section should appear."""
        report = generate_reading_report(_make_docs(5))
        report["llm_observations"] = []
        text = format_reading_report(report)
        assert "what stood out" not in text.lower()
