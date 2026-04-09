"""Tests for clawed.compile_journey — interactive learning journey HTML generation."""
from unittest.mock import MagicMock

import pytest

from clawed.compile_journey import compile_journey


def _make_mock_master(
    title="The Water Cycle",
    objective="Students will explain the stages of the water cycle.",
    do_now=None,
    vocabulary=None,
    direct_instruction=None,
    guided_notes=None,
    exit_ticket=None,
):
    """Build a mock MasterContent with controllable fields."""
    mc = MagicMock()
    mc.title = title
    mc.objective = objective

    if do_now is None:
        do_now_obj = MagicMock()
        do_now_obj.stimulus = "What happens to rain after it falls?"
        do_now_obj.questions = ["Where does rainwater go?", "Can water disappear?"]
        mc.do_now = do_now_obj
    else:
        mc.do_now = do_now

    if vocabulary is None:
        v1 = MagicMock()
        v1.term = "Evaporation"
        v1.definition = "The process of water turning into vapor"
        v2 = MagicMock()
        v2.term = "Condensation"
        v2.definition = "Water vapor turning into liquid droplets"
        mc.vocabulary = [v1, v2]
    else:
        mc.vocabulary = vocabulary

    if direct_instruction is None:
        s1 = MagicMock()
        s1.heading = "How Evaporation Works"
        s1.content = "The sun heats water in lakes and oceans..."
        s1.key_points = ["Heat drives evaporation", "Water becomes vapor"]
        s2 = MagicMock()
        s2.heading = "Cloud Formation"
        s2.content = "As water vapor rises, it cools and condenses..."
        s2.key_points = ["Cool air causes condensation", "Clouds form"]
        mc.direct_instruction = [s1, s2]
    else:
        mc.direct_instruction = direct_instruction

    if guided_notes is None:
        gn = MagicMock()
        gn.prompt = "Water turns into vapor through ___"
        gn.answer = "evaporation"
        mc.guided_notes = [gn]
    else:
        mc.guided_notes = guided_notes

    if exit_ticket is None:
        et = MagicMock()
        et.stimulus = "Describe the water cycle."
        et.question = "What are the three main stages?"
        mc.exit_ticket = [et]
    else:
        mc.exit_ticket = exit_ticket

    return mc


# ── Basic HTML output ─────────────────────────────────────────────────


class TestProducesHtml:
    """compile_journey must produce a valid self-contained HTML file."""

    @pytest.mark.asyncio
    async def test_produces_html_file(self, tmp_path):
        """Output should be an .html file on disk."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".html"

    @pytest.mark.asyncio
    async def test_html_has_valid_structure(self, tmp_path):
        """Generated HTML has doctype, head, body, and script."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "<script>" in html
        assert "</html>" in html

    @pytest.mark.asyncio
    async def test_html_contains_title(self, tmp_path):
        """The lesson title should appear in the HTML."""
        mc = _make_mock_master(title="Photosynthesis Basics")
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert "Photosynthesis Basics" in html

    @pytest.mark.asyncio
    async def test_html_contains_objective(self, tmp_path):
        """The lesson objective should appear in the HTML."""
        mc = _make_mock_master(objective="Explain how plants make food.")
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert "Explain how plants make food." in html


# ── Step count matches content ────────────────────────────────────────


