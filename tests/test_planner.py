"""Tests for multi-step request planning."""

from clawed.agent_core.planner import build_planning_prompt, is_planning_request


class TestPlanner:
    def test_detects_planning_requests(self):
        assert is_planning_request("prepare my week")
        assert is_planning_request("Create a full unit on photosynthesis")
        assert is_planning_request("Prep my week for civics")

    def test_does_not_detect_simple_requests(self):
        assert not is_planning_request("generate a lesson on fractions")
        assert not is_planning_request("what are the math standards?")
        assert not is_planning_request("hello")

    def test_planning_prompt_has_content(self):
        prompt = build_planning_prompt()
        assert "Multi-Step" in prompt
        assert "sequence" in prompt.lower()
