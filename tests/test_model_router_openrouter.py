"""Regression tests for OpenRouter model routing.

Guards the fix that stopped ``model_router`` from falling back to the
Ollama-centric default (``gemma4:31b-cloud``) when the teacher selected
OpenRouter with a bring-your-own model. OpenRouter has no entry in
``PROVIDER_TIER_MODELS``, so ``resolve_model`` must honor the configured
``openrouter_model`` instead of the built-in defaults — otherwise the
request goes out with a model ID OpenRouter does not recognize and 400s.

These tests are fully network-free: they only exercise pure routing logic
over an in-memory ``AppConfig``.
"""
from __future__ import annotations

import pytest

import clawed.model_router as model_router
from clawed.model_router import ModelTier, resolve_model, route
from clawed.models import AppConfig, LLMProvider

# The model the teacher configured for OpenRouter. The bug surfaced as this
# being silently replaced by the Ollama default below.
CONFIGURED_MODEL = "minimax/minimax-m3"
# The wrong value the router used to fall back to.
OLLAMA_DEFAULT = "gemma4:31b-cloud"


@pytest.fixture()
def openrouter_config() -> AppConfig:
    """An AppConfig pinned to OpenRouter + minimax/minimax-m3."""
    return AppConfig(
        provider=LLMProvider.OPENROUTER,
        openrouter_model=CONFIGURED_MODEL,
    )


# These three tasks all resolve to the DEEP tier (see TASK_TIERS). They are
# the high-value generation paths a teacher hits constantly, so a routing
# regression here breaks real usage.
@pytest.mark.parametrize("task_type", ["game_generate", "differentiation", "assessment"])
def test_route_uses_configured_openrouter_model(
    openrouter_config: AppConfig, task_type: str
) -> None:
    """route() must carry the configured OpenRouter model, not the fallback."""
    routed = route(task_type, openrouter_config)

    assert routed.openrouter_model == CONFIGURED_MODEL
    # Explicitly assert the regression value never reappears.
    assert routed.openrouter_model != OLLAMA_DEFAULT
    # Routing must not silently switch providers off OpenRouter.
    assert routed.provider == LLMProvider.OPENROUTER


def test_route_returns_a_copy_not_mutating_input(openrouter_config: AppConfig) -> None:
    """route() returns a copy; the caller's config is left untouched."""
    original_model = openrouter_config.openrouter_model
    routed = route("assessment", openrouter_config)

    assert routed is not openrouter_config
    assert openrouter_config.openrouter_model == original_model


@pytest.mark.parametrize("tier", [ModelTier.FAST, ModelTier.WORK, ModelTier.DEEP])
def test_resolve_model_returns_configured_openrouter_model(
    openrouter_config: AppConfig, tier: ModelTier
) -> None:
    """resolve_model() returns the configured model for every tier on OpenRouter.

    OpenRouter is bring-your-own-model: there is no per-tier provider map, so
    each tier resolves to the single configured ``openrouter_model``.
    """
    resolved = resolve_model(tier, openrouter_config)

    assert resolved == CONFIGURED_MODEL
    assert resolved != OLLAMA_DEFAULT


def test_resolve_model_honors_tier_override_over_provider_model() -> None:
    """An explicit tier_models override still wins for OpenRouter."""
    cfg = AppConfig(
        provider=LLMProvider.OPENROUTER,
        openrouter_model=CONFIGURED_MODEL,
        tier_models={"deep": "openrouter/some-other-model"},
    )

    assert resolve_model(ModelTier.DEEP, cfg) == "openrouter/some-other-model"
    # A tier without an override falls back to the configured provider model.
    assert resolve_model(ModelTier.FAST, cfg) == CONFIGURED_MODEL


def test_openrouter_has_no_builtin_tier_map() -> None:
    """Sanity guard: OpenRouter must stay absent from PROVIDER_TIER_MODELS.

    If a future change adds an OpenRouter entry there, the bring-your-own-model
    resolution path in resolve_model would be bypassed and this whole regression
    suite would stop testing the real code path — so we pin the assumption.
    """
    assert "openrouter" not in model_router.PROVIDER_TIER_MODELS