class TestStepCountMatchesContent:
    """Number of journey steps should match the MasterContent sections."""

    def _count_steps_in_html(self, html: str) -> int:
        """Extract the step count from the embedded JSON data in the HTML.

        The steps are stored as a JS var: var steps=[...];
        We parse the JSON array to count them.
        """
        import re
        # The JS variable is: var steps=<json>;
        match = re.search(r'var steps=(\[.*?\]);\s*var current', html, re.DOTALL)
        assert match is not None, "Could not find steps JSON in HTML"
        import json
        steps_data = json.loads(match.group(1))
        return len(steps_data)

    @pytest.mark.asyncio
    async def test_step_count_matches_content(self, tmp_path):
        """Steps = do_now + vocabulary + direct_instruction sections + guided_notes + exit_ticket."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        # Expected steps:
        # 1 (do_now) + 1 (vocabulary) + 2 (direct_instruction) + 1 (guided_notes) + 1 (exit_ticket) = 6
        total_steps = self._count_steps_in_html(html)
        assert total_steps == 6

    @pytest.mark.asyncio
    async def test_no_do_now_reduces_steps(self, tmp_path):
        """Without do_now, there should be one fewer step."""
        mc = _make_mock_master(do_now=None)
        mc.do_now = None
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        total_steps = self._count_steps_in_html(html)
        # Without do_now: 1 (vocab) + 2 (instruction) + 1 (guided) + 1 (exit) = 5
        assert total_steps == 5

    @pytest.mark.asyncio
    async def test_no_vocabulary_reduces_steps(self, tmp_path):
        """Without vocabulary, there should be one fewer step."""
        mc = _make_mock_master(vocabulary=[])
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        total_steps = self._count_steps_in_html(html)
        # Without vocab: 1 (do_now) + 2 (instruction) + 1 (guided) + 1 (exit) = 5
        assert total_steps == 5


# ── Progress bar ──────────────────────────────────────────────────────


class TestProgressBarPresent:
    """The progress bar element must be present in the HTML."""

    @pytest.mark.asyncio
    async def test_progress_bar_present(self, tmp_path):
        """HTML should contain a progress bar element."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert 'class="progress"' in html or 'class="progress-bar"' in html
        assert 'id="pb"' in html

    @pytest.mark.asyncio
    async def test_progress_bar_starts_at_zero(self, tmp_path):
        """Progress bar should start at 0% width."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert 'width:0%' in html

    @pytest.mark.asyncio
    async def test_progress_bar_has_aria_attributes(self, tmp_path):
        """Progress bar should have ARIA role and value attributes."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert 'role="progressbar"' in html
        assert 'aria-valuenow' in html
        assert 'aria-valuemin' in html
        assert 'aria-valuemax' in html


# ── Empty master content ──────────────────────────────────────────────


class TestEmptyMasterContent:
    """An empty MasterContent should return None, not crash."""

    @pytest.mark.asyncio
    async def test_empty_master_content_returns_none(self, tmp_path):
        """With no content at all, compile_journey should return None."""
        mc = MagicMock()
        mc.title = "Empty Lesson"
        mc.objective = ""
        mc.do_now = None
        mc.vocabulary = []
        mc.direct_instruction = []
        mc.guided_notes = []
        mc.exit_ticket = []

        result = await compile_journey(mc, output_dir=tmp_path)
        assert result is None

    @pytest.mark.asyncio
    async def test_only_direct_instruction_works(self, tmp_path):
        """Even with only direct instruction sections, a journey is produced."""
        section = MagicMock()
        section.heading = "Introduction"
        section.content = "Welcome to the lesson."
        section.key_points = ["Point A", "Point B"]

        mc = MagicMock()
        mc.title = "Minimal Lesson"
        mc.objective = "Learn something."
        mc.do_now = None
        mc.vocabulary = []
        mc.direct_instruction = [section]
        mc.guided_notes = []
        mc.exit_ticket = []

        result = await compile_journey(mc, output_dir=tmp_path)
        assert result is not None
        assert result.exists()

        html = result.read_text(encoding="utf-8")
        assert "Introduction" in html


# ── Accessibility features ────────────────────────────────────────────


class TestAccessibility:
    """The generated HTML should include accessibility features."""

    @pytest.mark.asyncio
    async def test_skip_link_present(self, tmp_path):
        """A 'Skip to main content' link should be present."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert "skip-link" in html
        assert "Skip to main content" in html

    @pytest.mark.asyncio
    async def test_aria_labels_on_steps(self, tmp_path):
        """Steps should have ARIA labels."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert "aria-label" in html

    @pytest.mark.asyncio
    async def test_keyboard_navigation_script(self, tmp_path):
        """Arrow key navigation should be wired up in the script."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert "ArrowRight" in html
        assert "ArrowLeft" in html
        assert "ArrowDown" in html
        assert "ArrowUp" in html

    @pytest.mark.asyncio
    async def test_sr_announce_region(self, tmp_path):
        """A screen reader announcement region should be present."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert 'aria-live="polite"' in html
        assert "sr-announce" in html

    @pytest.mark.asyncio
    async def test_focus_indicators_in_css(self, tmp_path):
        """Focus styles should be defined for interactive elements."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert ":focus" in html

    @pytest.mark.asyncio
    async def test_steps_have_tabindex(self, tmp_path):
        """Steps should be focusable via tabindex."""
        mc = _make_mock_master()
        result = await compile_journey(mc, output_dir=tmp_path)
        html = result.read_text(encoding="utf-8")

        assert "tabindex" in html
