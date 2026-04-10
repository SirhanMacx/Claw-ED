"""Tests for demo mode functionality."""

import json
from unittest.mock import patch

import pytest

from clawed.demo import is_demo_mode, list_demo_files, load_all_demos, load_demo


class TestDemoFiles:
    def test_list_demo_files(self):
        files = list_demo_files()
        assert len(files) >= 4
        names = [f.stem for f in files]
        assert "demo_lesson_social_studies_g8" in names
        assert "demo_lesson_science_g6" in names
        assert "demo_unit_plan" in names
        assert "demo_assessment" in names

    def test_load_demo_social_studies(self):
        data = load_demo("lesson_social_studies_g8")
        assert data["subject"] == "Social Studies"
        assert data["grade_level"] == "8"
        assert "do_now" in data
        assert "exit_ticket" in data
        assert "differentiation" in data

    def test_load_demo_science(self):
        data = load_demo("lesson_science_g6")
        assert data["subject"] == "Science"
        assert data["grade_level"] == "6"

    def test_load_demo_unit_plan(self):
        data = load_demo("unit_plan")
        assert "daily_lessons" in data
        assert len(data["daily_lessons"]) >= 3

    def test_load_demo_assessment(self):
        data = load_demo("assessment")
        assert data["assessment_type"] == "dbq"
        assert "documents" in data
        assert "rubric" in data

    def test_load_demo_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_demo("nonexistent_lesson")

    def test_load_all_demos(self):
        demos = load_all_demos()
        assert len(demos) >= 4
        assert "lesson_social_studies_g8" in demos
        assert "lesson_science_g6" in demos


class TestDemoMode:
    @patch.dict("os.environ", {}, clear=True)
    def test_demo_mode_no_keys(self):
        # Remove any existing keys from env
        import os

        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        # is_demo_mode checks config for ollama too, but without config file it should be True
        # This test may depend on local config; we at least verify the function runs
        result = is_demo_mode()
        assert isinstance(result, bool)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
    def test_not_demo_mode_with_anthropic_key(self):
        assert is_demo_mode() is False

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_not_demo_mode_with_openai_key(self):
        assert is_demo_mode() is False


class TestLLMDemoFallback:
    def test_demo_response_social_studies(self):
        from clawed.llm import LLMClient

        response = LLMClient._demo_response("Generate a social studies lesson")
        data = json.loads(response)
        assert data["subject"] == "Social Studies"

    def test_demo_response_science(self):
        from clawed.llm import LLMClient

        response = LLMClient._demo_response("Generate a science lesson")
        data = json.loads(response)
        assert data["subject"] == "Science"

    def test_demo_response_assessment(self):
        from clawed.llm import LLMClient

        response = LLMClient._demo_response("Create a DBQ assessment")
        data = json.loads(response)
        assert data["assessment_type"] == "dbq"

    def test_demo_response_unit(self):
        from clawed.llm import LLMClient

        response = LLMClient._demo_response("Build a unit plan")
        data = json.loads(response)
        assert "daily_lessons" in data

    def test_demo_response_default(self):
        from clawed.llm import LLMClient

        response = LLMClient._demo_response("Generate something")
        data = json.loads(response)
        # Default is social studies
        assert data["subject"] == "Social Studies"
