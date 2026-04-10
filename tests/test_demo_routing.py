"""Tests for schema-aware demo routing (Task 3, v2.3.5)."""

from __future__ import annotations

import inspect
import json
import os
from unittest.mock import patch

import pytest

# ── Fixture loading ───────────────────────────────────────────────────────────


class TestFixtureFiles:
    """Each new fixture file must load and be valid JSON."""

    def test_master_content_fixture_loads(self):
        from clawed.demo import load_demo

        data = load_demo("master_content")
        assert isinstance(data, dict)
        assert data["subject"] == "Social Studies"

    def test_quiz_fixture_loads(self):
        from clawed.demo import load_demo

        data = load_demo("quiz")
        assert isinstance(data, dict)
        assert "questions" in data
        assert len(data["questions"]) >= 3

    def test_rubric_fixture_loads(self):
        from clawed.demo import load_demo

        data = load_demo("rubric")
        assert isinstance(data, dict)
        assert "criteria" in data
        assert len(data["criteria"]) >= 2

    def test_year_map_fixture_loads(self):
        from clawed.demo import load_demo

        data = load_demo("year_map")
        assert isinstance(data, dict)
        assert "units" in data
        assert len(data["units"]) >= 5

    def test_formative_assessment_fixture_loads(self):
        from clawed.demo import load_demo

        data = load_demo("formative_assessment")
        assert isinstance(data, dict)
        assert "questions" in data
        assert "answer_key" in data

    def test_lesson_materials_fixture_loads(self):
        from clawed.demo import load_demo

        data = load_demo("lesson_materials")
        assert isinstance(data, dict)
        assert "lesson_title" in data

    def test_pacing_guide_fixture_loads(self):
        from clawed.demo import load_demo

        data = load_demo("pacing_guide")
        assert isinstance(data, dict)
        assert "weeks" in data
        assert len(data["weeks"]) >= 4


# ── Pydantic model validation ─────────────────────────────────────────────────


class TestFixtureValidation:
    """Fixtures must validate against their Pydantic models."""

    def test_master_content_validates(self):
        from clawed.demo import load_demo
        from clawed.master_content import MasterContent

        data = load_demo("master_content")
        obj = MasterContent.model_validate(data)
        assert obj.subject == "Social Studies"
        assert len(obj.guided_notes) >= 5
        assert len(obj.primary_sources) >= 2
        assert len(obj.exit_ticket) >= 2
        # Validate each exit ticket has non-empty stimulus
        for q in obj.exit_ticket:
            assert q.stimulus.strip(), "Every exit_ticket question must have a non-empty stimulus"

    def test_quiz_validates(self):
        from clawed.demo import load_demo
        from clawed.models import Quiz

        data = load_demo("quiz")
        obj = Quiz.model_validate(data)
        assert len(obj.questions) >= 3

    def test_rubric_validates(self):
        from clawed.demo import load_demo
        from clawed.models import Rubric

        data = load_demo("rubric")
        obj = Rubric.model_validate(data)
        assert len(obj.criteria) >= 2

    def test_year_map_validates(self):
        from clawed.demo import load_demo
        from clawed.models import YearMap

        data = load_demo("year_map")
        obj = YearMap.model_validate(data)
        assert len(obj.units) >= 5

    def test_formative_assessment_validates(self):
        from clawed.demo import load_demo
        from clawed.models import FormativeAssessment

        data = load_demo("formative_assessment")
        obj = FormativeAssessment.model_validate(data)
        assert len(obj.questions) >= 2

    def test_lesson_materials_validates(self):
        from clawed.demo import load_demo
        from clawed.models import LessonMaterials

        data = load_demo("lesson_materials")
        obj = LessonMaterials.model_validate(data)
        assert obj.lesson_title

    def test_pacing_guide_validates(self):
        from clawed.demo import load_demo
        from clawed.models import PacingGuide

        data = load_demo("pacing_guide")
        obj = PacingGuide.model_validate(data)
        assert len(obj.weeks) >= 4


