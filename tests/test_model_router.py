"""Tests for the tier-based model router."""

from clawed.model_router import (
    DEFAULT_TIER_MODELS,
    TASK_TIERS,
    ModelTier,
    resolve_model,
    resolve_tier,
    route,
)
from clawed.models import AppConfig, LLMProvider


class TestModelTier:
    def test_tier_enum_values(self):
        assert ModelTier.FAST.value == "fast"
        assert ModelTier.DEEP.value == "deep"

    def test_all_tiers_have_defaults(self):
        for tier in ModelTier:
            assert tier.value in DEFAULT_TIER_MODELS


class TestTaskTiers:
    def test_fast_tasks(self):
        fast_tasks = ["intent_detection", "quick_answer", "search", "bellringer", "formatting"]
        for task in fast_tasks:
            assert TASK_TIERS[task] == ModelTier.FAST, f"{task} should be fast"

    def test_deep_tasks(self):
        """All generation tasks route to DEEP (Opus) — maximum intelligence."""
        deep_tasks = [
            "lesson_plan",
            "unit_plan",
            "materials",
            "differentiation",
            "assessment",
            "year_map",
            "pacing_guide",
            "curriculum_gaps",
            "persona_extract",
            "evaluation",
            "master_content",
            "game_generate",
        ]
        for task in deep_tasks:
            assert TASK_TIERS[task] == ModelTier.DEEP, f"{task} should be deep"

    def test_unknown_task_defaults_to_deep(self):
        assert resolve_tier("totally_unknown_task") == ModelTier.DEEP


class TestResolveTier:
    def test_known_task(self):
        assert resolve_tier("bellringer") == ModelTier.FAST

    def test_unknown_task(self):
        assert resolve_tier("something_new") == ModelTier.DEEP


class TestResolveModel:
    def test_default_fast_model_ollama(self):
        config = AppConfig(provider=LLMProvider.OLLAMA)
        model = resolve_model(ModelTier.FAST, config)
        assert model == DEFAULT_TIER_MODELS["fast"]

    def test_default_deep_model_ollama(self):
        config = AppConfig(provider=LLMProvider.OLLAMA)
        model = resolve_model(ModelTier.DEEP, config)
        assert model == DEFAULT_TIER_MODELS["deep"]

    def test_default_model_uses_provider_defaults(self):
        from clawed.model_router import PROVIDER_TIER_MODELS

        config = AppConfig(provider=LLMProvider.ANTHROPIC)
        model = resolve_model(ModelTier.DEEP, config)
        assert model == PROVIDER_TIER_MODELS["anthropic"]["deep"]

    def test_teacher_tier_override(self):
        config = AppConfig(tier_models={"fast": "my-fast-model"})
        model = resolve_model(ModelTier.FAST, config)
        assert model == "my-fast-model"

    def test_teacher_tier_override_only_affects_specified(self):
        config = AppConfig(provider=LLMProvider.OLLAMA, tier_models={"fast": "my-fast-model"})
        model = resolve_model(ModelTier.DEEP, config)
        assert model == DEFAULT_TIER_MODELS["deep"]


class TestTierConfig:
    def test_appconfig_has_tier_models_field(self):
        config = AppConfig()
        assert hasattr(config, "tier_models")

    def test_tier_models_default_is_none(self):
        config = AppConfig()
        assert config.tier_models is None

    def test_tier_models_can_be_set(self):
        config = AppConfig(tier_models={"fast": "qwen3.5:cloud", "deep": "claude-opus-4-6"})
        assert config.tier_models["fast"] == "qwen3.5:cloud"

    def test_tier_models_survives_json_roundtrip(self):
        config = AppConfig(tier_models={"fast": "qwen3.5:cloud"})
        json_str = config.model_dump_json()
        loaded = AppConfig.model_validate_json(json_str)
        assert loaded.tier_models == {"fast": "qwen3.5:cloud"}


class TestRouteFunction:
    def test_route_returns_new_config(self):
        config = AppConfig(provider=LLMProvider.OLLAMA, ollama_model="llama3.2")
        routed = route("lesson_plan", config)
        assert routed is not config
        assert routed.ollama_model == DEFAULT_TIER_MODELS["deep"]

    def test_route_does_not_mutate_original(self):
        config = AppConfig(provider=LLMProvider.OLLAMA, ollama_model="llama3.2")
        route("lesson_plan", config)
        assert config.ollama_model == "llama3.2"

    def test_route_fast_task(self):
        config = AppConfig(provider=LLMProvider.OLLAMA, ollama_model="llama3.2")
        routed = route("bellringer", config)
        assert routed.ollama_model == DEFAULT_TIER_MODELS["fast"]

    def test_route_deep_task(self):
        config = AppConfig(provider=LLMProvider.OLLAMA, ollama_model="llama3.2")
        routed = route("persona_extract", config)
        assert routed.ollama_model == DEFAULT_TIER_MODELS["deep"]

    def test_route_lesson_is_deep(self):
        config = AppConfig(provider=LLMProvider.OLLAMA, ollama_model="llama3.2")
        routed = route("lesson_plan", config)
        assert routed.ollama_model == DEFAULT_TIER_MODELS["deep"]

    def test_route_unknown_task_falls_back_to_deep_tier(self):
        config = AppConfig(provider=LLMProvider.OLLAMA, ollama_model="llama3.2")
        routed = route("unknown_task_type", config)
        assert routed.ollama_model == DEFAULT_TIER_MODELS["deep"]

    def test_route_preserves_other_config_fields(self):
        config = AppConfig(
            provider=LLMProvider.OLLAMA,
            ollama_model="llama3.2",
            ollama_base_url="https://my-ollama.example.com",
            output_dir="/tmp/output",
        )
        routed = route("lesson_plan", config)
        assert routed.ollama_base_url == "https://my-ollama.example.com"
        assert routed.output_dir == "/tmp/output"

    def test_teacher_tier_override_via_route(self):
        config = AppConfig(
            provider=LLMProvider.OLLAMA,
            ollama_model="llama3.2",
            tier_models={"fast": "my-custom-fast"},
        )
        routed = route("bellringer", config)
        assert routed.ollama_model == "my-custom-fast"

    def test_legacy_task_models_override_still_works(self):
        config = AppConfig(
            provider=LLMProvider.OLLAMA,
            ollama_model="llama3.2",
            task_models={"bellringer": "specific-bellringer-model"},
        )
        routed = route("bellringer", config)
        assert routed.ollama_model == "specific-bellringer-model"

    def test_task_models_override_beats_tier_override(self):
        config = AppConfig(
            provider=LLMProvider.OLLAMA,
            ollama_model="llama3.2",
            tier_models={"fast": "tier-fast-model"},
            task_models={"bellringer": "task-specific-model"},
        )
        routed = route("bellringer", config)
        assert routed.ollama_model == "task-specific-model"

    def test_route_with_anthropic_provider(self):
        from clawed.model_router import PROVIDER_TIER_MODELS

        config = AppConfig(provider=LLMProvider.ANTHROPIC)
        routed = route("quick_answer", config)
        # Model should be written to anthropic_model, not ollama_model
        assert routed.anthropic_model == PROVIDER_TIER_MODELS["anthropic"]["fast"]
        assert routed.provider == LLMProvider.ANTHROPIC
