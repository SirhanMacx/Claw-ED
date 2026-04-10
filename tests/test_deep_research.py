"""Tests for clawed.deep_research — parallel sub-query research synthesis."""

from unittest.mock import AsyncMock

import pytest

from clawed.deep_research import deep_research


def _make_mock_llm(decomposition_response: str = "", research_response: str = ""):
    """Build a mock LLMClient that returns controlled responses."""
    llm = AsyncMock()

    call_count = 0

    async def _generate(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call is the decomposition; subsequent calls are sub-question research
        if call_count == 1:
            return decomposition_response
        return research_response

    llm.generate = AsyncMock(side_effect=_generate)
    return llm


# ── Decomposition ─────────────────────────────────────────────────────


class TestDecomposition:
    """The decomposition step should produce sub-questions from a topic."""

    @pytest.mark.asyncio
    async def test_decomposition_produces_questions(self):
        """LLM is asked to decompose; numbered lines become sub-questions."""
        decomposition = (
            "1. What were the major causes of WWI?\n"
            "2. Who were the key leaders during WWI?\n"
            "3. What was the impact on civilian populations?\n"
        )
        llm = _make_mock_llm(
            decomposition_response=decomposition,
            research_response="WWI began in 1914 after the assassination of Archduke Franz Ferdinand.",
        )

        await deep_research(
            topic="World War I",
            subject="History",
            grade="10",
            llm=llm,
        )

        # The decomposition prompt was the first call
        first_call_prompt = llm.generate.call_args_list[0][0][0]
        assert "World War I" in first_call_prompt
        assert "sub-question" in first_call_prompt.lower() or "break" in first_call_prompt.lower()

    @pytest.mark.asyncio
    async def test_decomposition_failure_produces_fallback(self):
        """If decomposition fails, a fallback single question is used."""
        llm = AsyncMock()
        llm.generate = AsyncMock(
            side_effect=[
                Exception("LLM timeout"),  # decomposition fails
            ]
        )

        report = await deep_research(
            topic="Photosynthesis",
            subject="Biology",
            grade="9",
            llm=llm,
        )

        assert "Photosynthesis" in report
        assert "decomposition failed" in report.lower()


# ── Parallel research ─────────────────────────────────────────────────


class TestParallelResearch:
    """Sub-questions should be researched concurrently."""

    @pytest.mark.asyncio
    async def test_parallel_research(self):
        """Each sub-question results in a research call."""
        decomposition = (
            "1. What caused the French Revolution?\n2. Who were the key figures?\n3. What were the outcomes?\n"
        )
        llm = _make_mock_llm(
            decomposition_response=decomposition,
            research_response="The French Revolution began in 1789.",
        )

        await deep_research(
            topic="French Revolution",
            subject="History",
            grade="10",
            llm=llm,
        )

        # 1 decomposition call + 3 research calls = 4 total
        assert llm.generate.call_count == 4

    @pytest.mark.asyncio
    async def test_report_contains_all_findings(self):
        """The final report includes sections for each sub-question."""
        decomposition = "1. What are the causes?\n2. What are the effects?\n"
        llm = _make_mock_llm(
            decomposition_response=decomposition,
            research_response="Finding details here.",
        )

        report = await deep_research(
            topic="Climate Change",
            subject="Science",
            grade="8",
            llm=llm,
        )

        assert "Research Report" in report
        assert "Climate Change" in report
        assert "## 1." in report
        assert "## 2." in report

    @pytest.mark.asyncio
    async def test_max_sub_queries_respected(self):
        """No more than max_sub_queries questions are researched."""
        decomposition = "\n".join(f"{i}. Question number {i}?" for i in range(1, 11))
        llm = _make_mock_llm(
            decomposition_response=decomposition,
            research_response="Answer here.",
        )

        await deep_research(
            topic="Big Topic",
            subject="General",
            grade="7",
            llm=llm,
            max_sub_queries=3,
        )

        # 1 decomposition + 3 research (capped) = 4
        assert llm.generate.call_count == 4


# ── Humanize applied ─────────────────────────────────────────────────


class TestHumanizeApplied:
    """The final report should be passed through humanize()."""

    @pytest.mark.asyncio
    async def test_humanize_applied_to_report(self):
        """AI-isms in the research output should be cleaned."""
        decomposition = "1. What were the key factors?\n"
        # The research response contains AI-isms that humanize should catch
        research_text = (
            "Let us delve into the multifaceted landscape of this topic. "
            "Moreover, we should utilize primary sources to leverage understanding."
        )
        llm = _make_mock_llm(
            decomposition_response=decomposition,
            research_response=research_text,
        )

        report = await deep_research(
            topic="Test Topic",
            subject="Test",
            grade="9",
            llm=llm,
        )

        # humanize() should have caught these tier-1 words
        assert "delve" not in report.lower()
        assert "utilize" not in report.lower()
        assert "Moreover" not in report


# ── Empty / edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case handling for empty or degenerate inputs."""

    @pytest.mark.asyncio
    async def test_empty_topic(self):
        """Empty topic should still produce some output (not crash)."""
        decomposition = "1. What is this about?\n"
        llm = _make_mock_llm(
            decomposition_response=decomposition,
            research_response="General information.",
        )

        report = await deep_research(
            topic="",
            subject="",
            grade="",
            llm=llm,
        )

        # Should return a string without crashing
        assert isinstance(report, str)
        assert len(report) > 0

    @pytest.mark.asyncio
    async def test_decomposition_returns_no_numbered_lines(self):
        """If LLM returns prose instead of numbered questions, fallback is used."""
        llm = _make_mock_llm(
            decomposition_response="This is a great topic to research in depth.",
            research_response="Some facts about the topic.",
        )

        report = await deep_research(
            topic="Ancient Egypt",
            subject="History",
            grade="6",
            llm=llm,
        )

        # Should still produce a report using the fallback question
        assert isinstance(report, str)
        assert "Research Report" in report