# ── Schema-aware routing via demo_hint ───────────────────────────────────────


class TestDemoHintRouting:
    """_demo_response must dispatch to the correct fixture when demo_hint is set."""

    def test_hint_master_content_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="MasterContent")
        data = json.loads(raw)
        assert "guided_notes" in data

    def test_hint_quiz_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="Quiz")
        data = json.loads(raw)
        assert "questions" in data

    def test_hint_rubric_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="Rubric")
        data = json.loads(raw)
        assert "criteria" in data

    def test_hint_year_map_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="YearMap")
        data = json.loads(raw)
        assert "units" in data

    def test_hint_formative_assessment_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="FormativeAssessment")
        data = json.loads(raw)
        assert "questions" in data

    def test_hint_lesson_materials_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="LessonMaterials")
        data = json.loads(raw)
        assert "lesson_title" in data

    def test_hint_pacing_guide_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="PacingGuide")
        data = json.loads(raw)
        assert "weeks" in data

    def test_hint_unit_plan_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="UnitPlan")
        data = json.loads(raw)
        assert "daily_lessons" in data

    def test_hint_summative_assessment_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="SummativeAssessment")
        data = json.loads(raw)
        # maps to demo_assessment.json which has assessment_type
        assert "assessment_type" in data or "documents" in data

    def test_hint_daily_lesson_returns_parseable_json(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("anything", demo_hint="DailyLesson")
        data = json.loads(raw)
        assert data["subject"] == "Social Studies"

    def test_unknown_hint_falls_back_to_keyword_routing(self):
        """An unrecognized hint must fall through to keyword routing."""
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("science lesson please", demo_hint="UnknownModel")
        data = json.loads(raw)
        assert data["subject"] == "Science"

    def test_empty_hint_falls_back_to_keyword_routing(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("build a unit plan")
        data = json.loads(raw)
        assert "daily_lessons" in data


# ── Keyword fallback still works ─────────────────────────────────────────────


class TestKeywordFallbackRouting:
    """Legacy keyword routing must still work when no demo_hint is provided."""

    def test_assessment_keyword(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("Create a DBQ assessment")
        data = json.loads(raw)
        assert data["assessment_type"] == "dbq"

    def test_unit_keyword(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("Build a unit plan")
        data = json.loads(raw)
        assert "daily_lessons" in data

    def test_science_keyword(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("Science lesson on cells")
        data = json.loads(raw)
        assert data["subject"] == "Science"

    def test_default_fallback(self):
        from clawed.llm import LLMClient

        raw = LLMClient._demo_response("Generate something")
        data = json.loads(raw)
        assert data["subject"] == "Social Studies"


# ── Method signatures ─────────────────────────────────────────────────────────


class TestMethodSignatures:
    """Public methods must have the demo_hint parameter in their signatures."""

    def test_generate_has_demo_hint(self):
        from clawed.llm import LLMClient

        sig = inspect.signature(LLMClient.generate)
        assert "demo_hint" in sig.parameters

    def test_generate_json_has_demo_hint(self):
        from clawed.llm import LLMClient

        sig = inspect.signature(LLMClient.generate_json)
        assert "demo_hint" in sig.parameters

    def test_safe_generate_json_has_demo_hint(self):
        from clawed.llm import LLMClient

        sig = inspect.signature(LLMClient.safe_generate_json)
        assert "demo_hint" in sig.parameters

    def test_demo_response_has_demo_hint(self):
        from clawed.llm import LLMClient

        sig = inspect.signature(LLMClient._demo_response)
        assert "demo_hint" in sig.parameters


# ── resolve_credentials() ─────────────────────────────────────────────────────


class TestResolveCredentials:
    """resolve_credentials must return the correct (provider, key) tuple."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    def test_env_anthropic_wins(self):
        from clawed.config import resolve_credentials

        provider, key = resolve_credentials()
        assert provider == "anthropic"
        assert key == "sk-ant-test"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-openai-test"}, clear=False)
    def test_env_openai_detected(self):
        # Remove anthropic key if present so openai can be tested
        env = {"OPENAI_API_KEY": "sk-openai-test"}
        with patch.dict("os.environ", env):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            from clawed.config import resolve_credentials

            provider, key = resolve_credentials()
            assert provider == "openai"
            assert key == "sk-openai-test"

    @patch.dict("os.environ", {}, clear=True)
    def test_no_credentials_returns_none_none(self):
        """When no env vars or keyring keys exist, returns (None, None)."""
        import os

        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
        with patch("clawed.config.get_api_key", return_value=None):
            from clawed.config import resolve_credentials

            provider, key = resolve_credentials()
            assert provider is None
            assert key is None

    def test_returns_tuple_of_two(self):
        from clawed.config import resolve_credentials

        result = resolve_credentials()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_ollama_config_returns_ollama(self):
        from clawed.config import resolve_credentials
        from clawed.models import AppConfig, LLMProvider

        config = AppConfig()
        config.provider = LLMProvider.OLLAMA
        with patch("clawed.config.get_api_key", return_value=None):
            with patch.dict("os.environ", {}, clear=True):
                os.environ.pop("ANTHROPIC_API_KEY", None)
                os.environ.pop("OPENAI_API_KEY", None)
                os.environ.pop("GOOGLE_API_KEY", None)
                provider, key = resolve_credentials(config=config)
                assert provider == "ollama"
                assert key is None


# ── is_demo_mode() ────────────────────────────────────────────────────────────


class TestIsDemoMode:
    """is_demo_mode must return a bool and respect credential state."""

    def test_returns_bool(self):
        from clawed.demo import is_demo_mode

        result = is_demo_mode()
        assert isinstance(result, bool)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
    def test_false_when_anthropic_key_in_env(self):
        from clawed.demo import is_demo_mode

        assert is_demo_mode() is False

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_false_when_openai_key_in_env(self):
        import os

        from clawed.demo import is_demo_mode

        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert is_demo_mode() is False

    @patch.dict("os.environ", {}, clear=True)
    def test_true_when_no_credentials(self):
        import os

        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
        with patch("clawed.config.get_api_key", return_value=None):
            from clawed.demo import is_demo_mode

            assert is_demo_mode() is True

    def test_uses_resolve_credentials(self):
        """is_demo_mode must call resolve_credentials, not bypass it."""
        with patch("clawed.config.resolve_credentials", return_value=("anthropic", "sk-x")) as mock_rc:
            from clawed.demo import is_demo_mode

            result = is_demo_mode()
            mock_rc.assert_called_once()
            assert result is False


# ── safe_generate_json auto-derives demo_hint ─────────────────────────────────


class TestSafeGenerateJsonAutoHint:
    """safe_generate_json must auto-derive demo_hint from model_class.__name__."""

    @pytest.mark.asyncio
    async def test_auto_hint_derived_from_model_class(self):
        """When demo mode is active, safe_generate_json should use model_class name."""
        from clawed.llm import LLMClient
        from clawed.models import Quiz

        captured_hints = []

        async def fake_generate_json(prompt, demo_hint="", **kwargs):
            captured_hints.append(demo_hint)
            from clawed.demo import load_demo

            return load_demo("quiz")

        client = LLMClient.__new__(LLMClient)
        client.generate_json = fake_generate_json

        await client.safe_generate_json("make a quiz", Quiz)
        assert captured_hints[0] == "Quiz"

    @pytest.mark.asyncio
    async def test_explicit_hint_overrides_auto_derive(self):
        """When demo_hint is explicitly passed, it should not be overridden."""
        from clawed.llm import LLMClient
        from clawed.models import Quiz

        captured_hints = []

        async def fake_generate_json(prompt, demo_hint="", **kwargs):
            captured_hints.append(demo_hint)
            from clawed.demo import load_demo

            return load_demo("quiz")

        client = LLMClient.__new__(LLMClient)
        client.generate_json = fake_generate_json

        await client.safe_generate_json("make a quiz", Quiz, demo_hint="CustomHint")
        assert captured_hints[0] == "CustomHint"
